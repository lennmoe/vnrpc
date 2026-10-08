use std::ffi::c_void;

use windows::core::{BOOL, PWSTR};
use windows::Win32::Foundation::{CloseHandle, HWND, LPARAM};
use windows::Win32::Foundation::{POINT, RECT};
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetCursorPos, GetForegroundWindow, GetSystemMetrics, GetWindow,
    GetWindowLongW, GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId, IsWindow,
    IsWindowVisible, SetWindowLongW, SystemParametersInfoW, GWL_EXSTYLE, GW_OWNER,
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SPI_GETWORKAREA,
    SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
};

#[derive(Debug, Clone, serde::Serialize)]
pub struct WindowInfo {
    pub hwnd: isize,
    pub title: String,
    pub pid: u32,
    pub exe_path: String,
    pub class_name: String,
}

impl WindowInfo {
    pub fn exe(&self) -> &str {
        self.exe_path.rsplit('\\').next().unwrap_or("")
    }
}

fn hwnd(h: isize) -> HWND {
    HWND(h as *mut c_void)
}

pub fn window_title(h: isize) -> String {
    unsafe {
        let len = GetWindowTextLengthW(hwnd(h));
        if len <= 0 {
            return String::new();
        }
        let mut buf = vec![0u16; len as usize + 1];
        let n = GetWindowTextW(hwnd(h), &mut buf);
        String::from_utf16_lossy(&buf[..n.max(0) as usize])
    }
}

fn class_name(h: isize) -> String {
    let mut buf = [0u16; 256];
    let n = unsafe { GetClassNameW(hwnd(h), &mut buf) };
    String::from_utf16_lossy(&buf[..n.max(0) as usize])
}

pub fn window_pid(h: isize) -> u32 {
    if h == 0 {
        return 0;
    }
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd(h), Some(&mut pid)) };
    pid
}

fn process_image_path(pid: u32) -> String {
    unsafe {
        let Ok(handle) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) else {
            return String::new();
        };
        let mut buf = vec![0u16; 32768];
        let mut size = buf.len() as u32;
        let ok = QueryFullProcessImageNameW(
            handle,
            PROCESS_NAME_WIN32,
            PWSTR(buf.as_mut_ptr()),
            &mut size,
        )
        .is_ok();
        let _ = CloseHandle(handle);
        if ok {
            String::from_utf16_lossy(&buf[..size as usize])
        } else {
            String::new()
        }
    }
}

pub fn is_window_visible(h: isize) -> bool {
    unsafe { IsWindow(Some(hwnd(h))).as_bool() && IsWindowVisible(hwnd(h)).as_bool() }
}

pub fn foreground_window() -> isize {
    unsafe { GetForegroundWindow().0 as isize }
}

unsafe extern "system" fn collect(h: HWND, lparam: LPARAM) -> BOOL {
    let out = &mut *(lparam.0 as *mut Vec<isize>);
    if !IsWindowVisible(h).as_bool() {
        return true.into();
    }
    if GetWindow(h, GW_OWNER)
        .map(|o| !o.0.is_null())
        .unwrap_or(false)
    {
        return true.into();
    }
    if GetWindowLongW(h, GWL_EXSTYLE) as u32 & WS_EX_TOOLWINDOW.0 != 0 {
        return true.into();
    }
    out.push(h.0 as isize);
    true.into()
}

pub fn list_top_level_windows() -> Vec<WindowInfo> {
    let mut handles: Vec<isize> = Vec::new();
    unsafe {
        let _ = EnumWindows(
            Some(collect),
            LPARAM(&mut handles as *mut Vec<isize> as isize),
        );
    }
    let own_pid = std::process::id();
    let mut out = Vec::new();
    for h in handles {
        let pid = window_pid(h);
        if pid == own_pid {
            continue;
        }

        let title = window_title(h);
        if title.trim().is_empty() {
            continue;
        }
        out.push(WindowInfo {
            hwnd: h,
            title,
            pid,
            exe_path: process_image_path(pid),
            class_name: class_name(h),
        });
    }
    out
}

pub fn make_no_activate(h: isize) {
    unsafe {
        let style = GetWindowLongW(hwnd(h), GWL_EXSTYLE) as u32;
        let style = style | WS_EX_NOACTIVATE.0 | WS_EX_TOOLWINDOW.0;
        SetWindowLongW(hwnd(h), GWL_EXSTYLE, style as i32);
    }
}

pub fn work_area() -> (i32, i32, i32, i32) {
    let mut rect = RECT::default();
    unsafe {
        let _ = SystemParametersInfoW(
            SPI_GETWORKAREA,
            0,
            Some(&mut rect as *mut RECT as *mut c_void),
            SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0),
        );
    }
    (rect.left, rect.top, rect.right, rect.bottom)
}

pub fn virtual_screen() -> (i32, i32, i32, i32) {
    unsafe {
        (
            GetSystemMetrics(SM_XVIRTUALSCREEN),
            GetSystemMetrics(SM_YVIRTUALSCREEN),
            GetSystemMetrics(SM_CXVIRTUALSCREEN),
            GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )
    }
}

pub fn cursor_pos() -> Option<(i32, i32)> {
    let mut point = POINT::default();
    unsafe { GetCursorPos(&mut point).ok()? };
    Some((point.x, point.y))
}
