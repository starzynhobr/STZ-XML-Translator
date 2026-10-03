import concurrent.futures
import html
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import deepl
import requests
from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
APP_DATA_DIR_NAME = "STZ XML Translator"
CONTEXT_CAPABLE_SERVICES = {"Gemini", "DeepL", "Llama 3 (Local)", "Ollama (Local)"}


class TranslationService:
    def translate(self, text, config):
        raise NotImplementedError


def normalize_target_lang(target_lang) -> str:
    """'pt_BR', 'PT-BR' and 'pt' all name the same glossary: 'pt'."""
    return re.split(r"[_-]", str(target_lang or "pt"))[0].lower() or "pt"


def glossary_filename(target_lang=None) -> str:
    """A glossary maps source terms to one target language, so each target has its own file.

    Portuguese keeps the original ``glossario.json`` name so existing glossaries stay in use.
    """
    code = normalize_target_lang(target_lang)
    return "glossario.json" if code == "pt" else f"glossario_{code}.json"


def carregar_glossario(target_lang=None):
    """Load the glossary for one target language (Portuguese when not given)."""
    code = normalize_target_lang(target_lang)
    user_dir = _user_data_dir()
    legacy_dir = os.path.dirname(__file__)
    names = [f"glossario_{code}.json"]
    if code == "pt":
        # The generic file predates per-language glossaries and is Portuguese.
        names.append("glossario.json")
    candidate_files = [os.path.join(folder, name) for name in names for folder in (user_dir, legacy_dir)]

    for path in candidate_files:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as stream:
                    data = json.load(stream)
            except (OSError, json.JSONDecodeError):
                return {}
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items() if str(k).strip()}
    return {}


def _is_packaged_app() -> bool:
    exe_name = os.path.basename(sys.executable).lower()
    return bool(
        getattr(sys, "frozen", False)
        or "__compiled__" in globals()
        or not exe_name.startswith("python")
    )


def _user_data_dir() -> str:
    override = os.environ.get("STZ_XML_TRANSLATOR_DATA_DIR")
    if override:
        return os.path.abspath(override)

    if not _is_packaged_app():
        # Same rule as app_controller.user_data_dir(), which is where the
        # glossary is saved; core/ is still read as the bundled fallback.
        return os.getcwd()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return os.path.join(base, APP_DATA_DIR_NAME)

    return os.path.join(os.path.expanduser("~"), f".{APP_DATA_DIR_NAME.replace(' ', '-').lower()}")


def _candidate_model_names(model_name: str):
    names = []
    if model_name:
        names.append(model_name)
        base = model_name.split("/")[-1]
        if base not in names:
            names.append(base)
        if base and not base.endswith("-latest"):
            names.append(base + "-latest")
            names.append(f"models/{base}-latest")
        if model_name.startswith("models/") and not model_name.endswith("-latest"):
            names.append(model_name + "-latest")
    # Fallback chain: keep only currently supported text models. Model discovery
    # remains the primary source; these IDs are used when discovery is unavailable.
    names.extend([
        "models/gemini-flash-lite-latest",
        "models/gemini-flash-latest",
        "models/gemini-3.5-flash-lite",
        "models/gemini-3.5-flash",
        "models/gemini-2.5-flash-lite",
        "models/gemini-2.5-flash",
    ])
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


