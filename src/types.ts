export type BirdSex = "雄" | "雌" | "未知";

export type BirdMetadata = {
  species?: string;
  sex?: BirdSex;
  confidence?: number;
  keywords: string[];
  rawTags: string[];
  updatedAt?: string;
};

export type ImageRecord = {
  path: string;
  fileName: string;
  extension: string;
  previewUrl?: string | null;
  metadata: BirdMetadata;
};

export type BirdPrediction = {
  species: string;
  speciesOriginal: string;
  sex: BirdSex;
  confidence: number;
  speciesConfidence: number;
  sexConfidence: number;
  reason: string;
  sexReason: string;
  matchedKeyword?: string;
  topSpecies: string[];
  topSpeciesOriginal: string[];
};

export type RecognitionStatus = "idle" | "running" | "done" | "error";
export type WriteStatus = "idle" | "writing" | "written" | "error";

export type RecognitionResult = {
  path: string;
  fileName: string;
  previewUrl?: string | null;
  species: string;
  speciesOriginal?: string;
  sex: BirdSex;
  confidence?: number;
  speciesConfidence?: number;
  sexConfidence?: number;
  reason?: string;
  sexReason?: string;
  topSpecies: string[];
  topSpeciesOriginal: string[];
  recognitionStatus: RecognitionStatus;
  writeStatus: WriteStatus;
  metadataUpdatedAt?: string;
  error?: string;
};

export type ScanSummary = {
  root: string;
  count: number;
  images: ImageRecord[];
};

export type SearchSummary = {
  query: string;
  count: number;
  images: ImageRecord[];
};
