"""Tell translatable text apart from the technical values around it.

A game XML mixes player-facing text (names, descriptions, dialog) with values
the game reads as data: ids, numbers, flags, asset paths, colours. Translating
the latter breaks the game, so the selection screen only offers text fields and
pre-selects them; technical fields stay available behind an "advanced" toggle.

Classification looks at both the field name and a sample of its values. A game
profile (see ``core.game_profiles``) can override the verdict per field.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.extrator import XmlDocumentIndex, _element_text, _local_name

SAMPLE_LIMIT = 300

TEXT, NAME, ID, NUMBER, FLAG, PATH, EMPTY, CODE = (
    "text", "name", "id", "number", "flag", "path", "empty", "code",
)
TRANSLATABLE = frozenset({TEXT, NAME})

_NUMBER = re.compile(r"^[-+]?(\d+([.,]\d+)?|\.\d+)([eE][-+]?\d+)?%?$")
_NUMBER_LIST = re.compile(r"^[-+]?\d+(\.\d+)?([,;| ]\s*[-+]?\d+(\.\d+)?)+$")
_FLAG = re.compile(r"^(true|false|yes|no|on|off|null|none|nil)$", re.I)
_UUID = re.compile(r"^[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}$", re.I)
_HEX = re.compile(r"^(0x|#)?[0-9a-f]{6,}$", re.I)
_PATH = re.compile(r"([\\/][^\s\\/]+)+|\.(png|jpe?g|gif|swf|dds|tga|bmp|ogg|mp3|wav|xml|json|txt|unity3d|bundle|prefab|mat|anim)$", re.I)
# "a/fs/Amulet of Ashake Action I": a short folder prefix makes it a path even with spaces.
_PATH_WITH_SPACES = re.compile(r"^[a-z0-9_.-]{1,12}(/[a-z0-9_.-]{1,12})+/[^/]+$")
_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
# Single tokens that only machines write: snake_case, CONSTANT_CASE, dotted keys, digits mixed in.
_TOKEN = re.compile(r"^[A-Za-z0-9]*[_.:\-][A-Za-z0-9_.:\-]*$|^[A-Za-z]+\d+[A-Za-z0-9]*$|^\d+[A-Za-z]+[A-Za-z0-9]*$")
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
# One word that reads as a key, not a label: "melee", "heroLevel", "on_create".
_KEY_WORD = re.compile(r"^([a-z][a-z0-9]*|[a-z]+[A-Z][A-Za-z0-9]*)$")
# "...name" fields that hold technical names (className, fileName, assetName).
_TECH_NAME_FIELD = re.compile(r"(class|type|file|asset|icon|sprite|anim|sound|scene|prefab|font|shader|method|event)name$", re.I)

_TEXT_NAMES = re.compile(
    r"(name|title|desc|bio|text|label|caption|tooltip|tip|hint|message|msg|dialog|dialogue|line|speech|"
    r"subtitle|summary|story|lore|flavor|flavour|quote|intro|outro|info|help|instruction|objective|prompt|"
    r"question|answer|button|header|body|content|greeting|note|comment|reward)",
    re.I,
)
_TECH_NAMES = re.compile(
    r"(^id$|id$|ids$|^key|key$|guid|uuid|hash|asset|icon|image|img|swf|sprite|texture|sound|sfx|music|"
    r"path|file|url|uri|color|colour|font|class|type$|kind$|layer|anim|prefab|scene|level$|index|order|"
    r"count|amount|cost|price|chance|rate|time|date|duration|cooldown|version|flag|enabled|visible|"
    r"width|height|^x$|^y$|^z$|offset|scale|size|target$|controller)",
    re.I,
)


@dataclass
class FieldInfo:
    tag: str
    kind: str
    count: int  # non-empty values
    sample: str
    translatable: bool


@dataclass
class TagInfo:
    tag: str
    records: int
    fields: list[FieldInfo] = field(default_factory=list)

    @property
    def text_fields(self) -> list[FieldInfo]:
        return [f for f in self.fields if f.translatable]

    @property
    def texts(self) -> int:
        return sum(f.count for f in self.text_fields)


def classify_value(value: str) -> str:
    v = value.strip()
    if not v:
        return EMPTY
    if _NUMBER.match(v) or _NUMBER_LIST.match(v):
        return NUMBER
    if _FLAG.match(v):
        return FLAG
    if _UUID.match(v) or _HEX.match(v):
        return ID
    if _URL.match(v):
        return PATH
    words = _WORD.findall(v)
    if (" " not in v and _PATH.search(v)) or _PATH_WITH_SPACES.match(v):
        return PATH
    if " " not in v and (_TOKEN.match(v) or _KEY_WORD.match(v)):
        return CODE
    if len(words) >= 2 and " " in v:
        return TEXT
    if words:
        return NAME  # one word: a name, a label, or a code word
    return CODE


def classify_field(tag: str, values: Sequence[str]) -> str:
    """The kind of a field from its name and its non-empty values."""
    if not values:
        return EMPTY
    kinds = [classify_value(v) for v in values]
    share = {kind: kinds.count(kind) / len(kinds) for kind in set(kinds)}
    tech_name = bool(_TECH_NAME_FIELD.search(tag))
    text_like = bool(_TEXT_NAMES.search(tag)) and not tech_name
    tech_like = tech_name or (bool(_TECH_NAMES.search(tag)) and not text_like)

    if share.get(TEXT, 0) >= 0.3 and not tech_like:
        return TEXT
    for kind in (NUMBER, FLAG, ID, PATH):
        if share.get(kind, 0) >= 0.6:
            return kind
    if tech_like:
        return TEXT if share.get(TEXT, 0) >= 0.8 else CODE
    words = share.get(TEXT, 0) + share.get(NAME, 0)
    if text_like and words >= 0.6:
        return NAME if share.get(TEXT, 0) < 0.3 else TEXT
    if share.get(TEXT, 0) >= 0.5:
        return TEXT
    return CODE


def _leaf_children(element: ET.Element) -> list[ET.Element]:
    return [child for child in element if isinstance(child.tag, str) and len(child) == 0]


def analyze(index: XmlDocumentIndex) -> list[TagInfo]:
    """Every record tag with leaf fields, its fields classified, busiest text first."""
    tags: list[TagInfo] = []
    for tag, elements in index.elements_by_tag.items():
        values: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        order: list[str] = []
        records = 0
        for element in elements:
            leaves = _leaf_children(element)
            if not leaves:
                continue
            records += 1
            for child in leaves:
                name = _local_name(child.tag)
                if name not in counts:
                    counts[name] = 0
                    values[name] = []
                    order.append(name)
                text = _element_text(child)
                if text:
                    counts[name] += 1
                    if len(values[name]) < SAMPLE_LIMIT:
                        values[name].append(text)
        if not records:
            continue
        info = TagInfo(tag=tag, records=records)
        for name in order:
            kind = classify_field(name, values[name])
            sample = next((v for v in values[name] if classify_value(v) in TRANSLATABLE), values[name][0] if values[name] else "")
            info.fields.append(FieldInfo(name, kind, counts[name], sample[:160], kind in TRANSLATABLE))
        tags.append(info)
    tags.sort(key=lambda t: (-t.texts, -t.records, t.tag))
    return tags
