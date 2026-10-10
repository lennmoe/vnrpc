use std::collections::HashSet;
use std::path::Path;
use std::sync::LazyLock;

use fancy_regex::Regex;

use crate::winapi::WindowInfo;

pub const BUILTIN_BLACKLIST: &[&str] = &[
    "explorer.exe",
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
    "discord.exe",
    "spotify.exe",
    "code.exe",
    "devenv.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "obs64.exe",
    "obs32.exe",
    "notepad.exe",
    "notepad++.exe",
    "python.exe",
    "pythonw.exe",
    "cmd.exe",
    "powershell.exe",
    "windowsterminal.exe",
    "textinputhost.exe",
    "searchhost.exe",
    "applicationframehost.exe",
    "systemsettings.exe",
    "taskmgr.exe",
    "vnrpc.exe",
    "visualnovelrpc.exe",
    "msedgewebview2.exe",
];

pub fn normalize_exe(name: &str) -> String {
    let base = name
        .trim()
        .rsplit(['\\', '/'])
        .next()
        .unwrap_or("")
        .to_lowercase();
    if !base.is_empty() && !base.ends_with(".exe") {
        format!("{base}.exe")
    } else {
        base
    }
}

pub fn blacklist_set<'a>(user: impl IntoIterator<Item = &'a str>) -> HashSet<String> {
    let mut set: HashSet<String> = BUILTIN_BLACKLIST.iter().map(|s| s.to_string()).collect();
    set.extend(
        user.into_iter()
            .map(normalize_exe)
            .filter(|s| !s.is_empty()),
    );
    set
}

pub struct Engine {
    pub name: &'static str,
    exe_patterns: Vec<Regex>,
    class_patterns: Vec<Regex>,
    dir_files: &'static [&'static str],
}

fn rx(patterns: &[&str]) -> Vec<Regex> {
    patterns
        .iter()
        .map(|p| Regex::new(p).expect("engine pattern"))
        .collect()
}

impl Engine {
    fn new(
        name: &'static str,
        exe: &[&str],
        class: &[&str],
        dir_files: &'static [&'static str],
    ) -> Self {
        Engine {
            name,
            exe_patterns: rx(exe),
            class_patterns: rx(class),
            dir_files,
        }
    }

    fn score(&self, win: &WindowInfo) -> u32 {
        let exe = win.exe().to_lowercase();
        let cls = win.class_name.to_lowercase();
        let mut pts = 0;
        if self
            .exe_patterns
            .iter()
            .any(|r| r.is_match(&exe).unwrap_or(false))
        {
            pts += 40;
        }
        if !self.dir_files.is_empty() && !win.exe_path.is_empty() {
            let listing: Vec<String> = Path::new(&win.exe_path)
                .parent()
                .and_then(|d| std::fs::read_dir(d).ok())
                .map(|it| {
                    it.flatten()
                        .map(|e| e.file_name().to_string_lossy().to_lowercase())
                        .collect()
                })
                .unwrap_or_default();
            if self
                .dir_files
                .iter()
                .any(|f| listing.iter().any(|n| n.contains(f)))
            {
                pts += 20;
            }
        }
        if pts > 0
            && self
                .class_patterns
                .iter()
                .any(|r| r.is_match(&cls).unwrap_or(false))
        {
            pts += 25;
        }
        pts
    }
}

