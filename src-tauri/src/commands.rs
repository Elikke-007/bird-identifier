use std::process::Command;

use crate::{
    error::AppError,
    metadata,
    model::{BirdPrediction, ImageRecord, ScanSummary, SearchSummary},
    recognizer,
};

#[tauri::command]
pub fn scan_images(root: String) -> Result<ScanSummary, AppError> {
    let images = metadata::collect_images(&root)?;

    Ok(ScanSummary {
        root,
        count: images.len(),
        images,
    })
}

#[tauri::command]
pub fn identify_bird(image_path: String) -> Result<BirdPrediction, AppError> {
    Ok(recognizer::identify(&image_path))
}

#[tauri::command]
pub fn write_bird_metadata(
    root: String,
    image_path: String,
    species: String,
    sex: String,
    confidence: Option<f32>,
) -> Result<ImageRecord, AppError> {
    metadata::upsert_bird_metadata(&root, &image_path, &species, &sex, confidence)
}

#[tauri::command]
pub fn search_images(root: String, query: String) -> Result<SearchSummary, AppError> {
    let images = metadata::search_images(&root, &query)?;

    Ok(SearchSummary {
        query,
        count: images.len(),
        images,
    })
}

#[tauri::command]
pub fn reveal_in_explorer(path: String) -> Result<(), AppError> {
    Command::new("explorer.exe").arg("/select,").arg(path).spawn()?;
    Ok(())
}
