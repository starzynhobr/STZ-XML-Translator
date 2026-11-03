"""Per-game knowledge layered over the generic field analysis.

The generic rules in ``core.field_analysis`` guess which fields hold text. A
profile corrects those guesses for one game: fields that look like prose but
are internal labels become context (still useful to the AI), fields the game
looks values up by are ignored, and whole tags with nothing to translate are
hidden. Games without a profile use the generic rules alone, so adding a
profile never changes another game's behaviour.

Rules are keyed by ``(record tag, field)``; a ``"*"`` field covers the whole tag.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from core.extrator import Group, XmlDocumentIndex
from core.field_analysis import TagInfo, analyze

TRANSLATE, CONTEXT, IGNORE = "translate", "context", "ignore"

# Generic: a non-translated field with one of these names says what the record is.
_CONTEXT_NAMES = ("name", "title", "label", "key", "internalName", "codeName")


@dataclass(frozen=True)
class GameProfile:
    id: str
    name: str
    detect: Callable[[str], bool]
    rules: dict[tuple[str, str], str] = field(default_factory=dict)

    def rule(self, tag: str, field_name: str) -> str | None:
        return self.rules.get((tag, field_name)) or self.rules.get((tag, "*"))


def _has(root: str, *names: str) -> bool:
    return any(os.path.exists(os.path.join(root, name)) for name in names)


MAA_REDUX = GameProfile(
    id="maa-redux",
    name="Marvel: Avengers Alliance Redux",
    detect=lambda root: _has(root, "MAA Redux_Data", "MAA Redux.exe"),
    rules={
        # Developer labels: never shown, but they tell the AI which variant this is.
        ("villain", "name"): CONTEXT,
        ("baseVillain", "name"): CONTEXT,
        ("research", "name"): CONTEXT,
        ("taskListCheckpoint", "name"): CONTEXT,
        ("combatEncounter", "groupBossEncounterName"): CONTEXT,
        ("dialog", "name"): CONTEXT,
        ("localeString", "name"): CONTEXT,
        # Lists of status names the game resolves by text: translating breaks them.
        ("actionLevel", "statusEffects"): IGNORE,
        ("questObjective", "objectiveDetail"): IGNORE,
        ("distressCallSet", "name"): IGNORE,
        ("entry", "author"): IGNORE,  # {AGENT_NAME} placeholder
        ("entry", "username"): IGNORE,
        ("command", "*"): IGNORE,  # internal command list
        ("chapter", "*"): IGNORE,  # "DO NOT DISPLAY" placeholders
    },
)

GENERIC = GameProfile(id="generic", name="", detect=lambda _root: True)

PROFILES: tuple[GameProfile, ...] = (MAA_REDUX,)


def profile_for(game_root: str) -> GameProfile:
    """The profile of the game installed at ``game_root``, or the generic one."""
    if game_root:
        for profile in PROFILES:
            try:
                if profile.detect(game_root):
                    return profile
            except OSError:
                continue
    return GENERIC


def get_profile(profile_id: str) -> GameProfile:
    return next((p for p in PROFILES if p.id == profile_id), GENERIC)


@dataclass
class FieldPlan:
    tag: str
    kind: str
    count: int
    sample: str
    role: str
    technical: bool

    def to_json(self) -> dict:
        return {"tag": self.tag, "kind": self.kind, "count": self.count, "sample": self.sample, "role": self.role, "technical": self.technical}


@dataclass
class TagPlan:
    tag: str
    records: int
    texts: int
    selected: bool
    fields: list[FieldPlan]

    @property
    def useful(self) -> bool:
        return any(f.role == TRANSLATE for f in self.fields)

    def group(self) -> Group:
        return Group.of(
            self.tag,
            [f.tag for f in self.fields if f.role == TRANSLATE],
            [f.tag for f in self.fields if f.role == CONTEXT],
        )

    def to_json(self) -> dict:
        return {
            "tag": self.tag,
            "records": self.records,
            "texts": self.texts,
            "selected": self.selected,
            "useful": self.useful,
            "fields": [f.to_json() for f in self.fields],
        }


def _plan_tag(info: TagInfo, profile: GameProfile) -> TagPlan:
    fields: list[FieldPlan] = []
    for item in info.fields:
        rule = profile.rule(info.tag, item.tag)
        role = rule or (TRANSLATE if item.translatable else IGNORE)
        technical = not item.translatable and rule != CONTEXT
        fields.append(FieldPlan(item.tag, item.kind, item.count, item.sample, role, technical))

    translating = [f for f in fields if f.role == TRANSLATE]
    if translating and not any(f.role == CONTEXT for f in fields):
        # Without a profile rule, give the AI the record's own label when it has one.
        for name in _CONTEXT_NAMES:
            candidate = next((f for f in fields if f.tag == name and f.role == IGNORE and f.count), None)
            if candidate:
                candidate.role = CONTEXT
                break
    texts = sum(f.count for f in translating)
    return TagPlan(info.tag, info.records, texts, bool(translating) and texts > 0, fields)


def plan(index: XmlDocumentIndex, profile: GameProfile) -> list[TagPlan]:
    """Every record tag with a suggested role per field; text-bearing tags first."""
    plans = [_plan_tag(info, profile) for info in analyze(index)]
    plans.sort(key=lambda p: (not p.useful, -p.texts, -p.records, p.tag))
    return plans


def suggested_groups(plans: Sequence[TagPlan]) -> list[Group]:
    return [p.group() for p in plans if p.selected]
