from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from core.extrator import ExtractedEntry, extrair_entradas
from core.injetor import injetar_traducoes
from core.translation_errors import ERROR_MESSAGES, normalize_error


class EntryStatus(StrEnum):
    PENDING = "pending"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    CONFIRMED = "confirmed"
    ERROR = "error"


def normalize_status(status: str) -> EntryStatus:
    # Legacy done means translated, never evidence of human review.
    return EntryStatus("translated" if status == "done" else status)


@dataclass
class TranslationEntry:
    xpath: str
    original: str
    translation: str = ""
    status: EntryStatus = EntryStatus.PENDING
    source_tag: str = ""
    container_xpath: str = ""
    context: dict[str, str] = field(default_factory=dict)
    error_code: str = ""

    def __post_init__(self) -> None:
        self.status = normalize_status(self.status)
        if self.status in (EntryStatus.TRANSLATED, EntryStatus.CONFIRMED) and not self.translation.strip():
            self.status = EntryStatus.PENDING
        self.error_code = normalize_error(self.error_code) if self.status == EntryStatus.ERROR else ""

    @property
    def error_message(self) -> str:
        return ERROR_MESSAGES[normalize_error(self.error_code)] if self.status == EntryStatus.ERROR else ""

    @property
    def needs_translation(self) -> bool:
        return self.status in (EntryStatus.PENDING, EntryStatus.ERROR)

    def set_translation(self, text: str, status: str = "translated") -> None:
        state = normalize_status(status)
        if state == EntryStatus.CONFIRMED and not text.strip():
            raise ValueError("Cannot confirm an empty translation")
        self.translation = text
        self.status = EntryStatus.PENDING if not text.strip() and state == EntryStatus.TRANSLATED else state
        if self.status != EntryStatus.ERROR:
            self.error_code = ""


