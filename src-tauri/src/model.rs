use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct BirdMetadata {
    pub species: Option<String>,
    pub sex: Option<String>,
    pub confidence: Option<f32>,
    #[serde(default)]
    pub keywords: Vec<String>,
    #[serde(default)]
    pub raw_tags: Vec<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImageRecord {
    pub path: String,
    pub file_name: String,
    pub extension: String,
    pub preview_url: Option<String>,
    pub metadata: BirdMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BirdPrediction {
    pub species: String,
    pub sex: String,
    pub confidence: f32,
    pub species_confidence: f32,
    pub sex_confidence: f32,
    pub reason: String,
    pub sex_reason: String,
    pub matched_keyword: Option<String>,
    #[serde(default)]
    pub top_species: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScanSummary {
    pub root: String,
    pub count: usize,
    pub images: Vec<ImageRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchSummary {
    pub query: String,
    pub count: usize,
    pub images: Vec<ImageRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MetadataSidecar {
    #[serde(default)]
    pub entries: std::collections::HashMap<String, BirdMetadata>,
}
