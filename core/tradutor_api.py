import json
import logging
import os
import re

import deepl
import requests
from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential
from google import genai
from google.genai.errors import ClientError as GeminiClientError


class TranslationService:
    def translate(self, text, config):
        raise NotImplementedError


def carregar_glossario(target_lang=None):
    """Load glossary entries; tries language specific file first."""
    base_dir = os.path.dirname(__file__)
    candidate_files = []
    if target_lang:
        candidate_files.append(os.path.join(base_dir, f"glossario_{target_lang}.json"))
    candidate_files.append(os.path.join(base_dir, "glossario.json"))

    for path in candidate_files:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as stream:
                return json.load(stream)
    return {}


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
    # Fallback chain: -latest aliases resolve to current stable at call time
    names.extend([
        "models/gemini-flash-lite-latest",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash-lite",
        "models/gemini-2.0-flash",
    ])
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


class _GeminiWrapper:
    """Duck-type wrapper matching the old GenerativeModel.generate_content() interface."""

    def __init__(self, client: genai.Client, model_name: str):
        self._client = client
        self._model_name = model_name

    def generate_content(self, prompt: str):
        return self._client.models.generate_content(model=self._model_name, contents=prompt)


def get_gemini_model(model_name: str, api_key: str = "") -> _GeminiWrapper:
    """Returns a _GeminiWrapper for the first resolvable candidate model name."""
    client = genai.Client(api_key=api_key) if api_key else genai.Client()
    last_error = None
    for candidate in _candidate_model_names(model_name):
        try:
            client.models.get(model=candidate)
            return _GeminiWrapper(client, candidate)
        except GeminiClientError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
    # Fallback: return wrapper with the original name even if get() failed
    if last_error and model_name:
        return _GeminiWrapper(client, model_name)
    if last_error:
        raise last_error
    raise RuntimeError("Nao foi possivel instanciar o modelo Gemini.")


def list_gemini_models(api_key: str) -> dict[str, tuple[str, int, bool]]:
    """
    Lists Gemini text-generation models available for this API key.
    Returns {bare_label: (model_name, timeout_seconds, is_paid)}.

    Sorted: free models first (-latest aliases, then stable flash), paid last.
    The caller is responsible for formatting the tier badge using i18n strings.

    SDK note: the field is `supported_actions` (not `supported_generation_methods`,
    which was the old REST name and is always None in the current SDK).
    """
    import re

    client = genai.Client(api_key=api_key)
    _SKIP_KW = {"tts", "audio", "image", "embedding", "robotics", "computer", "live"}

    entries: list[tuple[int, int, int, int, str, str, int, bool]] = []

    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" not in actions:
            continue
        base = model.name.split("/")[-1]
        if not base.startswith("gemini-"):
            continue
        if any(kw in base for kw in _SKIP_KW):
            continue
        if re.search(r"-\d{3}$", base):
            continue

        paid = _is_paid_tier(base)
        label = _format_model_label(model.name)
        timeout = 120 if "pro" in base else 60

        sort_paid = 1 if paid else 0
        sort_latest = 0 if base.endswith("-latest") else 1
        sort_pro = 1 if "pro" in base else 0
        sort_preview = 1 if "preview" in base else 0
        entries.append((sort_paid, sort_latest, sort_pro, sort_preview, label, model.name, timeout, paid))

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


def _context_hint(config: dict) -> str:
    ctx = (config.get("translation_context") or "").strip()
    return f" This content is from: {ctx}." if ctx else ""


class GeminiService(TranslationService):
    def translate(self, text, config):
        target_lang = (config.get("target_lang") or "pt").lower()
        target_label = config.get("target_label", "Portuguese (Brazil)")
        source_label = config.get("source_label", "English")
        api_key = config.get("api_key", "")
        context_hint = _context_hint(config)

        model = get_gemini_model(config.get("model", "gemini-1.5-flash"), api_key=api_key)

        # Only reuse glossary when translating to Brazilian Portuguese.
        glossary = carregar_glossario(target_lang if target_lang == "pt" else None)
        glossary_pairs = sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True)
        pretranslated_text = text
        glossary_used = False

        for original_term, target_term in glossary_pairs:
            if original_term in pretranslated_text:
                pretranslated_text = pretranslated_text.replace(original_term, target_term)
                glossary_used = True

        if glossary_used and target_lang == "pt":
            prompt = (
                f"Act as a game localization specialist.{context_hint} "
                "Refine the following pre-translated sentence so it sounds natural in "
                f"{target_label}, keeping the words that are already in Portuguese untouched. "
                f'Text: "{pretranslated_text}". Reply with the final text only.'
            )
        else:
            prompt = (
                f"Act as a game localization specialist.{context_hint} "
                f"Translate the following text from {source_label} to {target_label}: "
                f'"{text}". Reply with the final text only.'
            )

        response = model.generate_content(prompt)
        return response.text.strip()


