import json
import os
from unittest.mock import MagicMock, patch

import pytest

from core.tradutor_api import (
    AVAILABLE_SERVICES,
    DeepLService,
    GeminiService,
    OllamaService,
    _candidate_model_names,
    _gemini_request,
    apply_glossary,
    carregar_glossario,
    protect_glossary_for_xml,
    provider_supports_context,
    traduzir_arquivo_json,
    translate_batch_ollama,
    translate_text,
)


class TestCarregarGlossario:
    def test_returns_dict(self):
        result = carregar_glossario()
        assert isinstance(result, dict)

    def test_returns_empty_dict_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.tradutor_api.os.path.dirname", lambda _: str(tmp_path))
        result = carregar_glossario()
        assert result == {}

    def test_loads_language_specific_file_first(self, tmp_path, monkeypatch):
        lang_glossary = {"Sword": "Espada"}
        lang_file = tmp_path / "glossario_pt.json"
        lang_file.write_text(json.dumps(lang_glossary), encoding="utf-8")

        monkeypatch.setattr("core.tradutor_api.os.path.dirname", lambda _: str(tmp_path))
        result = carregar_glossario(target_lang="pt")
        assert result == lang_glossary

    def test_falls_back_to_generic_glossary(self, tmp_path, monkeypatch):
        generic = {"Dragon": "Dragão"}
        generic_file = tmp_path / "glossario.json"
        generic_file.write_text(json.dumps(generic), encoding="utf-8")

        monkeypatch.setattr("core.tradutor_api.os.path.dirname", lambda _: str(tmp_path))
        result = carregar_glossario(target_lang="pt")
        assert result == generic


class TestCandidateModelNames:
    def test_includes_original_name(self):
        candidates = _candidate_model_names("gemini-1.5-flash")
        assert "gemini-1.5-flash" in candidates

    def test_includes_latest_variant(self):
        candidates = _candidate_model_names("gemini-1.5-flash")
        assert "gemini-1.5-flash-latest" in candidates

    def test_includes_fallback_models(self):
        candidates = _candidate_model_names("some-weird-model")
        assert "models/gemini-3.5-flash-lite" in candidates
        assert "models/gemini-2.5-flash" in candidates
        assert "gemini-1.5-flash" not in candidates
        assert "models/gemini-2.0-flash" not in candidates

    def test_no_duplicates(self):
        candidates = _candidate_model_names("gemini-1.5-flash")
        assert len(candidates) == len(set(candidates))

    def test_empty_string_returns_fallbacks(self):
        candidates = _candidate_model_names("")
        assert "models/gemini-3.5-flash-lite" in candidates
        assert len(candidates) >= 1


class TestApplyGlossary:
    def test_applies_portuguese_glossary(self, tmp_path, monkeypatch):
        (tmp_path / "glossario_pt.json").write_text(
            json.dumps({"Sword": "Espada"}), encoding="utf-8"
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))

        text, used = apply_glossary("The Sword is ready", "pt")

        assert text == "The Espada is ready"
        assert used is True

    def test_does_not_apply_portuguese_glossary_to_other_targets(self, tmp_path, monkeypatch):
        (tmp_path / "glossario.json").write_text(
            json.dumps({"Sword": "Espada"}), encoding="utf-8"
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))

        text, used = apply_glossary("The Sword is ready", "en")

        assert text == "The Sword is ready"
        assert used is False

    def test_gemini_translates_surrounding_text_and_restores_glossary_term(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / "glossario_pt.json").write_text(
            json.dumps({"Hammerhead": "Cabeça de Martelo"}), encoding="utf-8"
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
        model = MagicMock()
        model.generate_content.return_value.text = (
            "STZGLOSSARYTOKEN0END venderá para qualquer um: Roxxon, Brand, Latvéria..."
        )

        with patch("core.tradutor_api.get_gemini_model", return_value=model):
            result = GeminiService().translate(
                "Hammerhead will sell to anyone: Roxxon, Brand, Latveria...",
                {
                    "api_key": "fake",
                    "target_lang": "pt",
                    "target_label": "Portuguese (Brazil)",
                },
            )

        prompt = model.generate_content.call_args.args[0]
        assert "STZGLOSSARYTOKEN0END will sell to anyone" in prompt
        assert "Cabeça de Martelo will sell to anyone" not in prompt
        assert "Translate all surrounding text" in prompt
        assert result == (
            "Cabeça de Martelo venderá para qualquer um: Roxxon, Brand, Latvéria..."
        )

    def test_protects_glossary_terms_for_xml_translation(self, tmp_path, monkeypatch):
        (tmp_path / "glossario_pt.json").write_text(
            json.dumps({"Sword": "Espada"}), encoding="utf-8"
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))

        text, used = protect_glossary_for_xml("Sword & shield", "pt")

        assert text == "<stz-glossary>Espada</stz-glossary> &amp; shield"
        assert used is True


