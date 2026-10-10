<script setup lang="ts">
import { computed } from "vue";
import { CircleHelp, SlidersHorizontal, Sparkles } from "@lucide/vue";
import type { Settings } from "../scripts/types";

const props = defineProps<{ modelValue: Settings; hasReference: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: Settings] }>();
const activePreset = computed(() => {
  if (
    props.modelValue.similarity_threshold === 0.68 &&
    props.modelValue.minimum_match_chars === 12
  )
    return "宽松";
  if (
    props.modelValue.similarity_threshold === 0.9 &&
    props.modelValue.minimum_match_chars === 24
  )
    return "严格";
  if (
    props.modelValue.similarity_threshold === 0.8 &&
    props.modelValue.minimum_match_chars === 16
  )
    return "平衡";
  return "自定义";
});

function update<K extends keyof Settings>(key: K, value: Settings[K]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
function preset(name: string) {
  const values =
    name === "宽松"
      ? { similarity_threshold: 0.68, minimum_match_chars: 12 }
      : name === "严格"
        ? { similarity_threshold: 0.9, minimum_match_chars: 24 }
        : { similarity_threshold: 0.8, minimum_match_chars: 16 };
  emit("update:modelValue", { ...props.modelValue, ...values });
}
function setOcrMode(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  if (value === "auto" || value === "always" || value === "off") {
    update("pdf_ocr_mode", value);
  }
}
</script>

<template>
  <section class="panel flex flex-col p-6 sm:p-7">
    <div class="flex items-start justify-between">
      <div>
        <div class="eyebrow mb-2">02 / 分析设置</div>
        <h2 class="text-[20px] font-semibold tracking-[-.03em] text-slate-900">
          匹配标准
        </h2>
        <p class="mt-1.5 text-[13px] text-slate-500">
          先从预设开始，也可以按项目调整。
        </p>
      </div>
      <div
        class="flex size-9 items-center justify-center rounded-xl bg-slate-100 text-slate-500"
      >
        <SlidersHorizontal :size="18" />
      </div>
    </div>
    <div
      class="mt-6 grid grid-cols-3 gap-2 rounded-2xl bg-slate-100 p-1"
      role="group"
      aria-label="匹配预设"
    >
      <button
        v-for="name in ['宽松', '平衡', '严格']"
        :key="name"
        class="rounded-xl px-3 py-2 text-[12px] font-medium transition-all"
        :class="
          activePreset === name
            ? 'bg-white text-blue-700 shadow-sm'
            : 'text-slate-500 hover:text-slate-900'
        "
        @click="preset(name)"
      >
        {{ name }}
      </button>
    </div>
    <div class="mt-6 space-y-5">
      <div
        v-if="hasReference"
        class="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3"
      >
        <label
          for="reference-minimum"
          class="mb-1.5 block text-[12px] font-semibold text-slate-700"
          >招标文件排除最短字符</label
        >
        <input
          id="reference-minimum"
          class="field w-full"
          type="number"
          min="8"
          max="100"
          :value="modelValue.reference_min_match_chars"
          @input="
            update(
              'reference_min_match_chars',
              Number(($event.target as HTMLInputElement).value),
            )
          "
        />
        <p class="mt-1.5 text-[11px] leading-4 text-slate-500">
          连续相同字符达到此长度才从重复统计中排除，默认 16。
        </p>
      </div>
      <div>
        <div class="mb-2 flex items-center justify-between">
          <label
            for="threshold"
            class="text-[12px] font-semibold text-slate-700"
            >文本相似度阈值</label
          ><span
            class="rounded-md bg-blue-50 px-2 py-1 text-[12px] font-semibold text-blue-700"
            >{{ Math.round(modelValue.similarity_threshold * 100) }}%</span
          >
        </div>
        <input
          id="threshold"
          class="range w-full"
          type="range"
          min="0.5"
          max="1"
          step="0.01"
          :value="modelValue.similarity_threshold"
          @input="
            update(
              'similarity_threshold',
              Number(($event.target as HTMLInputElement).value),
            )
          "
        />
        <div class="mt-1 flex justify-between text-[11px] text-slate-400">
          <span>更宽松</span><span>更严格</span>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label
            for="match-chars"
            class="mb-1.5 block text-[12px] font-semibold text-slate-700"
            >最少匹配字符</label
          ><input
            id="match-chars"
            class="field w-full"
            type="number"
            min="8"
            max="100"
            :value="modelValue.minimum_match_chars"
            @input="
              update(
                'minimum_match_chars',
                Number(($event.target as HTMLInputElement).value),
              )
            "
          />
        </div>
        <div>
          <label
            for="short-blocks"
            class="mb-1.5 block text-[12px] font-semibold text-slate-700"
            >忽略短片段</label
          ><input
            id="short-blocks"
            class="field w-full"
            type="number"
            min="0"
            max="100"
            :value="modelValue.ignore_short_blocks"
            @input="
              update(
                'ignore_short_blocks',
                Number(($event.target as HTMLInputElement).value),
              )
            "
          />
        </div>
      </div>
      <div>
        <div class="mb-2 flex items-center justify-between">
          <label
            for="image-distance"
            class="text-[12px] font-semibold text-slate-700"
            >相似图片容差</label
          ><span class="text-[12px] font-semibold text-blue-700"
            >{{ modelValue.image_near_distance }} / 16</span
          >
        </div>
        <input
          id="image-distance"
          class="range w-full"
          type="range"
          min="0"
          max="16"
          step="1"
          :value="modelValue.image_near_distance"
          @input="
            update(
              'image_near_distance',
              Number(($event.target as HTMLInputElement).value),
            )
          "
        />
        <p class="mt-1 text-[11px] text-slate-400">不影响完全一致图片的判定</p>
      </div>
      <div>
        <label
          for="pdf-ocr-mode"
          class="mb-1.5 block text-[12px] font-semibold text-slate-700"
          >PDF 文字识别</label
        >
        <select
          id="pdf-ocr-mode"
          class="field w-full"
          :value="modelValue.pdf_ocr_mode"
          @change="setOcrMode"
        >
          <option value="auto">自动识别扫描页（推荐）</option>
          <option value="always">强制识别所有 PDF 页面</option>
          <option value="off">关闭 OCR，仅提取文字层</option>
        </select>
        <p class="mt-1.5 text-[11px] leading-4 text-slate-400">
          扫描页识别可能较慢；原生文字 PDF 默认直接解析。
        </p>
      </div>
      <label
        class="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3"
        ><input
          type="checkbox"
          class="mt-0.5 size-4 accent-blue-600"
          :checked="modelValue.ignore_common_across_all"
          @change="
            update(
              'ignore_common_across_all',
              ($event.target as HTMLInputElement).checked,
            )
          "
        /><span
          ><span class="block text-[12px] font-semibold text-slate-700"
            >排除所有标书共有片段</span
          ><span class="mt-1 block text-[11px] leading-4 text-slate-400"
            >三份及以上时，可减少统一模板的影响</span
          ></span
        ></label
      >
    </div>
    <div class="mt-auto flex gap-2 pt-5 text-[11px] leading-5 text-slate-500">
      <Sparkles :size="15" class="mt-0.5 shrink-0 text-blue-500" /><span
        >先使用平衡模式查看证据；修改设置后重新比对即可更新结果。</span
      ><CircleHelp :size="14" class="mt-0.5 shrink-0 text-slate-300" />
    </div>
  </section>
</template>