class DeepLService(TranslationService):
    def translate(self, text, config):
        translator = deepl.Translator(config.get("api_key"))
        target_code = config.get("deepl_lang", "PT-BR")
        result = translator.translate_text(text, target_lang=target_code)
        return result.text


class AzureService(TranslationService):
    def translate(self, text, config):
        credential = AzureKeyCredential(config.get("api_key"))
        endpoint = "https://api.cognitive.microsofttranslator.com"
        text_translator = TextTranslationClient(endpoint=endpoint, credential=credential)
        target_code = config.get("target_lang", "pt")
        response = text_translator.translate(content=[text], to_language=[target_code])
        return response[0].translations[0].text


class OllamaService(TranslationService):
    def translate(self, text, config):
        url = "http://localhost:11434/api/generate"
        target_label = config.get("target_label", "Portuguese (Brazil)")
        context_hint = _context_hint(config)

        prompt = (
            f"[INST]Act as a game localization specialist.{context_hint} "
            f"Translate the JSON value below to {target_label}. Keep proper nouns and "
            "character names that should not be translated. Keep the key exactly the same. "
            "Respond with JSON only.\n\n"
            "Input:\n"
            "{\n"
            f'    "text": "{text}"\n'
            "}\n\n"
            "Output:[/INST]"
        )

        data = {
            "model": config.get("model", "llama3"),
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        response = requests.post(url, json=data, timeout=config.get("timeout", 120))
        response.raise_for_status()
        translated_dict = json.loads(response.json()["response"])
        return next(iter(translated_dict.values()))


def translate_batch_ollama(entries, config: dict) -> "dict[str, str] | None":
    """
    Translates multiple short entries in one Ollama request.
    Returns {xpath: translated_text} or None if the response can't be parsed.
    Falls back to sequential translation per entry on failure.
    """
    target_label = config.get("target_label", "Portuguese (Brazil)")
    context_hint = _context_hint(config)

    input_texts = [e.original for e in entries]
    input_json = json.dumps({"inputs": input_texts}, ensure_ascii=False)

    prompt = (
        f"[INST]Act as a game localization specialist.{context_hint} "
        f"Translate every string in the \"inputs\" array to {target_label}. "
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
        response = requests.post(
            "http://localhost:11434/api/generate",
            json=data,
            timeout=config.get("timeout", 300),
        )
        response.raise_for_status()
        result = json.loads(response.json()["response"])
        translations = result.get("translations") or result.get("Translations")
        if not isinstance(translations, list) or len(translations) != len(entries):
            return None
        return {e.xpath: str(t).strip() for e, t in zip(entries, translations)}
    except Exception:
        return None


AVAILABLE_SERVICES = {
    "Gemini": GeminiService(),
    "DeepL": DeepLService(),
    "Microsoft Azure": AzureService(),
    "Ollama (Local)": OllamaService(),
}


def translate_text(servico_escolhido, texto, config):
    if servico_escolhido in AVAILABLE_SERVICES:
        try:
            service = AVAILABLE_SERVICES[servico_escolhido]
            return service.translate(texto, config)
        except Exception as exc:
            error_message = str(exc)
            if "Connection refused" in error_message:
                return "ERRO: Nao foi possivel conectar ao servidor local do Ollama. Verifique se ele esta rodando."
            return f"ERRO na API ({servico_escolhido}): {exc}"
    return f"Servico '{servico_escolhido}' nao reconhecido."


def traduzir_arquivo_json(
    caminho_json_entrada: str,
    caminho_json_saida: str,
    api_key: str,
    servico: str = "Gemini",
    target_lang: str = "pt",
    target_label: str = "Portuguese (Brazil)",
    source_label: str = "English",
) -> bool:
    """Translates all values in a JSON {xpath: text} file and writes the result."""
    try:
        with open(caminho_json_entrada, encoding="utf-8") as f:
            dados = json.load(f)
        config = {
            "api_key": api_key,
            "target_lang": target_lang,
            "target_label": target_label,
            "source_label": source_label,
        }
        resultado = {xpath: translate_text(servico, texto, config) for xpath, texto in dados.items()}
        with open(caminho_json_saida, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        print(f"ERRO em traduzir_arquivo_json: {exc}")
        return False


__all__ = [
    "AVAILABLE_SERVICES",
    "translate_text",
    "translate_batch_ollama",
    "traduzir_arquivo_json",
    "get_gemini_model",
    "list_gemini_models",
]
