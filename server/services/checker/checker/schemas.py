from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    similarity_threshold: float = Field(default=0.80, ge=0.5, le=1)
    minimum_match_chars: int = Field(default=16, ge=8, le=100)
    ignore_short_blocks: int = Field(default=12, ge=0, le=100)
    ignore_common_across_all: bool = False
    image_near_distance: int = Field(default=6, ge=0, le=16)
    pdf_ocr_mode: Literal["auto", "always", "off"] = "auto"
    reference_min_match_chars: int = Field(default=16, ge=8, le=100)


class TextBlock(BaseModel):
    text: str
    location: str
    reference_excluded_ranges: list[tuple[int, int]] = Field(default_factory=list)


class ImageInfo(BaseModel):
    sha256: str
    name: str
    preview: str | None = None
    perceptual_hash: int | None = None
    mean_rgb: tuple[int, int, int] | None = None
    visual_variance: float | None = None
    pixel_sha256: str | None = None


class DocumentInfo(BaseModel):
    id: str
    name: str
    chars: int
    blocks: int
    images: int
    content: list[TextBlock]
    format: Literal["docx", "pdf"] = "docx"
    pages: int | None = None
    ocr_pages: int = 0
    warnings: list[str] = Field(default_factory=list)
    excluded_reference_chars: int = 0
    excluded_reference_images: int = 0


class ReferenceInfo(BaseModel):
    name: str
    format: Literal["docx", "pdf"]
    pages: int | None = None
    ocr_pages: int = 0
    warnings: list[str] = Field(default_factory=list)


class Passage(BaseModel):
    a_text: str
    b_text: str
    a_location: str
    b_location: str
    a_block_index: int
    b_block_index: int
    a_start: int
    b_start: int
    a_highlights: list[tuple[int, int]]
    b_highlights: list[tuple[int, int]]
    score: float
    matched_chars: int
    exact: bool


class ImageMatch(BaseModel):
    a_name: str
    b_name: str
    a_preview: str | None
    b_preview: str | None
    exact: bool
    distance: int
    sha256: str | None = None
    pixel_sha256: str | None = None
    match_type: Literal["byte_exact", "pixel_exact", "near"] = "near"


class PairResult(BaseModel):
    a_id: str
    b_id: str
    a_name: str
    b_name: str
    similarity: float
    a_coverage: float
    b_coverage: float
    matched_chars: int
    exact_image_count: int
    passages: list[Passage]
    images: list[ImageMatch]


class AnalysisResult(BaseModel):
    documents: list[DocumentInfo]
    pairs: list[PairResult]
    settings: Settings
    report_version: int | None = None
    reference: ReferenceInfo | None = None
    caveat: str = "文本比例为可解释的片段覆盖率估计；图片的字节一致、像素一致及疑似相似单独列出，不并入文本比例。OCR 识别质量取决于扫描清晰度。"


class JobStatus(BaseModel):
    id: str
    state: Literal["queued", "running", "completed", "failed"]
    phase: Literal["queued", "extracting", "comparing", "completed", "failed"]
    completed: float = 0
    total: int
    message: str
    error: str | None = None
    created_at: str
    updated_at: str
    files: list[str]
    reference_name: str | None = None


class JobFile(BaseModel):
    name: str
    stored_name: str
    format: Literal["docx", "pdf"]


class JobManifest(JobStatus):
    settings: Settings
    uploads: list[JobFile]
    reference_upload: JobFile | None = None


class HistoryItem(BaseModel):
    id: str
    state: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    files: list[str]
    reference_name: str | None = None
    pair_count: int | None = None
    max_similarity: float | None = None
    exact_image_count: int | None = None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None = None
