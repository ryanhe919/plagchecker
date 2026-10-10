import type { PairResult, Passage } from "./types";

export type Side = "a" | "b";
export type MarkKind = "active" | "matched" | "search" | "excluded" | null;
export interface Mark {
  start: number;
  end: number;
  kind: Exclude<MarkKind, null>;
}
export interface TextPiece {
  text: string;
  kind: MarkKind;
}

export function pairId(pair: PairResult): string {
  return `${pair.a_id}:${pair.b_id}`;
}

export function sortedPassages(
  pair: PairResult,
): Array<{ passage: Passage; index: number }> {
  return pair.passages
    .map((passage, index) => ({ passage, index }))
    .sort(
      (left, right) =>
        left.passage.a_block_index - right.passage.a_block_index ||
        left.passage.a_start - right.passage.a_start,
    );
}

export function marksForBlock(
  pair: PairResult,
  side: Side,
  blockIndex: number,
  activeIndex: number,
  visibleIndices?: ReadonlySet<number>,
): Mark[] {
  const marks: Mark[] = [];
  pair.passages.forEach((passage, index) => {
    if (visibleIndices && !visibleIndices.has(index)) return;
    const currentIndex =
      side === "a" ? passage.a_block_index : passage.b_block_index;
    if (currentIndex !== blockIndex) return;
    const offset = side === "a" ? passage.a_start : passage.b_start;
    const ranges = side === "a" ? passage.a_highlights : passage.b_highlights;
    for (const [start, end] of ranges) {
      marks.push({
        start: offset + start,
        end: offset + end,
        kind: index === activeIndex ? "active" : "matched",
      });
    }
  });
  return marks;
}

export function highlightedPieces(
  text: string,
  marks: Mark[],
  search = "",
): TextPiece[] {
  const allMarks = [...marks];
  const needle = search.trim().toLocaleLowerCase();
  if (needle) {
    const lower = text.toLocaleLowerCase();
    let start = lower.indexOf(needle);
    while (start >= 0) {
      allMarks.push({ start, end: start + needle.length, kind: "search" });
      start = lower.indexOf(needle, start + needle.length);
    }
  }
  const bounds = new Set([0, text.length]);
  for (const mark of allMarks) {
    bounds.add(Math.max(0, Math.min(text.length, mark.start)));
    bounds.add(Math.max(0, Math.min(text.length, mark.end)));
  }
  const ordered = [...bounds].sort((a, b) => a - b);
  const pieces: TextPiece[] = [];
  for (let index = 0; index < ordered.length - 1; index++) {
    const start = ordered[index];
    const end = ordered[index + 1];
    if (start === undefined || end === undefined || start === end) continue;
    const covering = allMarks.filter(
      (mark) => mark.start <= start && mark.end >= end,
    );
    const kind: MarkKind = covering.some((mark) => mark.kind === "active")
      ? "active"
      : covering.some((mark) => mark.kind === "search")
        ? "search"
        : covering.some((mark) => mark.kind === "matched")
          ? "matched"
          : covering.some((mark) => mark.kind === "excluded")
            ? "excluded"
            : null;
    const previous = pieces[pieces.length - 1];
    if (previous?.kind === kind) previous.text += text.slice(start, end);
    else pieces.push({ text: text.slice(start, end), kind });
  }
  return pieces;
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
