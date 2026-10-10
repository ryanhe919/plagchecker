export interface Settings {
  similarity_threshold: number;
  minimum_match_chars: number;
  ignore_short_blocks: number;
  ignore_common_across_all: boolean;
  image_near_distance: number;
  pdf_ocr_mode: "auto" | "always" | "off";
  reference_min_match_chars: number;
}

export interface DocumentInfo {
  id: string;
  name: string;
  chars: number;
  blocks: number;
  images: number;
  content: TextBlock[];
  format: "docx" | "pdf";
  pages: number | null;
  ocr_pages: number;
  warnings: string[];
  excluded_reference_chars: number;
  excluded_reference_images: number;
}

export interface ReferenceInfo {
  name: string;
  format: "docx" | "pdf";
  pages: number | null;
  ocr_pages: number;
  warnings: string[];
}

export interface TextBlock {
  text: string;
  location: string;
  reference_excluded_ranges: [number, number][];
}

export interface Passage {
  a_text: string;
  b_text: string;
  a_location: string;
  b_location: string;
  a_block_index: number;
  b_block_index: number;
  a_start: number;
  b_start: number;
  a_highlights: [number, number][];
  b_highlights: [number, number][];
  score: number;
  matched_chars: number;
  exact: boolean;
}

export interface ImageMatch {
  a_name: string;
  b_name: string;
  a_preview: string | null;
  b_preview: string | null;
  exact: boolean;
  distance: number;
  sha256: string | null;
  pixel_sha256: string | null;
  match_type: "byte_exact" | "pixel_exact" | "near";
}

export interface PairResult {
  a_id: string;
  b_id: string;
  a_name: string;
  b_name: string;
  similarity: number;
  a_coverage: number;
  b_coverage: number;
  matched_chars: number;
  exact_image_count: number;
  passages: Passage[];
  images: ImageMatch[];
}

export interface AnalysisResult {
  documents: DocumentInfo[];
  pairs: PairResult[];
  settings: Settings;
  report_version: number | null;
  reference: ReferenceInfo | null;
  caveat: string;
}

export interface JobStatus {
  id: string;
  state: "queued" | "running" | "completed" | "failed";
  phase: "queued" | "extracting" | "comparing" | "completed" | "failed";
  completed: number;
  total: number;
  message: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  files: string[];
  reference_name: string | null;
}

export interface HistoryItem {
  id: string;
  state: JobStatus["state"];
  created_at: string;
  updated_at: string;
  files: string[];
  reference_name: string | null;
  pair_count: number | null;
  max_similarity: number | null;
  exact_image_count: number | null;
}

export interface HistoryPage {
  items: HistoryItem[];
  next_cursor: string | null;
}
