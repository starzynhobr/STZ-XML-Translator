from __future__ import annotations

import json
import re

from lxml import etree as ET

from core.atomic import write_bytes_atomic

_PROLOG_ITEM_RE = re.compile(
    rb"\s+|<\?.*?\?>|<!--.*?-->|<!DOCTYPE(?:[^\[>]|\[.*?\])*>",
    re.DOTALL,
)
_UTF8_BOM = b"\xef\xbb\xbf"


def _is_ascii_compatible(encoding: str) -> bool:
    return not encoding.lower().replace("_", "-").startswith(("utf-16", "utf-32", "ucs-"))


def _prolog_end(original: bytes) -> int | None:
    """Offset where the root element starts, or None when it cannot be found."""
    position = len(_UTF8_BOM) if original.startswith(_UTF8_BOM) else 0
    while True:
        match = _PROLOG_ITEM_RE.match(original, position)
        if not match or match.end() == position:
            break
        position = match.end()
    return position if original[position : position + 1] == b"<" else None


def _was_cdata(element) -> bool:
    """True when the element's text was written as a CDATA section."""
    serialized = ET.tostring(element, encoding="unicode", with_tail=False)
    return serialized[serialized.find(">") + 1 :].startswith("<![CDATA[")


def injetar_traducoes(arquivo_xml_original: str, mapa_traducoes, arquivo_xml_final: str):
    """
    Apply an XPath -> translation map (a dict or the path of a JSON file) to the
    XML and write the result. Returns True on success, False on failure.

    Only the translated texts change: indentation, blank lines, line endings,
    CDATA sections, the XML declaration, comments before the root, the encoding
    and a BOM are written back as they were. The serializer still normalizes
    three things that mean the same to an XML parser: attribute quotes become
    double quotes, &quot;/&apos; in text become literal quotes, and an empty
    <a></a> becomes <a/>.
    """
    try:
        if isinstance(mapa_traducoes, str):
            with open(mapa_traducoes, encoding="utf-8") as f:
                mapa_xpath_traducao = json.load(f)
        else:
            mapa_xpath_traducao = mapa_traducoes

        with open(arquivo_xml_original, "rb") as f:
            original = f.read()

        # Keep whitespace and CDATA exactly: no blank-text removal, no reformatting.
        parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False)
        tree = ET.parse(arquivo_xml_original, parser)
        root = tree.getroot()

        itens_modificados = 0
        for xpath, traducao in mapa_xpath_traducao.items():
            elementos = root.xpath(xpath)
            if elementos:
                elemento = elementos[0]
                elemento.text = ET.CDATA(traducao) if _was_cdata(elemento) else traducao
                itens_modificados += 1

        print(f"Injeção concluída. Itens modificados: {itens_modificados}")
        if mapa_xpath_traducao and not itens_modificados:
            # Translations exist but none belongs to this file: writing a copy
            # of the original and calling it a success would hide the mismatch.
            print("ERRO no injetor: nenhuma tradução corresponde a este XML.")
            return False

        encoding = tree.docinfo.encoding or "UTF-8"
        crlf = b"\r\n" in original
        prolog_end = _prolog_end(original) if _is_ascii_compatible(encoding) else None
        if prolog_end is None:
            # UTF-16/32 or an unusual prolog: let lxml write the whole document.
            payload = ET.tostring(tree, encoding=encoding, xml_declaration=True)
        else:
            # Everything before the root element (BOM, declaration, comments,
            # DOCTYPE) is copied byte for byte; only the root is serialized.
            body = ET.tostring(root, encoding=encoding, xml_declaration=False, with_tail=False)
            for sibling in root.itersiblings():
                body += b"\n" + ET.tostring(sibling, encoding=encoding, with_tail=False)
            # The parser reads CRLF as LF; put the file's own line endings back.
            if crlf:
                body = body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            payload = original[:prolog_end] + body
            if original.endswith(b"\n") and not payload.endswith(b"\n"):
                payload += b"\r\n" if crlf else b"\n"

        # Atomic: saving over the original must never leave a half-written file.
        write_bytes_atomic(arquivo_xml_final, payload)
        return True

    except FileNotFoundError:
        print(f"ERRO no injetor: Arquivo não encontrado - {arquivo_xml_original} ou {mapa_traducoes}")
        return False
    except Exception as e:
        print(f"ERRO INESPERADO durante a injeção: {e}")
        return False
