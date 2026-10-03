//! Own the engine's lifecycle, including bounded recovery and support logs.
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const MAX_STARTS: u32 = 4;
const STARTUP_GRACE: Duration = Duration::from_secs(30);
const STABLE_PERIOD: Duration = Duration::from_secs(60);

#[derive(Deserialize)]
pub struct RuntimeFile {
    pub host: String,
    pub port: u16,
    pub token: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineStatus {
    pub phase: String,
    pub reason: String,
    pub attempts: u32,
    pub generation: u64,
    pub log_path: String,
}

pub struct CommandSpec {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub directory: Option<PathBuf>,
}

pub struct Supervisor {
    pub status: EngineStatus,
    pub stopping: bool,
    child: Option<Child>,
    command: CommandSpec,
    pub runtime: PathBuf,
    log: PathBuf,
    status_file: PathBuf,
    next_start: Instant,
    started_at: Instant,
    healthy_since: Option<Instant>,
    failures: u32,
    starts: u32,
}

pub fn hidden(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
}

impl Supervisor {
    pub fn new(command: CommandSpec, runtime: PathBuf) -> Self {
        let log = runtime.with_extension("log");
        let status_file = runtime.with_extension("status.json");
        let now = Instant::now();
        Self {
            status: EngineStatus {
                phase: "starting".into(),
                reason: String::new(),
                attempts: 0,
                generation: 0,
                log_path: log.to_string_lossy().into_owned(),
            },
            stopping: false,
            child: None,
            command,
            runtime,
            log,
            status_file,
            next_start: now,
            started_at: now,
            healthy_since: None,
            failures: 0,
            starts: 0,
        }
    }

    fn record(&self, message: &str) {
        if let Some(parent) = self.log.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&self.log) {
            let time = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            let _ = writeln!(file, "[supervisor {time}] {message}");
        }
        // No token or user content: this record supports installed-app diagnostics.
        if let Ok(data) = serde_json::to_vec(&self.status) {
            let temp = self.status_file.with_extension("tmp");
            if fs::write(&temp, data).is_ok() {
                let _ = fs::rename(temp, &self.status_file);
            }
        }
    }

    fn output(&self) -> std::io::Result<File> {
        if let Some(parent) = self.log.parent() {
            fs::create_dir_all(parent)?;
        }
        if fs::metadata(&self.log).is_ok_and(|meta| meta.len() > 1_048_576) {
            let old = self.log.with_extension("previous.log");
            let _ = fs::remove_file(&old);
            fs::rename(&self.log, old)?;
        }
        OpenOptions::new().create(true).append(true).open(&self.log)
    }

    fn start(&mut self, now: Instant) {
        self.starts += 1;
        self.status.attempts = self.starts;
        self.status.phase = if self.status.generation == 0 {
            "starting"
        } else {
            "restarting"
        }
        .into();
        let _ = fs::remove_file(&self.runtime);
        let mut command = Command::new(&self.command.program);
        command
            .args(&self.command.args)
            .env("STZ_XML_RUNTIME_FILE", &self.runtime);
        if let Some(dir) = &self.command.directory {
            command.current_dir(dir);
        }
        command.stdin(Stdio::null());
        hidden(&mut command);
        // Real handles avoid Python's None stdout/stderr in console-free builds.
        let result = self.output().and_then(|out| {
            command.stdout(out.try_clone()?).stderr(out);
            command.spawn()
        });
        match result {
            Ok(child) => {
                self.status.generation += 1;
                self.record(&format!(
                    "Started engine pid={} attempt={}",
                    child.id(),
                    self.starts
                ));
                self.child = Some(child);
                self.started_at = now;
                self.healthy_since = None;
                self.failures = 0;
            }
            Err(error) => {
                self.status.reason = if error.kind() == std::io::ErrorKind::NotFound {
                    "missing"
                } else {
                    "start"
                }
                .into();
                self.record(&format!("Engine launch failed: {error}"));
                self.schedule(now);
            }
        }
    }

    fn schedule(&mut self, now: Instant) {
        self.healthy_since = None;
        let _ = fs::remove_file(&self.runtime);
        if self.starts >= MAX_STARTS {
            self.status.phase = "failed".into();
            self.record("Automatic recovery exhausted; waiting for manual retry");
        } else {
            self.status.phase = "restarting".into();
            self.next_start = now + Duration::from_secs(u64::from(self.starts) * 2);
            self.record("Automatic recovery scheduled");
        }
    }

    pub fn tick(&mut self, now: Instant) {
        if self.stopping || self.status.phase == "failed" {
            return;
        }
        if self.child.is_none() {
            if now >= self.next_start {
                self.start(now);
            }
            return;
        }
        match self.child.as_mut().unwrap().try_wait() {
            Ok(Some(code)) => {
                self.child = None;
                self.status.reason = "exit".into();
                self.record(&format!("Engine exited: {code}"));
                self.schedule(now);
                return;
            }
            Err(error) => {
                self.status.reason = "exit".into();
                self.record(&format!("Cannot inspect engine process: {error}"));
                self.stop_child();
                self.schedule(now);
                return;
            }
            Ok(None) => {}
        }
        if self.healthy() {
            self.failures = 0;
            if self.status.phase != "ready" {
                self.status.phase = "ready".into();
                self.status.reason.clear();
                self.healthy_since = Some(now);
                self.record("Engine ready");
            }
            if self
                .healthy_since
                .is_some_and(|since| now.duration_since(since) >= STABLE_PERIOD)
            {
                self.starts = 0; // Isolated failures later still get a recovery budget.
            }
        } else {
            self.failures += 1;
            if now.duration_since(self.started_at) >= STARTUP_GRACE && self.failures >= 3 {
                self.status.reason = "timeout".into();
                self.record("Engine health check timed out");
                self.stop_child();
                self.schedule(now);
            }
        }
    }