class TestDeepLGlossary:
    def test_preserves_glossary_terms_with_ignored_xml_tag(self, tmp_path, monkeypatch):
        (tmp_path / "glossario_pt.json").write_text(
            json.dumps({"Sword": "Espada"}), encoding="utf-8"
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path))
        translator = MagicMock()
        translator.translate_text.return_value.text = (
            "A <stz-glossary>ESPADA</stz-glossary> &amp; o escudo"
        )

        with patch("core.tradutor_api.deepl.Translator", return_value=translator):
            result = DeepLService().translate(
                "The Sword & shield",
                {"api_key": "fake", "target_lang": "pt", "deepl_lang": "PT-BR"},
            )

        sent_text = translator.translate_text.call_args.args[0]
        assert "<stz-glossary>Espada</stz-glossary>" in sent_text
        assert translator.translate_text.call_args.kwargs["tag_handling"] == "xml"
        assert translator.translate_text.call_args.kwargs["ignore_tags"] == ["stz-glossary"]
        assert result == "A ESPADA & o escudo"

    def test_sends_entry_context_through_native_context_parameter(self):
        translator = MagicMock()
        translator.translate_text.return_value.text = "Técnico talentoso."

        with patch("core.tradutor_api.deepl.Translator", return_value=translator):
            result = DeepLService().translate(
                "Gifted technician.",
                {
                    "api_key": "fake",
                    "target_lang": "pt",
                    "deepl_lang": "PT-BR",
                    "source_tag": "bio",
                    "entry_context": {"dispName": "WHIPLASH"},
                },
            )

        assert translator.translate_text.call_args.args[0] == "Gifted technician."
        sent_context = translator.translate_text.call_args.kwargs["context"]
        assert "dispName: WHIPLASH" in sent_context
        assert "bio" in sent_context
        assert result == "Técnico talentoso."


class TestGeminiErrors:
    def test_http_error_includes_api_message(self):
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"error": {"message": "Quota exceeded"}}
        response.raise_for_status.side_effect = __import__("requests").HTTPError("429")

        with patch("core.tradutor_api.requests.request", return_value=response):
            with pytest.raises(RuntimeError, match="Gemini API HTTP 429: Quota exceeded"):
                _gemini_request("GET", "https://example.invalid", "fake")


