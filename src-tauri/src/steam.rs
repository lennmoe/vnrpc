use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use winreg::enums::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
use winreg::RegKey;

struct SteamApp {
    name: String,
    install_dir: PathBuf,
}

fn steam_path() -> Option<PathBuf> {
    [
        (HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ]
    .into_iter()
    .find_map(|(hive, sub)| {
        let value: String = RegKey::predef(hive)
            .open_subkey(sub)
            .ok()?
            .get_value("SteamPath")
            .ok()?;
        let path = PathBuf::from(value);
        path.is_dir().then_some(path)
    })
}

fn vdf_values<'a>(text: &'a str, key: &str) -> Vec<&'a str> {
    let needle = format!("\"{}\"", key.to_lowercase());
    text.lines()
        .filter_map(|line| {
            let line = line.trim();
            if !line.to_lowercase().starts_with(&needle) {
                return None;
            }
            let rest = line[needle.len()..].trim();
            rest.strip_prefix('"')?.strip_suffix('"')
        })
        .collect()
}

fn installed_apps() -> &'static Vec<SteamApp> {
    static APPS: OnceLock<Vec<SteamApp>> = OnceLock::new();
    APPS.get_or_init(|| {
        let Some(base) = steam_path() else {
            return vec![];
        };
        let mut libs = vec![base.clone()];
        if let Ok(text) = std::fs::read_to_string(base.join("steamapps").join("libraryfolders.vdf"))
        {
            libs.extend(
                vdf_values(&text, "path")
                    .into_iter()
                    .map(|p| PathBuf::from(p.replace("\\\\", "\\")))
                    .filter(|p| p.is_dir()),
            );
        }
        let mut apps = vec![];
        for lib in libs {
            let dir = lib.join("steamapps");
            for entry in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if !(name.starts_with("appmanifest_") && name.ends_with(".acf")) {
                    continue;
                }
                let Ok(text) = std::fs::read_to_string(entry.path()) else {
                    continue;
                };
                let (Some(app_name), Some(install)) = (
                    vdf_values(&text, "name").first().copied(),
                    vdf_values(&text, "installdir").first().copied(),
                ) else {
                    continue;
                };
                apps.push(SteamApp {
                    name: app_name.to_string(),
                    install_dir: dir.join("common").join(install),
                });
            }
        }
        apps
    })
}

pub fn name_for_exe(exe_path: &str) -> Option<String> {
    if exe_path.is_empty() {
        return None;
    }
    let exe = Path::new(exe_path).to_string_lossy().to_lowercase();
    installed_apps()
        .iter()
        .find(|app| {
            let dir = app.install_dir.to_string_lossy().to_lowercase();
            exe.starts_with(&format!("{}\\", dir.trim_end_matches('\\')))
        })
        .map(|app| app.name.clone())
}
