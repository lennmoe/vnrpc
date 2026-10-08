use std::ffi::c_void;

use image::RgbImage;
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Gdi::{
    BitBlt, ClientToScreen, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject,
    GetDC, GetDIBits, ReleaseDC, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    DIB_RGB_COLORS, HBITMAP, HDC, SRCCOPY,
};
use windows::Win32::Storage::Xps::{PrintWindow, PRINT_WINDOW_FLAGS};
use windows::Win32::UI::WindowsAndMessaging::{GetClientRect, GetWindowRect, IsIconic, IsWindow};

const PW_RENDERFULLCONTENT: u32 = 0x2;

#[derive(Debug, Clone, Copy)]
pub struct ScreenRect {
    pub left: i32,
    pub top: i32,
    pub right: i32,
    pub bottom: i32,
}

impl ScreenRect {
    fn width(&self) -> i32 {
        self.right - self.left
    }

    fn height(&self) -> i32 {
        self.bottom - self.top
    }
}

fn hwnd(handle: isize) -> HWND {
    HWND(handle as *mut c_void)
}

pub fn client_rect_on_screen(handle: isize) -> ScreenRect {
    let mut rect = RECT::default();
    let mut origin = POINT::default();
    unsafe {
        let _ = GetClientRect(hwnd(handle), &mut rect);
        let _ = ClientToScreen(hwnd(handle), &mut origin);
    }

    ScreenRect {
        left: origin.x,
        top: origin.y,
        right: origin.x + rect.right,
        bottom: origin.y + rect.bottom,
    }
}

pub fn capture_window(handle: isize) -> Result<RgbImage, String> {
    unsafe {
        if handle == 0 || !IsWindow(Some(hwnd(handle))).as_bool() {
            return Err("The game's window is gone.".into());
        }
        if IsIconic(hwnd(handle)).as_bool() {
            return Err("The game is minimized.".into());
        }
    }

    let client = client_rect_on_screen(handle);
    if client.width() < 2 || client.height() < 2 {
        return Err("The game's window has no visible content.".into());
    }

    if let Some(img) = print_window(handle, client) {
        if !is_all_black(&img) {
            return Ok(img);
        }
    }

    copy_screen(client).ok_or_else(|| "Windows refused the capture.".to_string())
}

fn is_all_black(img: &RgbImage) -> bool {
    img.pixels().all(|p| p.0 == [0, 0, 0])
}

fn print_window(handle: isize, client: ScreenRect) -> Option<RgbImage> {
    let mut win = RECT::default();
    unsafe { GetWindowRect(hwnd(handle), &mut win).ok()? };

    let (w, h) = (win.right - win.left, win.bottom - win.top);
    if w <= 0 || h <= 0 {
        return None;
    }

    let full = with_bitmap(w, h, |mem| unsafe {
        PrintWindow(hwnd(handle), mem, PRINT_WINDOW_FLAGS(PW_RENDERFULLCONTENT)).as_bool()
    })?;

    let x = (client.left - win.left).max(0) as u32;
    let y = (client.top - win.top).max(0) as u32;
    let cw = (client.width() as u32).min(full.width().saturating_sub(x));
    let ch = (client.height() as u32).min(full.height().saturating_sub(y));
    Some(image::imageops::crop_imm(&full, x, y, cw, ch).to_image())
}

fn copy_screen(area: ScreenRect) -> Option<RgbImage> {
    with_bitmap(area.width(), area.height(), |mem| unsafe {
        let screen = GetDC(None);
        let ok = BitBlt(
            mem,
            0,
            0,
            area.width(),
            area.height(),
            Some(screen),
            area.left,
            area.top,
            SRCCOPY,
        )
        .is_ok();
        ReleaseDC(None, screen);
        ok
    })
}

fn with_bitmap(w: i32, h: i32, draw: impl FnOnce(HDC) -> bool) -> Option<RgbImage> {
    unsafe {
        let screen = GetDC(None);
        let mem = CreateCompatibleDC(Some(screen));
        let bitmap = CreateCompatibleBitmap(screen, w, h);
        let old = SelectObject(mem, bitmap.into());

        let image = if draw(mem) {
            read_bitmap(mem, bitmap, w, h)
        } else {
            None
        };

        SelectObject(mem, old);
        let _ = DeleteObject(bitmap.into());
        let _ = DeleteDC(mem);
        ReleaseDC(None, screen);
        image
    }
}

unsafe fn read_bitmap(dc: HDC, bitmap: HBITMAP, w: i32, h: i32) -> Option<RgbImage> {
    let mut info = BITMAPINFO {
        bmiHeader: BITMAPINFOHEADER {
            biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: w,
            biHeight: -h,
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB.0,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut bgra = vec![0u8; (w * h * 4) as usize];
    let lines = GetDIBits(
        dc,
        bitmap,
        0,
        h as u32,
        Some(bgra.as_mut_ptr() as *mut c_void),
        &mut info,
        DIB_RGB_COLORS,
    );
    if lines == 0 {
        return None;
    }

    let rgb: Vec<u8> = bgra
        .chunks_exact(4)
        .flat_map(|px| [px[2], px[1], px[0]])
        .collect();
    RgbImage::from_raw(w as u32, h as u32, rgb)
}