    fn healthy(&self) -> bool {
        let Ok(runtime) = self.read_runtime() else {
            return false;
        };
        let address = SocketAddr::from(([127, 0, 0, 1], runtime.port));
        let timeout = Some(Duration::from_millis(700));
        let Ok(mut stream) = TcpStream::connect_timeout(&address, timeout.unwrap()) else {
            return false;
        };
        let _ = stream.set_read_timeout(timeout);
        let _ = stream.set_write_timeout(timeout);
        if write!(stream, "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n", runtime.token).is_err() { return false; }
        let mut response = [0; 256];
        stream
            .read(&mut response)
            .is_ok_and(|n| response[..n].starts_with(b"HTTP/1.1 200 "))
    }

    pub fn read_runtime(&self) -> Result<RuntimeFile, String> {
        let data = fs::read_to_string(&self.runtime).map_err(|_| "engine not ready".to_string())?;
        let runtime: RuntimeFile =
            serde_json::from_str(&data).map_err(|_| "invalid engine runtime".to_string())?;
        if runtime.host != "127.0.0.1" {
            return Err("invalid engine host".into());
        }
        Ok(runtime)
    }

    fn stop_child(&mut self) {
        if let Some(mut child) = self.child.take() {
            // A Windows venv python.exe can be a redirector with its own child.
            #[cfg(windows)]
            if matches!(child.try_wait(), Ok(None)) {
                let mut kill = Command::new("taskkill.exe");
                kill.args(["/PID", &child.id().to_string(), "/T", "/F"])
                    .stdout(Stdio::null())
                    .stderr(Stdio::null());
                hidden(&mut kill);
                let _ = kill.status();
            }
            let _ = child.kill();
            let _ = child.wait();
        }
        let _ = fs::remove_file(&self.runtime);
    }

    pub fn retry(&mut self) {
        if self.status.phase != "failed" {
            return;
        }
        self.starts = 0;
        self.status.attempts = 0;
        self.status.phase = "starting".into();
        self.status.reason.clear();
        self.next_start = Instant::now();
        self.record("Manual recovery requested");
    }

    pub fn stop(&mut self) {
        self.stopping = true;
        self.stop_child();
        self.status.phase = "stopped".into();
        self.record("Desktop closed; engine stopped");
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        self.stop_child();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn supervisor(name: &str, program: PathBuf, args: Vec<String>) -> Supervisor {
        let runtime = std::env::temp_dir()
            .join(format!("stz-supervisor-test-{}-{name}", std::process::id()))
            .join("runtime.json");
        Supervisor::new(
            CommandSpec {
                program,
                args,
                directory: None,
            },
            runtime,
        )
    }
    #[test]
    fn missing_engine_has_bounded_recovery_and_manual_retry() {
        let mut engine = supervisor(
            "missing",
            PathBuf::from("Z:/stz-missing-engine.exe"),
            vec![],
        );
        let now = Instant::now();
        for i in 0..4 {
            engine.tick(now + Duration::from_secs(i * 10));
        }
        assert_eq!(engine.status.phase, "failed");
        assert_eq!(engine.status.reason, "missing");
        assert_eq!(engine.status.attempts, 4);
        engine.tick(now + Duration::from_secs(100));
        assert_eq!(engine.status.attempts, 4);
        engine.retry();
        engine.tick(now + Duration::from_secs(110));
        assert_eq!(engine.status.attempts, 1);
        assert!(
            fs::read_to_string(&engine.log)
                .unwrap()
                .contains("launch failed")
        );
        let dir = engine.runtime.parent().unwrap().to_path_buf();
        drop(engine);
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    #[cfg(windows)]
    fn crashed_process_is_restarted_and_exit_code_is_logged() {
        let mut engine = supervisor(
            "exit",
            PathBuf::from("cmd.exe"),
            vec!["/C".into(), "exit 7".into()],
        );
        let now = Instant::now();
        engine.tick(now);
        engine.child.as_mut().unwrap().wait().unwrap();
        engine.tick(now + Duration::from_secs(1));
        assert_eq!(engine.status.phase, "restarting");
        engine.tick(now + Duration::from_secs(10));
        assert_eq!(engine.status.generation, 2);
        assert!(
            fs::read_to_string(&engine.log)
                .unwrap()
                .contains("exit code: 7")
        );
        let dir = engine.runtime.parent().unwrap().to_path_buf();
        drop(engine);
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    #[cfg(windows)]
    fn hung_process_is_stopped_and_recovery_is_scheduled() {
        let mut engine = supervisor(
            "hung",
            PathBuf::from("cmd.exe"),
            vec!["/C".into(), "ping -n 90 127.0.0.1 >nul".into()],
        );
        let now = Instant::now();
        engine.tick(now);
        for i in 1..=3 {
            engine.tick(now + Duration::from_secs(30 + i));
        }
        assert!(engine.child.is_none());
        assert_eq!(engine.status.phase, "restarting");
        assert_eq!(engine.status.reason, "timeout");
        let dir = engine.runtime.parent().unwrap().to_path_buf();
        drop(engine);
        fs::remove_dir_all(dir).unwrap();
    }
}
