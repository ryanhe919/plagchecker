<script setup lang="ts">
import { computed, ref } from "vue";
import {
  ArrowUpRight,
  FilePlus2,
  FileText,
  FolderOpen,
  Trash2,
  UploadCloud,
  X,
} from "@lucide/vue";

const props = defineProps<{
  files: File[];
  reference: File | null;
  busy: boolean;
}>();
const emit = defineEmits<{
  add: [files: File[]];
  remove: [index: number];
  clear: [];
  run: [];
  setReference: [file: File | null];
}>();
const input = ref<HTMLInputElement | null>(null);
const referenceInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);
const pairCount = computed(
  () => (props.files.length * (props.files.length - 1)) / 2,
);

function accept(files: FileList | null) {
  if (files) emit("add", Array.from(files));
}
function onInput(event: Event) {
  const element = event.target as HTMLInputElement;
  accept(element.files);
  element.value = "";
}
function onReferenceInput(event: Event) {
  const element = event.target as HTMLInputElement;
  emit("setReference", element.files?.[0] ?? null);
  element.value = "";
}
function onDrop(event: DragEvent) {
  dragging.value = false;
  accept(event.dataTransfer?.files ?? null);
}
function sizeLabel(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<template>
  <section class="panel flex min-h-[470px] flex-col overflow-hidden">
    <div
      class="flex flex-wrap items-start justify-between gap-3 px-6 pb-5 pt-6 sm:px-7"
    >
      <div>
        <div class="eyebrow mb-2">01 / 添加文档</div>
        <h2 class="text-[20px] font-semibold tracking-[-.03em] text-slate-900">
          上传需要核查的标书
        </h2>
        <p class="mt-1.5 text-[13px] text-slate-500">
          添加 2–12 份 DOCX 或 PDF，自动生成所有两两比对组合。
        </p>
      </div>
      <span
        class="rounded-full bg-slate-100 px-3 py-1.5 text-[12px] font-medium text-slate-600"
        >{{ files.length }} / 12 份</span
      >
    </div>
    <input
      ref="input"
      class="sr-only"
      type="file"
      accept=".docx,.pdf,application/pdf"
      multiple
      @change="onInput"
    />
    <div
      class="mx-6 flex min-h-[198px] flex-col items-center justify-center rounded-[18px] border-2 border-dashed px-4 text-center transition-all sm:mx-7"
      :class="
        dragging
          ? 'border-blue-500 bg-blue-50'
          : 'border-slate-200 bg-[#fafcff] hover:border-blue-300 hover:bg-blue-50/40'
      "
      role="button"
      tabindex="0"
      aria-label="选择 DOCX 或 PDF 文件或拖放文件"
      @click="input?.click()"
      @keydown.enter="input?.click()"
      @keydown.space.prevent="input?.click()"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <div
        class="mb-3 flex size-12 items-center justify-center rounded-2xl bg-white text-blue-600 shadow-sm ring-1 ring-blue-100"
      >
        <UploadCloud :size="22" />
      </div>
      <p class="text-[14px] font-semibold text-slate-800">
        拖拽文件到这里，或点击选择
      </p>
      <p class="mt-1 text-[12px] text-slate-500">
        支持 .docx / .pdf · 大文件需要更长处理时间
      </p>
      <span
        class="mt-4 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white px-4 py-2 text-[12px] font-semibold text-blue-700 shadow-sm"
        ><FilePlus2 :size="14" /> 添加文件</span
      >
    </div>

    <div v-if="files.length" class="px-6 pt-5 sm:px-7">
      <div class="mb-3 flex items-center justify-between">
        <span class="text-[12px] font-semibold text-slate-700">已添加文件</span
        ><button
          class="inline-flex items-center gap-1 text-[12px] text-slate-400 hover:text-red-600"
          @click="emit('clear')"
        >
          <Trash2 :size="13" /> 清空
        </button>
      </div>
      <div class="grid max-h-[180px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
        <div
          v-for="(file, index) in files"
          :key="`${file.name}:${file.size}:${file.lastModified}`"
          class="flex min-w-0 items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5"
        >
          <div
            class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600"
          >
            <FileText
              :size="17"
              :class="
                file.name.toLowerCase().endsWith('.pdf') ? 'text-red-600' : ''
              "
            />
          </div>
          <div class="min-w-0 flex-1">
            <p
              class="truncate text-[12px] font-medium text-slate-800"
              :title="file.name"
            >
              {{ file.name }}
            </p>
            <p class="mt-0.5 text-[11px] text-slate-400">
              {{ sizeLabel(file.size) }}
            </p>
          </div>
          <button
            class="rounded-md p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
            :aria-label="`移除 ${file.name}`"
            @click="emit('remove', index)"
          >
            <X :size="15" />
          </button>
        </div>
      </div>
    </div>

    <div
      class="mx-6 mt-5 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 sm:mx-7"
    >
      <input
        ref="referenceInput"
        class="sr-only"
        type="file"
        accept=".docx,.pdf,application/pdf"
        @change="onReferenceInput"
      />
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="text-[12px] font-semibold text-slate-800">
            招标文件
            <span class="font-normal text-slate-400">· 可选，仅 1 份</span>
          </div>
          <p class="mt-1 text-[11px] leading-5 text-slate-500">
            与招标文件相同的文字、图片会从投标文件间的重复统计中排除。
          </p>
        </div>
        <button
          class="secondary-button shrink-0"
          @click="referenceInput?.click()"
        >
          {{ reference ? "更换文件" : "选择招标文件" }}
        </button>
      </div>
      <div
        v-if="reference"
        class="mt-3 flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-[11px]"
      >
        <FileText :size="15" class="shrink-0 text-indigo-600" /><span
          class="min-w-0 flex-1 truncate font-medium text-slate-700"
          :title="reference.name"
          >{{ reference.name }}</span
        ><span class="shrink-0 text-slate-400">{{
          sizeLabel(reference.size)
        }}</span
        ><button
          class="shrink-0 rounded-md p-1 text-slate-400 hover:text-red-600"
          aria-label="移除招标文件"
          @click="emit('setReference', null)"
        >
          <X :size="14" />
        </button>
      </div>
    </div>

    <div
      class="mt-auto flex flex-wrap items-center justify-between gap-3 px-6 pb-6 pt-5 sm:px-7"
    >
      <div class="flex items-center gap-2 text-[12px] text-slate-500">
        <FolderOpen :size="15" /><span>{{
          files.length >= 2
            ? `将生成 ${pairCount} 组文件对照`
            : "至少添加两份文件开始分析"
        }}</span>
      </div>
      <button
        class="primary-button"
        :disabled="files.length < 2 || busy"
        @click="emit('run')"
      >
        <span
          v-if="busy"
          class="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
        ></span
        ><span>{{ busy ? "正在分析文档…" : "开始比对" }}</span
        ><ArrowUpRight v-if="!busy" :size="16" />
      </button>
    </div>
  </section>
</template>
