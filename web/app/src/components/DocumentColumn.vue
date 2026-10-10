<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { FileText, LocateFixed } from "@lucide/vue";
import { highlightedPieces, marksForBlock } from "../scripts/comparison";
import type { Side } from "../scripts/comparison";
import type { DocumentInfo, PairResult, TextBlock } from "../scripts/types";

const props = defineProps<{
  document: DocumentInfo;
  pair: PairResult;
  side: Side;
  activeIndex: number;
  query: string;
  onlyMatches: boolean;
  visibleIndices: number[];
}>();
const emit = defineEmits<{ select: [index: number] }>();
const scrollArea = ref<HTMLElement | null>(null);
const visibleIndexSet = computed(() => new Set(props.visibleIndices));
const blockHits = computed(() => {
  const hits = new Map<number, number[]>();
  props.pair.passages.forEach((passage, index) => {
    if (!visibleIndexSet.value.has(index)) return;
    const blockIndex =
      props.side === "a" ? passage.a_block_index : passage.b_block_index;
    const current = hits.get(blockIndex) ?? [];
    current.push(index);
    hits.set(blockIndex, current);
  });
  return hits;
});
const visibleBlocks = computed(() =>
  props.document.content
    .map((block, index) => ({ block, index }))
    .filter((entry) => !props.onlyMatches || blockHits.value.has(entry.index)),
);
function pieces(blockIndex: number, block: TextBlock) {
  const matched = marksForBlock(
    props.pair,
    props.side,
    blockIndex,
    props.activeIndex,
    visibleIndexSet.value,
  );
  const excluded = (block.reference_excluded_ranges ?? []).map(
    ([start, end]) => ({ start, end, kind: "excluded" as const }),
  );
  return highlightedPieces(block.text, [...matched, ...excluded], props.query);
}

watch(
  () => props.activeIndex,
  async () => {
    await nextTick();
    const passage = props.pair.passages[props.activeIndex];
    if (!passage || !scrollArea.value) return;
    const blockIndex =
      props.side === "a" ? passage.a_block_index : passage.b_block_index;
    const element = scrollArea.value.querySelector<HTMLElement>(
      `[data-block-index="${blockIndex}"]`,
    );
    if (element) {
      const container = scrollArea.value;
      const offset =
        element.getBoundingClientRect().top -
        container.getBoundingClientRect().top;
      scrollArea.value.scrollTo({
        top: container.scrollTop + offset - 90,
        behavior: "smooth",
      });
    }
  },
);
</script>

<template>
  <div
    class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white"
  >
    <div
      class="flex items-center justify-between gap-3 border-b border-slate-200 bg-[#fbfcfe] px-4 py-3.5"
    >
      <div class="flex min-w-0 items-center gap-3">
        <div
          class="flex size-8 shrink-0 items-center justify-center rounded-lg"
          :class="
            side === 'a'
              ? 'bg-blue-50 text-blue-600'
              : 'bg-emerald-50 text-emerald-600'
          "
        >
          <FileText :size="16" />
        </div>
        <div class="min-w-0">
          <div class="text-[10px] font-bold tracking-[.1em] text-slate-400">
            {{ side === "a" ? "DOCUMENT A" : "DOCUMENT B" }}
          </div>
          <h4
            class="truncate text-[12px] font-semibold text-slate-800"
            :title="document.name"
          >
            {{ document.name }}
          </h4>
        </div>
      </div>
      <span class="shrink-0 text-[11px] text-slate-400">{{
        document.format === "pdf"
          ? `${document.pages} 页`
          : `${document.blocks} 段`
      }}</span>
    </div>
    <div
      ref="scrollArea"
      class="h-[360px] space-y-2 overflow-y-auto bg-[#fafbfc] p-3 sm:h-[440px] sm:p-4 lg:h-[540px]"
    >
      <div
        v-if="!visibleBlocks.length"
        class="flex h-full flex-col items-center justify-center text-center text-[12px] text-slate-400"
      >
        <LocateFixed :size="20" class="mb-2" />当前筛选下没有命中段落
      </div>
      <article
        v-for="entry in visibleBlocks"
        :key="entry.index"
        :data-block-index="entry.index"
        class="rounded-xl border bg-white px-3.5 py-3 transition-colors"
        :class="
          (blockHits.get(entry.index) ?? []).includes(activeIndex)
            ? 'border-blue-300 shadow-[0_0_0_2px_rgba(26,115,232,.08)]'
            : blockHits.has(entry.index)
              ? 'border-blue-100'
              : 'border-slate-100'
        "
      >
        <div class="mb-2 flex items-center justify-between gap-2">
          <span
            class="truncate text-[10px] font-medium text-slate-400"
            :title="entry.block.location"
            >{{ entry.block.location }}</span
          ><button
            v-if="blockHits.has(entry.index)"
            class="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 hover:bg-blue-100"
            @click="emit('select', (blockHits.get(entry.index) ?? [])[0] ?? 0)"
          >
            {{ blockHits.get(entry.index)?.length }} 处命中
          </button>
        </div>
        <p
          class="whitespace-pre-wrap break-words text-[12px] leading-[1.9] text-slate-700"
        >
          <span
            v-for="(piece, pieceIndex) in pieces(entry.index, entry.block)"
            :key="pieceIndex"
            :class="
              piece.kind === 'active'
                ? 'rounded-sm bg-[#c9dcff] text-[#124a9c]'
                : piece.kind === 'matched'
                  ? 'rounded-sm bg-[#e7efff] text-[#265aab]'
                  : piece.kind === 'search'
                    ? 'rounded-sm bg-[#fff1be] text-[#735d15]'
                    : piece.kind === 'excluded'
                      ? 'rounded-sm bg-indigo-50 text-indigo-500 underline decoration-dotted'
                      : ''
            "
            >{{ piece.text }}</span
          >
        </p>
      </article>
    </div>
  </div>
</template>
