import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from itertools import combinations
from typing import Callable

from rapidfuzz.fuzz import partial_ratio, ratio

from checker.extract import ParsedDocument
from checker.schemas import AnalysisResult, DocumentInfo, ImageInfo, ImageMatch, PairResult, Passage, ReferenceInfo, Settings, TextBlock


@dataclass(frozen=True)
class Segment:
    text: str
    location: str
    block_index: int
    block_start: int
    normalized: str
    offsets: list[int]
    reference_mask: tuple[bool, ...] = ()


def normalize(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(text):
        for folded in unicodedata.normalize("NFKC", character).casefold():
            if folded.isalnum():
                chars.append(folded)
                offsets.append(index)
    return "".join(chars), offsets


def _segments(doc: ParsedDocument, settings: Settings) -> list[Segment]:
    result: list[Segment] = []
    for block_index, block in enumerate(doc.blocks):
        for match in re.finditer(r"[^。！？!?；;]+[。！？!?；;]?", block.text):
            raw_sentence = match.group()
            sentence = raw_sentence.strip()
            if not sentence:
                continue
            sentence_start = match.start() + len(raw_sentence) - len(raw_sentence.lstrip())
            # Long DOCX paragraphs often have no punctuation; bounded windows keep matching tractable.
            step = 190
            starts = range(0, len(sentence), step) if len(sentence) > 220 else (0,)
            for start in starts:
                fragment = sentence[start : start + 190]
                normalized, offsets = normalize(fragment)
                if len(normalized) >= settings.ignore_short_blocks:
                    result.append(Segment(fragment, block.location, block_index, sentence_start + start, normalized, offsets))
    return result


def _grams(value: str) -> set[str]:
    if len(value) < 3:
        return {value}
    return {value[index : index + 3] for index in range(len(value) - 2)}


def _reference_ngrams(reference: ParsedDocument, size: int) -> set[str]:
    grams: set[str] = set()
    for block in reference.blocks:
        normalized, _ = normalize(block.text)
        grams.update(normalized[index : index + size] for index in range(len(normalized) - size + 1))
    return grams


def _exclude_reference(segment: Segment, grams: set[str], size: int) -> Segment:
    mask = [False] * len(segment.normalized)
    for index in range(len(segment.normalized) - size + 1):
        if segment.normalized[index : index + size] in grams:
            mask[index : index + size] = [True] * size
    return replace(segment, reference_mask=tuple(mask))


def _effective(segment: Segment) -> str:
    if not segment.reference_mask:
        return segment.normalized
    return "".join(char for char, excluded in zip(segment.normalized, segment.reference_mask) if not excluded)


def _display_blocks(doc: ParsedDocument, segments: list[Segment]) -> list[TextBlock]:
    ranges: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for segment in segments:
        start: int | None = None
        for index in range(len(segment.reference_mask) + 1):
            excluded = index < len(segment.reference_mask) and segment.reference_mask[index]
            if excluded and start is None:
                start = index
            elif not excluded and start is not None:
                ranges[segment.block_index].append(
                    (
                        segment.block_start + segment.offsets[start],
                        segment.block_start + segment.offsets[index - 1] + 1,
                    )
                )
                start = None
    result = []
    for index, block in enumerate(doc.blocks):
        merged: list[tuple[int, int]] = []
        for start, end in sorted(ranges[index]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        result.append(block.model_copy(update={"reference_excluded_ranges": merged}))
    return result


def _unmasked_blocks(a: Segment, b: Segment) -> list[tuple[int, int, int]]:
    matcher = SequenceMatcher(None, a.normalized, b.normalized, autojunk=False)
    blocks: list[tuple[int, int, int]] = []
    for match in matcher.get_matching_blocks():
        start: int | None = None
        for offset in range(match.size + 1):
            included = (
                offset < match.size
                and not (a.reference_mask and a.reference_mask[match.a + offset])
                and not (b.reference_mask and b.reference_mask[match.b + offset])
            )
            if included and start is None:
                start = offset
            elif not included and start is not None:
                if offset - start >= 3:
                    blocks.append((match.a + start, match.b + start, offset - start))
                start = None
    return blocks


def _ranges(segment: Segment, blocks: list[tuple[int, int]], side: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for a_start, b_start, size in blocks:
        start = a_start if side == 0 else b_start
        if size and start + size <= len(segment.offsets):
            ranges.append((segment.offsets[start], segment.offsets[start + size - 1] + 1))
    return ranges


def _passage(a: Segment, b: Segment, threshold: int) -> Passage | None:
    blocks = _unmasked_blocks(a, b)
    matched = sum(size for _, _, size in blocks)
    if matched < threshold:
        return None
    return Passage(
        a_text=a.text,
        b_text=b.text,
        a_location=a.location,
        b_location=b.location,
        a_block_index=a.block_index,
        b_block_index=b.block_index,
        a_start=a.block_start,
        b_start=b.block_start,
        a_highlights=_ranges(a, blocks, 0),
        b_highlights=_ranges(b, blocks, 1),
        score=round(ratio(_effective(a), _effective(b)) / 100, 4),
        matched_chars=matched,
        exact=_effective(a) == _effective(b),
    )


def _text_matches(
    a: list[Segment], b: list[Segment], settings: Settings
) -> tuple[list[Passage], float, float, int]:
    index: dict[str, list[int]] = defaultdict(list)
    exact_index: dict[str, list[int]] = defaultdict(list)
    for b_index, segment in enumerate(b):
        effective = _effective(segment)
        exact_index[effective].append(b_index)
        for gram in _grams(effective):
            index[gram].append(b_index)
    passages: list[Passage] = []
    covered_a = 0
    covered_b = [0] * len(b)
    for a_segment in a:
        a_effective = _effective(a_segment)
        if not a_effective:
            continue
        exact_candidates = exact_index.get(a_effective)
        if exact_candidates:
            b_index = min(exact_candidates, key=lambda candidate: covered_b[candidate])
            passage = _passage(a_segment, b[b_index], settings.minimum_match_chars)
            if passage:
                passages.append(passage)
                covered_a += passage.matched_chars
                covered_b[b_index] = max(covered_b[b_index], passage.matched_chars)
                continue
        counts: Counter[int] = Counter()
        for gram in _grams(a_effective):
            counts.update(index.get(gram, []))
        best: tuple[int, Passage] | None = None
        for b_index, _ in counts.most_common(24):
            b_segment = b[b_index]
            b_effective = _effective(b_segment)
            if max(ratio(a_effective, b_effective), partial_ratio(a_effective, b_effective)) / 100 < settings.similarity_threshold:
                continue
            passage = _passage(a_segment, b_segment, settings.minimum_match_chars)
            if passage and (best is None or passage.matched_chars > best[1].matched_chars):
                best = (b_index, passage)
        if best:
            b_index, passage = best
            passages.append(passage)
            covered_a += passage.matched_chars
            covered_b[b_index] = max(covered_b[b_index], passage.matched_chars)
    total_a = sum(len(_effective(item)) for item in a)
    total_b = sum(len(_effective(item)) for item in b)
    a_coverage = covered_a / total_a if total_a else 0
    b_coverage = sum(covered_b) / total_b if total_b else 0
    passages.sort(key=lambda item: (item.matched_chars, item.score), reverse=True)
    return passages, min(a_coverage, 1), min(b_coverage, 1), min(covered_a, sum(covered_b))


def _reference_image_keys(reference: ParsedDocument | None) -> tuple[set[str], set[str]]:
    if reference is None:
        return set(), set()
    return (
        {image.sha256 for image in reference.images},
        {image.pixel_sha256 for image in reference.images if image.pixel_sha256 is not None},
    )


def _image_in_reference(image: ImageInfo, byte_hashes: set[str], pixel_hashes: set[str]) -> bool:
    return image.sha256 in byte_hashes or (image.pixel_sha256 is not None and image.pixel_sha256 in pixel_hashes)


def _image_matches(
    a: ParsedDocument,
    b: ParsedDocument,
    settings: Settings,
    reference_keys: tuple[set[str], set[str]],
) -> tuple[list[ImageMatch], int]:
    matches: list[ImageMatch] = []
    seen: set[tuple[str, str]] = set()
    byte_hashes, pixel_hashes = reference_keys
    for left in a.images:
        if _image_in_reference(left, byte_hashes, pixel_hashes):
            continue
        for right in b.images:
            if _image_in_reference(right, byte_hashes, pixel_hashes):
                continue
            key = (left.sha256, right.sha256)
            if key in seen:
                continue
            exact = left.sha256 == right.sha256
            pixel_exact = (
                left.pixel_sha256 is not None
                and left.pixel_sha256 == right.pixel_sha256
            )
            if left.perceptual_hash is None or right.perceptual_hash is None:
                distance = 64
            else:
                distance = (left.perceptual_hash ^ right.perceptual_hash).bit_count()
            color_close = (
                left.mean_rgb is not None
                and right.mean_rgb is not None
                and max(abs(x - y) for x, y in zip(left.mean_rgb, right.mean_rgb)) <= 28
            )
            textured = (left.visual_variance or 0) >= 20 and (right.visual_variance or 0) >= 20
            if exact or pixel_exact or (textured and color_close and distance <= settings.image_near_distance):
                seen.add(key)
                match_type = "byte_exact" if exact else "pixel_exact" if pixel_exact else "near"
                matches.append(
                    ImageMatch(
                        a_name=left.name,
                        b_name=right.name,
                        a_preview=left.preview,
                        b_preview=right.preview,
                        exact=exact or pixel_exact,
                        distance=distance,
                        sha256=left.sha256 if exact else None,
                        pixel_sha256=left.pixel_sha256 if pixel_exact and not exact else None,
                        match_type=match_type,
                    )
                )
    matches.sort(key=lambda item: (not item.exact, item.distance))
    return matches[:100], sum(item.exact for item in matches)


def analyze(
    documents: list[ParsedDocument],
    settings: Settings,
    progress: Callable[[int, int], None] | None = None,
    reference: ParsedDocument | None = None,
) -> AnalysisResult:
    segmented = {doc.id: _segments(doc, settings) for doc in documents}
    if reference is not None:
        grams = _reference_ngrams(reference, settings.reference_min_match_chars)
        segmented = {
            doc_id: [_exclude_reference(item, grams, settings.reference_min_match_chars) for item in items]
            for doc_id, items in segmented.items()
        }
    reference_keys = _reference_image_keys(reference)
    common: set[str] = set()
    if settings.ignore_common_across_all and len(documents) >= 3:
        sets = [{_effective(item) for item in segmented[doc.id] if _effective(item)} for doc in documents]
        common = set.intersection(*sets)
    summaries = [
        DocumentInfo(
            id=doc.id,
            name=doc.name,
            chars=sum(len(item.normalized) for item in segmented[doc.id]),
            blocks=len(doc.blocks),
            images=len(doc.images),
            content=_display_blocks(doc, segmented[doc.id]),
            format=doc.format,
            pages=doc.pages,
            ocr_pages=doc.ocr_pages,
            warnings=list(doc.warnings),
            excluded_reference_chars=sum(sum(item.reference_mask) for item in segmented[doc.id]),
            excluded_reference_images=sum(
                _image_in_reference(image, *reference_keys) for image in doc.images
            ),
        )
        for doc in documents
    ]
    pairs: list[PairResult] = []
    pair_total = len(documents) * (len(documents) - 1) // 2
    for pair_number, (a_doc, b_doc) in enumerate(combinations(documents, 2), start=1):
        a = [item for item in segmented[a_doc.id] if _effective(item) and _effective(item) not in common]
        b = [item for item in segmented[b_doc.id] if _effective(item) and _effective(item) not in common]
        passages, a_coverage, b_coverage, matched_chars = _text_matches(a, b, settings)
        similarity = 2 * a_coverage * b_coverage / (a_coverage + b_coverage) if a_coverage + b_coverage else 0
        images, exact_image_count = _image_matches(a_doc, b_doc, settings, reference_keys)
        pairs.append(
            PairResult(
                a_id=a_doc.id,
                b_id=b_doc.id,
                a_name=a_doc.name,
                b_name=b_doc.name,
                similarity=round(similarity, 4),
                a_coverage=round(a_coverage, 4),
                b_coverage=round(b_coverage, 4),
                matched_chars=matched_chars,
                exact_image_count=exact_image_count,
                passages=passages,
                images=images,
            )
        )
        if progress:
            progress(pair_number, pair_total)
    pairs.sort(key=lambda pair: (pair.exact_image_count > 0, pair.similarity), reverse=True)
    reference_info = None
    if reference is not None:
        reference_info = ReferenceInfo(
            name=reference.name,
            format=reference.format,
            pages=reference.pages,
            ocr_pages=reference.ocr_pages,
            warnings=list(reference.warnings),
        )
    return AnalysisResult(
        documents=summaries,
        pairs=pairs,
        settings=settings,
        report_version=3,
        reference=reference_info,
    )
