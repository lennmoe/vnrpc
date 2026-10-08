use std::fs::{self, File};
use std::io::{BufReader, BufWriter};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use image::RgbImage;
use serde::Serialize;
use serde_json::{json, Map, Value};
use tauri::Manager;

use crate::capture;
use crate::config::Config;
use crate::mascot;
use crate::shell;
use crate::sound;
use crate::state::Shared;
use crate::ui_windows::{self, Toast};

const IMAGE_EXTS: [&str; 5] = ["png", "jpg", "jpeg", "webp", "bmp"];
const RESERVED: [&str; 4] = ["CON", "PRN", "AUX", "NUL"];

pub fn default_root() -> PathBuf {
    shell::pictures_folder().join("Visual Novel RPC")
}

pub fn root(cfg: &Config) -> PathBuf {
    let custom = cfg.str("screenshot_dir");
    if custom.trim().is_empty() {
        default_root()
    } else {
        PathBuf::from(custom.trim())
    }
}

pub fn folder_name(title: &str, taken: &[String]) -> String {
    let cleaned: String = title
        .chars()
        .filter(|c| !"<>:\"/\\|?*".contains(*c) && (*c as u32) >= 0x20)
        .collect();
    let cleaned = cleaned.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut name: String = cleaned.chars().take(80).collect();
    name = name.trim_end_matches(['.', ' ']).to_string();

    let stem = name.split('.').next().unwrap_or("").to_uppercase();
    let numbered_device = (stem.starts_with("COM") || stem.starts_with("LPT"))
        && stem.len() == 4
        && stem.ends_with(|c: char| ('1'..='9').contains(&c));
    let reserved = RESERVED.contains(&stem.as_str()) || numbered_device;
    if name.is_empty() {
        name = "Game".into();
    } else if reserved {
        name.push('_');
    }

    let taken: Vec<String> = taken.iter().map(|t| t.to_lowercase()).collect();
    let mut candidate = name.clone();
    let mut n = 2;
    while taken.contains(&candidate.to_lowercase()) {
        candidate = format!("{name} ({n})");
        n += 1;
    }
    candidate
}

pub fn folder_for(cfg: &mut Config, key: &str, create: bool) -> Option<PathBuf> {
    let entry = cfg.game(key);
    let mut name = text(&entry, "screenshot_folder");

    if name.is_empty() {
        if !create {
            return None;
        }
        let taken: Vec<String> = cfg
            .all_games()
            .iter()
            .filter(|(k, _)| k.as_str() != key)
            .map(|(_, e)| text(e, "screenshot_folder"))
            .collect();
        let title = [text(&entry, "title"), text(&entry, "name"), key.to_string()]
            .into_iter()
            .find(|t| !t.is_empty())
            .unwrap_or_default();

        name = folder_name(&title, &taken);
        cfg.set_game(
            key,
            Map::from_iter([("screenshot_folder".into(), json!(name))]),
        );
    }

    let path = root(cfg).join(name);
    if create {
        let _ = fs::create_dir_all(&path);
    }
    Some(path)
}

fn text(entry: &Map<String, Value>, field: &str) -> String {
    entry
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn modified(path: &Path) -> std::time::SystemTime {
    fs::metadata(path)
        .and_then(|m| m.modified())
        .unwrap_or(std::time::UNIX_EPOCH)
}

pub fn list_shots(folder: Option<&Path>) -> Vec<PathBuf> {
    let Some(folder) = folder else {
        return vec![];
    };

    let mut shots: Vec<PathBuf> = fs::read_dir(folder)
        .into_iter()
        .flatten()
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.is_file())
        .filter(|path| {
            let ext = path.extension().map(|e| e.to_string_lossy().to_lowercase());
            ext.is_some_and(|ext| IMAGE_EXTS.contains(&ext.as_str()))
        })
        .collect();

    shots.sort_by_key(|path| std::cmp::Reverse(modified(path)));
    shots
}

#[derive(Serialize)]
pub struct GameShots {
    pub key: String,
    pub name: String,
    pub shots: Vec<String>,
}

pub fn games_with_shots(cfg: &mut Config) -> Vec<GameShots> {
    let games: Vec<(String, String)> = cfg
        .all_games()
        .iter()
        .map(|(key, e)| (key.clone(), display_name(key, e)))
        .collect();

    let mut out = Vec::new();
    for (key, name) in games {
        let folder = folder_for(cfg, &key, false);
        let shots = list_shots(folder.as_deref());
        if !shots.is_empty() {
            let shots = shots
                .iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();
            out.push(GameShots { key, name, shots });
        }
    }

    out.sort_by_key(|game| std::cmp::Reverse(modified(Path::new(&game.shots[0]))));
    out
}

pub fn display_name(key: &str, entry: &Map<String, Value>) -> String {
    [text(entry, "title"), text(entry, "name")]
        .into_iter()
        .find(|t| !t.is_empty())
        .unwrap_or_else(|| key.to_string())
}

