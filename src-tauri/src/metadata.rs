use std::{
    env,
    fs,
    io::BufReader,
    path::{Path, PathBuf},
    process::Command,
};

use chrono::Local;
use walkdir::WalkDir;

use crate::{
    error::AppError,
    model::{BirdMetadata, ImageRecord, MetadataSidecar},
};

const APP_META_FILE: &str = ".bird-identify-index.json";
const SUPPORTED_EXTENSIONS: [&str; 6] = ["jpg", "jpeg", "png", "webp", "bmp", "tiff"];
const WINDOWS_DETAILS_EXTENSIONS: [&str; 3] = ["jpg", "jpeg", "tiff"];

pub fn collect_images(root: &str) -> Result<Vec<ImageRecord>, AppError> {
    let root_path = Path::new(root);
    let sidecar = load_sidecar(root_path)?;

    let mut images = WalkDir::new(root_path)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .filter_map(|entry| {
            let path = entry.path();
            let extension = path
                .extension()
                .and_then(|ext| ext.to_str())
                .map(|ext| ext.to_ascii_lowercase())?;

            if !SUPPORTED_EXTENSIONS.contains(&extension.as_str()) {
                return None;
            }

            let path_string = path.to_string_lossy().to_string();
            let metadata = read_bird_metadata(root_path, path, &sidecar);

            Some(ImageRecord {
                path: path_string,
                file_name: path
                    .file_name()
                    .map(|value| value.to_string_lossy().to_string())
                    .unwrap_or_default(),
                extension,
                preview_url: None,
                metadata,
            })
        })
        .collect::<Vec<_>>();

    images.sort_by(|left, right| left.file_name.cmp(&right.file_name));
    Ok(images)
}

pub fn search_images(root: &str, query: &str) -> Result<Vec<ImageRecord>, AppError> {
    let query = query.trim().to_lowercase();
    let images = collect_images(root)?;

    Ok(images
        .into_iter()
        .filter(|image| {
            let mut haystacks = vec![image.file_name.to_lowercase()];

            if let Some(species) = &image.metadata.species {
                haystacks.push(species.to_lowercase());
            }

            if let Some(sex) = &image.metadata.sex {
                haystacks.push(sex.to_lowercase());
            }

            haystacks.extend(image.metadata.keywords.iter().map(|tag| tag.to_lowercase()));
            haystacks.extend(image.metadata.raw_tags.iter().map(|tag| tag.to_lowercase()));

            haystacks.iter().any(|value| value.contains(&query))
        })
        .collect())
}

pub fn upsert_bird_metadata(
    root: &str,
    image_path: &str,
    species: &str,
    _sex: &str,
    confidence: Option<f32>,
) -> Result<ImageRecord, AppError> {
    let root_path = Path::new(root);
    let image = Path::new(image_path);
    let extension = image
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();

    if !WINDOWS_DETAILS_EXTENSIONS.contains(&extension.as_str()) {
        return Err(AppError::Message(format!(
            "当前仅支持把鸟种写入 Windows 标题字段的图片格式：JPG/JPEG/TIFF。当前文件是 .{}",
            extension
        )));
    }

    try_write_embedded_metadata(image, species)?;

    let mut sidecar = load_sidecar(root_path)?;
    let relative_key = relative_key(root_path, image);
    let now = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let keywords = vec![species.to_string()];

    let record = BirdMetadata {
        species: Some(species.to_string()),
        sex: None,
        confidence,
        keywords: keywords.clone(),
        raw_tags: keywords,
        updated_at: Some(now),
    };

    sidecar.entries.insert(relative_key, record.clone());
    save_sidecar(root_path, &sidecar)?;

    Ok(ImageRecord {
        path: image_path.to_string(),
        file_name: image
            .file_name()
            .map(|value| value.to_string_lossy().to_string())
            .unwrap_or_default(),
        extension,
        preview_url: None,
        metadata: record,
    })
}

