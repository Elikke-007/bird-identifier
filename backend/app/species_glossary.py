from __future__ import annotations

from typing import Final

BIRD_SPECIES_GLOSSARY: Final[dict[str, str]] = {
    "Abbott S Babbler": "艾氏鹛",
    "Asian Green Bee Eater": "绿喉蜂虎",
    "Barn Owl": "仓鸮",
    "Black Drongo": "黑卷尾",
    "Black Headed Ibis": "黑头白鹮",
    "Black Kite": "黑鸢",
    "Black Necked Stork": "黑颈鹳",
    "Black Swan": "黑天鹅",
    "Black Tailed Godwit": "黑尾塍鹬",
    "Black Throated Bushtit": "黑喉长尾山雀",
    "Brown Fish Owl": "褐渔鸮",
    "Cattle Egret": "牛背鹭",
    "Common Hoopoe": "戴胜",
    "Common Kingfisher": "普通翠鸟",
    "Common Myna": "八哥",
    "Common Rosefinch": "普通朱雀",
    "Common Tailorbird": "长尾缝叶莺",
    "Coppersmith Barbet": "金喉拟啄木鸟",
    "Crested Serpent Eagle": "蛇雕",
    "Eurasian Coot": "骨顶鸡",
    "Eurasian Spoonbill": "白琵鹭",
    "Gray Heron": "苍鹭",
    "Great Egret": "大白鹭",
    "Green Imperial Pigeon": "绿皇鸠",
    "House Crow": "家鸦",
    "House Sparrow": "麻雀",
    "Indian Grey Hornbill": "灰角犀鸟",
    "Indian Peafowl": "蓝孔雀",
    "Indian Pitta": "八色鸫",
    "Indian Roller": "蓝胸佛法僧",
    "Jungle Babbler": "棕颈钩嘴鹛",
    "Laughing Dove": "棕斑鸠",
    "Little Cormorant": "小鸬鹚",
    "Little Egret": "小白鹭",
    "Malabar Parakeet": "蓝翼鹦鹉",
    "Oriental Darter": "蛇鹈",
    "Oriental Magpie Robin": "鹊鸲",
    "Purple Heron": "紫鹭",
    "Red Avadavat": "红梅花雀",
    "Red Whiskered Bulbul": "红耳鹎",
    "Red Wattled Lapwing": "肉垂麦鸡",
    "Rock Pigeon": "原鸽",
    "Rose Ringed Parakeet": "长尾鹦鹉",
    "Ruddy Shelduck": "赤麻鸭",
    "Rufous Treepie": "棕树鹊",
    "Sarus Crane": "赤颈鹤",
    "Shikra": "雀鹰",
    "White Breasted Kingfisher": "白胸翡翠",
    "White Breasted Waterhen": "白胸苦恶鸟",
    "White Wagtail": "白鹡鸰",
}


def normalize_species_name(value: str) -> str:
    return value.replace("_", " ").title().strip()


def glossary_lookup_species(value: str) -> tuple[str, str, bool]:
    normalized = normalize_species_name(value)
    chinese = BIRD_SPECIES_GLOSSARY.get(normalized, normalized)
    return chinese, normalized, chinese != normalized
