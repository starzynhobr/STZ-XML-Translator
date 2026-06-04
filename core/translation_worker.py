from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable

from core.project import TranslationProject
from core.tradutor_api import get_gemini_model, translate_text


class TranslationWorker:
    """
    Runs batch AI translation in a background thread.
    Completely decoupled from any GUI framework — communicates via callbacks.
    Supports all providers via translate_text(); Gemini uses the efficient
    batch-block format, other providers translate one entry at a time.
    """

    CHECKPOINT_FILE = "textos_traduzidos_checkpoint.json"
    BATCH_SIZE = 120
    BATCH_DELAY_SECONDS = 5

    def __init__(
        self,
        project: TranslationProject,
        config: dict,
        on_entry_translated: Callable[[str, str], None],
        on_log: Callable[[str], None],
        on_done: Callable[[], None],
    ) -> None:
        self._project = project
        self._config = config
        self._on_entry_translated = on_entry_translated
        self._on_log = on_log
        self._on_done = on_done
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

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
        try:
            return translate_text(service, entry.original, self._config)
        except Exception as exc:
            return f"ERRO na API: {exc}"

    # ------------------------------------------------------------------
    # Batch translation (background thread)
    # ------------------------------------------------------------------

    def _run(self) -> None:
        project = self._project

        loaded = project.load_checkpoint(self.CHECKPOINT_FILE)
        if loaded:
            self._on_log(f"Checkpoint carregado: {loaded} traduções retomadas.")

        pending = project.get_pending_entries()
        if not pending:
            self._on_log("Todos os itens já estão traduzidos no checkpoint.")
            self._on_done()
            return

        total = len(pending)
        self._on_log(f"Iniciando tradução em lote: {total} itens pendentes.")

        service = self._config.get("service", "Gemini")

        for i in range(0, total, self.BATCH_SIZE):
            if self._cancel_event.is_set():
                self._on_log("Tradução cancelada pelo usuário.")
                self._on_done()
                return

            batch = pending[i : i + self.BATCH_SIZE]

            if service == "Gemini":
                results = self._translate_batch_gemini(batch)
            else:
                results = self._translate_batch_sequential(batch, service)

            if results is None:
                self._on_log("Falha no lote — interrompendo tradução.")
                break

            skipped = 0
            for entry in batch:
                text = results.get(entry.xpath)
                if text:
                    project.set_translation(entry.xpath, text, status="done")
                    self._on_entry_translated(entry.xpath, text)
                else:
                    skipped += 1

            if skipped:
                self._on_log(f"AVISO: {skipped} item(ns) pulados pela IA neste lote.")

            project.save_checkpoint(self.CHECKPOINT_FILE)
            done, _ = project.stats()
            self._on_log(f"Lote concluído. Total traduzido: {done}")

            if i + self.BATCH_SIZE < total:
                time.sleep(self.BATCH_DELAY_SECONDS)

        self._on_log("Tradução em lote finalizada.")
        self._on_done()

    def _translate_batch_gemini(self, batch) -> dict[str, str] | None:
        """Gemini: sends all entries in one prompt block for efficiency."""
        batch_text = "".join(f"[ID: {e.xpath}]\n{e.original}\n---\n" for e in batch)
        try:
            model = get_gemini_model(
                self._config.get("model", "models/gemini-flash-lite-latest"),
                api_key=self._config.get("api_key", ""),
            )
            target_label = self._config.get("target_label", "Portuguese (Brazil)")
            prompt = (
                "Act as a game localization specialist.\n"
                "Each entry below is formatted as [ID: ...] followed by text.\n"
                f"Translate every entry to {target_label}. Keep the IDs and separators exactly as provided.\n\n"
                "---BEGIN BLOCK---\n"
                f"{batch_text}\n"
                "---END BLOCK---\n"
            )
            response = model.generate_content(prompt)
            pairs = re.findall(r"\[ID: (.*?)\]\n(.*?)\n---", response.text, re.DOTALL)
            return {xpath.strip(): text.strip() for xpath, text in pairs}
        except Exception as exc:
            self._on_log(f"ERRO na API: {exc}")
            return None

    def _translate_batch_sequential(self, batch, service: str) -> dict[str, str] | None:
        """Non-Gemini providers: translate one entry at a time."""
        results: dict[str, str] = {}
        for entry in batch:
            if self._cancel_event.is_set():
                return results  # return partial on cancel
            try:
                text = translate_text(service, entry.original, self._config)
                results[entry.xpath] = text
            except Exception as exc:
                self._on_log(f"ERRO na API: {exc}")
                return None
        return results
