# STZ XML Translator — desktop shell

React + Tailwind UI in a Tauri window. The Python `core/` stays the engine: the
shell starts `python -m engine`, which serves a local HTTP bridge on
`127.0.0.1` and publishes its port and a session token in
`%LOCALAPPDATA%\STZ XML Translator\runtime.json`.

```
desktop/src        React UI (screens, bridge, i18n)
desktop/src-tauri  Tauri shell: starts and stops the engine
engine/            HTTP bridge and Qt-free session over core/
```

## Run

From the repository root, with the virtualenv set up (`uv pip install -e ".[dev]"`):

```powershell
cd desktop
npm install
npm run tauri dev
```

The debug shell runs the engine from `.venv` (override with `STZ_PYTHON`).

### UI in a plain browser

```powershell
$env:STZ_XML_BRIDGE_PORT = '8791'; $env:STZ_XML_BRIDGE_TOKEN = 'dev-token'
.venv\Scripts\python.exe -m engine          # terminal 1, repository root

$env:VITE_BRIDGE_URL = 'http://127.0.0.1:8791'; $env:VITE_BRIDGE_TOKEN = 'dev-token'
npm run dev                                 # terminal 2, desktop/
```

Native file dialogs only exist inside Tauri; in a browser the app asks for a
typed path instead.

## Test

```powershell
.venv\Scripts\python.exe -m pytest tests\test_engine.py   # engine and bridge
npm run build                                              # type-check and bundle
```

## Not done yet

The release build expects a frozen engine named `stz-xml-engine.exe` next to
the shell. Freezing it (Nuitka), the installer and the release workflow still
build the Qt app.
