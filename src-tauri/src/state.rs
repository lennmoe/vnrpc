use std::path::PathBuf;
use std::sync::mpsc::Sender;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter};

use crate::config::Config;
use crate::discord::Activity;
use crate::mascot;
use crate::vndb::{VnResult, Vndb};

#[derive(Debug, Clone, Default, Serialize)]
pub struct Cover {
    pub source: String,
    pub local_path: Option<String>,
    pub discord_image: String,
    pub nsfw: bool,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Snapshot {
    pub detected: bool,
    pub key: String,
    pub exe: String,
    pub engine_name: String,
    pub raw_title: String,
    pub game_name: String,
    pub section_type: String,
    pub section_label: String,
    pub cover: Cover,
    pub vn: Option<VnResult>,
    pub privacy: String,
    pub playtime_seconds: i64,
    pub session_start: i64,
    pub idle: bool,
    pub paused: bool,
    pub activity: Option<Activity>,

    #[serde(skip)]
    pub hwnd: isize,
    #[serde(skip)]
    pub pid: u32,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Status {
    pub discord_ok: bool,
    pub discord_msg: String,
    pub vndb_msg: String,
    pub vndb_ok: bool,
}

pub enum Cmd {
    Reload,
    Pause(bool),
    SetPlaytime(String, i64),
    Quit,
}

pub struct Shared {
    pub app: AppHandle,
    pub data_dir: PathBuf,
    pub config: Mutex<Config>,
    pub vndb: Vndb,
    snapshot: Mutex<Snapshot>,
    status: Mutex<Status>,
    commands: Mutex<Sender<Cmd>>,
}

impl Shared {
    pub fn new(app: AppHandle, data_dir: PathBuf, config: Config, commands: Sender<Cmd>) -> Shared {
        Shared {
            vndb: Vndb::new(&data_dir),
            app,
            data_dir,
            config: Mutex::new(config),
            snapshot: Mutex::new(Snapshot::default()),
            status: Mutex::new(Status::default()),
            commands: Mutex::new(commands),
        }
    }

    pub fn send(&self, cmd: Cmd) {
        let _ = self.commands.lock().unwrap().send(cmd);
    }

    pub fn emit<P: Serialize + Clone>(&self, event: &str, payload: P) {
        let _ = self.app.emit(event, payload);
    }

    pub fn snapshot(&self) -> Snapshot {
        self.snapshot.lock().unwrap().clone()
    }

    pub fn publish_snapshot(&self, snap: Snapshot) {
        let old = std::mem::replace(&mut *self.snapshot.lock().unwrap(), snap.clone());
        self.emit("snapshot", &snap);
        mascot::react(&self.app, &old, &snap);
    }

    pub fn status(&self) -> Status {
        self.status.lock().unwrap().clone()
    }

    pub fn update_status(&self, change: impl FnOnce(&mut Status)) {
        let status = {
            let mut status = self.status.lock().unwrap();
            change(&mut status);
            status.clone()
        };
        self.emit("status", status);
    }

    pub fn vndb_message(&self, ok: bool, message: impl Into<String>) {
        let message = message.into();
        self.update_status(|st| {
            st.vndb_ok = ok;
            st.vndb_msg = message;
        });
    }
}
