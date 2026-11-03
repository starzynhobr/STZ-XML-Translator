"""MCP server: lets a coding agent (Claude Code, Codex, Cursor...) drive the translator.

Run it over stdio from the repository root::

    python -m engine.mcp_server                # data next to the repository (development)
    python -m engine.mcp_server --app-data     # the installed app's projects and translations
    python -m engine.mcp_server --data-dir DIR # any other data folder

It wraps the same ``Session`` the desktop app's engine uses, in its own
process: projects, the SQLite translations and the glossary are shared through
the data folder, while the open file is per process. Translations an agent
writes are recorded in the history with the source "agent".
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

INSTRUCTIONS = """\
Translate game XML files with STZ XML Translator.
Typical flow: list_projects (or create_project with the game folder) -> open_project ->
load_file (fields are suggested automatically; IDs, numbers and paths are never offered) ->
list_entries status="pending" -> set_translations in batches -> export_xml or keep going.
Keep markup such as <b>...</b>, {PLACEHOLDERS} and line breaks exactly as in the original.
Use the context of each entry (internal names, speaker) and the glossary for consistent terms.
Translations you write are saved immediately and are marked "to review" unless confirm=true.
"""

STATUSES = {
    "pending": ("pending", "translating", "error"),
    "translated": ("translated",),
    "confirmed": ("confirmed",),
    "error": ("error",),
    "all": (),
}


class TranslationItem(BaseModel):
    id: str = Field(description="Entry id as returned by list_entries")
    text: str = Field(description="The translated text")


class GroupItem(BaseModel):
    parent: str = Field(description="Repeating record tag, e.g. 'villain'")
    targets: list[str] = Field(description="Child fields to translate")
    contexts: list[str] = Field(default_factory=list, description="Child fields shown as context only")


class GlossaryTerm(BaseModel):
    original: str
    translation: str


def build_server(session: Any) -> Any:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    from core.extrator import Group
    from engine.session import SessionError

    server = MCPServer(name="stz-xml-translator", instructions=INSTRUCTIONS)

    def guard(call):
        try:
            return call()
        except SessionError as exc:
            # Stable machine code; the agent can react (e.g. "no_file" -> load_file first).
            raise ToolError(f"error: {exc.code}") from None

    def entry_json(entry: dict) -> dict:
        return {
            "id": entry["id"],
            "original": entry["original"],
            "translation": entry["translation"],
            "status": entry["status"],
            "field": f"{entry['group']} > {entry['sourceTag']}" if entry.get("group") else entry["sourceTag"],
            "context": entry["context"],
        }

    @server.tool()
    def status() -> dict:
        """Current project, open file, target language and translation counts."""
        state = session.state()
        return {
            "project": state["project"],
            "file": state["file"],
            "loaded": state["loaded"],
            "targetLanguage": state["settings"]["target"],
            "provider": state["settings"]["provider"],
            "total": state["total"],
            "counts": state["counts"],
            "translating": state["translating"],
        }

    @server.tool()
    def list_projects() -> list[dict]:
        """Saved translation projects with their game folder, language and progress."""
        return guard(session.list_projects)

    @server.tool()
    def create_project(game_folder: str, name: str = "", target_language: str = "") -> dict:
        """Create a project from a game folder (any level: install root, data folder or the XML folder).

        target_language is a locale such as "pt_BR"; empty keeps the current one.
        """
        return guard(lambda: session.create_project(name, game_folder, target_language))

    @server.tool()
    def open_project(project_id: str) -> dict:
        """Open a project: switches to its language and lists its XML files with progress."""
        return guard(lambda: session.open_project(project_id))

    @server.tool()
    def analyze_file(path: str) -> dict:
        """Open an XML file and suggest what to translate: record tags with their fields' kinds and roles."""
        def run() -> dict:
            session.open_xml(path)
            result = session.analyze()
            result["tags"] = [tag for tag in result["tags"] if tag["useful"] or tag["selected"]]
            return result
        return guard(run)

    @server.tool()
    def load_file(path: str, groups: list[GroupItem] | None = None) -> dict:
        """Load an XML file for translation. Without groups, the suggested tags and fields are used.

        Restores any saved progress for the file in the current language.
        """
        def run() -> dict:
            session.open_xml(path)
            if groups:
                chosen = [Group.of(g.parent, g.targets, g.contexts) for g in groups]
            else:
                tags = session.analyze()["tags"]
                chosen = [
                    Group.of(
                        tag["tag"],
                        [f["tag"] for f in tag["fields"] if f["role"] == "translate"],
                        [f["tag"] for f in tag["fields"] if f["role"] == "context"],
                    )
                    for tag in tags
                    if tag["selected"]
                ]
            loaded = session.load_groups(chosen)
            return {**loaded, "groups": [g.to_json() for g in chosen]}
        return guard(run)

    @server.tool()
    def list_entries(
        status: Literal["pending", "translated", "confirmed", "error", "all"] = "pending",
        search: str = "",
        field: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """Entries of the loaded file, filtered and paged.

        status "translated" means translated but not reviewed. field filters by "tag > field".
        """
        def run() -> dict:
            session._require_project()
            wanted = STATUSES[status]
            needle = search.strip().lower()
            items = []
            for entry in session.entries(0)["entries"]:
                if wanted and entry["status"] not in wanted:
                    continue
                shaped = entry_json(entry)
                if field and shaped["field"] != field:
                    continue
                if needle and needle not in (entry["original"] + "\n" + entry["translation"]).lower():
                    continue
                items.append(shaped)
            size = max(1, min(limit, 500))
            return {"total": len(items), "offset": offset, "entries": items[offset : offset + size]}
        return guard(run)

    @server.tool()
    def set_translations(translations: list[TranslationItem], confirm: bool = False) -> dict:
        """Write translations for entries of the loaded file (saved at once, recorded as "agent").

        With confirm=true they are also marked as reviewed.
        """
        def run() -> dict:
            done, failed = 0, []
            for item in translations:
                try:
                    session.edit(item.id, item.text, source="agent")
                    if confirm:
                        session.confirm(item.id, item.text)
                    done += 1
                except SessionError as exc:
                    failed.append({"id": item.id, "error": exc.code})
            return {"saved": done, "failed": failed}
        return guard(run)

    @server.tool()
    def confirm_entries(ids: list[str]) -> dict:
        """Mark translated entries as reviewed."""
        def run() -> dict:
            failed = []
            for entry_id in ids:
                try:
                    session.confirm(entry_id)
                except SessionError as exc:
                    failed.append({"id": entry_id, "error": exc.code})
            return {"confirmed": len(ids) - len(failed), "failed": failed}
        return guard(run)

    @server.tool()
    def translate_with_provider(ids: list[str] | None = None, wait_seconds: int = 600) -> dict:
        """Translate pending entries (or the given ids) with the app's configured provider (Gemini, Ollama...).

        Waits until it finishes or wait_seconds pass, then returns the counts.
        """
        def run() -> dict:
            session.translate(ids)
            deadline = time.time() + max(0, wait_seconds)
            while time.time() < deadline and session.state()["translating"]:
                time.sleep(1)
            state = session.state()
            return {"finished": not state["translating"], "counts": state["counts"]}
        return guard(run)

    @server.tool()
    def search_project(query: str) -> list[dict]:
        """Find a text (original or translation) in every file of the open project that was loaded before."""
        return guard(lambda: session.search_project(query))

    @server.tool()
    def entry_history(id: str) -> list[dict]:
        """Earlier versions of an entry, newest first, with where each came from."""
        return guard(lambda: session.history(id))

    @server.tool()
    def get_glossary() -> list[dict]:
        """Fixed term translations for the current target language."""
        return guard(session.glossary)

    @server.tool()
    def add_glossary_terms(terms: list[GlossaryTerm]) -> list[dict]:
        """Add or update glossary terms (by original) for the current target language."""
        def run() -> list[dict]:
            merged = {t["original"]: t for t in session.glossary()}
            for term in terms:
                merged[term.original] = {"original": term.original, "translation": term.translation}
            return session.save_glossary(list(merged.values()))
        return guard(run)

    @server.tool()
    def import_translation(clean_folder: str, apply: bool = False, wait_seconds: int = 300) -> dict:
        """Import a translation made by editing the game's XMLs by hand (open project only).

        clean_folder is an untranslated copy of the game. Every text that differs in the
        project's game folder becomes a translation "to review". With apply=false this only
        returns the summary; call again with apply=true to save it and keep the originals.
        """
        def run() -> dict:
            state = session.import_state()
            if not (apply and state.get("status") == "ready"):
                session.start_import(clean_folder)
                deadline = time.time() + max(0, wait_seconds)
                while time.time() < deadline and session.import_state()["status"] == "running":
                    time.sleep(0.2)
                state = session.import_state()
            if state["status"] != "ready":
                return state
            if apply:
                return session.apply_import()
            return {key: state[key] for key in ("found", "texts", "missing", "files")}
        return guard(run)

    def wait_job(wait_seconds: int) -> dict:
        deadline = time.time() + max(0, wait_seconds)
        while time.time() < deadline and session.job_state()["status"] == "running":
            time.sleep(0.3)
        state = session.job_state()
        if state["status"] == "error":
            raise ToolError(f"error: {state.get('error') or 'unknown'}")
        return state

    @server.tool()
    def translate_project(wait_seconds: int = 3600) -> dict:
        """Translate every pending text of every file of the open project with the app's provider.

        Files never opened get the suggested fields. Stops on a spent quota or a bad key;
        call again later to resume where it stopped.
        """
        def run() -> dict:
            session.translate_project()
            return wait_job(wait_seconds)
        return guard(run)

    @server.tool()
    def apply_to_game(launch: bool = False, confirmed_only: bool = False) -> dict:
        """Write the translated files into the game folder; the replaced files are kept for restore_game."""
        def run() -> dict:
            session.apply_to_game(confirmed_only, launch)
            return wait_job(600)
        return guard(run)

    @server.tool()
    def restore_game() -> dict:
        """Put the game's original files back."""
        def run() -> dict:
            session.restore_game()
            return wait_job(600)
        return guard(run)

    @server.tool()
    def update_to_new_build(game_folder: str, apply: bool = False) -> dict:
        """Compare a new build of the game with the project; with apply=true, move the project to it.

        Unchanged texts keep their translation; changed or moved ones keep it as "to review".
        """
        def run() -> dict:
            if apply and session.job_state().get("kind") == "update" and session.job_state()["status"] == "done":
                return session.apply_update()
            session.start_update(game_folder)
            state = wait_job(900)
            return session.apply_update() if apply else state.get("result", {})
        return guard(run)

    @server.tool()
    def export_package(output_path: str) -> dict:
        """Write a .stzpack with this language's translations and glossary for another translator."""
        return guard(lambda: session.export_package(output_path))

    @server.tool()
    def import_package(package_path: str) -> dict:
        """Import a .stzpack into the open project; texts already translated here are never overwritten."""
        return guard(lambda: session.import_package(package_path))

    @server.tool()
    def export_xml(output_path: str) -> dict:
        """Write the loaded file with its translations to output_path; structure and other text stay intact."""
        def run() -> dict:
            session.export_xml(output_path)
            return {"path": output_path}
        return guard(run)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="STZ XML Translator MCP server (stdio)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--data-dir", help="Folder with config, projects and translations.db")
    where.add_argument("--app-data", action="store_true", help="Use the installed app's data folder")
    args = parser.parse_args(argv)

    from core.app_controller import APP_DATA_DIR_NAME

    if args.data_dir:
        os.environ["STZ_XML_TRANSLATOR_DATA_DIR"] = os.path.abspath(args.data_dir)
    elif args.app_data:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        os.environ["STZ_XML_TRANSLATOR_DATA_DIR"] = os.path.join(base, APP_DATA_DIR_NAME)

    # stdout carries the protocol: nothing else may print there.
    sys.stdout.reconfigure(encoding="utf-8")
    from engine.session import Session

    build_server(Session()).run("stdio")


if __name__ == "__main__":
    main()
