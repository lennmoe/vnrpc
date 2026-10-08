use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use image::imageops::FilterType;
use image::RgbaImage;
use serde::Serialize;
use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::{AppHandle, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindowBuilder};

use crate::state::{Shared, Snapshot};
use crate::ui_windows;
use crate::winapi;

const BUILT_IN: &[u8] = include_bytes!("../assets/mascot.png");

const POKES: [&str; 3] = [
    "Need something to read? Right-click me for a random pick from your wishlist!",
    "I'm keeping an eye on your reading time~",
    "Hehe, that tickles!",
];

struct Character {
    file: PathBuf,
    alpha: RgbaImage,
}

static CHARACTER: Mutex<Option<Character>> = Mutex::new(None);

static GENERATION: AtomicU64 = AtomicU64::new(0);

fn shared(app: &AppHandle) -> Arc<Shared> {
    Arc::clone(&app.state::<Arc<Shared>>())
}

fn load_character(custom: &str, height: u32) -> RgbaImage {
    let custom_image = Some(custom)
        .filter(|path| !path.trim().is_empty())
        .and_then(|path| image::open(path.trim()).ok());
    let img = match custom_image {
        Some(img) => img,
        None => image::load_from_memory(BUILT_IN).expect("built-in mascot"),
    };
    let img = img.to_rgba8();

    let cropped = crop_transparent_margins(&img);
    let height = height.clamp(80, 2000);
    let width =
        ((cropped.width() as f64 * height as f64 / cropped.height() as f64).round() as u32).max(1);
    image::imageops::resize(&cropped, width, height, FilterType::Lanczos3)
}

fn crop_transparent_margins(img: &RgbaImage) -> RgbaImage {
    let (mut left, mut top, mut right, mut bottom) = (img.width(), img.height(), 0, 0);
    for (x, y, px) in img.enumerate_pixels() {
        if px.0[3] > 0 {
            left = left.min(x);
            top = top.min(y);
            right = right.max(x);
            bottom = bottom.max(y);
        }
    }
    if right < left {
        return img.clone();
    }
    image::imageops::crop_imm(img, left, top, right - left + 1, bottom - top + 1).to_image()
}

fn default_position(width: u32, height: u32) -> (i32, i32) {
    let (_, _, right, bottom) = winapi::work_area();
    (right - width as i32 - 40, bottom - height as i32)
}

fn saved_position(value: Option<&Value>, width: u32, height: u32) -> Option<(i32, i32)> {
    let pos = value?.as_array()?;
    let x = pos.first()?.as_i64()? as i32;
    let y = pos.get(1)?.as_i64()? as i32;

    let (vx, vy, vw, vh) = winapi::virtual_screen();
    let center_x = x + width as i32 / 2;
    let center_y = y + height as i32 / 2;
    let on_screen = center_x >= vx && center_x <= vx + vw && center_y >= vy && y <= vy + vh - 40;
    on_screen.then_some((x, y))
}

#[derive(Serialize)]
pub struct MascotInfo {
    pub file: String,
    pub width: u32,
    pub height: u32,
}

pub fn info() -> Option<MascotInfo> {
    let character = CHARACTER.lock().unwrap();
    let character = character.as_ref()?;
    Some(MascotInfo {
        file: character.file.to_string_lossy().to_string(),
        width: character.alpha.width(),
        height: character.alpha.height(),
    })
}

pub fn apply_settings(app: &AppHandle) {
    let shared = shared(app);
    let (enabled, image_path, height, topmost, saved) = {
        let cfg = shared.config.lock().unwrap();
        (
            cfg.bool("mascot_enabled"),
            cfg.str("mascot_image"),
            cfg.num("mascot_height") as u32,
            cfg.bool("mascot_topmost"),
            cfg.get("mascot_pos").cloned(),
        )
    };

    GENERATION.fetch_add(1, Ordering::SeqCst);
    ui_windows::hide_balloon(app);
    if let Some(window) = app.get_webview_window("mascot") {
        let _ = window.destroy();
    }
    if !enabled {
        return;
    }

    let character = load_character(&image_path, if height == 0 { 420 } else { height });
    let (width, height) = (character.width(), character.height());

    let file = shared
        .data_dir
        .join("cache")
        .join(format!("mascot_{}.png", GENERATION.load(Ordering::SeqCst)));
    remove_old_pictures(&shared.data_dir.join("cache"));
    if character.save(&file).is_err() {
        return;
    }
    *CHARACTER.lock().unwrap() = Some(Character {
        file,
        alpha: character,
    });

    let (x, y) = saved_position(saved.as_ref(), width, height)
        .unwrap_or_else(|| default_position(width, height));
    let app = app.clone();
    std::thread::spawn(move || build_window(&app, x, y, width, height, topmost));
}

fn remove_old_pictures(cache: &Path) {
    for entry in std::fs::read_dir(cache).into_iter().flatten().flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with("mascot_") && name.ends_with(".png") {
            let _ = std::fs::remove_file(entry.path());
        }
    }
}

