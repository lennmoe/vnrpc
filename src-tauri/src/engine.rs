use std::collections::{HashMap, HashSet};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, LazyLock};
use std::time::{Duration, Instant};

use fancy_regex::Regex;
use serde_json::{json, Map, Value};

use crate::config::{url_cache_key, Config};
use crate::discord::{self, Activity};
use crate::engines::{blacklist_set, clean_title, detect_engine, normalize_exe};
use crate::state::{Cmd, Cover, Shared, Snapshot};
use crate::steam;
use crate::title_parser::{parse, user_rules};
use crate::vndb::{best_match, VnResult};
use crate::vndb_list;
use crate::winapi::{self, WindowInfo};

const KNOWN_GAME_SCORE: u32 = 1000;

const GONE_AFTER: u32 = 3;

const PLAYTIME_FLUSH: Duration = Duration::from_secs(60);

struct Target {
    hwnd: isize,
    pid: u32,
    exe: String,
    exe_path: String,
    title: String,
    engine: String,
}

enum Change {
    Game(Target),
    Closed,
}

#[derive(Default)]
struct Watcher {
    locked: Option<(isize, String)>,
    last_key: Option<(isize, String)>,
    reported: bool,
    misses: u32,
}

struct WatchSettings {
    manual: bool,
    manual_exe: String,
    manual_title: String,
    blacklist: HashSet<String>,
    known_paths: HashSet<String>,
}

