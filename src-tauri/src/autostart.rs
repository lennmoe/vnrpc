use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE};
use winreg::RegKey;

const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const VALUE_NAME: &str = "VisualNovelRPC";

pub fn is_enabled() -> bool {
    RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey_with_flags(RUN_KEY, KEY_READ)
        .and_then(|key| key.get_value::<String, _>(VALUE_NAME))
        .is_ok()
}

pub fn set_enabled(enabled: bool) -> Result<(), String> {
    let key = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey_with_flags(RUN_KEY, KEY_SET_VALUE)
        .map_err(|e| e.to_string())?;

    if enabled {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let command = format!("\"{}\" --minimized", exe.display());
        return key
            .set_value(VALUE_NAME, &command)
            .map_err(|e| e.to_string());
    }

    match key.delete_value(VALUE_NAME) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(e.to_string()),
        _ => Ok(()),
    }
}
