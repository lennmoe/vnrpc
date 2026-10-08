use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};

use base64::Engine as _;
use image::codecs::jpeg::JpegEncoder;
use image::imageops::FilterType;
use image::{DynamicImage, RgbImage};

const IMAGE_EXTS: [&str; 6] = ["png", "jpg", "jpeg", "webp", "gif", "bmp"];

fn short_hash(data: &[u8], len: usize) -> String {
    sha1_smol::Sha1::from(data).digest().to_string()[..len].to_string()
}

fn extension(path: &Path) -> String {
    path.extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default()
}

fn open(path: &Path) -> Result<DynamicImage, String> {
    image::open(path).map_err(|e| format!("can't open the image: {e}"))
}

pub fn cover_fit(img: &DynamicImage, w: u32, h: u32, filter: FilterType) -> RgbImage {
    img.resize_to_fill(w, h, filter).to_rgb8()
}

pub fn store_local_cover(covers_dir: &Path, source: &Path) -> Result<PathBuf, String> {
    let ext = extension(source);
    if !source.is_file() || !IMAGE_EXTS.contains(&ext.as_str()) {
        return Err("that file isn't an image".into());
    }
    open(source)?;

    let resolved = fs::canonicalize(source).unwrap_or_else(|_| source.to_path_buf());
    let name = format!(
        "{}.{ext}",
        short_hash(resolved.to_string_lossy().as_bytes(), 16)
    );
    let dest = covers_dir.join("local").join(name);

    fs::create_dir_all(dest.parent().unwrap()).map_err(|e| e.to_string())?;
    if !dest.exists() {
        fs::copy(source, &dest).map_err(|e| e.to_string())?;
    }
    Ok(dest)
}

pub fn crop_cover(
    covers_dir: &Path,
    source: &Path,
    x: u32,
    y: u32,
    w: u32,
    h: u32,
) -> Result<PathBuf, String> {
    let img = open(source)?;
    let w = w.min(img.width().saturating_sub(x)).max(1);
    let h = h.min(img.height().saturating_sub(y)).max(1);
    let cropped = img.crop_imm(x, y, w, h).to_rgb8();

    let name = format!("crop_{}.png", short_hash(cropped.as_raw(), 16));
    let dest = covers_dir.join("local").join(name);

    fs::create_dir_all(dest.parent().unwrap()).map_err(|e| e.to_string())?;
    if !dest.exists() {
        cropped.save(&dest).map_err(|e| e.to_string())?;
    }
    Ok(dest)
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
