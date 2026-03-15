import type { BirdPrediction } from "../types";

const DEFAULT_API_BASE = "http://127.0.0.1:8008";
const API_BASE = (import.meta.env.VITE_RECOGNITION_API_URL as string | undefined)?.trim() || DEFAULT_API_BASE;

type IdentifyResponse = BirdPrediction & {
  detectionCount: number;
  detectionBox?: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    confidence: number;
  } | null;
};

export async function warmupBirdVisionModels() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`识别后端不可用：${response.status} ${response.statusText}`);
  }
}

export async function identifyBirdFromImage(imagePath: string): Promise<BirdPrediction> {
  const response = await fetch(`${API_BASE}/identify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      imagePath,
      topK: 5
    })
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `识别后端调用失败：${response.status} ${response.statusText}`);
  }

  const result = (await response.json()) as IdentifyResponse;
  return result;
}

export function getRecognitionApiBase() {
  return API_BASE;
}
