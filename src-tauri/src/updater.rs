use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const REPO: &str = "lennmoe/vnrpc";
pub const CURRENT: &str = env!("CARGO_PKG_VERSION");

fn http() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .user_agent(format!("VisualNovelRPC/{CURRENT}"))
        .timeout(Duration::from_secs(10))
        .build()
        .expect("http client")
}

fn get_json(url: &str) -> Result<Value, String> {
    http()
        .get(url)
        .header("Accept", "application/vnd.github+json")
        .send()
        .and_then(|r| r.error_for_status())
        .and_then(|r| r.json())
        .map_err(|e| e.to_string())
}

pub fn parse_version(tag: &str) -> Vec<u64> {
    let digits = tag.trim().trim_start_matches(['v', 'V']);
    let end = digits
        .find(|c: char| !(c.is_ascii_digit() || c == '.'))
        .unwrap_or(digits.len());
    let mut parts = Vec::new();
    for piece in digits[..end].split('.') {
        match piece.parse() {
            Ok(n) => parts.push(n),
            Err(_) => break,
        }
    }
    parts
}

pub fn is_newer(tag: &str, current: &str) -> bool {
    let mut new = parse_version(tag);
    let mut cur = parse_version(current);
    if new.is_empty() {
        return false;
    }
    let width = new.len().max(cur.len());
    new.resize(width, 0);
    cur.resize(width, 0);
    new > cur
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Release {
    pub version: String,
    pub url: String,
    pub size: u64,
    pub sha256: String,
    pub notes: String,
    pub page: String,
}

pub fn find_update() -> Result<Option<Release>, String> {
    let data = get_json(&format!(
        "https://api.github.com/repos/{REPO}/releases/latest"
    ))?;

    let tag = data["tag_name"].as_str().unwrap_or("");
    let draft = data["draft"].as_bool().unwrap_or(false);
    let prerelease = data["prerelease"].as_bool().unwrap_or(false);
    if draft || prerelease || !is_newer(tag, CURRENT) {
        return Ok(None);
    }

    let asset = data["assets"]
        .as_array()
        .into_iter()
        .flatten()
        .find(|asset| {
            let name = asset["name"].as_str().unwrap_or("").to_lowercase();
            name.ends_with(".exe")
        });
    let Some(asset) = asset else {
        return Ok(None);
    };

    let digest = asset["digest"].as_str().unwrap_or("");
    Ok(Some(Release {
        version: tag.trim_start_matches(['v', 'V']).to_string(),
        url: asset["browser_download_url"]
            .as_str()
            .unwrap_or("")
            .to_string(),
        size: asset["size"].as_u64().unwrap_or(0),
        sha256: digest.strip_prefix("sha256:").unwrap_or("").to_lowercase(),
        notes: data["body"].as_str().unwrap_or("").trim().to_string(),
        page: data["html_url"].as_str().unwrap_or("").to_string(),
    }))
}

pub fn staging_path(target: &Path) -> PathBuf {
    let stem = target
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    target.with_file_name(format!("{stem}.new.exe"))
}

pub fn download(release: &Release, dest: &Path) -> Result<PathBuf, String> {
    let bytes = reqwest::blocking::Client::builder()
        .user_agent(format!("VisualNovelRPC/{CURRENT}"))
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|e| e.to_string())?
        .get(&release.url)
        .send()
        .and_then(|r| r.error_for_status())
        .and_then(|r| r.bytes())
        .map_err(|e| e.to_string())?;

    let wrong_size = release.size > 0 && bytes.len() as u64 != release.size;
    let hash: String = Sha256::digest(&bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let wrong_hash = !release.sha256.is_empty() && hash != release.sha256;
    if wrong_size || wrong_hash {
        return Err("the downloaded file is incomplete or corrupted".into());
    }

    let part = dest.with_extension("exe.part");
    let mut file = fs::File::create(&part).map_err(|e| e.to_string())?;
    file.write_all(&bytes).map_err(|e| e.to_string())?;
    drop(file);
    fs::rename(&part, dest).map_err(|e| e.to_string())?;
    Ok(dest.to_path_buf())
}

pub fn install(new_exe: &Path) -> Result<(), String> {
    use std::os::windows::process::CommandExt;

    let target = std::env::current_exe().map_err(|e| e.to_string())?;
    let script = std::env::temp_dir().join("vnrpc_update.cmd");

    let lines = [
        "@echo off".to_string(),
        "set tries=0".to_string(),
        ":wait".to_string(),
        format!(
            "move /y \"{}\" \"{}\" >nul 2>&1 && goto run",
            new_exe.display(),
            target.display()
        ),
        "set /a tries+=1".to_string(),
        "if %tries% geq 60 goto end".to_string(),
        "ping -n 2 127.0.0.1 >nul".to_string(),
        "goto wait".to_string(),
        ":run".to_string(),
        format!("start \"\" \"{}\"", target.display()),
        ":end".to_string(),
        "del \"%~f0\"".to_string(),
    ];
    fs::write(&script, lines.join("\r\n")).map_err(|e| e.to_string())?;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    std::process::Command::new("cmd.exe")
        .arg("/c")
        .arg(&script)
        .current_dir(target.parent().unwrap_or(Path::new(".")))
        .creation_flags(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[derive(Debug, Serialize)]
pub struct Notes {
    pub version: String,
    pub date: String,
    pub body: String,
}

pub fn release_notes() -> Result<Vec<Notes>, String> {
    let data = get_json(&format!(
        "https://api.github.com/repos/{REPO}/releases?per_page=30"
    ))?;

    let mut notes: Vec<Notes> = data
        .as_array()
        .into_iter()
        .flatten()
        .filter(|rel| !rel["draft"].as_bool().unwrap_or(false))
        .filter(|rel| !rel["prerelease"].as_bool().unwrap_or(false))
        .filter(|rel| !parse_version(rel["tag_name"].as_str().unwrap_or("")).is_empty())
        .map(|rel| Notes {
            version: rel["tag_name"]
                .as_str()
                .unwrap_or("")
                .trim_start_matches(['v', 'V'])
                .to_string(),
            date: rel["published_at"]
                .as_str()
                .unwrap_or("")
                .chars()
                .take(10)
                .collect(),
            body: rel["body"].as_str().unwrap_or("").to_string(),
        })
        .collect();

    notes.sort_by(|a, b| parse_version(&b.version).cmp(&parse_version(&a.version)));
    Ok(notes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_compare_like_python() {
        assert!(is_newer("v1.2.1", "1.2.0"));
        assert!(!is_newer("1.2.1", "1.2.1"));
        assert!(is_newer("v1.10.0", "1.9.3"));
        assert!(!is_newer("v1.2", "1.2.0"));
        assert!(is_newer("1.2.0.1", "1.2"));
        assert!(!is_newer("v1.1.0", "1.2.0"));
        assert!(!is_newer("vn", "1.2.0"));
    }
}
