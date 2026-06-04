import os

import pytest
from lxml import etree

from core.extrator import extrair_textos
from core.injetor import injetar_traducoes

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "sample.xml")


class TestInjetarTraducoes:
    def test_round_trip_produces_valid_xml(self, tmp_path):
        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        traducoes = {xpath: f"[TR] {texto}" for xpath, texto in dados.items()}
        output_xml = str(tmp_path / "output.xml")

        resultado = injetar_traducoes(FIXTURE_XML, traducoes, output_xml)

        assert resultado is True
        assert os.path.exists(output_xml)

    def test_translations_are_applied(self, tmp_path):
        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        traducoes = {xpath: f"[TR] {texto}" for xpath, texto in dados.items()}
        output_xml = str(tmp_path / "output.xml")

        injetar_traducoes(FIXTURE_XML, traducoes, output_xml)

        tree = etree.parse(output_xml)
        root = tree.getroot()
        for xpath, expected in traducoes.items():
            elements = root.xpath(xpath)
            assert elements, f"XPath not found in output: {xpath}"
            assert elements[0].text == expected

    def test_accepts_json_file_as_input(self, tmp_path):
        import json

        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        traducoes = {xpath: f"PT: {texto}" for xpath, texto in dados.items()}

        json_path = str(tmp_path / "traducoes.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(traducoes, f, ensure_ascii=False)

        output_xml = str(tmp_path / "output.xml")
        resultado = injetar_traducoes(FIXTURE_XML, json_path, output_xml)
        assert resultado is True

    def test_missing_xml_returns_false(self, tmp_path):
        resultado = injetar_traducoes(
            "/nonexistent/path.xml",
            {"/root/item[1]/dispName[1]": "text"},
            str(tmp_path / "out.xml"),
        )
        assert resultado is False

    def test_unknown_xpath_is_silently_ignored(self, tmp_path):
        traducoes = {"/root/item[99]/dispName[1]": "Ghost"}
        output_xml = str(tmp_path / "output.xml")
        resultado = injetar_traducoes(FIXTURE_XML, traducoes, output_xml)
        assert resultado is True  # should not raise

    def test_output_is_valid_xml(self, tmp_path):
        _, dados = extrair_textos(FIXTURE_XML, "item", "dispName")
        output_xml = str(tmp_path / "output.xml")
        injetar_traducoes(FIXTURE_XML, dados, output_xml)
        # If invalid XML this will raise
        etree.parse(output_xml)
