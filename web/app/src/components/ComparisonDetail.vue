<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ArrowDown,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileImage,
  FileSearch2,
  Files,
  Info,
  Search,
  SlidersHorizontal,
} from "@lucide/vue";
import DocumentColumn from "./DocumentColumn.vue";
import {
  highlightedPieces,
  pairId,
  percent,
  sortedPassages,
} from "../scripts/comparison";
import type { Mark } from "../scripts/comparison";
import type {
  DocumentInfo,
  PairResult,
  Passage,
  ReferenceInfo,
} from "../scripts/types";

const props = defineProps<{
  pair: PairResult;
  aDocument: DocumentInfo;
  bDocument: DocumentInfo;
  reference: ReferenceInfo | null;
}>();
const tab = ref<"document" | "passages" | "images">("document");
const activeIndex = ref(sortedPassages(props.pair)[0]?.index ?? -1);
const query = ref("");
const filter = ref<"all" | "exact" | "similar">("all");
const onlyMatches = ref(false);
const mobileSide = ref<"a" | "b">("a");
const BATCH_SIZE = 100;
const catalogLimit = ref(BATCH_SIZE);
const passageLimit = ref(BATCH_SIZE);
const tabs: Array<{
  key: "document" | "passages" | "images";
  label: string;
  icon: typeof Files;
}> = [
  { key: "document", label: "全文对照", icon: Files },
  { key: "passages", label: "相似片段", icon: FileSearch2 },
  { key: "images", label: "图片证据", icon: FileImage },
];
const ordered = computed(() => sortedPassages(props.pair));
const filtered = computed(() =>
  ordered.value.filter(({ passage }) => {
    if (filter.value === "exact" && !passage.exact) return false;
    if (filter.value === "similar" && passage.exact) return false;
    const search = query.value.trim().toLocaleLowerCase();
    return (
      !search ||
      `${passage.a_text} ${passage.b_text} ${passage.a_location} ${passage.b_location}`
        .toLocaleLowerCase()
        .includes(search)
    );
  }),
);
const visibleIndices = computed(() => filtered.value.map((item) => item.index));
const catalogEntries = computed(() =>
  filtered.value.slice(0, catalogLimit.value),
);
const passageEntries = computed(() =>
  filtered.value.slice(0, passageLimit.value),
);
const activePassage = computed(() =>
  filtered.value.some((item) => item.index === activeIndex.value)
    ? (props.pair.passages[activeIndex.value] ?? null)
    : null,
);
const activeOrder = computed(() =>
  filtered.value.findIndex((item) => item.index === activeIndex.value),
);
const visibleActiveIndex = computed(() =>
  activePassage.value ? activeIndex.value : -1,
);

watch(
  () => pairId(props.pair),
  () => {
    tab.value = "document";
    activeIndex.value = sortedPassages(props.pair)[0]?.index ?? -1;
    query.value = "";
    filter.value = "all";
    onlyMatches.value = false;
    mobileSide.value = "a";
    catalogLimit.value = BATCH_SIZE;
    passageLimit.value = BATCH_SIZE;
  },
);
watch([query, filter], () => {
  catalogLimit.value = BATCH_SIZE;
  passageLimit.value = BATCH_SIZE;
});
watch(filtered, (items) => {
  if (items.length && !items.some((item) => item.index === activeIndex.value))
    activeIndex.value = items[0]?.index ?? 0;
});
watch(activeOrder, (position) => {
  if (position >= catalogLimit.value) {
    catalogLimit.value = Math.ceil((position + 1) / BATCH_SIZE) * BATCH_SIZE;
  }
});