fn build_window(app: &AppHandle, x: i32, y: i32, width: u32, height: u32, topmost: bool) {
    let built = WebviewWindowBuilder::new(app, "mascot", WebviewUrl::App("mascot.html".into()))
        .title("Visual Novel RPC mascot")
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .resizable(false)
        .skip_taskbar(true)
        .always_on_top(topmost)
        .focused(false)
        .visible(false)
        .build();
    let Ok(window) = built else {
        return;
    };

    let _ = window.set_size(PhysicalSize::new(width, height));
    let _ = window.set_position(PhysicalPosition::new(x, y));
    if !topmost {
        let _ = window.set_always_on_bottom(true);
    }
    let _ = window.show();

    let app = app.clone();
    let generation = GENERATION.load(Ordering::SeqCst);
    std::thread::spawn(move || click_through_loop(&app, generation));
}

fn click_through_loop(app: &AppHandle, generation: u64) {
    let mut ignoring: Option<bool> = None;

    while GENERATION.load(Ordering::SeqCst) == generation {
        std::thread::sleep(Duration::from_millis(40));

        let Some(window) = app.get_webview_window("mascot") else {
            return;
        };
        let (Some((cx, cy)), Ok(pos)) = (winapi::cursor_pos(), window.outer_position()) else {
            continue;
        };

        let over_character = {
            let character = CHARACTER.lock().unwrap();
            let Some(character) = character.as_ref() else {
                return;
            };
            let (x, y) = (cx - pos.x, cy - pos.y);
            let inside = x >= 0
                && y >= 0
                && (x as u32) < character.alpha.width()
                && (y as u32) < character.alpha.height();
            inside && character.alpha.get_pixel(x as u32, y as u32).0[3] > 10
        };

        let ignore = !over_character;
        if ignoring != Some(ignore) {
            let _ = window.set_ignore_cursor_events(ignore);
            ignoring = Some(ignore);
        }
    }
}

static MOVES: AtomicU64 = AtomicU64::new(0);

pub fn moved(app: &AppHandle) {
    let mine = MOVES.fetch_add(1, Ordering::SeqCst) + 1;
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(500));
        if MOVES.load(Ordering::SeqCst) == mine {
            save_position(&app);
        }
    });
}

fn save_position(app: &AppHandle) {
    let Some(window) = app.get_webview_window("mascot") else {
        return;
    };
    let Ok(pos) = window.outer_position() else {
        return;
    };

    let shared = shared(app);
    let mut cfg = shared.config.lock().unwrap();
    let _ = cfg.update(serde_json::Map::from_iter([(
        "mascot_pos".into(),
        json!([pos.x, pos.y]),
    )]));
}

pub fn say(app: &AppHandle, text: &str, seconds: u64) {
    if app.get_webview_window("mascot").is_none() {
        return;
    }
    let talks = shared(app)
        .config
        .lock()
        .unwrap()
        .get("mascot_talk")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    if talks {
        ui_windows::show_balloon(app, text, seconds as f64);
    }
}

pub fn poke(app: &AppHandle) {
    let pick = (chrono::Utc::now().timestamp_subsec_nanos() as usize) % POKES.len();
    say(app, POKES[pick], 6);
}

pub fn react(app: &AppHandle, old: &Snapshot, new: &Snapshot) {
    let name = if new.game_name.is_empty() {
        "this one"
    } else {
        &new.game_name
    };

    if new.detected && (!old.detected || old.key != new.key) {
        say(app, &format!("Ooh, {name}! Enjoy your reading~"), 6);
    } else if old.detected && !new.detected {
        say(app, "Done for today? Good reading session!", 6);
    } else if new.detected && new.idle && !old.idle {
        say(app, "Taking a break? I'll pause the timer for you.", 6);
    } else if new.detected && old.idle && !new.idle {
        say(app, "Welcome back!", 3);
    } else if new.detected
        && !new.section_label.is_empty()
        && new.section_label != old.section_label
    {
        say(app, &format!("{}... here we go!", new.section_label), 4);
    }
}

pub fn show_menu(app: &AppHandle) {
    let Some(window) = app.get_webview_window("mascot") else {
        return;
    };

    let menu = (|| -> tauri::Result<Menu<tauri::Wry>> {
        let open = MenuItem::with_id(
            app,
            "mascot-open",
            "Open Visual Novel RPC",
            true,
            None::<&str>,
        )?;
        let pick = MenuItem::with_id(
            app,
            "mascot-pick",
            "Random VN from my wishlist",
            true,
            None::<&str>,
        )?;
        let separator = PredefinedMenuItem::separator(app)?;
        let hide = MenuItem::with_id(app, "mascot-hide", "Hide the mascot", true, None::<&str>)?;
        Menu::with_items(app, &[&open, &pick, &separator, &hide])
    })();

    if let Ok(menu) = menu {
        let _ = window.popup_menu(&menu);
    }
}

pub fn hide(app: &AppHandle) {
    {
        let shared = shared(app);
        let mut cfg = shared.config.lock().unwrap();
        let _ = cfg.update(serde_json::Map::from_iter([(
            "mascot_enabled".into(),
            json!(false),
        )]));
    }
    apply_settings(app);
}
