from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from core import gemini_batch
from core.project import TranslationProject
from core.tradutor_api import (
    LOCALIZATION_RULES,
    get_gemini_model,
    glossary_ai_instruction,
    protect_glossary_for_ai,
    provider_supports_context,
    restore_glossary_tokens,
    translate_batch_google_free,
    translate_batch_ollama,
    translate_text,
)
from core.translation_errors import ERROR_MESSAGES, classify_error

# Gemini free keys allow 5-15 requests per minute depending on the model; 10 with
# 3 in flight stays under that and still overlaps the slow part (the answer).
GEMINI_PARALLEL = 3
GEMINI_RPM = 10


class TranslationWorker:
    """
    Runs batch AI translation in a background thread.
    Completely decoupled from any GUI framework — communicates via callbacks.
    Supports all providers via translate_text(); Gemini uses the efficient
    batch-block format, other providers translate one entry at a time.
    """

    @property
    def _checkpoint_file(self) -> str:
        from core.project import TranslationProject
        return TranslationProject.checkpoint_path(
            self._project.xml_path,
            self._config.get("target_lang", ""),
            self._config.get("checkpoint_dir", "checkpoints"),
            parent_tag=self._project.parent_tag,
            target_tags=self._project.target_tags,
            context_tags=self._project.context_tags,
            portable=True,
            groups=self._project.groups,
        )
    BATCH_SIZE = 120
    BATCH_DELAY_SECONDS = 5

    def __init__(
        self,
        project: TranslationProject,
        config: dict,
        on_entry_translated: Callable[[str, str], None],
        on_log: Callable[[str], None],
        on_done: Callable[[], None],
        on_batch_start: Callable[[list[str]], None] | None = None,
    ) -> None:
        self._project = project
        self._config = config
        self._on_entry_translated = on_entry_translated
        self._on_log = on_log
        self._on_done = on_done
        self._on_batch_start = on_batch_start
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Per pool thread: the error of the request that thread just made.
        self._local = threading.local()
        self._gate: gemini_batch.RateGate | None = None
        # Names translated before this pass: fixed references for the texts that mention them.
        self._names: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._cancel_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Single-entry translation (called from main thread via daemon thread)
    # ------------------------------------------------------------------

    def translate_single(self, xpath: str) -> str:
        entry = self._project.get_entry(xpath)
        if not entry:
            return "ERRO: entrada não encontrada."
        service = self._config.get("service", "Gemini")
        self._project.mark_translating(xpath)
        try:
            result = translate_text(service, entry.original, self._config_for_entry(entry))
            if not result or not result.strip():
                raise ValueError("Empty translation response")
            self._project.set_translation(xpath, result, source="ai")
            return result
        except Exception as exc:
            self._project.mark_error(xpath, classify_error(exc))
            return entry.error_message

    def _config_for_entry(self, entry) -> dict:
        """Attach XML metadata without mutating the shared worker configuration."""
        config = dict(self._config)
        config["source_tag"] = entry.source_tag
        config["entry_context"] = dict(entry.context)
        return config

    # ------------------------------------------------------------------
    # Batch translation (background thread)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Gemini: distinct texts, sized requests, several in flight
    # ------------------------------------------------------------------

    def _name_memory(self) -> dict[str, str]:
        """Names already translated in this file, from this run or an earlier one."""
        return {
            entry.original: entry.translation
            for entry in self._project.entries.values()
            if gemini_batch.is_name_field(entry.source_tag)
            and entry.translation.strip()
            and entry.status in ("translated", "confirmed")
        }

    def _run_gemini(self, pending: list) -> None:
        units = gemini_batch.dedupe(pending)
        if len(units) < len(pending):
            self._on_log(self._s("dedup", unique=len(units), total=len(pending)))
        self._gate = gemini_batch.RateGate(float(self._config.get("gemini_rpm", GEMINI_RPM)))
        names = [unit for unit in units if gemini_batch.is_name_field(unit.entry.source_tag)]
        rest = [unit for unit in units if not gemini_batch.is_name_field(unit.entry.source_tag)]

        # Names first: the texts that mention them then get the same translation as a reference.
        stopped = self._run_chunks(names) if names else ""
        if not stopped and not self._cancel_event.is_set() and rest:
            self._names = self._name_memory()
            stopped = self._run_chunks(rest)
        self._names = {}

        self._project.recover_interrupted()
        if self._cancel_event.is_set():
            self._on_log(self._s("cancelled"))
        elif stopped:
            self._on_log(self._s("api_error", exc=ERROR_MESSAGES[stopped]))
            self._on_log(self._s("batch_failed"))
        else:
            self._on_log(self._s("final_done"))
        self._on_done()

    def _run_chunks(self, units: list[gemini_batch.Unit]) -> str:
        """Translate units with up to N requests in flight; returns the error that stopped it, if any."""
        project = self._project
        parallel = max(1, int(self._config.get("gemini_parallel", GEMINI_PARALLEL)))

        def request(chunk: list[gemini_batch.Unit]):
            results = self._translate_batch_gemini([unit.entry for unit in chunk])
            if results is None:
                return None, self._local.error
            return {unit.id: results.get(unit.entry.xpath, "") for unit in chunk}, ""

        queue = gemini_batch.pack(units, gemini_batch.MAX_CHARS, gemini_batch.MAX_ITEMS)
        running: dict[Future, list[gemini_batch.Unit]] = {}
        stopped = ""
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            while queue or running:
                # Keep up to `parallel` requests in flight; each marks its entries as it leaves.
                while queue and len(running) < parallel and not stopped and not self._cancel_event.is_set():
                    chunk = queue.pop(0)
                    xpaths = [xpath for unit in chunk for xpath in unit.xpaths]
                    for xpath in xpaths:
                        project.mark_translating(xpath)
                    if self._on_batch_start:
                        self._on_batch_start(xpaths)
                    self._on_log(self._s("sending_gemini", n=len(xpaths)))
                    running[pool.submit(request, chunk)] = chunk
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    chunk = running.pop(future)
                    results, error = future.result()
                    if results is None:
                        # A failed request leaves its entries as errors: "translate pending" retries them.
                        for unit in chunk:
                            for xpath in unit.xpaths:
                                project.mark_error(xpath, error if error != "cancelled" else "batch_failed")
                        if error != "cancelled":
                            stopped = stopped or error
                    else:
                        skipped = 0
                        for unit in chunk:
                            text = results.get(unit.id, "")
                            for xpath in unit.xpaths:
                                if text.strip():
                                    project.set_translation(xpath, text, status="done", source="ai")
                                    self._on_entry_translated(xpath, text)
                                else:
                                    project.mark_error(xpath, "missing_result")
                                    skipped += 1
                        if skipped:
                            self._on_log(self._s("items_skipped", n=skipped))
                    # Every finished request is saved at once: an interruption loses at most what is in flight.
                    project.save_checkpoint(self._checkpoint_file)
                    if results is not None:
                        finished, _ = project.stats()
                        self._on_log(self._s("batch_count", done=finished))
        return stopped

    def _s(self, key: str, **kwargs) -> str:
        """Return a translated log string from config, falling back to Portuguese."""
        _fallbacks = {
            "checkpoint_loaded":   "Checkpoint carregado: {n} traduções retomadas.",
            "all_done":            "Todos os itens já estão traduzidos no checkpoint.",
            "batch_start":        "Iniciando tradução em lote: {total} itens pendentes.",
            "sending_gemini":     "Enviando lote de {n} itens para a API Gemini…",
            "sending_google":     "Traduzindo lote de {n} itens com Google Translate…",
            "cancelled":          "Tradução cancelada pelo usuário.",
            "batch_failed":       "Falha no lote — interrompendo tradução.",
            "items_skipped":      "AVISO: {n} item(ns) pulados pela IA neste lote.",
            "ollama_mini":        "Mini-lote Ollama: {n} itens…",
            "ollama_mini_failed": "Mini-lote falhou — tentando item a item.",
            "api_error":          "ERRO na API: {exc}",
            "batch_count":        "Lote concluído. Total traduzido: {done}",
            "final_done":         "Tradução em lote finalizada.",
            "dedup":              "{unique} textos diferentes para {total} entradas: cada repetido é traduzido uma vez.",
            "rate_wait":          "Limite por minuto atingido: aguardando {s} s e reduzindo o ritmo.",
            "context_unsupported": (
                "AVISO: {provider} não oferece contexto separado; "
                "os campos de contexto serão ignorados nesta execução."
            ),
        }
        strings = self._config.get("_strings", {})
        template = strings.get(key) or _fallbacks.get(key, key)
        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, IndexError):
            return template

    def _run(self) -> None:
        # Always clear transient states, including cancellation and unexpected errors.
        callback = self._on_done
        self._on_done = lambda: None
        try:
            self._run_batches()
        except Exception as exc:
            for entry in self._project.entries.values():
                if entry.status == "translating":
                    self._project.mark_error(entry.xpath, classify_error(exc))
            self._on_log(self._s("api_error", exc=ERROR_MESSAGES[classify_error(exc)]))
        finally:
            self._project.recover_interrupted()
            self._project.save_checkpoint(self._checkpoint_file)
            self._on_done = callback
            callback()

    def _run_batches(self) -> None:
        project = self._project

        loaded = 0 if any(e.translation or e.status != "pending" for e in project.entries.values()) else project.load_checkpoint_with_fallback(
            self._checkpoint_file,
            self._config.get("checkpoint_fallbacks", []),
        )
        if loaded:
            self._on_log(self._s("checkpoint_loaded", n=loaded))

        skip_rows = int(self._config.get("skip_rows", 0))
        all_entries = list(project.entries.values())
        selected_xpaths = self._config.get("selected_xpaths")
        if selected_xpaths is not None:
            selected_set = set(selected_xpaths)
            candidates = [entry for entry in all_entries if entry.xpath in selected_set]
        else:
            candidates = all_entries[skip_rows:] if skip_rows > 0 else all_entries
        if selected_xpaths is not None and self._config.get("include_done", False):
            pending = candidates
        else:
            pending = [e for e in candidates if e.needs_translation]

        if not pending:
            self._on_log(self._s("all_done"))
            self._on_done()
            return

        total = len(pending)
        self._on_log(self._s("batch_start", total=total))

        service = self._config.get("service", "Gemini")
        if any(entry.context for entry in pending) and not provider_supports_context(service):
            self._on_log(self._s("context_unsupported", provider=service))

        if service == "Gemini":
            self._run_gemini(pending)
            return

        for i in range(0, total, self.BATCH_SIZE):
            if self._cancel_event.is_set():
                self._on_log(self._s("cancelled"))
                self._on_done()
                return

            batch = pending[i : i + self.BATCH_SIZE]

            for entry in batch:
                project.mark_translating(entry.xpath)

            if service == "Google Translate (Free)":
                if self._on_batch_start:
                    self._on_batch_start([e.xpath for e in batch])
                self._on_log(self._s("sending_google", n=len(batch)))

                results = translate_batch_google_free(batch, self._config)

                if results is None and self._cancel_event.is_set():
                    self._on_log(self._s("cancelled"))
                    self._on_done()
                    return

                if results is None:
                    for entry in batch:
                        project.mark_error(entry.xpath, "batch_failed")
                    self._on_log(self._s("batch_failed"))
                    break

                skipped = 0
                for entry in batch:
                    text = results.get(entry.xpath)
                    if text and text.strip():
                        project.set_translation(entry.xpath, text, status="done", source="ai")
                        self._on_entry_translated(entry.xpath, text)
                    else:
                        project.mark_error(entry.xpath, "missing_result")
                        skipped += 1

                if skipped:
                    self._on_log(self._s("items_skipped", n=skipped))

            else:
                OLLAMA_MINI = 15
                OLLAMA_MAX_LEN = 400

                failed = False
                idx = 0
                while idx < len(batch):
                    if self._cancel_event.is_set():
                        self._on_log(self._s("cancelled"))
                        self._on_done()
                        return

                    if service == "Ollama (Local)":
                        mini = batch[idx : idx + OLLAMA_MINI]
                        if all(len(e.original) < OLLAMA_MAX_LEN for e in mini):
                            if self._on_batch_start:
                                self._on_batch_start([e.xpath for e in mini])
                            if len(mini) > 1:
                                self._on_log(self._s("ollama_mini", n=len(mini)))
                            results = translate_batch_ollama(mini, self._config)
                            if self._cancel_event.is_set():
                                return
                            if results is not None:
                                for entry in mini:
                                    text = results.get(entry.xpath, "")
                                    if text and text.strip():
                                        project.set_translation(entry.xpath, text, status="done", source="ai")
                                        self._on_entry_translated(entry.xpath, text)
                                    else:
                                        project.mark_error(entry.xpath, "missing_result")
                                idx += len(mini)
                                continue
                            if len(mini) > 1:
                                self._on_log(self._s("ollama_mini_failed"))

                    entry = batch[idx]
                    if self._on_batch_start:
                        self._on_batch_start([entry.xpath])
                    try:
                        text = translate_text(
                            service,
                            entry.original,
                            self._config_for_entry(entry),
                        )
                        if self._cancel_event.is_set():
                            return
                        if not text or not text.strip():
                            raise ValueError("Empty translation response")
                        project.set_translation(entry.xpath, text, status="done", source="ai")
                        self._on_entry_translated(entry.xpath, text)
                    except Exception as exc:
                        project.mark_error(entry.xpath, classify_error(exc))
                        self._on_log(self._s("api_error", exc=ERROR_MESSAGES[classify_error(exc)]))
                        failed = True
                        break
                    idx += 1

                if failed:
                    break

            project.save_checkpoint(self._checkpoint_file)
            done, _ = project.stats()
            self._on_log(self._s("batch_count", done=done))

            if i + self.BATCH_SIZE < total:
                cancelled = self._cancel_event.wait(timeout=self.BATCH_DELAY_SECONDS)
                if cancelled:
                    self._on_log(self._s("cancelled"))
                    self._on_done()
                    return

        self._on_log(self._s("final_done"))
        self._on_done()

    def _translate_batch_gemini(self, batch) -> dict[str, str] | None:
        """One Gemini request for these entries (runs on a pool thread).

        Returns {xpath: translation}, or None with the error code left in
        ``self._local.error``. Rate limits are retried after the wait the API
        asks for, slowing the shared pace down for every request.
        """
        self._local.error = "batch_failed"
        gate = self._gate or gemini_batch.RateGate(GEMINI_RPM)
        target_lang = self._config.get("target_lang", "pt")
        ids = {f"t{index}": entry for index, entry in enumerate(batch, start=1)}
        tokens_by_id: dict[str, dict[str, str]] = {}
        items = []
        for unit_id, entry in ids.items():
            protected, tokens = protect_glossary_for_ai(entry.original, target_lang)
            tokens_by_id[unit_id] = tokens
            item = {"id": unit_id, "text": protected, "field": entry.source_tag}
            if entry.context:
                item["context"] = dict(entry.context)
            items.append(item)
        all_tokens = {token: value for tokens in tokens_by_id.values() for token, value in tokens.items()}
        general = (self._config.get("translation_context") or "").strip()
        rules = LOCALIZATION_RULES + (f"Content/theme: {general}\n" if general else "") + glossary_ai_instruction(all_tokens)
        own = {entry.original for entry in batch}
        hints = [pair for pair in gemini_batch.names_in([e.original for e in batch], self._names) if pair[0] not in own]
        if hints:
            rules += "Names already used in this translation; write them exactly like this: " + "; ".join(
                f'"{original}" = "{translation}"' for original, translation in hints
            ) + "\n"
        prompt = gemini_batch.build_prompt(items, rules, self._config.get("target_label", "Portuguese (Brazil)"))
        error: Exception | None = None
        for _attempt in range(gemini_batch.RETRIES):
            if not gate.wait(self._cancel_event.is_set):
                self._local.error = "cancelled"
                return None
            try:
                model = get_gemini_model(
                    self._config.get("model", "models/gemini-flash-lite-latest"),
                    api_key=self._config.get("api_key", ""),
                )
                response = model.generate_content(prompt, response_schema=gemini_batch.RESPONSE_SCHEMA)
                results = gemini_batch.parse(response.text)
                return {
                    ids[unit_id].xpath: restore_glossary_tokens(text.strip(), tokens_by_id[unit_id])
                    for unit_id, text in results.items()
                    if unit_id in ids
                }
            except Exception as exc:  # classified below; the raw text never reaches the UI
                error = exc
                wait_for = None if gemini_batch.daily_quota_exhausted(exc) else gemini_batch.retry_after(exc)
                if wait_for is None:
                    break
                gate.slow_down(wait_for)
                self._on_log(self._s("rate_wait", s=round(wait_for)))
        self._local.error = classify_error(error) if error else "batch_failed"
        self._on_log(self._s("api_error", exc=ERROR_MESSAGES[self._local.error]))
        return None
