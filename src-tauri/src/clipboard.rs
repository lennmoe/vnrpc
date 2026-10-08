use std::time::Duration;

use image::RgbImage;
use windows::core::w;
use windows::Win32::Foundation::{GlobalFree, HANDLE, HGLOBAL};
use windows::Win32::System::DataExchange::{
    CloseClipboard, EmptyClipboard, OpenClipboard, RegisterClipboardFormatW, SetClipboardData,
};
use windows::Win32::System::Memory::{GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE};

const CF_DIB: u32 = 8;

pub fn copy_png(png: &[u8]) -> Result<(), String> {
    let img = image::load_from_memory(png)
        .map_err(|e| e.to_string())?
        .to_rgb8();
    let dib = dib_from(&img);

    open_clipboard()?;
    let result = unsafe { fill_clipboard(&dib, png) };
    unsafe {
        let _ = CloseClipboard();
    }
    result
}

fn open_clipboard() -> Result<(), String> {
    for _ in 0..10 {
        if unsafe { OpenClipboard(None) }.is_ok() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    Err("the clipboard is busy".into())
}

unsafe fn fill_clipboard(dib: &[u8], png: &[u8]) -> Result<(), String> {
    EmptyClipboard().map_err(|e| e.to_string())?;

    let png_format = RegisterClipboardFormatW(w!("PNG"));
    for (format, data) in [(CF_DIB, dib), (png_format, png)] {
        let handle = global_copy(data)?;
        if SetClipboardData(format, Some(HANDLE(handle.0))).is_err() {
            let _ = GlobalFree(Some(handle));
            return Err("Windows refused the clipboard data".into());
        }
    }
    Ok(())
}

unsafe fn global_copy(data: &[u8]) -> Result<HGLOBAL, String> {
    let handle = GlobalAlloc(GMEM_MOVEABLE, data.len()).map_err(|_| "out of memory".to_string())?;
    let ptr = GlobalLock(handle);
    if ptr.is_null() {
        let _ = GlobalFree(Some(handle));
        return Err("out of memory".into());
    }
    std::ptr::copy_nonoverlapping(data.as_ptr(), ptr as *mut u8, data.len());
    let _ = GlobalUnlock(handle);
    Ok(handle)
}

fn dib_from(img: &RgbImage) -> Vec<u8> {
    let (w, h) = (img.width() as usize, img.height() as usize);
    let stride = (w * 3 + 3) & !3;

    let mut out = Vec::with_capacity(40 + stride * h);
    out.extend_from_slice(&40u32.to_le_bytes());
    out.extend_from_slice(&(w as i32).to_le_bytes());
    out.extend_from_slice(&(h as i32).to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&24u16.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&((stride * h) as u32).to_le_bytes());
    out.extend_from_slice(&[0u8; 16]);

    for y in (0..h).rev() {
        let row_start = out.len();
        for x in 0..w {
            let [r, g, b] = img.get_pixel(x as u32, y as u32).0;
            out.extend_from_slice(&[b, g, r]);
        }
        out.resize(row_start + stride, 0);
    }
    out
}
