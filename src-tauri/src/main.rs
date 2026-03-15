#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod error;
mod metadata;
mod model;
mod recognizer;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            commands::scan_images,
            commands::identify_bird,
            commands::write_bird_metadata,
            commands::search_images,
            commands::reveal_in_explorer
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