class _GeminiWrapper:
    """Small REST-backed wrapper matching the old generate_content() interface."""

    def __init__(self, model_name: str, api_key: str):
        self._model_name = model_name
        self._api_key = api_key

    def generate_content(self, prompt: str):
        model_name = _normalize_gemini_model_name(self._model_name)
        url = f"{GEMINI_API_BASE}/{model_name}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = _gemini_request("POST", url, self._api_key, json=payload, timeout=120)
        parts = (
            response.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini retornou uma resposta vazia.")
        return _GeminiResponse(text)


class _GeminiResponse:
    def __init__(self, text: str):
        self.text = text


def _gemini_api_key(api_key: str = "") -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        raise RuntimeError("Chave da API Gemini ausente.")
    return key


def _normalize_gemini_model_name(model_name: str) -> str:
    if model_name.startswith("models/") or model_name.startswith("tunedModels/"):
        return model_name
    return f"models/{model_name}"


def _gemini_request(method: str, url: str, api_key: str, **kwargs) -> dict:
    headers = kwargs.pop("headers", {})
    headers["x-goog-api-key"] = _gemini_api_key(api_key)
    headers.setdefault("Content-Type", "application/json")
    response = requests.request(method, url, headers=headers, **kwargs)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = str(error.get("message", "")).strip()
        except (ValueError, AttributeError):
            detail = response.text.strip()[:500]
        status = response.status_code
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Gemini API HTTP {status}{suffix}") from exc
    return response.json()


# Model names that already resolved, per (requested name, key): resolving costs
# one request per candidate, and it used to run again for every translation.
_RESOLVED_GEMINI_MODELS: dict[tuple[str, str], str] = {}


def get_gemini_model(model_name: str, api_key: str = "") -> _GeminiWrapper:
    """Returns a _GeminiWrapper for the first resolvable candidate model name."""
    cache_key = (model_name, api_key)
    resolved = _RESOLVED_GEMINI_MODELS.get(cache_key)
    if resolved:
        return _GeminiWrapper(resolved, api_key)
    last_error = None
    for candidate in _candidate_model_names(model_name):
        try:
            url = f"{GEMINI_API_BASE}/{_normalize_gemini_model_name(candidate)}"
            _gemini_request("GET", url, api_key, timeout=30)
            _RESOLVED_GEMINI_MODELS[cache_key] = candidate
            return _GeminiWrapper(candidate, api_key)
        except Exception as exc:
            last_error = exc
    # Fallback: return wrapper with the original name even if get() failed
    if last_error and model_name:
        return _GeminiWrapper(model_name, api_key)
    if last_error:
        raise last_error
    raise RuntimeError("Nao foi possivel instanciar o modelo Gemini.")


def list_gemini_models(api_key: str) -> dict[str, tuple[str, int, bool]]:
    """
    Lists Gemini text-generation models available for this API key.
    Returns {bare_label: (model_name, timeout_seconds, is_paid)}.

    Sorted: free models first (-latest aliases, then stable flash), paid last.
    The caller is responsible for formatting the tier badge using i18n strings.

    REST note: Google has exposed both `supportedGenerationMethods` and
    `supportedActions` names across API surfaces, so accept either.
    """
    import re

    payload = _gemini_request("GET", f"{GEMINI_API_BASE}/models", api_key, timeout=30)
    _SKIP_KW = {"tts", "audio", "image", "embedding", "robotics", "computer", "live"}

    entries: list[tuple[int, int, int, int, str, str, int, bool]] = []

    for model in payload.get("models", []):
        actions = model.get("supportedGenerationMethods") or model.get("supportedActions") or []
        if "generateContent" not in actions:
            continue
        model_name = model.get("name", "")
        base = model_name.split("/")[-1]
        if not base.startswith("gemini-"):
            continue
        if any(kw in base for kw in _SKIP_KW):
            continue
        if re.search(r"-\d{3}$", base):
            continue

        paid = _is_paid_tier(base)
        label = _format_model_label(model_name)
        timeout = 120 if "pro" in base else 60

        sort_paid = 1 if paid else 0
        sort_latest = 0 if base.endswith("-latest") else 1
        sort_pro = 1 if "pro" in base else 0
        sort_preview = 1 if "preview" in base else 0
        entries.append((sort_paid, sort_latest, sort_pro, sort_preview, label, model_name, timeout, paid))

    entries.sort(key=lambda x: x[:4])
    return {label: (mid, timeout, paid) for *_, label, mid, timeout, paid in entries}


def _format_model_label(model_name: str) -> str:
    """Formats a model ID like 'models/gemini-1.5-flash' into 'Gemini 1.5 Flash'."""
    base = model_name.split("/")[-1]  # strip 'models/' prefix
    parts = base.replace("gemini-", "").split("-")
    parts = [p.upper() if p.isalpha() and len(p) <= 2 else p.capitalize() for p in parts]
    return "Gemini " + " ".join(parts)


def _is_paid_tier(base: str) -> bool:
    """
    Heuristic based on empirical free-tier testing (2026-06).
    Paid: any Pro model, gemini-2.0-flash, gemini-2.0-flash-lite.
    Everything else (flash 2.5+, flash-latest, flash-lite-latest) is free.
    """
    if "pro" in base:
        return True
    if base in {"gemini-2.0-flash", "gemini-2.0-flash-lite"}:
        return True
    return False


def _mirror_case(matched: str, replacement: str) -> str:
    """Give the replacement the case pattern of the text it replaces."""
    if matched.isupper():
        return replacement.upper()
    if matched.islower():
        return replacement.lower()
    return replacement


def _glossary_matcher(target_lang: str) -> tuple[re.Pattern | None, dict[str, str]]:
    """One pattern for every term of the target language's glossary.

    Terms match whole words only ("Strike" does not fire inside "Striker"),
    longest first, and in a single pass over the text, so a replacement or a
    placeholder token is never matched again by a later term.
    """
    glossary = {term: fixed for term, fixed in carregar_glossario(target_lang).items() if term.strip()}
    if not glossary:
        return None, {}
    terms = sorted(glossary, key=len, reverse=True)
    pattern = re.compile(
        "|".join(rf"(?<!\w){re.escape(term)}(?!\w)" for term in terms),
        re.IGNORECASE,
    )
    lookup: dict[str, str] = {}
    for term in terms:
        lookup.setdefault(term.casefold(), glossary[term])
    return pattern, lookup


def _tokenize_glossary(text: str, target_lang: str, token_format: str) -> tuple[str, dict[str, str]]:
    """Swap glossary terms for opaque tokens; returns the text and {token: fixed translation}."""
    pattern, lookup = _glossary_matcher(target_lang)
    if pattern is None:
        return text, {}
    replacements: dict[str, str] = {}
    counter = 0

    def repl(match: re.Match) -> str:
        nonlocal counter
        token = token_format.format(counter)
        while token in text:
            counter += 1
            token = token_format.format(counter)
        counter += 1
        replacements[token] = _mirror_case(match.group(0), lookup[match.group(0).casefold()])
        return token

    return pattern.sub(repl, text), replacements


def apply_glossary(text: str, target_lang: str) -> tuple[str, bool]:
    """Replace glossary terms in place with their fixed translation."""
    pattern, lookup = _glossary_matcher(target_lang)
    if pattern is None:
        return text, False
    prepared = pattern.sub(
        lambda match: _mirror_case(match.group(0), lookup[match.group(0).casefold()]), text
    )
    return prepared, prepared != text


def protect_glossary_for_ai(text: str, target_lang: str) -> tuple[str, dict[str, str]]:
    """Replace matching terms with opaque tokens while AI translates the rest."""
    return _tokenize_glossary(text, target_lang, "STZGLOSSARYTOKEN{}END")


def protect_glossary_for_mt(text: str, target_lang: str) -> tuple[str, dict[str, str]]:
    """Same idea for machine translation engines, with a token they leave alone."""
    return _tokenize_glossary(text, target_lang, "ZXG{}QXZ")


def restore_glossary_tokens(text: str, replacements: dict[str, str]) -> str:
    """Restore protected glossary tokens with their required translations."""
    for token, replacement in replacements.items():
        if token in text:
            text = text.replace(token, replacement)
        else:
            # Engines sometimes change the token's case; the fixed text is still owed.
            text = re.sub(re.escape(token), lambda _m, r=replacement: r, text, flags=re.IGNORECASE)
    return text


def glossary_ai_instruction(replacements: dict[str, str]) -> str:
    """Build the constraint used by AI providers for protected glossary tokens."""
    if not replacements:
        return ""
    tokens = ", ".join(replacements)
    return (
        f"The tokens {tokens} represent glossary terms. Keep every token exactly unchanged. "
        "Translate all surrounding text completely; do not treat the glossary token as the "
        "only text that needs translation.\n"
    )


def protect_glossary_for_xml(text: str, target_lang: str) -> tuple[str, bool]:
    """Wrap glossary replacements in XML tags that translation APIs can ignore."""
    protected, replacements = _tokenize_glossary(text, target_lang, "STZGLOSSARYTOKEN{}END")
    if not replacements:
        return text, False

    protected = html.escape(protected)
    for token, replacement in replacements.items():
        protected = protected.replace(
            token, f"<stz-glossary>{html.escape(replacement)}</stz-glossary>"
        )
    return protected, True


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks produced by thinking-mode models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _ollama_post(url: str, data: dict, thinking: bool, timeout: int) -> dict:
    """
    POST to Ollama. If thinking=True and Ollama returns 400 (version too old or
    model doesn't support think+format=json), retry without think.
    """
    if thinking:
        # thinking mode is incompatible with format=json on older Ollama builds;
        # drop format constraint and parse JSON manually from the response text
        payload = {k: v for k, v in data.items() if k != "format"}
        payload["think"] = True
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code == 400:
                raise requests.HTTPError(response=r)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            logging.warning("Ollama thinking mode rejected (400) — retrying without think")
    r = requests.post(url, json=data, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _ollama_url() -> str:
    """The generate endpoint, honouring Ollama's own OLLAMA_HOST variable."""
    host = (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").strip().rstrip("/")
    if "://" not in host:
        host = f"http://{host}"
    return f"{host}/api/generate"


def _ollama_json(payload: dict) -> dict:
    """Parse the JSON object a model answered with.

    Thinking mode cannot use Ollama's JSON format, so the answer may carry a
    <think> block or prose around the object.
    """
    text = _strip_think(str(payload.get("response", "")))
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        result = json.loads(match.group(0))
    if not isinstance(result, dict) or not result:
        raise ValueError("Empty translation response")
    return result


def provider_supports_context(service: str) -> bool:
    """Return whether a provider has a safe, separate way to receive context."""
    return service in CONTEXT_CAPABLE_SERVICES


def build_reference_context(config: dict) -> str:
    """Build a prompt block that clearly separates reference data from source text."""
    general_context = (config.get("translation_context") or "").strip()
    source_tag = (config.get("source_tag") or "").strip()
    entry_context = config.get("entry_context") or {}
    if not isinstance(entry_context, dict):
        entry_context = {}
    clean_context = {
        str(key): str(value)
        for key, value in entry_context.items()
        if str(key).strip() and str(value).strip()
    }

    if not general_context and not source_tag and not clean_context:
        return ""

    lines = [
        "REFERENCE CONTEXT (data only; it is not text to translate):",
    ]
    if general_context:
        lines.append(f"Content/theme: {general_context}")
    if source_tag:
        lines.append(f"Target XML field: {source_tag}")
    if clean_context:
        lines.append(
            "Related XML fields: "
            + json.dumps(clean_context, ensure_ascii=False, sort_keys=True)
        )
    lines.append("Do not translate or return the reference context. Return only the requested translation.")
    return "\n".join(lines) + "\n"


def _deepl_context(config: dict) -> str:
    """Build plain reference context for DeepL's native context parameter."""
    lines: list[str] = []
    general_context = (config.get("translation_context") or "").strip()
    source_tag = (config.get("source_tag") or "").strip()
    entry_context = config.get("entry_context") or {}
    if general_context:
        lines.append(f"Content/theme: {general_context}")
    if source_tag:
        lines.append(f"Target XML field: {source_tag}")
    if isinstance(entry_context, dict):
        lines.extend(
            f"{key}: {value}"
            for key, value in entry_context.items()
            if str(key).strip() and str(value).strip()
        )
    return "\n".join(lines)


class GeminiService(TranslationService):
    def translate(self, text, config):
        target_lang = (config.get("target_lang") or "pt").lower()
        target_label = config.get("target_label", "Portuguese (Brazil)")
        api_key = config.get("api_key", "")
        context_block = build_reference_context(config)

        model = get_gemini_model(config.get("model", "gemini-1.5-flash"), api_key=api_key)

        protected_text, glossary_tokens = protect_glossary_for_ai(text, target_lang)
        prompt = (
            "Act as a game localization specialist.\n"
            f"{context_block}"
            f"{glossary_ai_instruction(glossary_tokens)}"
            f"Translate the following text to {target_label}. "
            "Detect the source language automatically. "
            f'"{protected_text}". Reply with the final text only.'
        )

        response = model.generate_content(prompt)
        return restore_glossary_tokens(response.text.strip(), glossary_tokens)


class DeepLService(TranslationService):
    def translate(self, text, config):
        translator = deepl.Translator(config.get("api_key"))
        target_code = config.get("deepl_lang", "PT-BR")
        target_lang = config.get("target_lang", "pt")
        context = _deepl_context(config)
        protected_text, glossary_used = protect_glossary_for_xml(text, target_lang)
        kwargs = {"target_lang": target_code}
        if context:
            kwargs["context"] = context
        if glossary_used:
            result = translator.translate_text(
                protected_text,
                **kwargs,
                tag_handling="xml",
                ignore_tags=["stz-glossary"],
            )
            cleaned = re.sub(r"</?stz-glossary>", "", result.text)
            return html.unescape(cleaned)
        result = translator.translate_text(text, **kwargs)
        return result.text


class AzureService(TranslationService):
    def translate(self, text, config):
        credential = AzureKeyCredential(config.get("api_key"))
        endpoint = "https://api.cognitive.microsofttranslator.com"
        client_options = {"endpoint": endpoint, "credential": credential}
        # A resource created in a region answers 401 unless the region is sent.
        region = (config.get("azure_region") or "").strip()
        if region:
            client_options["region"] = region
        text_translator = TextTranslationClient(**client_options)
        target_code = config.get("target_lang", "pt")
        protected, glossary_tokens = protect_glossary_for_mt(text, target_code)
        response = text_translator.translate(content=[protected], to_language=[target_code])
        return restore_glossary_tokens(response[0].translations[0].text, glossary_tokens)


class OllamaService(TranslationService):
    def translate(self, text, config):
        url = _ollama_url()
        thinking = bool(config.get("ollama_thinking"))
        target_label = config.get("target_label", "Portuguese (Brazil)")
        context_block = build_reference_context(config)
        protected, glossary_tokens = protect_glossary_for_ai(text, config.get("target_lang", "pt"))
        # json.dumps escapes quotes and line breaks, so the input stays valid JSON.
        input_json = json.dumps({"text": protected}, ensure_ascii=False, indent=4)

        prompt = (
            "[INST]Act as a game localization specialist.\n"
            f"{context_block}"
            f"{glossary_ai_instruction(glossary_tokens)}"
            f"Translate the JSON value below to {target_label}. Keep proper nouns and "
            "character names that should not be translated. Keep the key exactly the same. "
            "Respond with JSON only.\n\n"
            "Input:\n"
            f"{input_json}\n\n"
            "Output:[/INST]"
        )

        data = {
            "model": config.get("model", "llama3"),
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        payload = _ollama_post(url, data, thinking, config.get("timeout", 120))
        translated_dict = _ollama_json(payload)
        return restore_glossary_tokens(str(next(iter(translated_dict.values()))), glossary_tokens)


def translate_batch_ollama(entries, config: dict) -> "dict[str, str] | None":
    """
    Translates multiple short entries in one Ollama request.
    Returns {xpath: translated_text} or None if the response can't be parsed.
    Falls back to sequential translation per entry on failure.
    """
    target_label = config.get("target_label", "Portuguese (Brazil)")
    context_block = build_reference_context(config)
    target_lang = config.get("target_lang", "pt")

    inputs = []
    tokens_by_entry: list[dict[str, str]] = []
    all_tokens: dict[str, str] = {}
    for entry in entries:
        protected, tokens = protect_glossary_for_ai(entry.original, target_lang)
        tokens_by_entry.append(tokens)
        all_tokens.update(tokens)
        inputs.append({"text": protected, "field": entry.source_tag, "context": entry.context})
    input_json = json.dumps({"inputs": inputs}, ensure_ascii=False)

    prompt = (
        "[INST]Act as a game localization specialist.\n"
        f"{context_block}"
        f"{glossary_ai_instruction(all_tokens)}"
        f"Translate every string in the \"inputs\" array to {target_label}. "
        "For each object, translate only its \"text\" value; \"field\" and \"context\" "
        "are reference data and must not appear in the translation. "
        "Keep proper nouns and character names that should not be translated. "
        "Return JSON with a single key \"translations\" containing the translated "
        f"strings as an array in the same order.\nInput: {input_json}[/INST]"
    )

    data = {
        "model": config.get("model", "llama3"),
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    try:
        payload = _ollama_post(
            _ollama_url(), data, bool(config.get("ollama_thinking")), config.get("timeout", 300)
        )
        result = _ollama_json(payload)
        translations = result.get("translations") or result.get("Translations")
        if not isinstance(translations, list) or len(translations) != len(entries):
            return None
        return {
            entry.xpath: restore_glossary_tokens(str(text).strip(), tokens)
            for entry, text, tokens in zip(entries, translations, tokens_by_entry)
        }
    except Exception:
        return None


_GT_PROTECTED_RE = re.compile(
    r"(\{[^{}]+\}|&[A-Za-z]+;|S\.H\.I\.E\.L\.D\.|\$\d+(?:\.\d+)?|%\d|%s|%%|\$\w+)"
)
_GT_LANG_MAP = {"pt": "pt-BR", "en": "en", "es": "es", "fr": "fr", "ja": "ja"}


class GoogleTranslateFreeService(TranslationService):
    def translate(self, text, config):
        tl = _GT_LANG_MAP.get(config.get("target_lang", "pt"), config.get("target_lang", "pt-BR"))
        text, glossary_tokens = protect_glossary_for_mt(text, config.get("target_lang", "pt"))
        segments = text.split("\n")
        translated = []
        for seg in segments:
            # Any letter counts, in any script: a line of Russian or Japanese is
            # text to translate too. Only lines without letters are passed through.
            if not re.search(r"[^\W\d_]", seg):
                translated.append(seg)
                continue
            protected, replacements = self._protect(seg)
            result = self._call_api(protected, tl)
            translated.append(self._unprotect(result, replacements))
        return restore_glossary_tokens("\n".join(translated), glossary_tokens)

    def _protect(self, text):
        replacements = {}
        counter = [0]
        def repl(m):
            token = f"ZXQ{counter[0]}QXZ"
            counter[0] += 1
            replacements[token] = m.group(0)
            return token
        return _GT_PROTECTED_RE.sub(repl, text), replacements

    def _unprotect(self, text, replacements):
        for token, original in replacements.items():
            text = text.replace(token, original)
        return text

    def _call_api(self, text, tl):
        params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text})
        url = f"https://translate.googleapis.com/translate_a/single?{params}"
        last_error = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return "".join(p[0] for p in payload[0] if p and p[0] is not None)
            except Exception as exc:
                last_error = exc
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"Google Translate falhou: {last_error}")


def translate_batch_google_free(entries, config: dict) -> "dict[str, str] | None":
    """Translate a batch of entries in parallel using the free Google Translate endpoint."""
    service = GoogleTranslateFreeService()
    results: dict[str, str] = {}
    failed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_entry = {
            executor.submit(service.translate, entry.original, config): entry
            for entry in entries
        }
        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                results[entry.xpath] = future.result()
            except Exception:
                failed += 1

    if failed > len(entries) // 2:
        return None
    return results


AVAILABLE_SERVICES = {
    "Gemini": GeminiService(),
    "Google Translate (Free)": GoogleTranslateFreeService(),
    "DeepL": DeepLService(),
    "Microsoft Azure": AzureService(),
    "Llama 3 (Local)": OllamaService(),
    "Ollama (Local)": OllamaService(),
}


def translate_text(servico_escolhido, texto, config):
    """Translate one text. Failures raise: an error message must never be
    returned as if it were the translation, or it ends up in the exported XML."""
    service = AVAILABLE_SERVICES.get(servico_escolhido)
    if service is None:
        raise ValueError(f"Unknown translation service: {servico_escolhido}")
    return service.translate(texto, config)


__all__ = [
    "AVAILABLE_SERVICES",
    "translate_text",
    "translate_batch_ollama",
    "translate_batch_google_free",
    "get_gemini_model",
    "list_gemini_models",
    "provider_supports_context",
    "build_reference_context",
]
