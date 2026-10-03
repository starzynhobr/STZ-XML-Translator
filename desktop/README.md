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

## Installed app and recovery

`build_nuitka.bat` builds both the standalone Python bundle and the Tauri shell,
then packages them with Inno Setup. The installed shortcut opens
`stz-xml-translator.exe`; its engine is `STZXMLTranslator.exe --engine` in the
same directory. Python and the repository are not needed on the target machine.
The Qt UI remains available by launching `STZXMLTranslator.exe` directly.

The shell monitors process exits and `/api/health`. It allows 30 seconds for
startup and three automatic restarts, then shows a diagnostic path and a manual
retry button. A minute of healthy operation resets the restart budget.
Logs and token-free status records are under
`%LOCALAPPDATA%\STZ XML Translator\logs`. Each shell has its own runtime record.
After a restart, reopen the XML and select its fields to restore its checkpoint;
translation is not resumed automatically.

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
.venv\Scripts\python.exe -m pytest      # core, bridge, and the engine process end to end
npm run build                           # type-check and bundle
npm run test:e2e                        # the whole flow in Edge, against the real engine
```

The end-to-end tests start their own engine with an isolated data directory and
a fake Ollama, on their own ports, so they can run while `tauri dev` is open.
Edge is used because it is the engine behind the WebView2 the shell embeds; no
browser download is needed.

## Not done yet

The release build expects a frozen engine named `stz-xml-engine.exe` next to
the shell. Freezing it (Nuitka), the installer and the release workflow still
build the Qt app.