function step(delta: number) {
  if (!filtered.value.length) return;
  const next = Math.max(
    0,
    Math.min(filtered.value.length - 1, activeOrder.value + delta),
  );
  activeIndex.value = filtered.value[next]?.index ?? 0;
}
function passageMarks(passage: Passage, side: "a" | "b"): Mark[] {
  const ranges = side === "a" ? passage.a_highlights : passage.b_highlights;
  const marks: Mark[] = ranges.map(([start, end]) => ({
    start,
    end,
    kind: "active",
  }));
  const document = side === "a" ? props.aDocument : props.bDocument;
  const blockIndex =
    side === "a" ? passage.a_block_index : passage.b_block_index;
  const offset = side === "a" ? passage.a_start : passage.b_start;
  const text = side === "a" ? passage.a_text : passage.b_text;
  for (const [start, end] of document.content[blockIndex]
    ?.reference_excluded_ranges ?? []) {
    const localStart = Math.max(0, start - offset);
    const localEnd = Math.min(text.length, end - offset);
    if (localEnd > localStart)
      marks.push({ start: localStart, end: localEnd, kind: "excluded" });
  }
  return marks;
}
function matchedPreview(passage: Passage): string {
  return (
    passage.a_highlights
      .map(([start, end]) => passage.a_text.slice(start, end))
      .filter(Boolean)
      .join("…") || passage.a_text
  );
}
</script>

