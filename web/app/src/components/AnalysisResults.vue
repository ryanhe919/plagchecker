<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ArrowDownToLine,
  ArrowRight,
  FileImage,
  FileText,
  Layers3,
  Search,
  Sparkles,
} from "@lucide/vue";
import ComparisonDetail from "./ComparisonDetail.vue";
import { pairId, percent } from "../scripts/comparison";
import type { AnalysisResult, PairResult } from "../scripts/types";

const props = defineProps<{ result: AnalysisResult }>();
const selectedId = ref(
  props.result.pairs[0] ? pairId(props.result.pairs[0]) : "",
);
const search = ref("");
const filter = ref<"all" | "attention" | "images">("all");
const sort = ref<"risk" | "similarity" | "name">("risk");
watch(
  () => props.result,
  (value) => {
    selectedId.value = value.pairs[0] ? pairId(value.pairs[0]) : "";
    search.value = "";
    filter.value = "all";
  },
);
const selected = computed(
  () =>
    props.result.pairs.find((pair) => pairId(pair) === selectedId.value) ??
    props.result.pairs[0],
);
const aDocument = computed(() =>
  props.result.documents.find((doc) => doc.id === selected.value?.a_id),
);
const bDocument = computed(() =>
  props.result.documents.find((doc) => doc.id === selected.value?.b_id),
);
const maxSimilarity = computed(() =>
  Math.max(0, ...props.result.pairs.map((pair) => pair.similarity)),
);
const exactImages = computed(() =>
  props.result.pairs.reduce((sum, pair) => sum + pair.exact_image_count, 0),
);
const excludedReferenceChars = computed(() =>
  props.result.documents.reduce(
    (sum, document) => sum + document.excluded_reference_chars,
    0,
  ),
);
const excludedReferenceImages = computed(() =>
  props.result.documents.reduce(
    (sum, document) => sum + document.excluded_reference_images,
    0,
  ),
);
const pdfCount = computed(
  () =>
    props.result.documents.filter((document) => document.format === "pdf")
      .length,
);
const ocrPages = computed(() =>
  props.result.documents.reduce((sum, document) => sum + document.ocr_pages, 0),
);
const extractionWarnings = computed(() =>
  props.result.documents.flatMap((document) =>
    document.warnings.map((warning) => `${document.name}：${warning}`),
  ),
);
const attentionCount = computed(
  () =>
    props.result.pairs.filter(
      (pair) => pair.similarity >= 0.35 || pair.exact_image_count > 0,
    ).length,
);
const visiblePairs = computed(() =>
  props.result.pairs
    .filter((pair) =>
      `${pair.a_name} ${pair.b_name}`
        .toLocaleLowerCase()
        .includes(search.value.trim().toLocaleLowerCase()),
    )
    .filter(
      (pair) =>
        filter.value === "all" ||
        (filter.value === "attention" &&
          (pair.similarity >= 0.35 || pair.exact_image_count > 0)) ||
        (filter.value === "images" && pair.exact_image_count > 0),
    )
    .sort((a, b) =>
      sort.value === "name"
        ? `${a.a_name}${a.b_name}`.localeCompare(`${b.a_name}${b.b_name}`)
        : sort.value === "similarity"
          ? b.similarity - a.similarity
          : Number(b.exact_image_count > 0) - Number(a.exact_image_count > 0) ||
            b.similarity - a.similarity,
    ),
);

