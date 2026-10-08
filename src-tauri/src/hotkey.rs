use std::sync::{Arc, Mutex};

use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState;
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, MsgWaitForMultipleObjects, PeekMessageW, SetWindowsHookExW,
    UnhookWindowsHookEx, HHOOK, KBDLLHOOKSTRUCT, MSG, PM_REMOVE, QS_ALLINPUT, WH_KEYBOARD_LL,
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
};

use crate::state::Shared;
use crate::winapi;

const MOD_ALT: u32 = 0x1;
const MOD_CONTROL: u32 = 0x2;
const MOD_SHIFT: u32 = 0x4;
const MOD_WIN: u32 = 0x8;

const MODIFIERS: [(&str, u32); 4] = [
    ("Ctrl", MOD_CONTROL),
    ("Alt", MOD_ALT),
    ("Shift", MOD_SHIFT),
    ("Win", MOD_WIN),
];

const MODIFIER_KEYS: [(u32, &[i32]); 4] = [
    (MOD_CONTROL, &[0x11]),
    (MOD_ALT, &[0x12]),
    (MOD_SHIFT, &[0x10]),
    (MOD_WIN, &[0x5B, 0x5C]),
];

const NAMED_KEYS: [(&str, u32); 31] = [
    ("PrintScreen", 0x2C),
    ("Pause", 0x13),
    ("Insert", 0x2D),
    ("Delete", 0x2E),
    ("Home", 0x24),
    ("End", 0x23),
    ("PageUp", 0x21),
    ("PageDown", 0x22),
    ("ScrollLock", 0x91),
    ("Space", 0x20),
    ("Tab", 0x09),
    ("Left", 0x25),
    ("Up", 0x26),
    ("Right", 0x27),
    ("Down", 0x28),
    ("Numpad0", 0x60),
    ("Numpad1", 0x61),
    ("Numpad2", 0x62),
    ("Numpad3", 0x63),
    ("Numpad4", 0x64),
    ("Numpad5", 0x65),
    ("Numpad6", 0x66),
    ("Numpad7", 0x67),
    ("Numpad8", 0x68),
    ("Numpad9", 0x69),
    ("NumpadMultiply", 0x6A),
    ("NumpadAdd", 0x6B),
    ("NumpadSubtract", 0x6D),
    ("NumpadDecimal", 0x6E),
    ("NumpadDivide", 0x6F),
    ("Escape", 0x1B),
];

fn vk_for(name: &str) -> Option<u32> {
    let upper = name.to_uppercase();

    if name.len() == 1 && name.chars().all(|c| c.is_ascii_alphanumeric()) {
        return Some(upper.chars().next()? as u32);
    }

    if let Some(n) = upper.strip_prefix('F').and_then(|n| n.parse::<u32>().ok()) {
        if (1..=24).contains(&n) {
            return Some(0x70 + n - 1);
        }
    }

    NAMED_KEYS
        .iter()
        .find(|(key, _)| key.to_uppercase() == upper)
        .map(|(_, vk)| *vk)
}

pub fn parse(text: &str) -> Option<(u32, u32)> {
    let parts: Vec<&str> = text
        .split('+')
        .map(str::trim)
        .filter(|p| !p.is_empty())
        .collect();
    let (key, mods) = parts.split_last()?;

    let mut flags = 0;
    for part in mods {
        let (_, flag) = MODIFIERS
            .iter()
            .find(|(name, _)| name.eq_ignore_ascii_case(part))?;
        flags |= flag;
    }

    Some((flags, vk_for(key)?))
}

pub fn normalize(text: &str) -> String {
    let Some((mods, vk)) = parse(text) else {
        return String::new();
    };

    let key = if (0x70..=0x87).contains(&vk) {
        format!("F{}", vk - 0x6F)
    } else if let Some((name, _)) = NAMED_KEYS.iter().find(|(_, code)| *code == vk) {
        name.to_string()
    } else {
        char::from_u32(vk).map(String::from).unwrap_or_default()
    };

    let mut parts: Vec<String> = MODIFIERS
        .iter()
        .filter(|(_, flag)| mods & flag != 0)
        .map(|(name, _)| name.to_string())
        .collect();
    parts.push(key);
    parts.join("+")
}

