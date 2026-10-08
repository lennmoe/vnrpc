use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use windows::core::{HSTRING, PCWSTR};
use windows::Win32::System::Com::CoTaskMemFree;
use windows::Win32::UI::Shell::{
    FOLDERID_Pictures, SHFileOperationW, SHGetKnownFolderPath, ShellExecuteW, KNOWN_FOLDER_FLAG,
    SHFILEOPSTRUCTW,
};
use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

pub fn open(target: &str) -> Result<(), String> {
    shell_execute(target, "", None)
}

pub fn start_program(program: &Path, params: &str, cwd: &Path) -> Result<(), String> {
    shell_execute(&program.to_string_lossy(), params, Some(cwd))
}

fn shell_execute(target: &str, params: &str, cwd: Option<&Path>) -> Result<(), String> {
    let target = HSTRING::from(target);
    let params = HSTRING::from(params);
    let cwd = HSTRING::from(
        cwd.map(|p| p.to_string_lossy().to_string())
            .unwrap_or_default(),
    );

    let result = unsafe {
        ShellExecuteW(
            None,
            &HSTRING::from("open"),
            &target,
            if params.is_empty() {
                PCWSTR::null()
            } else {
                PCWSTR(params.as_ptr())
            },
            if cwd.is_empty() {
                PCWSTR::null()
            } else {
                PCWSTR(cwd.as_ptr())
            },
            SW_SHOWNORMAL,
        )
    };

    if result.0 as isize > 32 {
        Ok(())
    } else {
        Err(format!(
            "Windows couldn't open it (error {})",
            result.0 as isize
        ))
    }
}

pub fn show_in_folder(path: &Path) -> Result<(), String> {
    Command::new("explorer")
        .raw_arg(format!("/select,\"{}\"", path.display()))
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

pub fn send_to_recycle_bin(path: &Path) -> Result<(), String> {
    const FO_DELETE: u32 = 3;
    const FOF_SILENT: u16 = 0x4;
    const FOF_NOCONFIRMATION: u16 = 0x10;
    const FOF_ALLOWUNDO: u16 = 0x40;
    const FOF_NOERRORUI: u16 = 0x400;

    let mut from: Vec<u16> = path.to_string_lossy().encode_utf16().collect();
    from.extend([0, 0]);

    let mut op = SHFILEOPSTRUCTW {
        wFunc: FO_DELETE,
        pFrom: PCWSTR(from.as_ptr()),
        fFlags: FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
        ..Default::default()
    };

    let code = unsafe { SHFileOperationW(&mut op) };
    if code != 0 || op.fAnyOperationsAborted.as_bool() {
        return Err(format!(
            "couldn't move it to the Recycle Bin (error {code})"
        ));
    }
    Ok(())
}

pub fn pictures_folder() -> PathBuf {
    unsafe {
        if let Ok(ptr) = SHGetKnownFolderPath(&FOLDERID_Pictures, KNOWN_FOLDER_FLAG(0), None) {
            let path = ptr.to_string().unwrap_or_default();
            CoTaskMemFree(Some(ptr.0 as *const _));
            if !path.is_empty() {
                return PathBuf::from(path);
            }
        }
    }

    let home = std::env::var("USERPROFILE").unwrap_or_default();
    PathBuf::from(home).join("Pictures")
}