fn load_sidecar(root: &Path) -> Result<MetadataSidecar, AppError> {
    let sidecar_path = root.join(APP_META_FILE);
    if !sidecar_path.exists() {
        return Ok(MetadataSidecar::default());
    }

    let raw = fs::read_to_string(sidecar_path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn save_sidecar(root: &Path, sidecar: &MetadataSidecar) -> Result<(), AppError> {
    let content = serde_json::to_string_pretty(sidecar)?;
    fs::write(root.join(APP_META_FILE), content)?;
    Ok(())
}

fn read_bird_metadata(root: &Path, image_path: &Path, sidecar: &MetadataSidecar) -> BirdMetadata {
    let key = relative_key(root, image_path);
    if let Some(saved) = sidecar.entries.get(&key) {
        return saved.clone();
    }

    let mut metadata = BirdMetadata::default();

    if let Ok(file) = fs::File::open(image_path) {
        let mut reader = BufReader::new(file);
        if let Ok(exif) = exif::Reader::new().read_from_container(&mut reader) {
            for field in exif.fields() {
                let tag_name = format!("{:?}", field.tag);
                let display_value = field.display_value().with_unit(&exif).to_string();

                if tag_name.contains("XPTitle") || tag_name.contains("Title") {
                    metadata.raw_tags.push(display_value.clone());

                    if metadata.species.is_none() && !display_value.trim().is_empty() {
                        metadata.species = Some(display_value.trim().to_string());
                    }

                    if !display_value.trim().is_empty() {
                        metadata.keywords.push(display_value.trim().to_string());
                    }
                }
            }
        }
    }

    metadata.keywords.sort();
    metadata.keywords.dedup();
    metadata.raw_tags.sort();
    metadata.raw_tags.dedup();
    metadata
}

fn try_write_embedded_metadata(image: &Path, species: &str) -> Result<(), AppError> {
    let exiftool_path = resolve_exiftool_path()?;

    let output = Command::new(exiftool_path)
        .arg("-overwrite_original")
        .arg("-charset")
        .arg("filename=utf8")
        .arg(format!("-XMP-dc:Title={species}"))
        .arg(format!("-XPTitle={species}"))
        .arg(image)
        .output();

    match output {
        Ok(result) if result.status.success() => Ok(()),
        Ok(result) => {
            let stderr = String::from_utf8_lossy(&result.stderr).trim().to_string();
            let stdout = String::from_utf8_lossy(&result.stdout).trim().to_string();
            let detail = if !stderr.is_empty() { stderr } else { stdout };
            Err(AppError::Message(format!("写入图片本体元数据失败：{}", detail)))
        }
        Err(error) => Err(AppError::Io(error)),
    }
}

fn resolve_exiftool_path() -> Result<PathBuf, AppError> {
    if let Ok(configured) = env::var("EXIFTOOL_PATH") {
        let path = PathBuf::from(configured.trim_matches('"'));
        if path.is_file() {
            return Ok(path);
        }
    }

    let candidates = [
        PathBuf::from("exiftool.exe"),
        PathBuf::from(r"C:\Windows\exiftool.exe"),
        PathBuf::from(r"C:\Windows\System32\exiftool.exe"),
        PathBuf::from(r"C:\Program Files\ExifTool\exiftool.exe"),
        PathBuf::from(r"C:\Program Files (x86)\ExifTool\exiftool.exe"),
        PathBuf::from(r"C:\Tools\ExifTool\exiftool.exe"),
    ];

    for candidate in candidates {
        if candidate.is_file() || candidate == PathBuf::from("exiftool.exe") {
            return Ok(candidate);
        }
    }

    Err(AppError::Message(
        "未检测到 exiftool。请确认 exiftool.exe 已加入 PATH，或者设置环境变量 EXIFTOOL_PATH 指向 exiftool.exe 的完整路径。".to_string(),
    ))
}

fn relative_key(root: &Path, image: &Path) -> String {
    image
        .strip_prefix(root)
        .unwrap_or(image)
        .to_string_lossy()
        .replace('\\', "/")
}

#[allow(dead_code)]
fn root_for_image(image_path: &str) -> String {
    PathBuf::from(image_path)
        .parent()
        .map(|path| path.to_string_lossy().to_string())
        .unwrap_or_else(|| ".".to_string())
}