impl WatchSettings {
    fn from(cfg: &Config) -> WatchSettings {
        let entries: Vec<String> = cfg
            .get("blacklist_exe")
            .and_then(Value::as_array)
            .map(|list| {
                list.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();

        let target = cfg.get("manual_target").cloned().unwrap_or(json!({}));
        let field = |name: &str| target[name].as_str().unwrap_or("").trim().to_lowercase();

        WatchSettings {
            manual: cfg.str("detection_mode") == "manual",
            manual_exe: field("exe"),
            manual_title: field("title_contains"),
            blacklist: blacklist_set(entries.iter().map(String::as_str)),
            known_paths: cfg.known_game_paths().into_iter().collect(),
        }
    }
}

impl Watcher {
    fn poke(&mut self) {
        self.last_key = None;
        self.locked = None;
    }

    fn tick(&mut self, settings: &WatchSettings) -> Option<Change> {
        if let Some((hwnd, engine)) = self.locked.clone() {
            if winapi::is_window_visible(hwnd) {
                let title = winapi::window_title(hwnd);
                if !title.trim().is_empty() {
                    return self.emit(hwnd, title, engine, None);
                }
            }
            self.locked = None;
        }

        let windows: Vec<WindowInfo> = winapi::list_top_level_windows()
            .into_iter()
            .filter(|w| !settings.blacklist.contains(&normalize_exe(w.exe())))
            .collect();

        let picked = if settings.manual {
            pick_manual(settings, windows)
        } else {
            pick_auto(settings, windows)
        };

        match picked {
            Some((win, engine)) => {
                self.locked = Some((win.hwnd, engine.clone()));
                let title = win.title.clone();
                self.emit(win.hwnd, title, engine, Some(win))
            }
            None => {
                self.misses += 1;
                if self.reported && self.misses >= GONE_AFTER {
                    self.last_key = None;
                    self.reported = false;
                    return Some(Change::Closed);
                }
                None
            }
        }
    }

    fn emit(
        &mut self,
        hwnd: isize,
        title: String,
        engine: String,
        win: Option<WindowInfo>,
    ) -> Option<Change> {
        self.misses = 0;

        let key = (hwnd, title.clone());
        if self.last_key.as_ref() == Some(&key) {
            return None;
        }
        self.last_key = Some(key);

        let win = win.or_else(|| {
            winapi::list_top_level_windows()
                .into_iter()
                .find(|w| w.hwnd == hwnd)
        })?;
        self.reported = true;

        Some(Change::Game(Target {
            hwnd,
            pid: win.pid,
            exe: win.exe().to_string(),
            exe_path: win.exe_path.clone(),
            title,
            engine,
        }))
    }
}

fn engine_name(win: &WindowInfo) -> String {
    detect_engine(win)
        .map(|(engine, _)| engine.name.to_string())
        .unwrap_or_default()
}

fn pick_manual(settings: &WatchSettings, windows: Vec<WindowInfo>) -> Option<(WindowInfo, String)> {
    let (exe, title) = (&settings.manual_exe, &settings.manual_title);
    if exe.is_empty() {
        return None;
    }

    let win = windows.into_iter().find(|w| {
        w.exe().to_lowercase() == *exe
            && (title.is_empty() || w.title.to_lowercase().contains(title.as_str()))
    })?;
    let engine = engine_name(&win);
    Some((win, engine))
}

fn pick_auto(settings: &WatchSettings, windows: Vec<WindowInfo>) -> Option<(WindowInfo, String)> {
    let known = &settings.known_paths;
    let mut best: Option<(WindowInfo, String)> = None;
    let mut best_score = 0;

    for win in windows {
        let (engine, mut score) = match detect_engine(&win) {
            Some((engine, score)) => (engine.name.to_string(), score),
            None => (String::new(), 0),
        };
        let path = win.exe_path.replace('/', "\\").to_lowercase();
        if !win.exe_path.is_empty() && known.contains(&path) {
            score = KNOWN_GAME_SCORE;
        }
        if score > best_score {
            best_score = score;
            best = Some((win, engine));
        }
    }
    best
}

static SECTION_TAIL: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s*[-–—~～:|].*$").unwrap());
static VERSION_WORD: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\bver(?:sion)?\.?\s*[\d.;]+").unwrap());
static VERSION_NUM: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\bv?\d+[.;]\d+(?:[.;]\d+)*[a-z]?\b").unwrap());
static BRACKETS: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[\[\]（）()【】]").unwrap());
static SPACES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s{2,}").unwrap());

fn guess_game_name(cleaned: &str) -> String {
    let head = SECTION_TAIL.replace(cleaned, "");
    let head = head.trim_matches(|c| " -–—|:·•".contains(c));
    if head.is_empty() {
        cleaned.trim().to_string()
    } else {
        head.to_string()
    }
}

fn search_query(cleaned: &str) -> String {
    let q = SECTION_TAIL.replace(cleaned, "");
    let q = VERSION_WORD.replace_all(&q, "");
    let q = VERSION_NUM.replace_all(&q, " ");
    let q = BRACKETS.replace_all(&q, " ");
    let q = SPACES.replace_all(&q, " ").trim().to_string();
    if q.is_empty() {
        cleaned.trim().to_string()
    } else {
        q
    }
}

fn text(entry: &Map<String, Value>, field: &str) -> String {
    entry
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

pub fn format_playtime(seconds: i64) -> String {
    let minutes = seconds.max(0) / 60;
    format!("{}h {:02}m", minutes / 60, minutes % 60)
}

fn now_f() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

pub struct Engine {
    shared: Arc<Shared>,
    discord: Sender<discord::Msg>,
    watcher: Watcher,
    current_key: String,
    session_start: i64,
    auto_match: HashMap<String, Option<VnResult>>,
    paused: bool,

    playtime_key: String,
    tick_start: f64,
    last_flush: Instant,

    unfocused_since: f64,
    idle_since: f64,
    idle: bool,
}

impl Engine {
    pub fn new(shared: Arc<Shared>, discord: Sender<discord::Msg>) -> Engine {
        Engine {
            shared,
            discord,
            watcher: Watcher::default(),
            current_key: String::new(),
            session_start: 0,
            auto_match: HashMap::new(),
            paused: false,
            playtime_key: String::new(),
            tick_start: 0.0,
            last_flush: Instant::now(),
            unfocused_since: 0.0,
            idle_since: 0.0,
            idle: false,
        }
    }

    pub fn run(mut self, commands: Receiver<Cmd>) {
        loop {
            match commands.recv_timeout(Duration::from_secs(1)) {
                Ok(Cmd::Quit) | Err(RecvTimeoutError::Disconnected) => break,
                Ok(Cmd::Reload) => self.reload(),
                Ok(Cmd::Pause(paused)) => self.set_paused(paused),
                Ok(Cmd::SetPlaytime(key, seconds)) => self.set_playtime(&key, seconds),
                Err(RecvTimeoutError::Timeout) => {}
            }

            let change = {
                let settings = WatchSettings::from(&self.shared.config.lock().unwrap());
                self.watcher.tick(&settings)
            };
            match change {
                Some(Change::Game(target)) => self.handle_target(target),
                Some(Change::Closed) => self.handle_closed(),
                None => {}
            }

            self.check_idle();

            if self.last_flush.elapsed() >= PLAYTIME_FLUSH {
                self.last_flush = Instant::now();
                self.refresh_playtime();
            }
        }

        self.flush_playtime();
        let _ = self.discord.send(discord::Msg::Quit);
    }

    fn reload(&mut self) {
        self.auto_match.clear();
        self.watcher.poke();

        let cfg = self.shared.config.lock().unwrap();
        let _ = self
            .discord
            .send(discord::Msg::ClientId(cfg.str("discord_client_id")));
        let _ = self
            .discord
            .send(discord::Msg::Interval(cfg.num("update_min_interval")));
    }

    fn set_playtime(&mut self, key: &str, seconds: i64) {
        if key == self.playtime_key {
            self.flush_playtime();
            self.tick_start = now_f();
        }
        self.shared
            .config
            .lock()
            .unwrap()
            .set_playtime(key, seconds);
        self.watcher.poke();
    }

    fn store(&self, mut snap: Snapshot) {
        snap.paused = self.paused;
        snap.activity = self.activity_for(&snap);
        if !self.paused {
            let _ = self.discord.send(discord::Msg::Set(snap.activity.clone()));
        }
        self.shared.publish_snapshot(snap);
    }

    fn set_paused(&mut self, paused: bool) {
        if paused {
            self.flush_playtime();
            let _ = self.discord.send(discord::Msg::Set(None));
        } else {
            self.tick_start = now_f();
        }
        self.paused = paused;

        self.store(self.shared.snapshot());
        if !paused {
            self.watcher.poke();
        }
    }

    fn handle_closed(&mut self) {
        if self.shared.config.lock().unwrap().bool("clear_on_close") {
            let _ = self.discord.send(discord::Msg::Set(None));
        }
        self.flush_playtime();
        self.playtime_key.clear();
        self.current_key.clear();
        self.reset_idle();

        self.shared.publish_snapshot(Snapshot {
            paused: self.paused,
            ..Default::default()
        });
    }

    fn handle_target(&mut self, target: Target) {
        let key = self
            .shared
            .config
            .lock()
            .unwrap()
            .key_for(&target.exe, &target.exe_path);
        if key != self.current_key {
            self.start_session(&key);
        }

        let (mut entry, use_steam, nsfw_ok, asset) = {
            let mut cfg = self.shared.config.lock().unwrap();
            if !target.exe_path.is_empty() && text(&cfg.game(&key), "path") != target.exe_path {
                cfg.set_game(
                    &key,
                    Map::from_iter([("path".into(), json!(target.exe_path))]),
                );
            }
            (
                cfg.game(&key),
                cfg.bool("use_steam_names"),
                cfg.bool("allow_nsfw_covers"),
                cfg.str("default_asset_key"),
            )
        };

        let cleaned = clean_title(&target.title);
        let steam_name = if use_steam {
            steam::name_for_exe(&target.exe_path).unwrap_or_default()
        } else {
            String::new()
        };

        let vn = self.resolve_vn(&key, &cleaned, &entry, &steam_name);
        let game_name = [
            text(&entry, "title"),
            vn.as_ref().map(|v| v.title.clone()).unwrap_or_default(),
            steam_name,
        ]
        .into_iter()
        .find(|name| !name.is_empty())
        .unwrap_or_else(|| guess_game_name(&cleaned));

        let cover = self.resolve_cover(&entry, vn.as_ref(), nsfw_ok, &asset);
        let learned = learned_fields(&entry, &game_name, vn.as_ref(), &cover);

        let (rules, playtime) = {
            let mut cfg = self.shared.config.lock().unwrap();
            if !learned.is_empty() {
                cfg.set_game(&key, learned.clone());
                entry.extend(learned);
            }

            let mut extra: Vec<Value> = entry
                .get("title_rules")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            extra.extend(
                cfg.get("title_rules")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default(),
            );
            (user_rules(&extra), cfg.playtime(&key))
        };

        let vn_id = text(&entry, "vndb_id");
        if !vn_id.is_empty() && text(&entry, "vndb_synced") != vn_id {
            let status = Some(text(&entry, "status"))
                .filter(|s| !s.is_empty())
                .unwrap_or("playing".into());
            vndb_list::sync_status(&self.shared, &key, &vn_id, &status, true);
        }

        let mut info = parse(&cleaned, &game_name, &rules);
        let manual_section = text(&entry, "section");
        if info.section_label.is_empty() && !manual_section.trim().is_empty() {
            info.section_type = "manual".into();
            info.section_label = manual_section.trim().to_string();
        }
        let privacy = Some(text(&entry, "privacy").to_lowercase())
            .filter(|p| !p.is_empty())
            .unwrap_or("full".into());

        self.store(Snapshot {
            detected: true,
            key,
            exe: target.exe,
            engine_name: target.engine,
            raw_title: target.title,
            game_name,
            section_type: info.section_type,
            section_label: info.section_label,
            cover,
            vn,
            privacy,
            playtime_seconds: playtime,
            session_start: self.session_start,
            idle: self.idle,
            paused: false,
            activity: None,
            hwnd: target.hwnd,
            pid: target.pid,
        });
    }

    fn start_session(&mut self, key: &str) {
        self.flush_playtime();
        self.playtime_key = key.to_string();
        self.tick_start = now_f();
        self.reset_idle();
        self.current_key = key.to_string();
        self.session_start = crate::config::now();
        self.shared.config.lock().unwrap().start_session(key);
    }

    fn resolve_vn(
        &mut self,
        key: &str,
        cleaned: &str,
        entry: &Map<String, Value>,
        steam_name: &str,
    ) -> Option<VnResult> {
        let vndb_id = text(entry, "vndb_id");
        let cache_key = if !vndb_id.is_empty() {
            format!("id:{vndb_id}")
        } else if matches!(
            text(entry, "cover_source").as_str(),
            "url" | "local" | "none"
        ) {
            return None;
        } else {
            key.to_string()
        };

        if let Some(hit) = self.auto_match.get(&cache_key) {
            return hit.clone();
        }

        let result = if !vndb_id.is_empty() {
            self.shared.vndb.get(&vndb_id)
        } else {
            let query = if steam_name.is_empty() {
                search_query(cleaned)
            } else {
                steam_name.to_string()
            };
            self.shared
                .vndb
                .search(&query, 8)
                .map(|results| best_match(results, &query))
        };

        match result {
            Ok(vn) => {
                self.auto_match.insert(cache_key, vn.clone());
                vn
            }
            Err(e) => {
                self.shared
                    .vndb_message(false, format!("VNDB lookup failed: {e}"));
                None
            }
        }
    }

    fn resolve_cover(
        &self,
        entry: &Map<String, Value>,
        vn: Option<&VnResult>,
        nsfw_ok: bool,
        asset: &str,
    ) -> Cover {
        let vndb = &self.shared.vndb;
        let to_string = |p: Option<std::path::PathBuf>| p.map(|p| p.to_string_lossy().to_string());
        let value = text(entry, "cover_value");

        match text(entry, "cover_source").as_str() {
            "url" if !value.is_empty() => {
                let discord_image = if value.starts_with("http") {
                    value.clone()
                } else {
                    asset.to_string()
                };
                return Cover {
                    source: "url".into(),
                    local_path: to_string(vndb.cover_path(&url_cache_key(&value), &value)),
                    discord_image,
                    nsfw: false,
                };
            }
            "local" if !value.is_empty() => {
                return Cover {
                    source: "local".into(),
                    local_path: Some(value),
                    discord_image: asset.to_string(),
                    nsfw: false,
                };
            }
            _ => {}
        }

        let Some(vn) = vn else {
            return Cover {
                source: "none".into(),
                ..Default::default()
            };
        };
        let usable = !vn.image_url.is_empty() && (nsfw_ok || !vn.nsfw);

        Cover {
            source: "vndb".into(),
            local_path: to_string(vndb.cover_path(&vn.id, &vn.image_url)),
            discord_image: if usable {
                vn.image_url.clone()
            } else {
                asset.to_string()
            },
            nsfw: vn.nsfw,
        }
    }

    fn activity_for(&self, snap: &Snapshot) -> Option<Activity> {
        if !snap.detected || snap.privacy == "off" || snap.idle {
            return None;
        }

        let cfg = self.shared.config.lock().unwrap();
        let asset = cfg.str("default_asset_key");
        let start = cfg
            .bool("show_elapsed")
            .then_some(snap.session_start)
            .filter(|s| *s > 0);

        if snap.privacy == "private" {
            return Some(Activity {
                name: "Visual Novel".into(),
                details: "Reading".into(),
                large_image: asset,
                large_text: "Visual Novel".into(),
                small_text: "via Visual Novel RPC".into(),
                start,
                ..Default::default()
            });
        }

        let mut buttons = vec![];
        if cfg.bool("show_vndb_button") && snap.privacy != "partial" {
            if let Some(vn) = &snap.vn {
                buttons.push(("View on VNDB".to_string(), vn.url()));
            }
        }

        let state = if cfg.bool("show_total_read") && snap.playtime_seconds > 0 {
            format!("Total read: {}", format_playtime(snap.playtime_seconds))
        } else {
            String::new()
        };

        let show_section = cfg.bool("show_section") && snap.privacy != "partial";
        let details = if !show_section {
            String::new()
        } else if snap.section_label.is_empty() {
            "Reading".into()
        } else {
            format!("Reading・{}", snap.section_label)
        };

        let name = [&snap.game_name, &snap.raw_title]
            .into_iter()
            .find(|n| !n.is_empty())
            .cloned()
            .unwrap_or_else(|| "Visual Novel".into());
        let large_image = if snap.cover.discord_image.is_empty() {
            asset
        } else {
            snap.cover.discord_image.clone()
        };

        Some(Activity {
            name: name.clone(),
            details,
            state,
            large_image,
            large_text: name,
            small_text: "via Visual Novel RPC".into(),
            start,
            buttons,
        })
    }

    fn flush_playtime(&mut self) {
        if self.paused || self.idle || self.playtime_key.is_empty() || self.tick_start <= 0.0 {
            return;
        }

        let end = if self.unfocused_since > 0.0 {
            now_f().min(self.unfocused_since)
        } else {
            now_f()
        };
        let elapsed = end - self.tick_start;
        if elapsed > 0.0 {
            self.tick_start = end;
            self.shared
                .config
                .lock()
                .unwrap()
                .add_playtime(&self.playtime_key, elapsed);
        }
    }

    fn refresh_playtime(&mut self) {
        if self.paused || self.playtime_key.is_empty() {
            return;
        }
        let snap = self.shared.snapshot();
        if !snap.detected {
            return;
        }

        self.flush_playtime();
        let total = self.shared.config.lock().unwrap().playtime(&snap.key);
        self.store(Snapshot {
            playtime_seconds: total,
            ..snap
        });
    }

    fn reset_idle(&mut self) {
        self.unfocused_since = 0.0;
        self.idle = false;
    }

    fn check_idle(&mut self) {
        let (enabled, idle_seconds) = {
            let cfg = self.shared.config.lock().unwrap();
            (cfg.bool("idle_when_unfocused"), cfg.num("idle_seconds"))
        };
        let snap = self.shared.snapshot();
        let now = now_f();

        let focused = !(enabled && snap.detected) || {
            let front = winapi::foreground_window();
            front != 0
                && (front == snap.hwnd || (snap.pid != 0 && winapi::window_pid(front) == snap.pid))
        };

        if focused {
            self.unfocused_since = 0.0;
            if !self.idle {
                return;
            }
            self.session_start += (now - self.idle_since).max(0.0) as i64;
            self.tick_start = now;
            self.idle = false;
        } else if self.unfocused_since == 0.0 {
            self.unfocused_since = now;
            return;
        } else if self.idle || now - self.unfocused_since < idle_seconds.max(0.0) {
            return;
        } else {
            self.flush_playtime();
            self.idle = true;
            self.idle_since = self.unfocused_since;
        }

        if snap.detected {
            self.store(Snapshot {
                idle: self.idle,
                session_start: self.session_start,
                ..snap
            });
        }
    }
}

fn learned_fields(
    entry: &Map<String, Value>,
    game_name: &str,
    vn: Option<&VnResult>,
    cover: &Cover,
) -> Map<String, Value> {
    let mut learned = Map::new();

    if !game_name.is_empty() && text(entry, "title").is_empty() && text(entry, "name") != game_name
    {
        learned.insert("name".into(), json!(game_name));
    }
    if let Some(vn) = vn {
        if text(entry, "vndb_id").is_empty() && text(entry, "matched_vndb_id") != vn.id {
            learned.insert("matched_vndb_id".into(), json!(vn.id));
        }
    }
    if !entry.contains_key("status") {
        learned.insert("status".into(), json!("playing"));
    }
    if cover.source != "none"
        && entry.get("cover_nsfw").and_then(Value::as_bool) != Some(cover.nsfw)
    {
        learned.insert("cover_nsfw".into(), json!(cover.nsfw));
    }
    learned
}
