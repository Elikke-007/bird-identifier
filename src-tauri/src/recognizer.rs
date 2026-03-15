use std::path::Path;

use crate::model::BirdPrediction;

const BIRD_KEYWORDS: [(&str, &str, f32); 12] = [
    ("红耳鹎", "red-whiskered bulbul", 0.93),
    ("白头鹎", "light-vented bulbul", 0.90),
    ("珠颈斑鸠", "spotted dove", 0.89),
    ("麻雀", "tree sparrow", 0.84),
    ("翠鸟", "kingfisher", 0.88),
    ("白鹭", "egret", 0.83),
    ("喜鹊", "magpie", 0.82),
    ("乌鸫", "blackbird", 0.86),
    ("灰喜鹊", "azure-winged magpie", 0.87),
    ("太阳鸟", "sunbird", 0.80),
    ("啄木鸟", "woodpecker", 0.81),
    ("伯劳", "shrike", 0.79),
];

pub fn identify(image_path: &str) -> BirdPrediction {
    let normalized = image_path.to_lowercase();
    let file_name = Path::new(image_path)
        .file_name()
        .map(|value| value.to_string_lossy().to_lowercase())
        .unwrap_or_default();

    if let Some((species, matched_keyword, confidence)) =
        BIRD_KEYWORDS.iter().find_map(|(species, english, score)| {
            let species_match = normalized.contains(&species.to_lowercase());
            let english_match = normalized.contains(english);

            if species_match {
                Some(((*species).to_string(), Some((*species).to_string()), *score))
            } else if english_match {
                Some((
                    (*species).to_string(),
                    Some((*english).to_string()),
                    (*score - 0.05).max(0.5),
                ))
            } else {
                None
            }
        })
    {
        return BirdPrediction {
            species: species.clone(),
            sex: "未知".to_string(),
            confidence,
            species_confidence: confidence,
            sex_confidence: 0.33,
            reason: format!(
                "根据文件名或路径命中关键词 “{}”",
                matched_keyword.clone().unwrap_or_default()
            ),
            sex_reason: "本地兜底识别器不判断性别".to_string(),
            matched_keyword,
            top_species: vec![species],
        };
    }

    let fallback = if file_name.contains("dove") || file_name.contains("pigeon") {
        ("珠颈斑鸠", 0.61, "文件名包含鸠类常见英文关键词".to_string())
    } else if file_name.contains("sparrow") {
        ("麻雀", 0.60, "文件名包含麻雀英文关键词".to_string())
    } else if file_name.contains("bulbul") {
        ("白头鹎", 0.64, "文件名包含鹎科英文关键词".to_string())
    } else {
        (
            "未知鸟种",
            0.32,
            "当前命令仅保留本地兜底识别器；主流程已切换到真实视觉模型".to_string(),
        )
    };

    BirdPrediction {
        species: fallback.0.to_string(),
        sex: "未知".to_string(),
        confidence: fallback.1,
        species_confidence: fallback.1,
        sex_confidence: 0.33,
        reason: fallback.2,
        sex_reason: "本地兜底识别器不判断性别".to_string(),
        matched_keyword: None,
        top_species: vec![fallback.0.to_string()],
    }
}
