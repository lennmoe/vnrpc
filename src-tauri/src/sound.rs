use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use windows::core::HSTRING;
use windows::Win32::Media::Multimedia::mciSendStringW;
use windows::Win32::System::Com::{CoInitializeEx, COINIT_APARTMENTTHREADED};
use windows::Win32::UI::WindowsAndMessaging::{PeekMessageW, MSG, PM_REMOVE};

const SHUTTER_MP3: &[u8] = include_bytes!("../assets/screenshot.mp3");
const ALIAS: &str = "vnrpc_shutter";

enum Request {
    Play(i64),
    #[allow(dead_code)]
    Status(Sender<String>),
}

static PLAYER: OnceLock<Mutex<Sender<Request>>> = OnceLock::new();

fn mci(command: &str) -> bool {
    unsafe { mciSendStringW(&HSTRING::from(command), None, None) == 0 }
}

pub fn play_shutter(cache_dir: &Path, volume: i64) {
    if volume > 0 {
        send(cache_dir, Request::Play(volume));
    }
}

fn send(cache_dir: &Path, request: Request) {
    let player = PLAYER.get_or_init(|| {
        let (requests, queue) = mpsc::channel();
        let file = cache_dir.join("shutter.mp3");
        std::thread::Builder::new()
            .name("sound".into())
            .spawn(move || run(file, queue))
            .expect("sound thread");
        Mutex::new(requests)
    });

    let _ = player.lock().unwrap().send(request);
}

fn run(file: PathBuf, queue: mpsc::Receiver<Request>) {
    unsafe {
        let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
    }

    let opened = std::fs::write(&file, SHUTTER_MP3).is_ok()
        && mci(&format!(
            "open \"{}\" type mpegvideo alias {ALIAS}",
            file.display()
        ));
    if !opened {
        return;
    }

    let mut msg = MSG::default();
    loop {
        match queue.recv_timeout(Duration::from_millis(50)) {
            Ok(Request::Play(volume)) => {
                mci(&format!(
                    "setaudio {ALIAS} volume to {}",
                    volume.min(100) * 10
                ));
                mci(&format!("play {ALIAS} from 0"));
            }
            Ok(Request::Status(reply)) => {
                let mut answer = [0u16; 64];
                let command = HSTRING::from(format!("status {ALIAS} mode"));
                unsafe { mciSendStringW(&command, Some(&mut answer), None) };
                let text = String::from_utf16_lossy(&answer);
                let _ = reply.send(text.trim_end_matches('\0').to_string());
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }

        unsafe { while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {} }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore]
    fn shutter_plays() {
        let dir = std::env::temp_dir();
        play_shutter(&dir, 30);
        std::thread::sleep(Duration::from_millis(300));

        let (reply, answer) = mpsc::channel();
        send(&dir, Request::Status(reply));
        let mode = answer.recv_timeout(Duration::from_secs(2)).unwrap();
        assert_eq!(mode, "playing");
    }
}
