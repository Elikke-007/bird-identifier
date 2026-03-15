import { invoke } from "@tauri-apps/api/core";
import type { ImageRecord, ScanSummary, SearchSummary } from "../types";

export async function scanImages(root: string) {
  return invoke<ScanSummary>("scan_images", { root });
}

export async function writeBirdMetadata(root: string, imagePath: string, species: string, sex: string, confidence?: number) {
  return invoke<ImageRecord>("write_bird_metadata", { root, imagePath, species, sex, confidence });
}

export async function searchImages(root: string, query: string) {
  return invoke<SearchSummary>("search_images", { root, query });
}

export async function revealInExplorer(path: string) {
  return invoke<void>("reveal_in_explorer", { path });
}