pub fn save(img: &RgbImage, folder: &Path, game: &str, section: &str) -> Result<PathBuf, String> {
    let now = chrono::Local::now();
    fs::create_dir_all(folder).map_err(|e| e.to_string())?;

    let stem = now.format("%Y-%m-%d %H-%M-%S").to_string();
    let mut path = folder.join(format!("{stem}.png"));
    let mut n = 2;
    while path.exists() {
        path = folder.join(format!("{stem} ({n}).png"));
        n += 1;
    }

    let part = path.with_extension("png.part");
    write_png(
        img,
        &part,
        &now.format("%Y-%m-%dT%H:%M:%S").to_string(),
        game,
        section,
    )
    .map_err(|e| e.to_string())?;
    fs::rename(&part, &path).map_err(|e| e.to_string())?;
    Ok(path)
}

fn write_png(
    img: &RgbImage,
    path: &Path,
    taken: &str,
    game: &str,
    section: &str,
) -> Result<(), png::EncodingError> {
    let file = BufWriter::new(File::create(path)?);
    let mut encoder = png::Encoder::new(file, img.width(), img.height());
    encoder.set_color(png::ColorType::Rgb);
    encoder.set_depth(png::BitDepth::Eight);

    encoder.add_text_chunk("Creation Time".into(), taken.into())?;
    encoder.add_text_chunk("Software".into(), "Visual Novel RPC".into())?;
    if !game.is_empty() {
        encoder.add_itxt_chunk("Title".into(), game.into())?;
    }
    if !section.is_empty() {
        encoder.add_itxt_chunk("Section".into(), section.into())?;
    }

    let mut writer = encoder.write_header()?;
    writer.write_image_data(img.as_raw())?;
    writer.finish()
}

#[derive(Serialize, Default)]
pub struct ShotInfo {
    pub taken: String,
    pub width: u32,
    pub height: u32,
    pub section: String,
    pub file_name: String,
}

pub fn info(path: &Path) -> ShotInfo {
    let taken: chrono::DateTime<chrono::Local> = modified(path).into();
    let mut info = ShotInfo {
        taken: taken.format("%Y-%m-%dT%H:%M:%S").to_string(),
        file_name: path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default(),
        ..Default::default()
    };

    if let Ok((w, h)) = image::image_dimensions(path) {
        info.width = w;
        info.height = h;
    }

    let Ok(file) = File::open(path) else {
        return info;
    };
    let Ok(reader) = png::Decoder::new(BufReader::new(file)).read_info() else {
        return info;
    };

    let png_info = reader.info();
    for chunk in &png_info.uncompressed_latin1_text {
        if chunk.keyword == "Creation Time" {
            info.taken = chunk.text.clone();
        }
    }
    for chunk in &png_info.utf8_text {
        if chunk.keyword == "Section" {
            info.section = chunk.get_text().unwrap_or_default();
        }
    }
    info
}

pub fn take(shared: &Arc<Shared>) {
    match capture_and_save(shared) {
        Ok((path, key, area)) => {
            shared.emit("screenshots-changed", json!({ "key": key }));
            ui_windows::show_toast(
                &shared.app,
                Toast {
                    title: "Screenshot saved".into(),
                    detail: path
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_default(),
                    image: Some(path.to_string_lossy().to_string()),
                    ok: true,
                },
                Some(area),
            );
            mascot::say(&shared.app, "Got it! Screenshot saved.", 3);
        }
        Err(message) => {
            let toast = Toast {
                title: "No screenshot".into(),
                detail: message,
                image: None,
                ok: false,
            };
            ui_windows::show_toast(&shared.app, toast, None);
        }
    }
}

fn capture_and_save(
    shared: &Arc<Shared>,
) -> Result<(PathBuf, String, capture::ScreenRect), String> {
    let snap = shared.snapshot();
    if !snap.detected || snap.hwnd == 0 {
        return Err("No visual novel is running.".into());
    }

    let img = capture::capture_window(snap.hwnd)?;
    let area = capture::client_rect_on_screen(snap.hwnd);

    let (folder, volume) = {
        let mut cfg = shared.config.lock().unwrap();
        let folder = folder_for(&mut cfg, &snap.key, true).ok_or("no screenshot folder")?;
        let volume = cfg
            .get("screenshot_volume")
            .and_then(Value::as_i64)
            .unwrap_or(30);
        (folder, volume)
    };

    sound::play_shutter(&shared.data_dir.join("cache"), volume);

    let path = save(&img, &folder, &snap.game_name, &snap.section_label)?;
    let _ = shared
        .app
        .asset_protocol_scope()
        .allow_directory(&folder, false);
    Ok((path, snap.key, area))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn folder_names_are_windows_safe() {
        assert_eq!(folder_name("Fate/stay night", &[]), "Fatestay night");
        assert_eq!(folder_name("CON", &[]), "CON_");
        assert_eq!(folder_name("", &[]), "Game");
        assert_eq!(
            folder_name("Amatsutsumi", &["amatsutsumi".into()]),
            "Amatsutsumi (2)"
        );
        assert_eq!(folder_name("Dots...", &[]), "Dots");
    }
}
