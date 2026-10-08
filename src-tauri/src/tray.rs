use std::sync::Arc;

use tauri::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

use crate::commands::app::quit_app;
use crate::state::{Cmd, Shared};
use crate::{mascot, screenshots, ui_windows};

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Show", true, None::<&str>)?;
    let pause = MenuItem::with_id(app, "pause", "Pause / resume presence", true, None::<&str>)?;
    let screenshot = MenuItem::with_id(app, "screenshot", "Take screenshot", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &pause, &screenshot, &separator, &quit])?;

    TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().cloned().expect("app icon"))
        .tooltip("Visual Novel RPC")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            let left_click = matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            );
            if left_click {
                ui_windows::show_main(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

pub fn handle_menu(app: &AppHandle, event: MenuEvent) {
    let shared = Arc::clone(&app.state::<Arc<Shared>>());

    match event.id.as_ref() {
        "open" | "mascot-open" => ui_windows::show_main(app),
        "pause" => {
            let paused = shared.snapshot().paused;
            shared.send(Cmd::Pause(!paused));
        }
        "screenshot" => {
            std::thread::spawn(move || screenshots::take(&shared));
        }
        "quit" => quit_app(app, &shared),
        "mascot-pick" => ui_windows::open_page(app, "wishlist"),
        "mascot-hide" => mascot::hide(app),
        _ => {}
    }
}