class TranslationProject:
    """Encapsulates all state and I/O for a single XML translation session."""

    def __init__(self) -> None:
        self.xml_path: str = ""
        self.parent_tag: str = ""
        self.target_tag: str = ""
        self.target_tags: list[str] = []
        self.context_tags: list[str] = []
        self.entries: dict[str, TranslationEntry] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(
        self,
        xml_path: str,
        parent_tag: str,
        target_tag: str | Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> tuple[bool, str]:
        """
        Extract text from the XML and populate self.entries.
        Returns (True, "") on success or (False, error_message) on failure.
        Preserves existing translations for entries that are re-loaded.
        """
        target_tags = [target_tag] if isinstance(target_tag, str) else list(target_tag)
        selected_context_tags = list(context_tags)
        sucesso, dados = extrair_entradas(
            xml_path,
            parent_tag,
            target_tags,
            selected_context_tags,
        )
        if not sucesso:
            return False, dados

        self.load_extracted(xml_path, parent_tag, target_tags, selected_context_tags, dados)
        return True, ""

    def load_extracted(
        self,
        xml_path: str,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str],
        extracted_entries: Sequence[ExtractedEntry],
    ) -> None:
        """Install entries prepared outside the UI thread into this project."""
        selected_target_tags = list(target_tags)
        selected_context_tags = list(context_tags)

        prev_entries = self.entries
        self.entries = {}
        for extracted in extracted_entries:
            prev = prev_entries.get(extracted.xpath)
            self.entries[extracted.xpath] = TranslationEntry(
                xpath=extracted.xpath,
                original=extracted.original,
                translation=prev.translation if prev else "",
                status=prev.status if prev else "pending",
                source_tag=extracted.source_tag,
                container_xpath=extracted.container_xpath,
                context=dict(extracted.context),
                error_code=prev.error_code if prev else "",
            )

        self.xml_path = xml_path
        self.parent_tag = parent_tag
        self.target_tags = list(
            dict.fromkeys(tag.strip() for tag in selected_target_tags if tag.strip())
        )
        self.context_tags = list(
            dict.fromkeys(tag.strip() for tag in selected_context_tags if tag.strip())
        )
        self.target_tag = self.target_tags[0] if self.target_tags else ""

    # ------------------------------------------------------------------
    # Entry access
    # ------------------------------------------------------------------

    def get_entry(self, xpath: str) -> TranslationEntry | None:
        return self.entries.get(xpath)

    def set_translation(self, xpath: str, text: str, status: str = "translated") -> None:
        entry = self.entries.get(xpath)
        if entry:
            entry.set_translation(text, status)

    def confirm_translation(self, xpath: str, text: str | None = None) -> bool:
        entry = self.entries.get(xpath)
        if not entry or entry.status == EntryStatus.TRANSLATING:
            return False
        value = entry.translation if text is None else text
        if not value.strip():
            return False
        entry.set_translation(value, EntryStatus.CONFIRMED)
        return True

    def mark_translating(self, xpath: str) -> None:
        entry = self.entries.get(xpath)
        if entry:
            entry.status = EntryStatus.TRANSLATING
            entry.error_code = ""

    def mark_error(self, xpath: str, code: str = "unknown") -> None:
        entry = self.entries.get(xpath)
        if entry:
            entry.status = EntryStatus.ERROR
            entry.error_code = normalize_error(code)

    def recover_interrupted(self) -> None:
        for entry in self.entries.values():
            if entry.status == EntryStatus.TRANSLATING:
                entry.status = EntryStatus.TRANSLATED if entry.translation.strip() else EntryStatus.PENDING

    def state_counts(self) -> dict[str, int]:
        counts = {state.value: 0 for state in EntryStatus}
        for entry in self.entries.values():
            counts[normalize_status(entry.status).value] += 1
        return counts

    def duplicate_count(self, xpath: str, pending_only: bool = True) -> int:
        """Count entries whose complete original text matches the selected entry."""
        source = self.entries.get(xpath)
        if not source:
            return 0
        return sum(
            1
            for entry in self.entries.values()
            if entry.original == source.original and (not pending_only or entry.needs_translation)
        )

    def duplicate_update_count(self, xpath: str, translation: str) -> int:
        """Count unconfirmed duplicate rows whose translation differs from the draft."""
        source = self.entries.get(xpath)
        if not source or not translation.strip():
            return 0
        return sum(
            1
            for entry in self.entries.values()
            if entry.xpath != xpath
            and entry.original == source.original
            and entry.status not in (EntryStatus.CONFIRMED, EntryStatus.TRANSLATING)
            and entry.translation != translation
        )

    def apply_translation_to_duplicates(
        self, xpath: str, translation: str, pending_only: bool = True
    ) -> list[str]:
        """Apply a translation to exact full-text duplicates and return changed XPaths."""
        source = self.entries.get(xpath)
        if not source or not translation.strip():
            return []

        changed: list[str] = []
        for entry in self.entries.values():
            if entry.original != source.original:
                continue
            if entry.status == EntryStatus.TRANSLATING:
                continue
            if entry.status == EntryStatus.CONFIRMED and entry.xpath != xpath:
                continue
            if pending_only and not entry.needs_translation and entry.xpath != xpath:
                continue
            if entry.translation == translation and entry.status == EntryStatus.TRANSLATED:
                continue
            entry.set_translation(translation)
            changed.append(entry.xpath)
        return changed

    def get_pending_entries(self) -> list[TranslationEntry]:
        return [e for e in self.entries.values() if e.needs_translation]

    def reset_translations(self) -> int:
        """Reset every entry to pending/empty. Returns the number of entries reset."""
        count = 0
        for entry in self.entries.values():
            entry.translation = ""
            entry.status = "pending"
            entry.error_code = ""
            count += 1
        return count

    def get_translations_map(self) -> dict[str, str]:
        """Returns {xpath: translation} for entries that have a non-empty translation."""
        return {e.xpath: e.translation for e in self.entries.values() if e.translation.strip()}

    def stats(self) -> tuple[int, int]:
        """Returns (done_count, total_count)."""
        done = sum(1 for e in self.entries.values() if e.status in (EntryStatus.TRANSLATED, EntryStatus.CONFIRMED))
        return done, len(self.entries)

    # ------------------------------------------------------------------
    # Checkpoint (resume support)
    # ------------------------------------------------------------------

    @staticmethod
    def checkpoint_path(
        xml_path: str,
        target_lang: str = "",
        folder: str = "checkpoints",
        *,
        parent_tag: str = "",
        target_tags: Sequence[str] = (),
        context_tags: Sequence[str] = (),
    ) -> str:
        """Return a per-file checkpoint path inside the checkpoints/ folder.

        Calls without a tag selection intentionally retain the legacy filename.
        Current callers include a stable selection signature so distinct tag
        configurations for the same XML and language cannot share progress.
        """
        abs_path = os.path.abspath(xml_path)
        target = re.sub(r"[^a-z0-9_-]+", "_", (target_lang or "").lower()).strip("_")
        h = hashlib.md5(f"{abs_path}|{target}".encode()).hexdigest()[:8]
        stem = os.path.splitext(os.path.basename(abs_path))[0]
        os.makedirs(folder, exist_ok=True)
        target_suffix = f"_{target}" if target else ""

        normalized_targets = sorted({tag.strip() for tag in target_tags if tag.strip()})
        normalized_contexts = sorted({tag.strip() for tag in context_tags if tag.strip()})
        selection_suffix = ""
        if parent_tag.strip() or normalized_targets or normalized_contexts:
            payload = json.dumps(
                {
                    "parent_tag": parent_tag.strip(),
                    "target_tags": normalized_targets,
                    "context_tags": normalized_contexts,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
            selection_suffix = f"_{signature}"

        return os.path.join(folder, f"{stem}{target_suffix}{selection_suffix}_{h}.json")

    def save_checkpoint(self, path: str) -> bool:
        """Persist current translations to a JSON checkpoint file."""
        try:
            data = {
                "version": 2,
                "entries": {
                    xpath: {
                        "translation": e.translation,
                        "status": normalize_status(e.status).value,
                        "error_code": normalize_error(e.error_code) if e.status == EntryStatus.ERROR else "",
                    }
                    for xpath, e in self.entries.items()
                },
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except OSError:
            return False

    def load_checkpoint(self, path: str) -> int:
        """
        Applies translations from a checkpoint file to entries.
        Returns the number of entries updated.
        """
        if not os.path.exists(path):
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0

        if not isinstance(data, dict):
            return 0
        versioned = "version" in data
        if versioned and data.get("version") != 2:
            return 0
        records = data.get("entries") if versioned else data
        if not isinstance(records, dict):
            return 0
        count = 0
        for xpath, record in records.items():
            if xpath not in self.entries:
                continue
            translation = record.get("translation") if versioned and isinstance(record, dict) else record
            status = record.get("status", "translated") if versioned and isinstance(record, dict) else "translated"
            if not isinstance(translation, str) or (not versioned and not translation):
                continue
            try:
                self.entries[xpath].set_translation(translation, status)
                if self.entries[xpath].status == EntryStatus.ERROR:
                    code = record.get("error_code") if isinstance(record, dict) else None
                    self.entries[xpath].error_code = normalize_error(code)
            except (ValueError, TypeError):
                continue
            count += bool(translation.strip())
        self.recover_interrupted()
        return count

    def load_checkpoint_with_fallback(self, primary_path: str, fallback_paths: Sequence[str]) -> int:
        """Load the current checkpoint, or the first existing legacy fallback.

        An existing primary always wins, even when it is empty or corrupted. This
        prevents silently mixing older progress into a current configuration.
        """
        if os.path.exists(primary_path):
            return self.load_checkpoint(primary_path)
        for fallback_path in fallback_paths:
            if fallback_path and os.path.exists(fallback_path):
                return self.load_checkpoint(fallback_path)
        return 0

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_xml(self, output_path: str) -> bool:
        """Write the translated XML to output_path."""
        if not self.xml_path:
            return False
        translations = self.get_translations_map()
        if not translations:
            return False
        return injetar_traducoes(self.xml_path, translations, output_path)

    def export_json(self, output_path: str) -> bool:
        """Write {xpath: original_text} to a JSON file for external translation."""
        try:
            data = {e.xpath: e.original for e in self.entries.values()}
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except OSError:
            return False

    def export_csv(self, output_path: str) -> bool:
        """Write xpath, original_text, translated_text rows to a CSV file."""
        try:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["xpath", "original_text", "translated_text"])
                for e in self.entries.values():
                    writer.writerow([e.xpath, e.original, e.translation])
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_json(self, path: str) -> int:
        """
        Apply translations from a JSON {xpath: text} file.
        Returns the number of entries updated.
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0

        count = 0
        for xpath, translation in data.items():
            if xpath in self.entries:
                self.entries[xpath].set_translation(translation)
                count += 1
        return count

    def import_csv(self, path: str) -> int:
        """
        Apply translations from a CSV file with columns xpath, translated_text.
        Returns the number of entries updated.
        """
        try:
            count = 0
            with open(path, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    xpath = row.get("xpath")
                    translation = row.get("translated_text")
                    if xpath and translation is not None and xpath in self.entries:
                        self.entries[xpath].set_translation(translation)
                        count += 1
            return count
        except OSError:
            return 0