class TestTranslateText:
    def test_unknown_service_returns_error_string(self):
        result = translate_text("UnknownServiceXYZ", "hello", {})
        assert "nao reconhecido" in result.lower() or "não reconhecido" in result.lower()

    def test_available_services_registered(self):
        assert "Gemini" in AVAILABLE_SERVICES
        assert "DeepL" in AVAILABLE_SERVICES
        assert "Microsoft Azure" in AVAILABLE_SERVICES
        assert "Llama 3 (Local)" in AVAILABLE_SERVICES

    def test_gemini_translate_called_with_correct_args(self):
        mock_service = MagicMock()
        mock_service.translate.return_value = "Olá"

        with patch.dict("core.tradutor_api.AVAILABLE_SERVICES", {"Gemini": mock_service}):
            result = translate_text("Gemini", "Hello", {"api_key": "fake"})

        mock_service.translate.assert_called_once_with("Hello", {"api_key": "fake"})
        assert result == "Olá"

    def test_gemini_prompt_detects_source_language(self):
        model = MagicMock()
        model.generate_content.return_value.text = "Radiation"

        with patch("core.tradutor_api.get_gemini_model", return_value=model):
            result = GeminiService().translate(
                "Radiação",
                {"api_key": "fake", "model": "gemini-test", "target_label": "English", "target_lang": "en"},
            )

        prompt = model.generate_content.call_args.args[0]
        assert "to English" in prompt
        assert "Detect the source language automatically" in prompt
        assert "from English to English" not in prompt
        assert result == "Radiation"

    def test_gemini_prompt_delimits_entry_context_as_reference_only(self):
        model = MagicMock()
        model.generate_content.return_value.text = "Técnico talentoso."

        with patch("core.tradutor_api.get_gemini_model", return_value=model):
            GeminiService().translate(
                "Gifted technician.",
                {
                    "api_key": "fake",
                    "model": "gemini-test",
                    "target_label": "Portuguese (Brazil)",
                    "source_tag": "bio",
                    "entry_context": {"dispName": "WHIPLASH"},
                },
            )

        prompt = model.generate_content.call_args.args[0]
        assert "REFERENCE CONTEXT" in prompt
        assert '"dispName": "WHIPLASH"' in prompt
        assert "Do not translate or return the reference context" in prompt

    def test_ollama_prompt_contains_structured_entry_context(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": '{"text":"Técnico talentoso."}'}

        with patch("core.tradutor_api.requests.post", return_value=response) as post:
            result = OllamaService().translate(
                "Gifted technician.",
                {
                    "model": "llama3",
                    "target_label": "Portuguese (Brazil)",
                    "source_tag": "bio",
                    "entry_context": {"dispName": "WHIPLASH"},
                },
            )

        sent_prompt = post.call_args.kwargs["json"]["prompt"]
        assert "REFERENCE CONTEXT" in sent_prompt
        assert '"dispName": "WHIPLASH"' in sent_prompt
        assert result == "Técnico talentoso."

    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("Gemini", True),
            ("DeepL", True),
            ("Ollama (Local)", True),
            ("Google Translate (Free)", False),
            ("Microsoft Azure", False),
        ],
    )
    def test_provider_context_capability(self, provider, expected):
        assert provider_supports_context(provider) is expected

    def test_ollama_batch_keeps_context_separate_from_translatable_text(self):
        entries = [
            MagicMock(
                xpath="/root/item[1]/bio[1]",
                original="Gifted technician.",
                source_tag="bio",
                context={"dispName": "WHIPLASH"},
            )
        ]
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": '{"translations":["Técnico talentoso."]}'}

        with patch("core.tradutor_api.requests.post", return_value=response) as post:
            result = translate_batch_ollama(entries, {"model": "llama3"})

        prompt = post.call_args.kwargs["json"]["prompt"]
        assert '"text": "Gifted technician."' in prompt
        assert '"field": "bio"' in prompt
        assert '"context": {"dispName": "WHIPLASH"}' in prompt
        assert "reference data and must not appear" in prompt
        assert result == {"/root/item[1]/bio[1]": "Técnico talentoso."}

    def test_api_exception_returns_error_string(self):
        mock_service = MagicMock()
        mock_service.translate.side_effect = RuntimeError("boom")

        with patch.dict("core.tradutor_api.AVAILABLE_SERVICES", {"Gemini": mock_service}):
            result = translate_text("Gemini", "Hello", {})

        assert "ERRO" in result

    def test_ollama_connection_refused_returns_friendly_message(self):
        mock_service = MagicMock()
        mock_service.translate.side_effect = Exception("Connection refused")

        with patch.dict("core.tradutor_api.AVAILABLE_SERVICES", {"Llama 3 (Local)": mock_service}):
            result = translate_text("Llama 3 (Local)", "Hello", {})

        assert "Ollama" in result


class TestTraduzirArquivoJson:
    def test_translates_and_writes_output(self, tmp_path):
        input_data = {"/root/item[1]/dispName[1]": "Hello World"}
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(input_data), encoding="utf-8")
        output_file = tmp_path / "output.json"

        mock_service = MagicMock()
        mock_service.translate.return_value = "Olá Mundo"

        with patch.dict("core.tradutor_api.AVAILABLE_SERVICES", {"Gemini": mock_service}):
            result = traduzir_arquivo_json(
                str(input_file), str(output_file), api_key="fake", servico="Gemini"
            )

        assert result is True
        assert output_file.exists()
        output_data = json.loads(output_file.read_text(encoding="utf-8"))
        assert output_data["/root/item[1]/dispName[1]"] == "Olá Mundo"

    def test_returns_false_on_missing_input_file(self, tmp_path):
        result = traduzir_arquivo_json(
            str(tmp_path / "nonexistent.json"),
            str(tmp_path / "output.json"),
            api_key="fake",
        )
        assert result is False
