use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::{Map, Value};

use crate::config::Config;
use crate::shell;

pub const NORMAL: &str = "";
pub const LOCALE_EMULATOR: &str = "le";
pub const NTLEA: &str = "ntlea";

pub fn tool_setting(launcher: &str) -> &'static str {
    match launcher {
        LOCALE_EMULATOR => "locale_emulator_path",
        NTLEA => "ntlea_path",
        _ => "",
    }
}

pub fn tool_path(cfg: &Config, launcher: &str) -> Option<PathBuf> {
    let path = cfg.str(tool_setting(launcher));
    let path = PathBuf::from(path.trim());
    path.is_file().then_some(path)
}

#[derive(Debug, Serialize)]
#[serde(tag = "kind", content = "detail")]
pub enum LaunchError {
    GameMissing,
    ToolMissing(String),
    Failed(String),
}

pub fn launch(cfg: &Config, entry: &Map<String, Value>) -> Result<(), LaunchError> {
    let exe = entry.get("path").and_then(Value::as_str).unwrap_or("");
    let exe = Path::new(exe);
    if exe.as_os_str().is_empty() || !exe.is_file() {
        return Err(LaunchError::GameMissing);
    }
    let folder = exe.parent().unwrap_or(Path::new("."));

    let launcher = entry
        .get("launcher")
        .and_then(Value::as_str)
        .unwrap_or(NORMAL);
    if launcher != LOCALE_EMULATOR && launcher != NTLEA {
        return shell::start_program(exe, "", folder).map_err(LaunchError::Failed);
    }

    let Some(tool) = tool_path(cfg, launcher) else {
        return Err(LaunchError::ToolMissing(launcher.to_string()));
    };

    let params = if launcher == LOCALE_EMULATOR {
        format!("\"{}\"", exe.display())
    } else {
        format!("\"{}\" C932 L1041", exe.display())
    };
    shell::start_program(&tool, &params, folder).map_err(LaunchError::Failed)
}