<template>
  <section
    class="panel overflow-hidden"
    :aria-label="`${pair.a_name} 和 ${pair.b_name} 的详细比对`"
  >
    <div class="border-b border-slate-200 px-5 pb-0 pt-5 sm:px-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="eyebrow mb-1.5">详细比对 / PAIR REVIEW</div>
          <h3
            class="flex flex-wrap items-center gap-2 text-[18px] font-semibold tracking-[-.03em] text-slate-900"
          >
            <span>{{ pair.a_name }}</span
            ><ArrowRight :size="16" class="text-slate-300" /><span>{{
              pair.b_name
            }}</span>
          </h3>
          <p class="mt-1.5 text-[12px] text-slate-500">
            按原文位置核查每一处匹配，文字高亮可定位到两份文件。
          </p>
          <p v-if="reference" class="mt-2 text-[11px] text-indigo-700">
            已扣除招标文件重复内容：A
            {{ aDocument.excluded_reference_chars }} 字，B
            {{ bDocument.excluded_reference_chars }} 字；相同图片 A
            {{ aDocument.excluded_reference_images }} 张，B
            {{ bDocument.excluded_reference_images }} 张。
          </p>
        </div>
        <div
          class="flex items-baseline gap-1 rounded-2xl bg-blue-50 px-4 py-2 text-blue-700"
        >
          <span class="text-[23px] font-semibold tracking-[-.04em]">{{
            percent(pair.similarity)
          }}</span
          ><span class="text-[11px]">综合</span>
        </div>
      </div>
      <div class="mt-5 grid gap-3 sm:grid-cols-3">
        <div
          v-for="item in [
            {
              label: reference ? 'A 净文本覆盖' : 'A 文本覆盖',
              value: pair.a_coverage,
              color: 'bg-blue-500',
            },
            {
              label: reference ? 'B 净文本覆盖' : 'B 文本覆盖',
              value: pair.b_coverage,
              color: 'bg-emerald-500',
            },
          ]"
          :key="item.label"
          class="rounded-xl border border-slate-200 p-3"
        >
          <div class="flex justify-between text-[11px] text-slate-500">
            <span>{{ item.label }}</span
            ><strong class="text-[12px] text-slate-800">{{
              percent(item.value)
            }}</strong>
          </div>
          <div class="mt-2.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              class="h-full rounded-full"
              :class="item.color"
              :style="{ width: `${item.value * 100}%` }"
            ></div>
          </div>
        </div>
        <div
          class="flex items-center justify-between rounded-xl border border-slate-200 p-3"
        >
          <div>
            <div class="text-[11px] text-slate-500">重合字符</div>
            <strong class="mt-1 block text-[16px] text-slate-800">{{
              pair.matched_chars.toLocaleString()
            }}</strong>
          </div>
          <div
            class="flex size-9 items-center justify-center rounded-lg bg-slate-50 text-slate-500"
          >
            <Files :size="18" />
          </div>
        </div>
      </div>
      <div class="mt-5 flex gap-6 overflow-x-auto">
        <button
          v-for="item in tabs"
          :key="item.key"
          class="flex shrink-0 items-center gap-1.5 border-b-2 pb-3 text-[12px] font-semibold transition-colors"
          :class="
            tab === item.key
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          "
          @click="tab = item.key"
        >
          <component :is="item.icon" :size="15" />{{ item.label
          }}<span
            class="rounded-full px-1.5 py-0.5 text-[10px]"
            :class="tab === item.key ? 'bg-blue-50' : 'bg-slate-100'"
            >{{
              item.key === "images" ? pair.images.length : pair.passages.length
            }}</span
          >
        </button>
      </div>
    </div>

    <div
      v-if="tab !== 'images'"
      class="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-[#fcfdff] px-5 py-3 sm:px-6"
    >
      <div class="relative min-w-[180px] flex-1">
        <Search
          :size="15"
          class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
        /><input
          v-model="query"
          class="field w-full !py-2 !pl-9"
          type="search"
          placeholder="搜索片段或文档文字"
          aria-label="搜索片段或文档文字"
        />
      </div>
      <select
        v-model="filter"
        class="field !py-2 text-[12px]"
        aria-label="匹配类型"
      >
        <option value="all">全部匹配</option>
        <option value="exact">完全一致</option>
        <option value="similar">相似改写</option></select
      ><label
        v-if="tab === 'document'"
        class="flex items-center gap-2 whitespace-nowrap rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-600"
        ><input
          v-model="onlyMatches"
          type="checkbox"
          class="size-3.5 accent-blue-600"
        />仅看命中段落</label
      >
    </div>

    <div
      v-if="tab === 'document'"
      class="grid gap-4 bg-[#f6f8fb] p-4 sm:p-5 lg:grid-cols-[215px_minmax(0,1fr)]"
    >
      <aside class="min-w-0 rounded-2xl border border-slate-200 bg-white">
        <div
          class="flex items-center justify-between border-b border-slate-100 px-4 py-3"
        >
          <span class="text-[12px] font-semibold text-slate-800">匹配目录</span
          ><span class="text-[11px] text-slate-400"
            >{{ filtered.length }} 处</span
          >
        </div>
        <div class="max-h-[540px] space-y-1 overflow-y-auto p-2">
          <div
            v-if="!filtered.length"
            class="px-3 py-8 text-center text-[11px] leading-5 text-slate-400"
          >
            当前条件下没有匹配片段
          </div>
          <button
            v-for="({ passage, index }, position) in catalogEntries"
            :key="index"
            class="w-full rounded-xl px-3 py-2.5 text-left transition-colors"
            :class="activeIndex === index ? 'bg-blue-50' : 'hover:bg-slate-50'"
            @click="activeIndex = index"
          >
            <div class="mb-1 flex items-center justify-between">
              <span
                class="text-[10px] font-bold"
                :class="
                  activeIndex === index ? 'text-blue-700' : 'text-slate-400'
                "
                >{{ String(position + 1).padStart(2, "0") }} ·
                {{ passage.exact ? "完全一致" : "相似改写" }}</span
              ><span class="text-[10px] text-slate-400">{{
                percent(passage.score)
              }}</span>
            </div>
            <p class="line-clamp-2 text-[11px] leading-[1.6] text-slate-600">
              {{ matchedPreview(passage) }}
            </p>
            <p class="mt-1 truncate text-[10px] text-slate-400">
              {{ passage.a_location }}
            </p>
          </button>
          <button
            v-if="catalogLimit < filtered.length"
            class="w-full rounded-xl bg-blue-50 px-3 py-2.5 text-center text-[11px] font-semibold text-blue-700 hover:bg-blue-100"
            @click="catalogLimit += BATCH_SIZE"
          >
            继续显示匹配（{{ catalogEntries.length }} / {{ filtered.length }}）
          </button>
        </div>
      </aside>
      <div class="min-w-0">
        <div
          class="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5"
        >
          <div
            v-if="activePassage"
            class="flex items-center gap-2 text-[11px] text-slate-600"
          >
            <span class="size-2 rounded-full bg-blue-500"></span
            ><strong class="text-slate-800"
              >当前第 {{ Math.max(activeOrder + 1, 1) }} /
              {{ filtered.length }} 处</strong
            ><span class="hidden sm:inline"
              >· 蓝色为相似文字，浅紫为招标文件排除文字</span
            >
          </div>
          <span v-else class="text-[11px] text-slate-500">暂无选中匹配</span>
          <div class="flex gap-1">
            <button
              class="icon-button"
              aria-label="上一处匹配"
              :disabled="activeOrder <= 0"
              @click="step(-1)"
            >
              <ChevronUp :size="16" /></button
            ><button
              class="icon-button"
              aria-label="下一处匹配"
              :disabled="activeOrder < 0 || activeOrder >= filtered.length - 1"
              @click="step(1)"
            >
              <ChevronDown :size="16" />
            </button>
          </div>
        </div>
        <div
          class="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1 lg:hidden"
          role="group"
          aria-label="切换对照文档"
        >
          <button
            class="rounded-lg px-3 py-2 text-[11px] font-semibold"
            :class="
              mobileSide === 'a'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-500'
            "
            @click="mobileSide = 'a'"
          >
            文档 A</button
          ><button
            class="rounded-lg px-3 py-2 text-[11px] font-semibold"
            :class="
              mobileSide === 'b'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-500'
            "
            @click="mobileSide = 'b'"
          >
            文档 B
          </button>
        </div>
        <div class="grid min-w-0 gap-3 lg:grid-cols-2">
          <DocumentColumn
            :key="`${pairId(pair)}:a`"
            :class="mobileSide === 'a' ? '' : 'hidden lg:block'"
            :document="aDocument"
            :pair="pair"
            side="a"
            :active-index="visibleActiveIndex"
            :query="query"
            :only-matches="onlyMatches"
            :visible-indices="visibleIndices"
            @select="activeIndex = $event"
          /><DocumentColumn
            :key="`${pairId(pair)}:b`"
            :class="mobileSide === 'b' ? '' : 'hidden lg:block'"
            :document="bDocument"
            :pair="pair"
            side="b"
            :active-index="visibleActiveIndex"
            :query="query"
            :only-matches="onlyMatches"
            :visible-indices="visibleIndices"
            @select="activeIndex = $event"
          />
        </div>
      </div>
    </div>

    <div
      v-else-if="tab === 'passages'"
      class="space-y-3 bg-[#f6f8fb] p-4 sm:p-5"
    >
      <div
        v-if="!filtered.length"
        class="rounded-xl border border-slate-200 bg-white py-16 text-center text-[12px] text-slate-400"
      >
        当前筛选下没有相似片段
      </div>
      <article
        v-for="({ passage, index }, position) in passageEntries"
        :key="index"
        class="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5"
      >
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span
              class="flex size-7 items-center justify-center rounded-lg bg-blue-50 text-[11px] font-bold text-blue-700"
              >{{ String(position + 1).padStart(2, "0") }}</span
            ><strong class="text-[12px] text-slate-800">{{
              passage.exact ? "完全一致" : "相似改写"
            }}</strong
            ><span
              class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500"
              >{{ passage.matched_chars }} 字符</span
            >
          </div>
          <span class="text-[11px] font-semibold text-blue-700"
            >片段相似 {{ percent(passage.score) }}</span
          >
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <div
            v-for="side in [
              {
                key: 'a',
                name: pair.a_name,
                text: passage.a_text,
                location: passage.a_location,
              },
              {
                key: 'b',
                name: pair.b_name,
                text: passage.b_text,
                location: passage.b_location,
              },
            ] as const"
            :key="side.key"
            class="rounded-xl border border-slate-200 bg-[#fafbfe] p-4"
          >
            <div class="mb-2 truncate text-[11px] font-semibold text-slate-500">
              {{ side.key.toUpperCase() }} · {{ side.name }} ·
              {{ side.location }}
            </div>
            <p
              class="whitespace-pre-wrap break-words text-[13px] leading-[1.9] text-slate-700"
            >
              <span
                v-for="(piece, pieceIndex) in highlightedPieces(
                  side.text,
                  passageMarks(passage, side.key),
                  query,
                )"
                :key="pieceIndex"
                :class="
                  piece.kind === 'active'
                    ? 'rounded-sm bg-[#d7e5ff] text-[#1553a3]'
                    : piece.kind === 'search'
                      ? 'bg-amber-100'
                      : piece.kind === 'excluded'
                        ? 'rounded-sm bg-indigo-50 text-indigo-500 underline decoration-dotted'
                        : ''
                "
                >{{ piece.text }}</span
              >
            </p>
          </div>
        </div>
        <button
          class="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 hover:text-blue-900"
          @click="
            activeIndex = index;
            tab = 'document';
          "
        >
          在全文中定位 <ArrowDown :size="13" />
        </button>
      </article>
      <button
        v-if="passageLimit < filtered.length"
        class="secondary-button mx-auto !flex"
        @click="passageLimit += BATCH_SIZE"
      >
        继续加载相似片段（{{ passageEntries.length }} / {{ filtered.length }}）
      </button>
    </div>

    <div v-else class="bg-[#f6f8fb] p-4 sm:p-5">
      <div
        v-if="!pair.images.length"
        class="rounded-2xl border border-slate-200 bg-white py-16 text-center"
      >
        <FileImage :size="26" class="mx-auto mb-3 text-slate-300" />
        <p class="text-[13px] font-medium text-slate-600">
          未发现一致或疑似相似图片
        </p>
      </div>
      <div v-else class="grid gap-4 2xl:grid-cols-2">
        <article
          v-for="(match, index) in pair.images"
          :key="`${match.a_name}:${match.b_name}:${index}`"
          class="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5"
        >
          <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span
                class="flex size-7 items-center justify-center rounded-lg"
                :class="
                  match.exact
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-amber-50 text-amber-700'
                "
                ><CheckCircle2
                  v-if="match.exact"
                  :size="16" /><SlidersHorizontal v-else :size="16" /></span
              ><strong class="text-[12px] text-slate-800">{{
                match.match_type === "byte_exact"
                  ? "图片字节一致"
                  : match.match_type === "pixel_exact"
                    ? "图片像素一致"
                    : "图片疑似相似"
              }}</strong>
            </div>
            <span class="text-[11px] text-slate-400">{{
              match.match_type === "byte_exact"
                ? "SHA-256 字节一致"
                : match.match_type === "pixel_exact"
                  ? "像素内容一致，编码不同"
                  : `感知距离 ${match.distance}`
            }}</span>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div
              v-for="side in [
                { label: 'A', name: match.a_name, preview: match.a_preview },
                { label: 'B', name: match.b_name, preview: match.b_preview },
              ]"
              :key="side.label"
              class="min-w-0 rounded-xl border border-slate-100 bg-slate-50 p-2"
            >
              <img
                v-if="side.preview"
                :src="side.preview"
                :alt="`${side.label} 图片预览`"
                class="h-40 w-full rounded-lg bg-white object-contain"
              />
              <div
                v-else
                class="flex h-40 items-center justify-center text-[11px] text-slate-400"
              >
                无法预览
              </div>
              <p class="mt-2 truncate px-1 text-[11px] text-slate-500">
                {{ side.label }} · {{ side.name }}
              </p>
            </div>
          </div>
          <p
            v-if="match.sha256 || match.pixel_sha256"
            class="mt-3 truncate font-mono text-[10px] text-slate-400"
            :title="match.sha256 || match.pixel_sha256 || ''"
          >
            {{ match.sha256 ? "文件 SHA-256" : "像素 SHA-256" }}
            {{ match.sha256 || match.pixel_sha256 }}
          </p>
        </article>
      </div>
    </div>
    <div
      class="flex items-start gap-2 border-t border-slate-200 bg-white px-5 py-3.5 text-[11px] leading-5 text-slate-500 sm:px-6"
    >
      <Info :size="14" class="mt-0.5 shrink-0" /><span
        >文本比例为片段覆盖率估计，综合分数取 A/B
        覆盖率的调和平均值。图片单独报告，不计入文本比例；结果需人工复核。</span
      >
    </div>
  </section>
</template>
