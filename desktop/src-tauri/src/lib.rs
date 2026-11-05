//! Desktop shell and supervisor for the local Python translation engine.
mod backend;
use backend::{CommandSpec, EngineStatus, Supervisor};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, RunEvent};

struct Backend(Arc<Mutex<Supervisor>>);
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BridgeInfo {
    base_url: String,
    token: String,
}

#[tauri::command]
fn bridge_info(app: AppHandle) -> Result<BridgeInfo, String> {
    let backend = app.state::<Backend>();
    let supervisor = backend
        .0
        .lock()
        .map_err(|_| "engine supervisor unavailable")?;
    let runtime = supervisor.read_runtime()?;
    Ok(BridgeInfo {
        base_url: format!("http://{}:{}", runtime.host, runtime.port),
        token: runtime.token,
    })
}
#[tauri::command]
fn engine_status(app: AppHandle) -> Result<EngineStatus, String> {
    app.state::<Backend>()
        .0
        .lock()
        .map(|s| s.status.clone())
        .map_err(|_| "engine supervisor unavailable".into())
}
#[tauri::command]
fn retry_engine(app: AppHandle) -> Result<(), String> {
    app.state::<Backend>()
        .0
        .lock()
        .map_err(|_| "engine supervisor unavailable")?
        .retry();
    Ok(())
}
#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

fn command_spec() -> CommandSpec {
    let parent = vec!["--parent-pid".into(), std::process::id().to_string()];
    if cfg!(debug_assertions) {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..");
        let python = std::env::var_os("STZ_PYTHON")
            .map(PathBuf::from)
            .unwrap_or_else(|| repo.join(".venv/Scripts/python.exe"));
        let mut args = vec!["-m".into(), "engine".into()];
        args.extend(parent);
        CommandSpec {
            program: python,
            args,
            directory: Some(repo),
        }
    } else {
        let program = std::env::current_exe()
            .expect("current exe")
            .with_file_name("stz-xml-engine.exe");
        CommandSpec {
            program,
            args: parent,
            directory: None,
        }
    }
}
fn show_main(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
    }
}
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main(app)
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            bridge_info,
            engine_status,
            retry_engine,
            quit
        ])
        .setup(|app| {
            let base = std::env::var_os("LOCALAPPDATA")
                .or_else(|| std::env::var_os("APPDATA"))
                .ok_or("no per-user data directory")?;
            // Separate debug/release shells cannot overwrite each other's bridge.
            let runtime = PathBuf::from(base)
                .join("STZ XML Translator")
                .join("logs")
                .join(format!("engine-{}.json", std::process::id()));
            let supervisor = Arc::new(Mutex::new(Supervisor::new(command_spec(), runtime)));
            app.manage(Backend(supervisor.clone()));
            std::thread::spawn(move || {
                loop {
                    {
                        let Ok(mut backend) = supervisor.lock() else {
                            break;
                        };
                        if backend.stopping {
                            break;
                        }
                        backend.tick(Instant::now());
                    }
                    std::thread::sleep(Duration::from_secs(1));
                }
            });
            show_main(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Ok(mut backend) = app.state::<Backend>().0.lock() {
                    backend.stop();
                }
            }
        });
}
