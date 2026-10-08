pub mod app;
pub mod covers;
pub mod data;
pub mod library;
pub mod popups;
pub mod screenshots;
pub mod share;

use std::sync::Arc;

use tauri::State;

use crate::state::Shared;

pub type SharedState<'a> = State<'a, Arc<Shared>>;

pub async fn blocking<T, F>(work: F) -> Result<T, String>
where
    T: Send + 'static,
    F: FnOnce() -> Result<T, String> + Send + 'static,
{
    tauri::async_runtime::spawn_blocking(work)
        .await
        .map_err(|e| e.to_string())?
}
