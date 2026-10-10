<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  CheckCircle2,
  FileSearch2,
  LockKeyhole,
  Sparkles,
  X,
} from "@lucide/vue";
import UploadPanel from "../../components/UploadPanel.vue";
import SettingsPanel from "../../components/SettingsPanel.vue";
import { submitAnalysis } from "../../scripts/api";
import type { Settings } from "../../scripts/types";

const router = useRouter();
const files = ref<File[]>([]);
const referenceFile = ref<File | null>(null);
const settings = ref<Settings>({
  similarity_threshold: 0.8,
  minimum_match_chars: 16,
  ignore_short_blocks: 12,
  ignore_common_across_all: false,
  image_near_distance: 6,
  pdf_ocr_mode: "auto",
  reference_min_match_chars: 16,
});
const submitting = ref(false);
const error = ref("");

function addFiles(incoming: File[]) {
  const next = [...files.value];
  error.value = "";
  for (const file of incoming) {
    if (!/\.(docx|pdf)$/i.test(file.name)) {
      error.value = "仅支持 .docx 和 .pdf 文件。";
      continue;
    }
    if (
      !next.some(
        (item) =>
          item.name === file.name &&
          item.size === file.size &&
          item.lastModified === file.lastModified,
      )
    )
      next.push(file);
  }
  if (next.length > 12) {
    error.value = "一次最多分析 12 份投标文件。";
    return;
  }
  files.value = next;
}
function setReferenceFile(file: File | null) {
  if (file && !/\.(docx|pdf)$/i.test(file.name)) {
    error.value = "招标文件必须是 .docx 或 .pdf 文件。";
    return;
  }
  referenceFile.value = file;
  error.value = "";
}
function removeFile(index: number) {
  files.value.splice(index, 1);
  error.value = "";
}
function clearFiles() {
  files.value = [];
  referenceFile.value = null;
  error.value = "";
}

async function submit() {
  if (files.value.length < 2) {
    error.value = "请至少添加两份投标文件。";
    return;
  }
  if (submitting.value) return;
  submitting.value = true;
  error.value = "";
  try {
    const job = await submitAnalysis(
      files.value,
      settings.value,
      referenceFile.value,
    );
    localStorage.setItem("bid-review.current-job", job.id);
    await router.push({ name: "job", params: { id: job.id } });
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "上传失败，请重试。";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="space-y-8">
    <section
      class="hero relative overflow-hidden rounded-[28px] border border-[#e2eaf6] px-6 py-8 sm:px-9 sm:py-9"
    >
      <div class="relative z-10 max-w-[760px]">
        <div
          class="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white/80 px-3 py-1.5 text-[11px] font-semibold text-blue-700"
        >
          <Sparkles :size="13" /> 为标书核查而设计
        </div>
        <h1
          class="text-[31px] font-semibold leading-[1.25] tracking-[-.065em] text-slate-950 sm:text-[42px]"
        >
          新建一次<span class="text-blue-600">标书相似性检测。</span>
        </h1>
        <p
          class="mt-3 max-w-[650px] text-[13px] leading-6 text-slate-600 sm:text-[14px]"
        >
          上传多份投标文件，可额外指定一份招标文件。系统只比较投标文件之间的独有内容，并保留可追溯的历史报告。
        </p>
        <div
          class="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] font-medium text-slate-500"
        >
          <span class="inline-flex items-center gap-1.5"
            ><CheckCircle2 :size="14" class="text-blue-600" />
            自动两两比对</span
          ><span class="inline-flex items-center gap-1.5"
            ><CheckCircle2 :size="14" class="text-indigo-600" />
            招标内容排除</span
          ><span class="inline-flex items-center gap-1.5"
            ><CheckCircle2 :size="14" class="text-emerald-600" />
            历史报告可重开</span
          >
        </div>
      </div>
      <div
        class="pointer-events-none absolute -right-5 -top-24 hidden size-[360px] rounded-full border-[55px] border-white/45 md:block"
      ></div>
    </section>
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <div class="eyebrow mb-1">NEW ANALYSIS</div>
        <h2 class="text-[23px] font-semibold tracking-[-.045em] text-slate-900">
          配置本次检测
        </h2>
      </div>
      <span class="inline-flex items-center gap-1.5 text-[11px] text-slate-400"
        ><LockKeyhole :size="13" /> 上传原件分析后清理 · 报告存入历史</span
      >
    </div>
    <div class="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(350px,.9fr)]">
      <UploadPanel
        :files="files"
        :reference="referenceFile"
        :busy="submitting"
        @add="addFiles"
        @set-reference="setReferenceFile"
        @remove="removeFile"
        @clear="clearFiles"
        @run="submit"
      /><SettingsPanel
        v-model="settings"
        :has-reference="Boolean(referenceFile)"
      />
    </div>
    <div
      v-if="error"
      role="alert"
      class="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-red-700"
    >
      <X :size="15" /> {{ error }}
    </div>
    <div
      v-if="submitting"
      role="status"
      class="flex items-center gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4 text-[12px] text-blue-800"
    >
      <div
        class="size-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-700"
      ></div>
      正在上传文件并创建后台任务，请等待页面进入检测详情…
    </div>
    <div
      class="panel flex items-start gap-3 p-5 text-[12px] leading-6 text-slate-500"
    >
      <FileSearch2 :size="19" class="mt-0.5 shrink-0 text-blue-600" />
      <p>
        上传完成后会进入独立的检测详情页。分析由服务器后台执行，离开或刷新页面不会中断任务；稍后也可从历史记录重新打开。
      </p>
    </div>
  </div>
</template>
