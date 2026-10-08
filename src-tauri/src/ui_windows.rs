use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::{
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};

use crate::capture::ScreenRect;
use crate::winapi;

pub fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
        return;
    }

    let app = app.clone();
    std::thread::spawn(move || {
        let Some(conf) = app
            .config()
            .app
            .windows
            .iter()
            .find(|w| w.label == "main")
            .cloned()
        else {
            return;
        };
        match WebviewWindowBuilder::from_config(&app, &conf).and_then(|b| b.build()) {
            Ok(window) => {
                let _ = window.show();
                let _ = window.set_focus();
            }
            Err(e) => eprintln!("couldn't open the window: {e}"),
        }
    });
}

static PENDING_PAGE: Mutex<Option<String>> = Mutex::new(None);

pub fn open_page(app: &AppHandle, page: &str) {
    if app.get_webview_window("main").is_some() {
        let _ = app.emit_to("main", "navigate", page);
    } else {
        *PENDING_PAGE.lock().unwrap() = Some(page.to_string());
    }
    show_main(app);
}

pub fn take_pending_page() -> Option<String> {
    PENDING_PAGE.lock().unwrap().take()
}

fn popup(
    app: &AppHandle,
    label: &str,
    page: &str,
    width: f64,
    height: f64,
) -> Option<WebviewWindow> {
    if let Some(existing) = app.get_webview_window(label) {
        return Some(existing);
    }

    let window = WebviewWindowBuilder::new(app, label, WebviewUrl::App(page.into()))
        .title("Visual Novel RPC")
        .inner_size(width, height)
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .resizable(false)
        .skip_taskbar(true)
        .always_on_top(true)
        .focused(false)
        .visible(false)
        .build()
        .ok()?;

    if let Ok(hwnd) = window.hwnd() {
        winapi::make_no_activate(hwnd.0 as isize);
    }
    Some(window)
}

fn close_later(app: &AppHandle, label: &'static str, generation: &'static AtomicU64, seconds: f64) {
    let mine = generation.fetch_add(1, Ordering::SeqCst) + 1;
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs_f64(seconds));
        if generation.load(Ordering::SeqCst) == mine {
            if let Some(window) = app.get_webview_window(label) {
                let _ = window.destroy();
            }
        }
    });
}

#[derive(Debug, Clone, Serialize)]
pub struct Toast {
    pub title: String,
    pub detail: String,
    pub image: Option<String>,
    pub ok: bool,
}

static TOAST: Mutex<Option<Toast>> = Mutex::new(None);
static TOAST_GENERATION: AtomicU64 = AtomicU64::new(0);

pub fn show_toast(app: &AppHandle, toast: Toast, area: Option<ScreenRect>) {
    *TOAST.lock().unwrap() = Some(toast.clone());

    let app = app.clone();
    std::thread::spawn(move || {
        let app = &app;
        let Some(window) = popup(app, "toast", "toast.html", 340.0, 76.0) else {
            return;
        };

        let (x, y) = match area {
            Some(area) => (area.left + 16, area.top + 16),
            None => {
                let (left, top, _, _) = winapi::work_area();
                (left + 16, top + 16)
            }
        };
        let _ = window.set_position(PhysicalPosition::new(x, y));
        let _ = window.emit("toast", &toast);
        let _ = window.show();

        close_later(app, "toast", &TOAST_GENERATION, 2.8);
    });
}

pub fn current_toast() -> Option<Toast> {
    TOAST.lock().unwrap().clone()
}

static BALLOON_TEXT: Mutex<String> = Mutex::new(String::new());
static BALLOON_GENERATION: AtomicU64 = AtomicU64::new(0);

pub fn show_balloon(app: &AppHandle, text: &str, seconds: f64) {
    *BALLOON_TEXT.lock().unwrap() = text.to_string();

    let app = app.clone();
    let text = text.to_string();
    std::thread::spawn(move || {
        let app = &app;
        let Some(window) = popup(app, "balloon", "balloon.html", 280.0, 80.0) else {
            return;
        };
        let _ = window.emit("say", &text);
        close_later(app, "balloon", &BALLOON_GENERATION, seconds);
    });
}

pub fn balloon_text() -> String {
    BALLOON_TEXT.lock().unwrap().clone()
}

pub fn place_balloon(app: &AppHandle, width: u32, height: u32) {
    let (Some(balloon), Some(mascot)) = (
        app.get_webview_window("balloon"),
        app.get_webview_window("mascot"),
    ) else {
        return;
    };
    let (Ok(pos), Ok(size)) = (mascot.outer_position(), mascot.outer_size()) else {
        return;
    };

    let scale = balloon.scale_factor().unwrap_or(1.0);
    let (bw, bh) = (
        (width as f64 * scale) as i32,
        (height as f64 * scale) as i32,
    );
    let (cw, ch) = (size.width as i32, size.height as i32);
    let (left, top, right, _) = winapi::work_area();

    let mut x = pos.x - bw + cw / 6;
    if x < left {
        x = pos.x + cw - cw / 6;
    }
    let x = x.clamp(left, (right - bw).max(left));
    let y = top.max(pos.y + ch / 10);

    let _ = balloon.set_size(PhysicalSize::new(bw as u32, bh as u32));
    let _ = balloon.set_position(PhysicalPosition::new(x, y));
    let _ = balloon.show();
}

pub fn hide_balloon(app: &AppHandle) {
    BALLOON_GENERATION.fetch_add(1, Ordering::SeqCst);
    if let Some(window) = app.get_webview_window("balloon") {
        let _ = window.destroy();
    }
}
