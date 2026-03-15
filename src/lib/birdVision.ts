import { convertFileSrc } from "@tauri-apps/api/core";
import type { BirdPrediction, BirdSex } from "../types";

const SPECIES_MODEL_ID = "chriamue/bird-species-classifier";
const SEX_MODEL_ID = "Xenova/clip-vit-base-patch32";
const SPECIES_NAME_MAP: Record<string, string> = {
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
  Shikra: "雀鹰",
  "White Breasted Kingfisher": "白胸翡翠",
  "White Breasted Waterhen": "白胸苦恶鸟",
  "White Wagtail": "白鹡鸰"
};

type ImageClassificationItem = {
  label: string;
  score: number;
};

type ZeroShotItem = {
  label: string;
  score: number;
};

type PipelineFactory = (task: string, model?: string, options?: Record<string, unknown>) => Promise<(...args: unknown[]) => Promise<unknown>>;

let speciesPipelinePromise: Promise<(...args: unknown[]) => Promise<unknown>> | null = null;
let sexPipelinePromise: Promise<(...args: unknown[]) => Promise<unknown>> | null = null;

async function getTransformers() {
  const module = await import("@huggingface/transformers");
  module.env.allowRemoteModels = true;
  module.env.allowLocalModels = false;
  module.env.useBrowserCache = true;

  if (module.env.backends?.onnx?.wasm) {
    module.env.backends.onnx.wasm.numThreads = 1;
    module.env.backends.onnx.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/";
  }

  return module;
}

async function getSpeciesPipeline() {
  if (!speciesPipelinePromise) {
    speciesPipelinePromise = getTransformers().then(({ pipeline }) =>
      (pipeline as PipelineFactory)("image-classification", SPECIES_MODEL_ID, {
        dtype: "fp32"
      })
    );
  }

  return speciesPipelinePromise;
}

async function getSexPipeline() {
  if (!sexPipelinePromise) {
    sexPipelinePromise = getTransformers().then(({ pipeline }) =>
      (pipeline as PipelineFactory)("zero-shot-image-classification", SEX_MODEL_ID, {
        dtype: "q8"
      })
    );
  }

  return sexPipelinePromise;
}

function normalizeSpeciesLabel(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

function mapSpeciesName(value: string) {
  const normalized = normalizeSpeciesLabel(value);
  return {
    chinese: SPECIES_NAME_MAP[normalized] ?? normalized,
    original: normalized,
    translated: Boolean(SPECIES_NAME_MAP[normalized])
  };
}

function normalizeSex(result: ZeroShotItem): { sex: BirdSex; reason: string } {
  const label = result.label.toLowerCase();

  if (label.includes("male")) {
    return { sex: "雄", reason: `零样本视觉分类命中“${result.label}”` };
  }

  if (label.includes("female")) {
    return { sex: "雌", reason: `零样本视觉分类命中“${result.label}”` };
  }

  return { sex: "未知", reason: `零样本视觉分类命中“${result.label}”` };
}

export async function warmupBirdVisionModels() {
  await Promise.all([getSpeciesPipeline(), getSexPipeline()]);
}

export async function identifyBirdFromImage(imagePath: string): Promise<BirdPrediction> {
  const imageSource = convertFileSrc(imagePath);
  const [speciesClassifier, sexClassifier] = await Promise.all([getSpeciesPipeline(), getSexPipeline()]);

  const speciesRaw = (await speciesClassifier(imageSource, { top_k: 3 })) as ImageClassificationItem[] | ImageClassificationItem;
  const speciesResults = Array.isArray(speciesRaw) ? speciesRaw : [speciesRaw];
  const topSpeciesMapped = speciesResults.map((item) => mapSpeciesName(item.label));
  const bestSpecies = topSpeciesMapped[0];

  const sexRaw = (await sexClassifier(imageSource, [
    "male bird",
    "female bird",
    "bird with unknown sex"
  ], {
    hypothesis_template: "a photo of a {}"
  })) as ZeroShotItem[] | ZeroShotItem;
  const sexResults = Array.isArray(sexRaw) ? sexRaw : [sexRaw];
  const bestSex = sexResults[0];
  const normalizedSex = normalizeSex(bestSex);

  const speciesConfidence = speciesResults[0]?.score ?? 0;
  const sexConfidence = bestSex?.score ?? 0;
  const reasonSuffix = bestSpecies?.translated
    ? `已映射为中文名“${bestSpecies.chinese}”`
    : `当前暂无词典映射，保留英文原名“${bestSpecies?.original ?? "Unknown Bird"}”`;

  return {
    species: bestSpecies?.chinese ?? "Unknown Bird",
    speciesOriginal: bestSpecies?.original ?? "Unknown Bird",
    sex: normalizedSex.sex,
    confidence: Number(((speciesConfidence * 0.75) + (sexConfidence * 0.25)).toFixed(4)),
    speciesConfidence,
    sexConfidence,
    reason: `鸟类分类模型 ${SPECIES_MODEL_ID} 输出 Top-1：${bestSpecies?.original ?? "Unknown Bird"}，${reasonSuffix}`,
    sexReason: normalizedSex.reason,
    matchedKeyword: undefined,
    topSpecies: topSpeciesMapped.map((item) => item.chinese),
    topSpeciesOriginal: topSpeciesMapped.map((item) => item.original)
  };
}

