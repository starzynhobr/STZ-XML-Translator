import json
import os
from unittest.mock import MagicMock, patch

import pytest

from core.tradutor_api import (
    AVAILABLE_SERVICES,
    _candidate_model_names,
    carregar_glossario,
    traduzir_arquivo_json,
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
        assert "gemini-1.5-flash" in candidates

    def test_no_duplicates(self):
        candidates = _candidate_model_names("gemini-1.5-flash")
        assert len(candidates) == len(set(candidates))

    def test_empty_string_returns_fallbacks(self):
        candidates = _candidate_model_names("")
        assert "gemini-1.5-flash" in candidates
        assert len(candidates) >= 1


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
