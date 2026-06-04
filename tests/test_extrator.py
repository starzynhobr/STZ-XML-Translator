import os

import pytest

from core.extrator import extrair_textos, get_xpath

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "sample.xml")


class TestExtrairTextos:
    def test_returns_tuple(self):
        sucesso, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        assert isinstance(sucesso, bool)

    def test_extracts_named_items(self):
        sucesso, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        assert sucesso is True
        assert len(dados) == 3  # 4th item has empty dispName

    def test_extracted_values_are_strings(self):
        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        for xpath, texto in dados.items():
            assert isinstance(texto, str)
            assert texto.strip() != ""

    def test_xpath_keys_start_with_slash(self):
        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        for xpath in dados:
            assert xpath.startswith("/"), f"XPath should start with '/': {xpath}"

    def test_extraction_without_parent_tag(self):
        sucesso, dados = extrair_textos(FIXTURE_XML, "", "dispName")
        assert sucesso is True
        assert len(dados) == 3

    def test_target_tag_not_found_returns_false(self):
        sucesso, msg = extrair_textos(FIXTURE_XML, "item", "nonexistent_tag")
        assert sucesso is False
        assert isinstance(msg, str)

    def test_invalid_xml_returns_false(self, tmp_path):
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("this is not xml at all <><>", encoding="utf-8")
        sucesso, msg = extrair_textos(str(bad_xml), "item", "dispName")
        assert sucesso is False

    def test_empty_texts_are_excluded(self):
        _, dados = extrair_textos(FIXTURE_XML, "item", "description")
        for texto in dados.values():
            assert texto.strip() != ""

    def test_description_extraction(self):
        sucesso, dados = extrair_textos(FIXTURE_XML, "item", "description")
        assert sucesso is True
        assert any("brave warrior" in v for v in dados.values())