static ENGINES: LazyLock<Vec<Engine>> = LazyLock::new(|| {
    vec![
        Engine::new(
            "Ren'Py",
            &[],
            &[r"^sdl_app$", r"pygame", r"renpy"],
            &[".rpa", ".rpyc", "renpy", "game/script"],
        ),
        Engine::new(
            "KiriKiri",
            &[r"^krkr", r"kirikiri"],
            &[r"^tform", r"kirikiri"],
            &[".xp3", "data.xp3", "startup.tjs"],
        ),
        Engine::new(
            "Buriko General Interpreter",
            &[r"^bgi\.exe$", r"ethornell"],
            &[],
            &["sysgrp.arc", "sysprg.arc", "data01000.arc", "bgi.gdb"],
        ),
        Engine::new("AdvHD", &[r"^advhd"], &[], &["rio.arc", ".ws2"]),
        Engine::new(
            "CatSystem2",
            &[r"^cs2\.exe$", r"catsystem"],
            &[],
            &["scene.int", "config.int", "cs2.conf"],
        ),
        Engine::new("KaGuYa", &[r"kaguya"], &[], &["message.dat"]),
        Engine::new("Majiro", &[r"majiro"], &[], &["scenario.arc", ".mjo"]),
        Engine::new("Musica", &[r"musica"], &[], &["scr.paz", "sys.paz"]),
        Engine::new("Propeller", &[], &[], &[".mpk"]),
        Engine::new("ShSystem", &[], &[], &[".hxp", ".hst"]),
        Engine::new("AI6WIN", &[r"^ai[56]win"], &[], &["mes.arc"]),
        Engine::new("Qlie", &[r"qlie"], &[], &[".pack", "gamedata"]),
        Engine::new("Softpal", &[], &[], &["pal.dll", "script.src"]),
        Engine::new("SystemNNN", &[r"systemnnn"], &[], &[".spt", ".nnn"]),
        Engine::new("TmrHiroAdvSystem", &[], &[], &[".srp"]),
        Engine::new(
            "TyranoScript",
            &[r"nw\.exe$", r"tyrano"],
            &[r"^nw_", r"chrome_widgetwin"],
            &["tyrano", "data/scenario"],
        ),
        Engine::new(
            "SiglusEngine",
            &[r"siglus", r"^gameexe"],
            &[],
            &["scene.pck", "gameexe.dat"],
        ),
        Engine::new(
            "RealLive",
            &[r"reallive", r"^rlvm"],
            &[],
            &["seen.txt", "gameexe.ini"],
        ),
        Engine::new("Artemis", &[r"artemis"], &[], &[".pfs", "root.pfs"]),
        Engine::new("YU-RIS", &[r"yuris", r"^ys_"], &[], &["ysbin", "ypf"]),
        Engine::new(
            "NScripter",
            &[r"nscr", r"onscripter", r"ons\.exe$"],
            &[],
            &["nscript.dat", "0.txt", "arc.nsa"],
        ),
        Engine::new(
            "Unity",
            &[],
            &[r"^unitywndclass$"],
            &["_data/globalgamemanagers", "unityplayer.dll"],
        ),
    ]
});

pub fn detect_engine(win: &WindowInfo) -> Option<(&'static Engine, u32)> {
    if BUILTIN_BLACKLIST.contains(&win.exe().to_lowercase().as_str()) {
        return None;
    }
    let mut best: Option<(&'static Engine, u32)> = None;
    for eng in ENGINES.iter() {
        let s = eng.score(win);
        if s > best.map_or(0, |(_, b)| b) {
            best = Some((eng, s));
        }
    }
    best.filter(|(_, s)| *s >= 20)
}

static COMMON_CLEANERS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    [
        r"\s*[-–—]\s*steam\s*$",
        r"[\(\[【]?R[\-\s]?18\+?[\)\]】]?(?:版|edition)?[@＠]*",
        r"\s*\[?\d{3,4}\s*[xX]\s*\d{3,4}\]?",
        r"\s*\bver(?:sion)?\.?\s*\d+(?:[.;]\d+)*[a-z]?\b",
        r"\s*\[ver\.[^\]]*\]",
        r"\s*[\[(]\s*v?\d+(?:[.;]\d+)+[a-z]?\s*[\])]",
        r"\s*\bv\d+(?:[.;]\d+)+[a-z]?\b",
        r"\s*(?<![\w/])\d+[.;]\d+(?:[.;]\d+)*[a-z]?\b",
        r"\s*\bfps[:=]?\s*\d+\b",
        r"\s*\bDirect3D\b|\s*\bOpenGL\b",
        r"\s*[\[(（【]\s*[\])）】]",
    ]
    .iter()
    .map(|p| Regex::new(&format!("(?i){p}")).expect("cleaner"))
    .collect()
});

static MULTI_SPACE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s{2,}").unwrap());

pub fn tidy(text: &str) -> String {
    let text = MULTI_SPACE.replace_all(text, " ");
    text.trim()
        .trim_matches(|c: char| " -–—|:·•".contains(c))
        .trim()
        .to_string()
}

pub fn clean_title(title: &str) -> String {
    let mut out = title.replace("\u{81}\u{40}", " ");
    for r in COMMON_CLEANERS.iter() {
        out = r.replace_all(&out, "").into_owned();
    }
    tidy(&out)
}