function download(name: string, body: string, mime: string) {
  const url = URL.createObjectURL(new Blob([body], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
function csvCell(value: string | number): string {
  const text = String(value);
  const safe = /^\s*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}
function downloadCsv() {
  const rows = [
    [
      "文件 A",
      "文件 B",
      "综合相似度",
      "A 覆盖率",
      "B 覆盖率",
      "相似片段",
      "完全一致图片",
    ],
  ];
  for (const pair of props.result.pairs)
    rows.push([
      pair.a_name,
      pair.b_name,
      percent(pair.similarity),
      percent(pair.a_coverage),
      percent(pair.b_coverage),
      String(pair.passages.length),
      String(pair.exact_image_count),
    ]);
  download(
    "标书查重摘要.csv",
    "\ufeff" + rows.map((row) => row.map(csvCell).join(",")).join("\r\n"),
    "text/csv;charset=utf-8",
  );
}
function downloadJson() {
  download(
    "标书查重完整报告.json",
    JSON.stringify(props.result, null, 2),
    "application/json;charset=utf-8",
  );
}
function riskLabel(pair: PairResult): string {
  if (pair.exact_image_count) return "图片一致";
  if (pair.similarity >= 0.35) return "建议核查";
  return "常规比对";
}
</script>

<template>
  <section id="results" class="scroll-mt-7 space-y-5">
    <div
      v-if="
        result.report_version !== 2 &&
        result.pairs.some((pair) => pair.passages.length >= 200)
      "
      class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] leading-5 text-amber-900"
    >
      这份旧版报告可能只保留了前 200
      处相似片段。请重新上传原文件并开始新的分析，以获取完整片段列表。
    </div>

    <div
      v-if="result.reference"
      class="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-[12px] leading-5 text-indigo-900"
    >
      排除依据：<strong>{{ result.reference.name }}</strong
      >。已从投标文件中排除
      {{ excludedReferenceChars.toLocaleString() }} 个相同字符和
      {{ excludedReferenceImages }} 张一致图片；招标文件本身不参与两两比对。
    </div>
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div class="eyebrow mb-2">ANALYSIS RESULTS</div>
        <h2 class="text-[27px] font-semibold tracking-[-.05em] text-slate-900">
          比对工作台
        </h2>
        <p class="mt-1.5 text-[13px] text-slate-500">
          从概览进入任意一组文件，查看完整文字和对应证据。
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="secondary-button" @click="downloadCsv">
          <ArrowDownToLine :size="15" /> 摘要 CSV</button
        ><button class="secondary-button" @click="downloadJson">
          <ArrowDownToLine :size="15" /> 完整 JSON
        </button>
      </div>
    </div>

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div
        v-for="item in [
          {
            label: '分析文件',
            value: result.documents.length,
            unit: '份',
            icon: FileText,
            color: 'bg-blue-50 text-blue-600',
          },
          {
            label: '两两组合',
            value: result.pairs.length,
            unit: '组',
            icon: Layers3,
            color: 'bg-violet-50 text-violet-600',
          },
          {
            label: '最高文本相似度',
            value: percent(maxSimilarity),
            unit: '',
            icon: Sparkles,
            color: 'bg-amber-50 text-amber-600',
          },
          {
            label: '完全一致图片',
            value: exactImages,
            unit: '组',
            icon: FileImage,
            color: 'bg-emerald-50 text-emerald-600',
          },
        ]"
        :key="item.label"
        class="panel flex items-center justify-between p-4 sm:p-5"
      >
        <div>
          <div class="text-[11px] font-medium text-slate-500">
            {{ item.label }}
          </div>
          <div
            class="mt-2 text-[24px] font-semibold tracking-[-.04em] text-slate-900"
          >
            {{ item.value
            }}<span class="ml-1 text-[12px] font-normal text-slate-400">{{
              item.unit
            }}</span>
          </div>
        </div>
        <div
          class="flex size-10 items-center justify-center rounded-xl"
          :class="item.color"
        >
          <component :is="item.icon" :size="19" />
        </div>
      </div>
    </div>

    <div
      v-if="pdfCount"
      class="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-[12px] text-blue-800"
    >
      本次包含 {{ pdfCount }} 份 PDF；{{
        ocrPages ? `${ocrPages} 页已进行 OCR 识别` : "文字直接从 PDF 提取"
      }}。PDF 匹配位置按页显示。
    </div>
    <div
      v-if="extractionWarnings.length"
      class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[11px] leading-5 text-amber-900"
    >
      <p class="font-semibold">部分页面需要留意</p>
      <ul class="mt-1 list-inside list-disc">
        <li v-for="warning in extractionWarnings.slice(0, 5)" :key="warning">
          {{ warning }}
        </li>
      </ul>
      <p v-if="extractionWarnings.length > 5" class="mt-1">
        其余提示可在完整 JSON 报告中查看。
      </p>
    </div>

    <div
      v-if="attentionCount"
      class="flex items-start gap-2 rounded-2xl border border-amber-200 bg-[#fffaf0] px-4 py-3 text-[12px] leading-5 text-amber-900"
    >
      <Sparkles :size="15" class="mt-0.5 shrink-0" /><span
        >{{ attentionCount }} 组建议优先核查：文本相似度达到 35%
        或发现完全一致图片。此提示只用于安排核查顺序。</span
      >
    </div>

    <div class="panel overflow-hidden">
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 sm:px-6"
      >
        <div>
          <h3 class="text-[14px] font-semibold text-slate-900">文件对</h3>
          <p class="mt-0.5 text-[11px] text-slate-400">
            选择一组，进入详细比对
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <div class="relative">
            <Search
              :size="14"
              class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            /><input
              v-model="search"
              class="field w-[190px] !py-2 !pl-8"
              type="search"
              placeholder="搜索文件名"
              aria-label="搜索文件名"
            />
          </div>
          <select v-model="filter" class="field !py-2" aria-label="筛选文件对">
            <option value="all">全部 {{ result.pairs.length }}</option>
            <option value="attention">优先核查 {{ attentionCount }}</option>
            <option value="images">
              图片一致
              {{ result.pairs.filter((pair) => pair.exact_image_count).length }}
            </option></select
          ><select v-model="sort" class="field !py-2" aria-label="排序文件对">
            <option value="risk">按风险</option>
            <option value="similarity">按相似度</option>
            <option value="name">按名称</option>
          </select>
        </div>
      </div>
      <div
        v-if="!visiblePairs.length"
        class="px-5 py-10 text-center text-[12px] text-slate-400"
      >
        没有符合当前搜索或筛选条件的文件对
      </div>
      <div
        v-else
        class="grid max-h-[310px] gap-3 overflow-y-auto p-3 sm:grid-cols-2 xl:grid-cols-3"
      >
        <button
          v-for="pair in visiblePairs"
          :key="pairId(pair)"
          class="group min-w-0 rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-sm"
          :class="
            pairId(pair) === selectedId
              ? 'border-blue-300 bg-blue-50/55 shadow-[0_0_0_1px_rgba(26,115,232,.08)]'
              : 'border-slate-200 bg-white hover:border-blue-200'
          "
          @click="selectedId = pairId(pair)"
        >
          <div class="mb-3 flex items-start justify-between gap-3">
            <span
              class="rounded-full px-2 py-1 text-[10px] font-semibold"
              :class="
                pair.exact_image_count
                  ? 'bg-emerald-50 text-emerald-700'
                  : pair.similarity >= 0.35
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-slate-100 text-slate-500'
              "
              >{{ riskLabel(pair) }}</span
            ><span
              class="text-[18px] font-semibold tracking-[-.04em] text-slate-900"
              >{{ percent(pair.similarity) }}</span
            >
          </div>
          <div
            class="flex items-center gap-1.5 text-[12px] font-medium text-slate-800"
          >
            <span class="min-w-0 truncate" :title="pair.a_name">{{
              pair.a_name
            }}</span
            ><ArrowRight :size="13" class="shrink-0 text-slate-300" /><span
              class="min-w-0 truncate"
              :title="pair.b_name"
              >{{ pair.b_name }}</span
            >
          </div>
          <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              class="h-full rounded-full bg-blue-500"
              :style="{ width: `${pair.similarity * 100}%` }"
            ></div>
          </div>
          <div class="mt-3 flex items-center gap-3 text-[11px] text-slate-500">
            <span>{{ pair.passages.length }} 处片段</span
            ><span v-if="pair.exact_image_count" class="text-emerald-700"
              >{{ pair.exact_image_count }} 组图片一致</span
            >
          </div>
        </button>
      </div>
    </div>

    <ComparisonDetail
      v-if="selected && aDocument && bDocument"
      :key="pairId(selected)"
      :pair="selected"
      :a-document="aDocument"
      :b-document="bDocument"
      :reference="result.reference"
    />
    <p class="text-[11px] leading-5 text-slate-400">
      {{ result.caveat }}
      所有文本匹配均保留，页面分批加载以保持流畅；图片证据列表展示前 100
      组，完全一致总数按全部结果统计。
    </p>
  </section>
</template>
