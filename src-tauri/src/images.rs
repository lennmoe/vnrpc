use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};

use base64::Engine as _;
use image::codecs::jpeg::JpegEncoder;
use image::imageops::FilterType;
use image::{DynamicImage, RgbImage};

fn short_hash(data: &[u8], len: usize) -> String {
    sha1_smol::Sha1::from(data).digest().to_string()[..len].to_string()
}

fn open(path: &Path) -> Result<DynamicImage, String> {
    image::open(path).map_err(|e| format!("can't open the image: {e}"))
}

pub fn cover_fit(img: &DynamicImage, w: u32, h: u32, filter: FilterType) -> RgbImage {
    img.resize_to_fill(w, h, filter).to_rgb8()
}

pub fn store_download(downloads_dir: &Path, url: &str, bytes: &[u8]) -> Result<PathBuf, String> {
    let format = image::guess_format(bytes).map_err(|_| "that link isn't an image".to_string())?;
    let ext = format.extensions_str().first().copied().unwrap_or("img");

    let dest = downloads_dir.join(format!("{}.{ext}", short_hash(url.as_bytes(), 16)));
    fs::create_dir_all(downloads_dir).map_err(|e| e.to_string())?;
    fs::write(&dest, bytes).map_err(|e| e.to_string())?;
    Ok(dest)
}

pub fn thumbnail(thumbs_dir: &Path, path: &Path, w: u32, h: u32) -> Result<PathBuf, String> {
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    let stamp = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_nanos())
        .unwrap_or(0);

    let tag = format!("{}|{stamp}|{}|{w}x{h}", path.display(), meta.len());
    let cached = thumbs_dir.join(format!("{}.jpg", short_hash(tag.as_bytes(), 24)));
    if cached.exists() {
        return Ok(cached);
    }

    let thumb = cover_fit(&open(path)?, w, h, FilterType::Triangle);
    fs::create_dir_all(thumbs_dir).map_err(|e| e.to_string())?;
    let file = fs::File::create(&cached).map_err(|e| e.to_string())?;
    JpegEncoder::new_with_quality(file, 88)
        .encode_image(&thumb)
        .map_err(|e| e.to_string())?;
    Ok(cached)
}

pub fn data_url(path: &Path, w: u32, h: u32) -> Result<String, String> {
    let fitted = cover_fit(&open(path)?, w, h, FilterType::Lanczos3);

    let mut jpeg = Vec::new();
    JpegEncoder::new_with_quality(Cursor::new(&mut jpeg), 90)
        .encode_image(&fitted)
        .map_err(|e| e.to_string())?;

    let encoded = base64::engine::general_purpose::STANDARD.encode(jpeg);
    Ok(format!("data:image/jpeg;base64,{encoded}"))
}
