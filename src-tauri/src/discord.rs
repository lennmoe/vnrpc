use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

#[derive(Debug, Clone, Default, PartialEq, serde::Serialize)]
pub struct Activity {
    pub name: String,
    pub details: String,
    pub state: String,
    pub large_image: String,
    pub large_text: String,
    pub small_text: String,
    pub start: Option<i64>,
    pub buttons: Vec<(String, String)>,
}

fn cut(text: &str) -> String {
    text.chars().take(128).collect()
}

impl Activity {
    fn to_json(&self) -> Value {
        let mut act = json!({"type": 0});
        if !self.name.is_empty() {
            act["name"] = json!(cut(&self.name));
        }
        if !self.details.is_empty() {
            act["details"] = json!(cut(&self.details));
        }
        if !self.state.is_empty() {
            act["state"] = json!(cut(&self.state));
        }
        let mut assets = json!({});
        if !self.large_image.is_empty() {
            assets["large_image"] = json!(self.large_image);
            let text = [&self.large_text, &self.name, &self.details]
                .into_iter()
                .find(|s| !s.is_empty())
                .cloned();
            assets["large_text"] = json!(cut(&text.unwrap_or_default()));
        }
        if !self.small_text.is_empty() {
            assets["small_text"] = json!(cut(&self.small_text));
        }
        act["assets"] = assets;
        if let Some(start) = self.start {
            act["timestamps"] = json!({"start": start});
        }
        if !self.buttons.is_empty() {
            act["buttons"] = self
                .buttons
                .iter()
                .take(2)
                .map(|(l, u)| json!({"label": l, "url": u}))
                .collect();
        }
        act
    }
}

pub enum Msg {
    Set(Option<Activity>),
    ClientId(String),
    Interval(f64),
    Quit,
}

pub type StatusFn = Box<dyn Fn(bool, String) + Send>;

struct Pipe(File);

impl Pipe {
    fn connect(client_id: &str) -> Result<Pipe, String> {
        let mut last_err = String::from("Discord isn't running");
        let name = std::env::var("VNRPC_DISCORD_PIPE").unwrap_or_else(|_| "discord-ipc".into());
        for i in 0..10 {
            let path = format!(r"\\?\pipe\{name}-{i}");
            match OpenOptions::new().read(true).write(true).open(&path) {
                Ok(f) => {
                    let mut pipe = Pipe(f);
                    pipe.send(0, &json!({"v": 1, "client_id": client_id}))?;
                    let (op, reply) = pipe.recv()?;
                    if op == 2 || reply.get("evt").and_then(Value::as_str) == Some("ERROR") {
                        return Err(format!("Discord refused the connection: {reply}"));
                    }
                    return Ok(pipe);
                }
                Err(e) => last_err = format!("Discord not reachable: {e}"),
            }
        }
        Err(last_err)
    }

    fn send(&mut self, op: u32, payload: &Value) -> Result<(), String> {
        let body = payload.to_string().into_bytes();
        let mut frame = Vec::with_capacity(8 + body.len());
        frame.extend_from_slice(&op.to_le_bytes());
        frame.extend_from_slice(&(body.len() as u32).to_le_bytes());
        frame.extend_from_slice(&body);
        self.0.write_all(&frame).map_err(|e| e.to_string())
    }

    fn recv(&mut self) -> Result<(u32, Value), String> {
        let mut header = [0u8; 8];
        self.0.read_exact(&mut header).map_err(|e| e.to_string())?;
        let op = u32::from_le_bytes(header[..4].try_into().unwrap());
        let len = u32::from_le_bytes(header[4..].try_into().unwrap()) as usize;
        let mut body = vec![0u8; len];
        self.0.read_exact(&mut body).map_err(|e| e.to_string())?;
        Ok((op, serde_json::from_slice(&body).unwrap_or(Value::Null)))
    }

    fn set_activity(&mut self, activity: Option<&Activity>, nonce: u64) -> Result<(), String> {
        let payload = json!({
            "cmd": "SET_ACTIVITY",
            "args": {"pid": std::process::id(), "activity": activity.map(Activity::to_json)},
            "nonce": nonce.to_string(),
        });
        self.send(1, &payload)?;
        let (op, reply) = self.recv()?;
        if op == 2 || reply.get("evt").and_then(Value::as_str) == Some("ERROR") {
            return Err(format!(
                "Discord rejected the update: {}",
                reply["data"]["message"]
            ));
        }
        Ok(())
    }
}

pub fn test_connection(client_id: &str) -> Result<(), String> {
    Pipe::connect(client_id).map(|_| ())
}

pub fn run(rx: Receiver<Msg>, mut client_id: String, mut interval: f64, status: StatusFn) {
    let mut pipe: Option<Pipe> = None;
    let mut desired: Option<Activity> = None;
    let mut pushed: Option<Option<Activity>> = None;
    let mut last_push = Instant::now() - Duration::from_secs(3600);
    let mut backoff = 2.0f64;
    let mut retry_at = Instant::now();
    let mut nonce = 0u64;

    loop {
        let wait = if pipe.is_none() {
            retry_at.saturating_duration_since(Instant::now())
        } else if pushed.as_ref() != Some(&desired) {
            Duration::from_secs_f64(interval).saturating_sub(last_push.elapsed())
        } else {
            Duration::from_secs(3600)
        };
        match rx.recv_timeout(wait) {
            Ok(Msg::Set(a)) => desired = a,
            Ok(Msg::ClientId(id)) => {
                if id != client_id {
                    client_id = id;
                    pipe = None;
                    pushed = None;
                    retry_at = Instant::now();
                }
            }
            Ok(Msg::Interval(s)) => interval = s.max(1.0),
            Ok(Msg::Quit) | Err(RecvTimeoutError::Disconnected) => break,
            Err(RecvTimeoutError::Timeout) => {}
        }

        if pipe.is_none() {
            if Instant::now() < retry_at {
                continue;
            }
            match Pipe::connect(&client_id) {
                Ok(p) => {
                    pipe = Some(p);
                    pushed = None;
                    backoff = 2.0;
                    status(true, "connected".into());
                }
                Err(e) => {
                    status(false, e);
                    retry_at = Instant::now() + Duration::from_secs_f64(backoff);
                    backoff = (backoff * 1.7).min(30.0);
                    continue;
                }
            }
        }

        if pushed.as_ref() == Some(&desired) {
            continue;
        }
        if desired.is_some() && last_push.elapsed().as_secs_f64() < interval {
            continue;
        }
        nonce += 1;
        let result = pipe.as_mut().unwrap().set_activity(desired.as_ref(), nonce);
        match result {
            Ok(()) => {
                pushed = Some(desired.clone());
                last_push = Instant::now();
            }
            Err(e) => {
                status(false, format!("lost Discord connection: {e}"));
                pipe = None;
                pushed = None;
                retry_at = Instant::now() + Duration::from_secs(2);
            }
        }
    }
    if let Some(mut p) = pipe {
        let _ = p.set_activity(None, nonce + 1);
    }
}

pub fn channel() -> (Sender<Msg>, Receiver<Msg>) {
    std::sync::mpsc::channel()
}
