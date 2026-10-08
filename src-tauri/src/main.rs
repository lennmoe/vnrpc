#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod discord;
mod engine;
mod engines;
mod state;
mod steam;
mod title_parser;
mod vndb;
mod vndb_list;

mod capture;
mod clipboard;
mod hotkey;
mod shell;
mod sound;
mod winapi;

mod autostart;
mod backup;
mod images;
mod launcher;
mod mascot;
mod screenshots;
mod updater;

mod commands;
mod tray;
mod ui_windows;

use std::path::PathBuf;
use std::sync::Arc;

use tauri::{App, Manager, RunEvent, WindowEvent};

use config::Config;
use engine::Engine;
use state::Shared;

fn data_dir_override() -> Option<PathBuf> {
    std::env::var_os("VNRPC_DATA_DIR").map(PathBuf::from)
}

fn setup(app: &mut App) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = match data_dir_override() {
        Some(dir) => dir,
        None => {
            let data_dir = app.path().app_data_dir()?;
            import_python_data(&data_dir);
            data_dir
        }
    };
    app.asset_protocol_scope()
        .allow_directory(&data_dir, true)?;

    let cfg = Config::load(&data_dir);
    let client_id = cfg.str("discord_client_id");
    let interval = cfg.num("update_min_interval");
    let start_minimized =
        cfg.bool("start_minimized") || std::env::args().any(|a| a == "--minimized");

    let (commands, command_queue) = std::sync::mpsc::channel();
    let shared = Arc::new(Shared::new(app.handle().clone(), data_dir, cfg, commands));
    app.manage(Arc::clone(&shared));
    commands::app::allow_screenshot_folder(&shared);

    let (discord_tx, discord_rx) = discord::channel();
    let for_status = Arc::clone(&shared);
    std::thread::Builder::new()
        .name("discord".into())
        .spawn(move || {
            let on_status = Box::new(move |ok: bool, message: String| {
                for_status.update_status(|st| {
                    st.discord_ok = ok;
                    st.discord_msg = message;
                });
            });
            discord::run(discord_rx, client_id, interval, on_status);
        })?;

    let engine = Engine::new(Arc::clone(&shared), discord_tx);
    std::thread::Builder::new()
        .name("engine".into())
        .spawn(move || engine.run(command_queue))?;

    let for_hotkey = Arc::clone(&shared);
    std::thread::Builder::new()
        .name("hotkey".into())
        .spawn(move || hotkey::run(for_hotkey))?;

    tray::build(app.handle())?;
    mascot::apply_settings(app.handle());

    if !start_minimized {
        ui_windows::show_main(app.handle());
    }
    Ok(())
}

fn import_python_data(data_dir: &std::path::Path) {
    let Ok(appdata) = std::env::var("APPDATA") else {
        return;
    };
    let source = PathBuf::from(appdata).join("VisualNovelRPC");
    if source.is_dir() {
        Config::import_from(data_dir, &source);
    }
}

fn main() {
    let mut builder = tauri::Builder::default();

    if data_dir_override().is_none() {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            ui_windows::show_main(app)
        }));
    }

    builder
        .plugin(tauri_plugin_dialog::init())
        .setup(setup)
        .on_menu_event(tray::handle_menu)
        .on_window_event(|window, event| {
            if window.label() == "mascot" && matches!(event, WindowEvent::Moved(_)) {
                mascot::moved(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::app::get_state,
            commands::app::update_settings,
            commands::app::set_paused,
            commands::app::set_autostart,
            commands::app::not_a_vn,
            commands::app::list_windows,
            commands::app::open_url,
            commands::app::test_discord,
            commands::app::check_vndb_token,
            commands::app::take_screenshot,
            commands::app::play_shutter,
            commands::app::quit,
            commands::library::get_library,
            commands::library::get_game,
            commands::library::update_game,
            commands::library::set_playtime,
            commands::library::remove_game,
            commands::library::confirm_match,
            commands::library::set_game_path,
            commands::library::set_tool_path,
            commands::library::play_game,
            commands::library::get_vote,
            commands::library::set_vote,
            commands::library::get_wishlist,
            commands::covers::search_vndb,
            commands::covers::release_covers,
            commands::covers::set_game_vn,
            commands::covers::set_release_cover,
            commands::covers::set_cover_url,
            commands::covers::set_cover_file,
            commands::covers::prepare_image,
            commands::covers::crop_cover,
            commands::screenshots::list_screenshots,
            commands::screenshots::screenshot_info,
            commands::screenshots::thumbnail,
            commands::screenshots::delete_screenshot,
            commands::screenshots::copy_image_file,
            commands::screenshots::open_path,
            commands::screenshots::show_in_folder,
            commands::screenshots::open_screenshot_folder,
            commands::share::share_games,
            commands::share::learn_cover_nsfw,
            commands::share::image_data_url,
            commands::share::copy_png,
            commands::share::save_png,
            commands::data::backup_default_name,
            commands::data::export_data,
            commands::data::import_data,
            commands::data::backup_folder,
            commands::data::check_update,
            commands::data::install_update,
            commands::data::release_notes,
            commands::popups::mascot_info,
            commands::popups::mascot_poke,
            commands::popups::mascot_open_app,
            commands::popups::mascot_menu,
            commands::popups::balloon_text,
            commands::popups::place_balloon,
            commands::popups::hide_balloon,
            commands::popups::toast_content,
        ])
        .build(tauri::generate_context!())
        .expect("error while building the app")
        .run(|_app, event| {
            if let RunEvent::ExitRequested {
                api, code: None, ..
            } = event
            {
                api.prevent_exit();
            }
        });
}
