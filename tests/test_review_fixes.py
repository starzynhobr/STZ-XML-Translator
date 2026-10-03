"""Regressions for the bugs found in the pre-migration review."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core import tradutor_api
from core.atomic import write_json_atomic
from core.injetor import injetar_traducoes
from core.project import TranslationEntry, TranslationProject
from core.tradutor_api import (
    AzureService,
    GoogleTranslateFreeService,
    OllamaService,
    apply_glossary,
    carregar_glossario,
    glossary_filename,
    protect_glossary_for_ai,
    protect_glossary_for_mt,
    restore_glossary_tokens,
    translate_batch_ollama,
)
from core.translation_worker import TranslationWorker


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """An isolated user-data dir with no bundled glossary behind it."""
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("core.tradutor_api.os.path.dirname", lambda _: str(tmp_path / "bundled"))
    return tmp_path


def write_glossary(data_dir, target, terms):
    (data_dir / glossary_filename(target)).write_text(json.dumps(terms), encoding="utf-8")


# --- 1. API errors must not be stored as translations -----------------------


def test_single_translation_failure_marks_error_and_keeps_text_empty(tmp_path):
    project = TranslationProject()
    project.entries["/a"] = TranslationEntry("/a", "Hello")
    worker = TranslationWorker(project, {"service": "DeepL", "checkpoint_dir": str(tmp_path)},
                               MagicMock(), MagicMock(), MagicMock())
    failing = MagicMock()
    failing.translate.side_effect = RuntimeError("403 Forbidden: invalid key")
    with patch.dict("core.tradutor_api.AVAILABLE_SERVICES", {"DeepL": failing}):
        worker.translate_single("/a")
    entry = project.entries["/a"]
    assert (entry.status, entry.translation, entry.error_code) == ("error", "", "authentication")
    assert project.get_translations_map() == {}


# --- 3. Export changes nothing but the translated text ----------------------

TRICKY_XML = (
    b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>\r\n'
    b"<!-- header -->\r\n"
    b"<data>\r\n"
    b'\t<item id="1">\r\n'
    b"\t\t<name>Sword &amp; Shield</name>\r\n"
    b"\t\t<bio><![CDATA[<b>Bold</b> text]]></bio>\r\n"
    b"\t\t<note>keep &quot;this&quot;</note>\r\n"
    b"\t</item>\r\n"
    b"</data>\r\n"
)


def test_export_preserves_layout_cdata_prolog_and_line_endings(tmp_path):
    source = tmp_path / "in.xml"
    source.write_bytes(TRICKY_XML)
    out = tmp_path / "out.xml"
    assert injetar_traducoes(str(source), {"/data/item[1]/bio[1]": "<b>Negrito</b>"}, str(out)) is True
    # The serializer still writes a literal quote for &quot; in text (the same
    # character to any XML parser); everything else is byte for byte.
    expected = TRICKY_XML.replace(b"<b>Bold</b> text", b"<b>Negrito</b>").replace(b"&quot;", b'"')
    assert out.read_bytes() == expected


def test_export_keeps_a_non_utf8_encoding_and_single_quoted_declaration(tmp_path):
    original = "<?xml version='1.0' encoding='ISO-8859-1'?>\n<r>\n  <t>café</t>\n</r>\n".encode("latin-1")
    source = tmp_path / "in.xml"
    source.write_bytes(original)
    out = tmp_path / "out.xml"
    assert injetar_traducoes(str(source), {"/r/t[1]": "chá"}, str(out)) is True
    assert out.read_bytes() == original.replace("café".encode("latin-1"), "chá".encode("latin-1"))


def test_save_over_the_original_is_atomic(tmp_path, monkeypatch):
    source = tmp_path / "in.xml"
    source.write_bytes(TRICKY_XML)
    monkeypatch.setattr("core.atomic.os.replace", MagicMock(side_effect=OSError("disk full")))
    assert injetar_traducoes(str(source), {"/data/item[1]/bio[1]": "x"}, str(source)) is False
    assert source.read_bytes() == TRICKY_XML
    assert [p.name for p in tmp_path.iterdir()] == ["in.xml"]


# --- 4. Google: text without Latin letters is still text --------------------


@pytest.mark.parametrize("text", ["Привет, мир", "こんにちは", "你好"])
def test_google_translates_non_latin_source(data_dir, text):
    service = GoogleTranslateFreeService()
    with patch.object(service, "_call_api", return_value="Hello") as call:
        assert service.translate(text, {"target_lang": "en"}) == "Hello"
    call.assert_called_once()


def test_google_passes_through_lines_without_letters(data_dir):
    service = GoogleTranslateFreeService()
    with patch.object(service, "_call_api", return_value="Olá") as call:
        assert service.translate("Hello\n123 / 456\n", {"target_lang": "pt"}) == "Olá\n123 / 456\n"
    call.assert_called_once()


# --- 5. Glossary: whole words, every target language, every provider -------


def test_glossary_matches_whole_words_only(data_dir):
    write_glossary(data_dir, "pt", {"Strike": "Golpe", "Energy": "Energia", "End": "Fim", "Token": "Ficha"})
    text = "Striker uses Energyze, then a Strike. The End Token."
    assert apply_glossary(text, "pt")[0] == "Striker uses Energyze, then a Golpe. The Fim Ficha."
    protected, tokens = protect_glossary_for_ai(text, "pt")
    assert sorted(tokens.values()) == ["Ficha", "Fim", "Golpe"]
    assert restore_glossary_tokens(protected, tokens) == "Striker uses Energyze, then a Golpe. The Fim Ficha."


def test_longest_term_wins_and_case_is_mirrored(data_dir):
    write_glossary(data_dir, "pt", {"Blade": "Lâmina", "Ember Blade": "Lâmina de Brasa"})
    assert apply_glossary("EMBER BLADE and a blade", "pt")[0] == "LÂMINA DE BRASA and a lâmina"


def test_each_target_language_has_its_own_glossary(data_dir):
    write_glossary(data_dir, "pt", {"Blade": "Lâmina"})
    write_glossary(data_dir, "es", {"Blade": "Hoja"})
    assert glossary_filename("pt_BR") == "glossario.json"
    assert glossary_filename("es") == "glossario_es.json"
    assert apply_glossary("Blade", "es")[0] == "Hoja"
    assert apply_glossary("Blade", "pt")[0] == "Lâmina"
    # The Portuguese glossary must never leak into another language.
    assert carregar_glossario("fr") == {}
    assert apply_glossary("Blade", "fr") == ("Blade", False)


def test_google_applies_the_glossary(data_dir):
    write_glossary(data_dir, "es", {"Hawkeye": "Ojo de Halcón"})
    service = GoogleTranslateFreeService()
    with patch.object(service, "_call_api", side_effect=lambda text, _tl: text.replace("An analog to", "Un análogo de")):
        result = service.translate("An analog to Hawkeye", {"target_lang": "es"})
    assert result == "Un análogo de Ojo de Halcón"


def test_azure_applies_the_glossary(data_dir):
    write_glossary(data_dir, "pt", {"Hawkeye": "Gavião Arqueiro"})
    client = MagicMock()
    client.translate.side_effect = lambda content, to_language: [
        MagicMock(translations=[MagicMock(text=content[0].replace("Meet", "Conheça"))])
    ]
    with patch("core.tradutor_api.TextTranslationClient", return_value=client):
        result = AzureService().translate("Meet Hawkeye", {"api_key": "k", "target_lang": "pt"})
    assert result == "Conheça Gavião Arqueiro"
    assert "Hawkeye" not in client.translate.call_args.kwargs["content"][0]


def ollama_reply(payload):
    response = MagicMock()
    response.json.return_value = {"response": json.dumps(payload)}
    return response


def test_ollama_prompt_stays_valid_json_and_applies_the_glossary(data_dir):
    write_glossary(data_dir, "pt", {"Wrecker": "Demolidor"})
    text = 'Dirk "The Wrecker" said:\nhello'
    protected, tokens = protect_glossary_for_ai(text, "pt")
    token = next(iter(tokens))
    with patch("core.tradutor_api.requests.post", return_value=ollama_reply({"text": f'Dirk "O {token}" disse'})) as post:
        result = OllamaService().translate(text, {"target_lang": "pt"})
    prompt = post.call_args.kwargs["json"]["prompt"]
    sent = json.loads(prompt[prompt.index("Input:\n") + 7 : prompt.index("\n\nOutput:")])
    assert sent == {"text": protected}
    assert result == 'Dirk "O Demolidor" disse'


def test_ollama_batch_applies_the_glossary(data_dir):
    write_glossary(data_dir, "pt", {"Blade": "Lâmina"})
    entries = [TranslationEntry("/a", "A Blade"), TranslationEntry("/b", "No term")]
    token = next(iter(protect_glossary_for_ai("A Blade", "pt")[1]))
    reply = ollama_reply({"translations": [f"Uma {token}", "Sem termo"]})
    with patch("core.tradutor_api.requests.post", return_value=reply):
        assert translate_batch_ollama(entries, {"target_lang": "pt"}) == {"/a": "Uma Lâmina", "/b": "Sem termo"}


def test_mt_token_survives_a_case_change(data_dir):
    write_glossary(data_dir, "pt", {"Blade": "Lâmina"})
    protected, tokens = protect_glossary_for_mt("Blade", "pt")
    assert restore_glossary_tokens(protected.lower(), tokens) == "Lâmina"


# --- Atomic writes and tolerant imports -------------------------------------


def test_failed_atomic_write_keeps_the_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_text('{"api_keys": {"DeepL": "kept"}}', encoding="utf-8")
    monkeypatch.setattr("core.atomic.os.replace", MagicMock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        write_json_atomic(str(target), {"api_keys": {}})
    assert json.loads(target.read_text(encoding="utf-8")) == {"api_keys": {"DeepL": "kept"}}
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


@pytest.mark.parametrize("content", ['["a", "b"]', '"text"', "{broken", '{"/a": 5, "/b": null}'])
def test_import_json_ignores_files_that_are_not_a_backup(tmp_path, content):
    project = TranslationProject()
    project.entries["/a"] = TranslationEntry("/a", "A")
    path = tmp_path / "import.json"
    path.write_text(content, encoding="utf-8")
    assert project.import_json(str(path)) == 0
    assert project.entries["/a"].translation == ""


def test_import_csv_in_another_encoding_does_not_raise(tmp_path):
    project = TranslationProject()
    project.entries["/a"] = TranslationEntry("/a", "A")
    path = tmp_path / "import.csv"
    path.write_bytes("xpath,translated_text\n/a,café\n".encode("utf-16"))
    assert project.import_csv(str(path)) == 0


def test_gemini_model_is_resolved_once_per_key(monkeypatch):
    monkeypatch.setattr(tradutor_api, "_RESOLVED_GEMINI_MODELS", {})
    request = MagicMock(return_value={})
    monkeypatch.setattr(tradutor_api, "_gemini_request", request)
    for _ in range(3):
        tradutor_api.get_gemini_model("models/gemini-flash-latest", api_key="k")
    assert request.call_count == 1


# --- Keys at rest, Azure region, Ollama options -----------------------------


def test_api_keys_are_not_stored_in_plain_text(tmp_path, monkeypatch):
    from core import key_protection
    from core.app_controller import AppController

    if not key_protection.available():
        pytest.skip("DPAPI is Windows-only")
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
    ctrl = AppController()
    ctrl.set_api_key("DeepL", "secret-key-123")
    ctrl.save_config(api_key="", model_label="", model_id="")

    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "secret-key-123" not in raw and '"api_keys"' not in raw
    assert AppController().get_api_key("DeepL") == "secret-key-123"


def test_plain_text_keys_from_an_older_config_are_read_and_then_protected(tmp_path, monkeypatch):
    from core import key_protection
    from core.app_controller import AppController

    if not key_protection.available():
        pytest.skip("DPAPI is Windows-only")
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"provider": "DeepL", "api_keys": {"DeepL": "old-plain-key"}}), encoding="utf-8"
    )
    ctrl = AppController()
    assert ctrl.api_key == "old-plain-key"
    ctrl.save_preferred_theme("Cool Tint")
    assert "old-plain-key" not in (tmp_path / "config.json").read_text(encoding="utf-8")
    assert AppController().get_api_key("DeepL") == "old-plain-key"


def test_a_key_protected_elsewhere_is_ignored_instead_of_breaking_the_config(tmp_path, monkeypatch):
    from core.app_controller import AppController

    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"provider": "DeepL", "theme": "Cool Tint", "api_keys_protected": {"DeepL": "bm90IGEgYmxvYg=="}}),
        encoding="utf-8",
    )
    ctrl = AppController()
    assert (ctrl.get_api_key("DeepL"), ctrl.preferred_theme) == ("", "Cool Tint")


@pytest.mark.parametrize("region, expected", [("brazilsouth", "brazilsouth"), ("", None)])
def test_azure_sends_the_region_only_when_configured(data_dir, region, expected):
    client = MagicMock()
    client.translate.return_value = [MagicMock(translations=[MagicMock(text="Ol\u00e1")])]
    with patch("core.tradutor_api.TextTranslationClient", return_value=client) as factory:
        AzureService().translate("Hello", {"api_key": "k", "target_lang": "pt", "azure_region": region})
    assert factory.call_args.kwargs.get("region") == expected


def test_ollama_honours_ollama_host(data_dir, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "192.168.0.5:11434")
    with patch("core.tradutor_api.requests.post", return_value=ollama_reply({"text": "Ol\u00e1"})) as post:
        OllamaService().translate("Hello", {"target_lang": "pt"})
    assert post.call_args.args[0] == "http://192.168.0.5:11434/api/generate"


def test_ollama_thinking_mode_is_requested_and_its_reasoning_is_stripped(data_dir):
    response = MagicMock(status_code=200)
    response.json.return_value = {"response": '<think>hmm, a greeting</think>\nHere it is: {"text": "Ol\u00e1"}'}
    with patch("core.tradutor_api.requests.post", return_value=response) as post:
        result = OllamaService().translate("Hello", {"target_lang": "pt", "ollama_thinking": True})
    sent = post.call_args.kwargs["json"]
    assert sent["think"] is True and "format" not in sent
    assert result == "Ol\u00e1"