fn held_modifiers() -> u32 {
    let is_down = |vk: i32| unsafe { GetAsyncKeyState(vk) } as u16 & 0x8000 != 0;

    MODIFIER_KEYS
        .iter()
        .filter(|(_, keys)| keys.iter().any(|vk| is_down(*vk)))
        .map(|(flag, _)| flag)
        .sum()
}

struct HookState {
    combo: Option<(u32, u32)>,
    held: bool,
    target_pid: u32,
    shared: Option<Arc<Shared>>,
}

static STATE: Mutex<HookState> = Mutex::new(HookState {
    combo: None,
    held: false,
    target_pid: 0,
    shared: None,
});

fn game_in_front(pid: u32) -> bool {
    pid != 0 && winapi::window_pid(winapi::foreground_window()) == pid
}

fn handle_key(msg: u32, vk: u32) -> bool {
    let mut state = STATE.lock().unwrap();
    let Some((mods, key)) = state.combo else {
        return false;
    };
    if vk != key {
        return false;
    }

    let pressed = msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN;
    let released = msg == WM_KEYUP || msg == WM_SYSKEYUP;

    if pressed {
        if state.held {
            return true;
        }
        if held_modifiers() != mods || !game_in_front(state.target_pid) {
            return false;
        }
        state.held = true;
        fire(&state);
        return true;
    }

    if released {
        if state.held {
            state.held = false;
            return true;
        }
        if held_modifiers() == mods && game_in_front(state.target_pid) {
            fire(&state);
            return true;
        }
    }
    false
}

fn fire(state: &HookState) {
    if let Some(shared) = state.shared.clone() {
        std::thread::spawn(move || crate::screenshots::take(&shared));
    }
}

unsafe extern "system" fn hook_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code == 0 {
        let info = &*(lparam.0 as *const KBDLLHOOKSTRUCT);
        if handle_key(wparam.0 as u32, info.vkCode) {
            return LRESULT(1);
        }
    }
    CallNextHookEx(None, code, wparam, lparam)
}

pub fn run(shared: Arc<Shared>) {
    STATE.lock().unwrap().shared = Some(Arc::clone(&shared));

    let mut hook: Option<HHOOK> = None;
    let mut active: Option<(u32, u32)> = None;
    let mut reported = false;
    let mut msg = MSG::default();

    loop {
        unsafe { while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {} }

        let pid = shared.snapshot().pid;
        let hotkey = shared.config.lock().unwrap().str("screenshot_hotkey");
        let wanted = if game_in_front(pid) {
            parse(&hotkey)
        } else {
            None
        };

        {
            let mut state = STATE.lock().unwrap();
            state.target_pid = pid;

            if wanted != active {
                if let Some(h) = hook.take() {
                    unsafe {
                        let _ = UnhookWindowsHookEx(h);
                    }
                }
                state.combo = None;
                state.held = false;

                if wanted.is_some() {
                    match install_hook() {
                        Some(h) => {
                            hook = Some(h);
                            state.combo = wanted;
                        }
                        None if !reported => {
                            reported = true;
                            shared.emit(
                                "toast",
                                serde_json::json!({
                                    "title": "Couldn't watch the screenshot key",
                                    "ok": false,
                                }),
                            );
                        }
                        None => {}
                    }
                }
                active = wanted;
            }
        }

        unsafe {
            MsgWaitForMultipleObjects(None, false, 100, QS_ALLINPUT);
        }
    }
}

fn install_hook() -> Option<HHOOK> {
    unsafe {
        let module = GetModuleHandleW(None).ok()?;
        SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), Some(module.into()), 0).ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hotkeys_are_normalized_like_python() {
        assert_eq!(normalize("shift+ctrl+f12"), "Ctrl+Shift+F12");
        assert_eq!(normalize("PrintScreen"), "PrintScreen");
        assert_eq!(normalize("alt+s"), "Alt+S");
        assert_eq!(normalize("Ctrl+"), "");
        assert_eq!(normalize("Hyper+S"), "");
        assert_eq!(normalize(""), "");
    }
}
