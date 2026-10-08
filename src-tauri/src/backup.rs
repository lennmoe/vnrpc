use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipArchive, ZipWriter};

use crate::config::{safe_filename, Config, Entry};

const FORMAT: i64 = 1;
const MANIFEST: &str = "vnrpc-backup.json";

pub fn default_name() -> String {
    chrono::Local::now()
        .format("VisualNovelRPC-backup-%Y-%m-%d.zip")
        .to_string()
}

pub fn backup_dir(cfg: &Config) -> PathBuf {
    cfg.dir.join("backups")
}

fn yaml(value: &Map<String, Value>) -> Result<String, String> {
    serde_yaml::to_string(value).map_err(|e| e.to_string())
}

fn local_cover(entry: &Entry) -> Option<PathBuf> {
    if entry.get("cover_source").and_then(Value::as_str) != Some("local") {
        return None;
    }
    let path = PathBuf::from(entry.get("cover_value").and_then(Value::as_str)?);
    path.is_file().then_some(path)
}

pub fn export(cfg: &Config, dest: &Path) -> Result<usize, String> {
    let part = dest.with_extension("zip.part");
    let result = write_zip(cfg, &part);

    match result {
        Ok(count) => {
            fs::rename(&part, dest).map_err(|e| e.to_string())?;
            Ok(count)
        }
        Err(e) => {
            let _ = fs::remove_file(&part);
            Err(e)
        }
    }
}

fn write_zip(cfg: &Config, path: &Path) -> Result<usize, String> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let file = File::create(path).map_err(|e| e.to_string())?;
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);

    let add = |zip: &mut ZipWriter<File>, name: &str, bytes: &[u8]| -> Result<(), String> {
        zip.start_file(name, options).map_err(|e| e.to_string())?;
        zip.write_all(bytes).map_err(|e| e.to_string())
    };

    add(&mut zip, "config.yaml", yaml(cfg.data())?.as_bytes())?;

    let mut covers = Map::new();
    let games = cfg.all_games();
    for (n, (key, entry)) in games.iter().enumerate() {
        let n = n + 1;
        let mut with_key = entry.clone();
        with_key.insert("_key".into(), json!(key));
        add(
            &mut zip,
            &format!("games/{n:04}.yaml"),
            yaml(&with_key)?.as_bytes(),
        )?;

        if let Some(cover) = local_cover(entry) {
            let name = cover
                .file_name()
                .map(|f| f.to_string_lossy().to_string())
                .unwrap_or_default();
            let arc = format!("covers/{n:04}_{}", safe_filename(&name));
            let bytes = fs::read(&cover).map_err(|e| e.to_string())?;
            add(&mut zip, &arc, &bytes)?;
            covers.insert(key.clone(), json!(arc));
        }
    }

    let manifest = json!({
        "format": FORMAT,
        "app_version": env!("CARGO_PKG_VERSION"),
        "exported_at": chrono::Utc::now().timestamp(),
        "games": games.len(),
        "covers": covers,
    });
    add(
        &mut zip,
        MANIFEST,
        serde_json::to_string_pretty(&manifest).unwrap().as_bytes(),
    )?;

    zip.finish().map_err(|e| e.to_string())?;
    Ok(games.len())
}

fn read_entry(zip: &mut ZipArchive<File>, name: &str) -> Result<Vec<u8>, String> {
    let mut file = zip
        .by_name(name)
        .map_err(|_| format!("{name} is missing"))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    Ok(bytes)
}

fn read_yaml(zip: &mut ZipArchive<File>, name: &str) -> Result<Map<String, Value>, String> {
    let bytes = read_entry(zip, name)?;
    match serde_yaml::from_slice::<Value>(&bytes) {
        Ok(Value::Object(map)) => Ok(map),
        Ok(_) => Ok(Map::new()),
        Err(e) => Err(format!("{name} is damaged ({e})")),
    }
}

pub fn import(cfg: &mut Config, src: &Path) -> Result<usize, String> {
    let file = File::open(src).map_err(|e| e.to_string())?;
    let mut zip = ZipArchive::new(file).map_err(|_| "not a Visual Novel RPC backup".to_string())?;

    let manifest: Value = read_entry(&mut zip, MANIFEST)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .ok_or("not a Visual Novel RPC backup")?;
    if manifest["format"].as_i64().unwrap_or(0) > FORMAT {
        return Err("this backup was made by a newer version of the app: update it first".into());
    }

    let data =
        read_yaml(&mut zip, "config.yaml").map_err(|_| "the backup is missing its settings")?;

    let mut games: Vec<(String, Entry)> = Vec::new();
    let names: Vec<String> = zip.file_names().map(str::to_string).collect();
    for name in names
        .iter()
        .filter(|n| n.starts_with("games/") && n.ends_with(".yaml"))
    {
        let mut entry = read_yaml(&mut zip, name)?;
        if let Some(Value::String(key)) = entry.remove("_key") {
            if !key.is_empty() {
                games.push((key, entry));
            }
        }
    }

    let stamp = chrono::Local::now().format("before-import-%Y-%m-%d_%H-%M-%S.zip");
    export(cfg, &backup_dir(cfg).join(stamp.to_string()))?;

    let covers_dir = cfg.covers_dir().join("local");
    fs::create_dir_all(&covers_dir).map_err(|e| e.to_string())?;
    let covers = manifest["covers"].as_object().cloned().unwrap_or_default();
    for (key, entry) in games.iter_mut() {
        let Some(arc) = covers.get(key.as_str()).and_then(Value::as_str) else {
            continue;
        };
        let Ok(bytes) = read_entry(&mut zip, arc) else {
            continue;
        };
        let file_name = arc.rsplit('/').next().unwrap_or(arc);
        let dest = covers_dir.join(safe_filename(file_name));
        fs::write(&dest, bytes).map_err(|e| e.to_string())?;
        entry.insert("cover_value".into(), json!(dest.to_string_lossy()));
    }

    let count = games.len();
    cfg.replace_all(data, games).map_err(|e| e.to_string())?;
    Ok(count)
}
