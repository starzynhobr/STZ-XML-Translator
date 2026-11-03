"""Fast bulk translation with Gemini.

Three things make a large file cheap and quick:

* **Each distinct text once.** Game data repeats a lot (``bio`` and ``cogBio``,
  the same weapon name on many enemies). Identical originals are sent once and
  the answer is applied to every copy.
* **Names first.** Name fields are translated before everything else; the
  names a later request mentions travel with it as fixed references, so a
  character is called the same in its name, its bio and every dialog.
* **Requests sized by text, sent in parallel.** A request is filled up to a
  character budget instead of a fixed count, so short names travel in big
  groups and long bios in small ones. Several requests run at once, paced to
  the key's requests-per-minute limit; a 429 slows the pace down and retries.
* **JSON with a schema.** The model must answer ``[{"id", "text"}]``, so one
  malformed separator can no longer drop part of a batch.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

# Source characters per request. ~12k characters is a few thousand tokens in and
# out: comfortably inside the free tier's per-minute token budget even with
# several requests in flight, and small enough to answer in seconds.
MAX_CHARS = 12_000
MAX_ITEMS = 150
# A per-minute limit only asks to wait: retry longer before giving up on a request.
RATE_RETRIES = 6
MIN_RATE_WAIT = 10.0
# Longer waits (a model with no quota on this key asks for ~18 h) are not worth
# waiting for: the request fails as an exhausted quota instead.
MAX_RATE_WAIT = 90.0
RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"id": {"type": "STRING"}, "text": {"type": "STRING"}},
        "required": ["id", "text"],
    },
}
_RETRY_AFTER = re.compile(r"retry in ([\d.]+)\s*s", re.I)
# Up to this many words a text is "short": shared only within its own field.
SHORT_WORDS = 3
_NAME_FIELD = re.compile(r"^(disp|cog|display|short|full|nick|hero|villain)?_?name$", re.I)
MAX_NAME_HINTS = 40


@dataclass
class Unit:
    """One distinct original and every entry that carries it."""

    id: str
    original: str
    entry: object  # the first entry: its field and context go to the model
    xpaths: list[str] = field(default_factory=list)


def dedupe(entries: Sequence) -> list[Unit]:
    """One unit per distinct text.

    A sentence means the same wherever it appears, so long texts are shared
    across fields (``bio`` and ``cogBio``). A word or two can be a button in one
    field and an item in another ("Charge", "Guard"): short texts are only
    shared within the same field.
    """
    units: dict[object, Unit] = {}
    for entry in entries:
        key = entry.original if len(entry.original.split()) > SHORT_WORDS else (entry.original, entry.source_tag)
        unit = units.get(key)
        if unit is None:
            unit = units[key] = Unit(f"t{len(units) + 1}", entry.original, entry)
        unit.xpaths.append(entry.xpath)
    return list(units.values())


def is_name_field(tag: str) -> bool:
    """Fields that hold a name: dispName, cogName, displayName, name..."""
    return bool(_NAME_FIELD.match(tag))


def names_in(texts: Sequence[str], memory: dict[str, str], limit: int = MAX_NAME_HINTS) -> list[tuple[str, str]]:
    """Translated names that appear in these texts, so the model reuses them."""
    if not memory:
        return []
    joined = "\n".join(texts).casefold()
    found = []
    for original, translation in memory.items():
        needle = original.casefold()
        if len(needle) < 3 or needle not in joined:
            continue
        if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", joined):
            found.append((original, translation))
            if len(found) >= limit:
                break
    return found


def pack(units: Sequence[Unit], max_chars: int = MAX_CHARS, max_items: int = MAX_ITEMS) -> list[list[Unit]]:
    """Group units into requests by size, keeping their order."""
    chunks: list[list[Unit]] = []
    current: list[Unit] = []
    size = 0
    for unit in units:
        length = len(unit.original)
        if current and (size + length > max_chars or len(current) >= max_items):
            chunks.append(current)
            current, size = [], 0
        current.append(unit)
        size += length
    if current:
        chunks.append(current)
    return chunks


class RateGate:
    """Spaces request starts to stay under a requests-per-minute limit.

    ``slow_down`` (after a 429) halves the pace and holds every caller until
    the wait the API asked for has passed.
    """

    def __init__(self, rpm: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = 60.0 / max(rpm, 0.1)
        self._next = 0.0
        self._lock = threading.Lock()
        self._clock = clock
        self._sleep = sleep

    def wait(self, cancelled: Callable[[], bool] = lambda: False) -> bool:
        """Block until this caller may start a request; False when cancelled meanwhile."""
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.interval
        while not cancelled():
            remaining = start - self._clock()
            if remaining <= 0:
                return True
            self._sleep(min(remaining, 0.5))
        return False

    def slow_down(self, retry_after: float) -> None:
        with self._lock:
            self.interval = min(self.interval * 2, 60.0)
            self._next = max(self._next, self._clock() + retry_after)


def retry_after(exc: Exception) -> float | None:
    """Seconds a 429 asks to wait, or None when it is not a rate limit."""
    text = str(exc)
    if "429" not in text and "RESOURCE_EXHAUSTED" not in text and "quota" not in text.lower():
        return None
    match = _RETRY_AFTER.search(text)
    return max(float(match.group(1)), MIN_RATE_WAIT) if match else 20.0


def daily_quota_exhausted(exc: Exception) -> bool:
    """A 429 whose only violated quotas are per day: waiting minutes will not help.

    Google lists the violated quota ids (``...PerMinute...``, ``...PerDay...``);
    a per-minute limit in the list means the request may pass after a wait.
    """
    text = str(exc)
    if "429" not in text:
        return False
    match = re.search(r"\[quota: ([^\]]*)\]", text)
    if not match:
        return False  # without the ids, assume the recoverable case and wait
    ids = [quota.strip().lower() for quota in match.group(1).split(",") if quota.strip()]
    return bool(ids) and all("perday" in quota for quota in ids)


def build_prompt(items: Sequence[dict], rules: str, target_label: str) -> str:
    """Items are {"id", "text", "field", "context"?}; the answer must be [{"id", "text"}]."""
    return (
        "Act as a game localization specialist.\n"
        f"{rules}"
        f"Translate the \"text\" of every item to {target_label}. \"field\" and \"context\" are "
        "reference data from the same game record (internal names, speaker, item); never translate "
        "or return them.\n"
        "Answer with one object per item, with the same \"id\" and the translated \"text\".\n"
        f"Items: {json.dumps(items, ensure_ascii=False)}"
    )


def parse(response_text: str) -> dict[str, str]:
    data = json.loads(response_text)
    if isinstance(data, dict):  # some models wrap the array
        data = next((v for v in data.values() if isinstance(v, list)), [])
    return {
        str(item["id"]): str(item["text"])
        for item in data
        if isinstance(item, dict) and "id" in item and isinstance(item.get("text"), str)
    }
