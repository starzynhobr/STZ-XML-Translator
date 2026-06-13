from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Literal

from core.extrator import extrair_textos
from core.injetor import injetar_traducoes


@dataclass
class TranslationEntry:
    xpath: str
    original: str
    translation: str = ""
    status: Literal["pending", "translating", "done"] = "pending"


class TranslationProject:
    """Encapsulates all state and I/O for a single XML translation session."""

    def __init__(self) -> None:
        self.xml_path: str = ""
        self.parent_tag: str = ""
        self.target_tag: str = ""
        self.entries: dict[str, TranslationEntry] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, xml_path: str, parent_tag: str, target_tag: str) -> tuple[bool, str]:
        """
        Extract text from the XML and populate self.entries.
        Returns (True, "") on success or (False, error_message) on failure.
        Preserves existing translations for entries that are re-loaded.
        """
        sucesso, dados = extrair_textos(xml_path, parent_tag, target_tag)
        if not sucesso:
            return False, dados

        prev_entries = self.entries
        self.entries = {}
        for xpath, original in dados.items():
            prev = prev_entries.get(xpath)
            self.entries[xpath] = TranslationEntry(
                xpath=xpath,
                original=original,
                translation=prev.translation if prev else "",
                status=prev.status if prev else "pending",
            )

        self.xml_path = xml_path
        self.parent_tag = parent_tag
        self.target_tag = target_tag
        return True, ""

    # ------------------------------------------------------------------
    # Entry access
    # ------------------------------------------------------------------

    def get_entry(self, xpath: str) -> TranslationEntry | None:
        return self.entries.get(xpath)

    def set_translation(self, xpath: str, text: str, status: Literal["pending", "translating", "done"] = "done") -> None:
        entry = self.entries.get(xpath)
        if entry:
            entry.translation = text
            entry.status = status

    def get_pending_entries(self) -> list[TranslationEntry]:
        return [e for e in self.entries.values() if e.status != "done"]

    def reset_translations(self) -> int:
        """Reset every entry to pending/empty. Returns the number of entries reset."""
        count = 0
        for entry in self.entries.values():
            entry.translation = ""
            entry.status = "pending"
            count += 1
        return count

    def get_translations_map(self) -> dict[str, str]:
        """Returns {xpath: translation} for entries that have a non-empty translation."""
        return {e.xpath: e.translation for e in self.entries.values() if e.translation.strip()}

    def stats(self) -> tuple[int, int]:
        """Returns (done_count, total_count)."""
        done = sum(1 for e in self.entries.values() if e.status == "done")
        return done, len(self.entries)

    # ------------------------------------------------------------------
    # Checkpoint (resume support)
    # ------------------------------------------------------------------

    @staticmethod
    def checkpoint_path(xml_path: str, target_lang: str = "") -> str:
        """Return a per-file checkpoint path inside the checkpoints/ folder.

        Format: checkpoints/<stem>_<target>_<8-char hash>.json
        The hash is derived from the absolute XML path and the optional target
        language, so the same file can keep separate resume data per target.
        """
        abs_path = os.path.abspath(xml_path)
        target = re.sub(r"[^a-z0-9_-]+", "_", (target_lang or "").lower()).strip("_")
        h = hashlib.md5(f"{abs_path}|{target}".encode()).hexdigest()[:8]
        stem = os.path.splitext(os.path.basename(abs_path))[0]
        folder = "checkpoints"
        os.makedirs(folder, exist_ok=True)
        suffix = f"_{target}" if target else ""
        return os.path.join(folder, f"{stem}{suffix}_{h}.json")

    def save_checkpoint(self, path: str) -> bool:
        """Persist current translations to a JSON checkpoint file."""
        try:
            data = {xpath: e.translation for xpath, e in self.entries.items() if e.translation}
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

        count = 0
        for xpath, translation in data.items():
            if xpath in self.entries and translation:
                self.entries[xpath].translation = translation
                self.entries[xpath].status = "done"
                count += 1
        return count

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
                self.entries[xpath].translation = translation
                self.entries[xpath].status = "done"
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
                        self.entries[xpath].translation = translation
                        self.entries[xpath].status = "done"
                        count += 1
            return count
        except OSError:
            return 0
