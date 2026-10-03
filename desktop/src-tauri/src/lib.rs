//! Desktop shell for STZ XML Translator.
//!
//! The Python engine (`python -m engine`) stays the brain. This shell starts
//! it headless, tells the web UI where it listens, and stops it on exit.

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, RunEvent};

/// The engine process this shell started, if it started one.
struct Backend(Mutex<Option<Child>>);

/// What the engine publishes in `runtime.json` (see `engine/__main__.py`).
#[derive(Deserialize)]
struct RuntimeFile {
    host: String,
    port: u16,
    token: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BridgeInfo {
    base_url: String,
    token: String,
}

fn runtime_path() -> Option<PathBuf> {
    let base = std::env::var_os("LOCALAPPDATA").or_else(|| std::env::var_os("APPDATA"))?;
    Some(PathBuf::from(base).join("STZ XML Translator").join("runtime.json"))
}

/// Where the running engine listens. The UI retries until this succeeds and
/// the engine answers.
#[tauri::command]
fn bridge_info() -> Result<BridgeInfo, String> {
    let path = runtime_path().ok_or("no per-user data directory")?;
    let text = std::fs::read_to_string(&path).map_err(|_| "engine not running yet".to_string())?;
    let rt: RuntimeFile = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    Ok(BridgeInfo {
        base_url: format!("http://{}:{}", rt.host, rt.port),
        token: rt.token,
    })
}

/// Used after the update installer is launched: the app must get out of its way.
#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

/// The command that runs the engine headless.
///
/// Debug builds use the repository's virtualenv (override with STZ_PYTHON);
/// release builds expect the frozen engine (`stz-xml-engine.exe`) next to this
/// executable.
fn backend_command() -> Command {
    let mut cmd = if cfg!(debug_assertions) {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
        let python = std::env::var_os("STZ_PYTHON")
            .map(PathBuf::from)
            .unwrap_or_else(|| repo.join(".venv").join("Scripts").join("python.exe"));
        let mut c = Command::new(python);
        c.args(["-m", "engine"]).current_dir(repo);
        c
    } else {
        let exe = std::env::current_exe().expect("current exe");
        Command::new(exe.with_file_name("stz-xml-engine.exe"))
    };
    // The engine exits on its own if this shell dies without stopping it.
    cmd.args(["--parent-pid", &std::process::id().to_string()]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn show_main(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
    }
}

fn stop_backend(app: &AppHandle) {
    if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

pub fn run() {
    tauri::Builder::default()
        // Must be registered first: a second launch just focuses this one.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Backend(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![bridge_info, quit])
        .setup(|app| {
            // A record left by a previous run would point the UI at a dead port
            // until the new engine publishes its own.
            if let Some(path) = runtime_path() {
                let _ = std::fs::remove_file(path);
            }
            match backend_command().spawn() {
                Ok(child) => *app.state::<Backend>().0.lock().unwrap() = Some(child),
                Err(e) => eprintln!("could not start the engine: {e}"),
            }
            show_main(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
