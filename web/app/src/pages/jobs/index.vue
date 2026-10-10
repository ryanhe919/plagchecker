<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  FilePlus2,
  Info,
  X,
} from "@lucide/vue";
import AnalysisResults from "../../components/AnalysisResults.vue";
import { getJobResult, getJobStatus } from "../../scripts/api";
import type { AnalysisResult, JobStatus } from "../../scripts/types";

const route = useRoute();
const status = ref<JobStatus | null>(null);
const result = ref<AnalysisResult | null>(null);
const error = ref("");
const progress = computed(() =>
  status.value
    ? Math.min(
        99,
        Math.max(
          0,
          Math.round((status.value.completed / status.value.total) * 100),
        ),
      )
    : 0,
);
let timer: number | undefined;
let generation = 0;

async function poll(jobId: string, current: number) {
  try {
    const currentStatus = await getJobStatus(jobId);
    if (current !== generation) return;
    status.value = currentStatus;
    error.value = "";
    if (currentStatus.state === "completed") {
      const report = await getJobResult(jobId);
      if (current !== generation) return;
      result.value = report;
      return;
    }
    if (currentStatus.state === "failed") {
      error.value = currentStatus.error || "分析失败，请重新上传文件。";
      return;
    }
  } catch (cause) {
    if (current !== generation) return;
    error.value =
      cause instanceof Error ? cause.message : "暂时无法读取进度，正在重试。";
    if (error.value.includes("任务不存在") || error.value.includes("已过期"))
      return;
  }
  if (current === generation)
    timer = window.setTimeout(() => void poll(jobId, current), 1500);
}

watch(
  () => route.params.id,
  (value) => {
    generation += 1;
    if (timer) window.clearTimeout(timer);
    status.value = null;
    result.value = null;
    error.value = "";
    if (typeof value === "string") {
      localStorage.setItem("bid-review.current-job", value);
      void poll(value, generation);
    }
  },
  { immediate: true },
);
onUnmounted(() => {
  generation += 1;
  if (timer) window.clearTimeout(timer);
});
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <RouterLink
          to="/history"
          class="mb-3 inline-flex items-center gap-1 text-[12px] font-medium text-blue-700 hover:underline"
          ><ArrowLeft :size="14" /> 历史记录</RouterLink
        >
        <div class="eyebrow mb-1.5">ANALYSIS DETAIL</div>
        <h1 class="text-[27px] font-semibold tracking-[-.05em] text-slate-900">
          检测详情
        </h1>
        <p class="mt-1.5 max-w-[850px] break-words text-[12px] text-slate-500">
          {{ status?.files.join("、") || "正在读取任务…"
          }}<span v-if="status?.reference_name" class="ml-2 text-indigo-700"
            >· 招标文件：{{ status.reference_name }}</span
          >
        </p>
      </div>
      <RouterLink to="/new" class="secondary-button"
        ><FilePlus2 :size="14" /> 新建检测</RouterLink
      >
    </div>
    <div
      v-if="!status && !error"
      class="panel flex min-h-[180px] items-center justify-center gap-3 text-[12px] text-slate-500"
    >
      <div
        class="size-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-700"
      ></div>
      正在读取检测任务…
    </div>
    <section
      v-if="status && (status.state === 'queued' || status.state === 'running')"
      class="panel p-5 sm:p-6"
      role="status"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="eyebrow mb-1.5">BACKGROUND ANALYSIS</div>
          <h2 class="text-[18px] font-semibold text-slate-900">
            后台分析进行中
          </h2>
          <p class="mt-1.5 text-[12px] text-slate-500">{{ status.message }}</p>
        </div>
        <span
          class="rounded-full bg-blue-50 px-3 py-1.5 text-[13px] font-semibold text-blue-700"
          >{{ progress }}%</span
        >
      </div>
      <div
        class="mt-5 h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        :aria-valuenow="progress"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-label="分析进度"
      >
        <div
          class="h-full rounded-full bg-blue-600 transition-[width] duration-500"
          :style="{ width: `${progress}%` }"
        ></div>
      </div>
      <div
        class="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500"
      >
        <span class="inline-flex items-center gap-1"
          ><Clock3 :size="13" />
          {{
            status.phase === "queued"
              ? "等待后台处理"
              : status.phase === "extracting"
                ? "提取文档内容"
                : "逐对比对"
          }}</span
        ><span>此任务有独立地址，刷新或离开页面不会中断分析</span>
      </div>
    </section>
    <div
      v-if="error"
      role="alert"
      class="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-red-700"
    >
      <X :size="15" /> {{ error }}
    </div>
    <div
      v-if="status?.state === 'completed' && result"
      class="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-[12px] text-emerald-800"
    >
      <CheckCircle2 :size="16" /> 检测已完成，完整报告已存入历史记录。
    </div>
    <AnalysisResults v-if="result" :result="result" />
    <div
      v-else-if="status?.state === 'failed'"
      class="panel flex items-start gap-3 p-5 text-[12px] text-slate-500"
    >
      <Info :size="17" class="mt-0.5 shrink-0" />
      本次任务未生成报告。可以返回新建检测重新上传，失败记录仍会保留在历史中。
    </div>
  </div>
</template>
