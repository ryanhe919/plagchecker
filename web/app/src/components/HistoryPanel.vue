<script setup lang="ts">
import { computed, ref } from "vue";
import {
  ArrowLeft,
  ArrowRight,
  Clock3,
  FileText,
  RefreshCw,
  Search,
} from "@lucide/vue";
import type { HistoryItem } from "../scripts/types";

const props = defineProps<{
  items: HistoryItem[];
  loading: boolean;
  error: string;
  hasMore: boolean;
}>();
const emit = defineEmits<{
  back: [];
  refresh: [];
  loadMore: [];
  open: [jobId: string];
}>();
const query = ref("");
const visible = computed(() =>
  props.items.filter((item) =>
    `${item.files.join(" ")} ${item.reference_name ?? ""}`
      .toLocaleLowerCase()
      .includes(query.value.trim().toLocaleLowerCase()),
  ),
);

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
function stateLabel(state: HistoryItem["state"]): string {
  return {
    queued: "排队中",
    running: "分析中",
    completed: "已完成",
    failed: "失败",
  }[state];
}
</script>

<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <button
          class="mb-3 inline-flex items-center gap-1 text-[12px] font-medium text-blue-700 hover:underline"
          @click="emit('back')"
        >
          <ArrowLeft :size="14" /> 返回工作台
        </button>
        <div class="eyebrow mb-1.5">ANALYSIS HISTORY</div>
        <h1 class="text-[27px] font-semibold tracking-[-.05em] text-slate-900">
          历史检测记录
        </h1>
        <p class="mt-1.5 text-[12px] text-slate-500">
          本服务器的检测结果会持续保存；上传原件在任务结束后清理。
        </p>
      </div>
      <button
        class="secondary-button"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <RefreshCw :size="14" :class="loading ? 'animate-spin' : ''" /> 刷新记录
      </button>
    </div>
    <div class="panel overflow-hidden">
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 sm:px-6"
      >
        <div>
          <h2 class="text-[14px] font-semibold text-slate-800">检测任务</h2>
          <p class="mt-0.5 text-[11px] text-slate-400">
            已载入 {{ items.length }} 条 · 点击可查看报告或进度
          </p>
        </div>
        <div class="relative">
          <Search
            :size="14"
            class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          /><input
            v-model="query"
            class="field w-[220px] !py-2 !pl-8"
            type="search"
            placeholder="搜索已载入的文件名"
            aria-label="搜索历史文件名"
          />
        </div>
      </div>
      <div
        v-if="error"
        class="mx-5 my-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[12px] text-red-700"
      >
        {{ error }}
      </div>
      <div
        v-if="!visible.length && !loading"
        class="px-5 py-16 text-center text-[12px] text-slate-400"
      >
        {{ items.length ? "没有匹配的文件名" : "暂无历史检测记录" }}
      </div>
      <div
        v-for="item in visible"
        :key="item.id"
        class="border-b border-slate-100 last:border-0"
      >
        <button
          class="flex w-full flex-wrap items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-slate-50 sm:px-6"
          @click="emit('open', item.id)"
        >
          <div
            class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600"
          >
            <FileText :size="19" />
          </div>
          <div class="min-w-[170px] flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="max-w-[520px] truncate text-[12px] font-semibold text-slate-800"
                :title="item.files.join('、')"
                >{{ item.files.join("、") }}</span
              ><span
                class="rounded-full px-2 py-0.5 text-[10px] font-medium"
                :class="
                  item.state === 'completed'
                    ? 'bg-emerald-50 text-emerald-700'
                    : item.state === 'failed'
                      ? 'bg-red-50 text-red-700'
                      : 'bg-blue-50 text-blue-700'
                "
                >{{ stateLabel(item.state) }}</span
              >
            </div>
            <div
              class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400"
            >
              <span class="inline-flex items-center gap-1"
                ><Clock3 :size="12" /> {{ formatDate(item.created_at) }}</span
              ><span>{{ item.files.length }} 份投标文件</span
              ><span v-if="item.reference_name" class="text-indigo-600"
                >招标文件：{{ item.reference_name }}</span
              >
            </div>
          </div>
          <div
            v-if="item.state === 'completed'"
            class="flex shrink-0 items-center gap-3 text-[11px] text-slate-500"
          >
            <span>{{ item.pair_count ?? 0 }} 组比对</span
            ><strong class="text-[15px] text-slate-800"
              >{{ ((item.max_similarity ?? 0) * 100).toFixed(1) }}%</strong
            >
          </div>
          <ArrowRight :size="15" class="shrink-0 text-slate-300" />
        </button>
      </div>
      <div v-if="hasMore" class="border-t border-slate-100 p-4 text-center">
        <button
          class="secondary-button"
          :disabled="loading"
          @click="emit('loadMore')"
        >
          {{ loading ? "正在载入…" : "加载更早记录" }}
        </button>
      </div>
    </div>
    <p class="text-[11px] leading-5 text-slate-400">
      历史记录对能够访问此系统的人员可见。正式对外使用时，请为部署入口配置 HTTPS
      和访问控制。
    </p>
  </section>
</template>
