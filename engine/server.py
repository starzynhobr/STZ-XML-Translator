"""Local HTTP bridge between the web UI and ``Session``.

Bound to 127.0.0.1 only. Every ``/api`` call needs the per-launch bearer token
the shell reads from ``runtime.json``, so other local pages cannot drive it.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.extrator import Group
from engine.session import Session, SessionError

# The Tauri webview (release and dev) and the Vite dev server in a browser.
ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


class PathBody(BaseModel):
    path: str


class TagsBody(BaseModel):
    parent: str
    targets: list[str] = []
    contexts: list[str] = []


class GroupsBody(BaseModel):
    groups: list[TagsBody]


class TranslateBody(BaseModel):
    ids: list[str] | None = None


class EntryBody(BaseModel):
    id: str
    text: str | None = None


class BackupBody(BaseModel):
    path: str
    format: str = "json"


class Term(BaseModel):
    original: str
    translation: str


class GlossaryBody(BaseModel):
    terms: list[Term]


class PresetBody(TagsBody):
    label: str


class ApiKeyBody(BaseModel):
    provider: str
    key: str


class FeedbackBody(BaseModel):
    text: str


class ProjectBody(BaseModel):
    name: str = ""
    folder: str
    target: str = ""


class ProjectUpdateBody(BaseModel):
    name: str = ""
    folder: str | None = None


def create_app(session: Session, token: str) -> FastAPI:
    app = FastAPI(title="STZ XML Translator engine", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(SessionError)
    async def session_error(_request: Request, exc: SessionError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    def authorized(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, f"Bearer {token}"):
            raise SessionError("unauthorized", 401)

    auth = [Depends(authorized)]
    ok = {"ok": True}

    @app.get("/api/health")
    async def health() -> dict:
        return {"app": "stz-xml-translator"}

    @app.get("/api/state", dependencies=auth)
    def state() -> dict:
        return session.state()

    @app.get("/api/entries", dependencies=auth)
    def entries(since: int = 0) -> dict:
        return session.entries(since)

    # --- XML ---------------------------------------------------------------

    @app.post("/api/xml/open", dependencies=auth)
    def open_xml(body: PathBody) -> dict:
        return session.open_xml(body.path)

    @app.get("/api/xml/children", dependencies=auth)
    def children(parent: str) -> dict:
        return {"tags": session.child_tags(parent)}

    @app.post("/api/xml/preview", dependencies=auth)
    def preview(body: TagsBody) -> dict:
        return session.preview(body.parent, body.targets, body.contexts)

    @app.post("/api/xml/load", dependencies=auth)
    def load(body: TagsBody | GroupsBody) -> dict:
        if isinstance(body, GroupsBody):
            return session.load_groups([Group.of(g.parent, g.targets, g.contexts) for g in body.groups])
        return session.load(body.parent, body.targets, body.contexts)

    @app.get("/api/xml/analyze", dependencies=auth)
    def analyze() -> dict:
        return session.analyze()

    @app.post("/api/xml/preview-groups", dependencies=auth)
    def preview_groups(body: GroupsBody) -> dict:
        return session.preview_groups([Group.of(g.parent, g.targets, g.contexts) for g in body.groups])

    @app.post("/api/xml/close", dependencies=auth)
    def close_xml() -> dict:
        session.close_file()
        return ok

    # --- Projects ----------------------------------------------------------

    @app.get("/api/projects", dependencies=auth)
    def projects() -> dict:
        return {"projects": session.list_projects()}

    @app.post("/api/projects", dependencies=auth)
    def create_project(body: ProjectBody) -> dict:
        return session.create_project(body.name, body.folder, body.target)

    @app.post("/api/projects/detect", dependencies=auth)
    def detect_game(body: PathBody) -> dict:
        return session.detect_game(body.path)

    @app.post("/api/projects/close", dependencies=auth)
    def close_project() -> dict:
        session.close_project()
        return ok

    @app.get("/api/projects/{project_id}", dependencies=auth)
    def project(project_id: str) -> dict:
        return session.project_detail(project_id)

    @app.put("/api/projects/{project_id}", dependencies=auth)
    def update_project(project_id: str, body: ProjectUpdateBody) -> dict:
        return session.rename_project(project_id, body.name, body.folder)

    @app.delete("/api/projects/{project_id}", dependencies=auth)
    def delete_project(project_id: str) -> dict:
        session.delete_project(project_id)
        return ok

    @app.post("/api/projects/{project_id}/open", dependencies=auth)
    def open_project(project_id: str) -> dict:
        return session.open_project(project_id)

    @app.post("/api/xml/export", dependencies=auth)
    def export_xml(body: PathBody) -> dict:
        session.export_xml(body.path)
        return ok

    # --- Translation -------------------------------------------------------

    @app.post("/api/translate", dependencies=auth)
    def translate(body: TranslateBody) -> dict:
        session.translate(body.ids)
        return ok

    @app.post("/api/translate/cancel", dependencies=auth)
    def cancel() -> dict:
        session.cancel()
        return ok

    @app.post("/api/entries/translate", dependencies=auth)
    def translate_entry(body: EntryBody) -> dict:
        session.translate_entry(body.id)
        return ok

    @app.post("/api/entries/edit", dependencies=auth)
    def edit(body: EntryBody) -> dict:
        session.edit(body.id, body.text or "")
        return ok

    @app.get("/api/entries/history", dependencies=auth)
    def history(id: str) -> dict:
        return {"versions": session.history(id)}

    @app.post("/api/entries/confirm", dependencies=auth)
    def confirm(body: EntryBody) -> dict:
        session.confirm(body.id, body.text)
        return ok

    # --- Backup, glossary, presets ----------------------------------------

    @app.post("/api/backup/export", dependencies=auth)
    def export_backup(body: BackupBody) -> dict:
        session.export_backup(body.path, body.format)
        return ok

    @app.post("/api/backup/import", dependencies=auth)
    def import_backup(body: PathBody) -> dict:
        return {"count": session.import_backup(body.path)}

    @app.get("/api/glossary", dependencies=auth)
    def glossary() -> dict:
        return {"terms": session.glossary()}

    @app.put("/api/glossary", dependencies=auth)
    def save_glossary(body: GlossaryBody) -> dict:
        return {"terms": session.save_glossary([term.model_dump() for term in body.terms])}

    @app.post("/api/glossary/export", dependencies=auth)
    def export_glossary(body: PathBody) -> dict:
        session.export_glossary(body.path)
        return ok

    @app.post("/api/glossary/import", dependencies=auth)
    def import_glossary(body: PathBody) -> dict:
        return {"terms": session.import_glossary(body.path)}

    @app.get("/api/presets", dependencies=auth)
    def presets() -> dict:
        return {"presets": session.presets()}

    @app.post("/api/presets", dependencies=auth)
    def save_preset(body: PresetBody) -> dict:
        return {"presets": session.save_preset(body.label, body.parent, body.targets, body.contexts)}

    @app.delete("/api/presets/{preset_id}", dependencies=auth)
    def delete_preset(preset_id: int) -> dict:
        return {"presets": session.delete_preset(preset_id)}

    @app.post("/api/presets/export", dependencies=auth)
    def export_presets(body: PathBody) -> dict:
        session.export_presets(body.path)
        return ok

    @app.post("/api/presets/import", dependencies=auth)
    def import_presets(body: PathBody) -> dict:
        return session.import_presets(body.path)

    # --- Settings, updates, feedback --------------------------------------

    @app.put("/api/settings", dependencies=auth)
    def update_settings(changes: dict) -> dict:
        return session.update_settings(changes)

    @app.put("/api/settings/api-key", dependencies=auth)
    def set_api_key(body: ApiKeyBody) -> dict:
        return session.set_api_key(body.provider, body.key)

    @app.post("/api/update/check", dependencies=auth)
    def check_updates() -> dict:
        session.check_updates()
        return ok

    @app.post("/api/update/download", dependencies=auth)
    def download_update() -> dict:
        session.download_update()
        return ok

    @app.post("/api/update/install", dependencies=auth)
    def install_update() -> dict:
        session.install_update()
        return ok

    @app.post("/api/update/skip", dependencies=auth)
    def skip_update() -> dict:
        session.skip_update()
        return ok

    @app.post("/api/feedback", dependencies=auth)
    def feedback(body: FeedbackBody) -> dict:
        session.send_feedback(body.text)
        return ok

    return app
