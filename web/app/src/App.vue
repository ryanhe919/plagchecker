<script setup lang="ts">
import { computed } from "vue";
import { useRoute, RouterLink, RouterView } from "vue-router";
import { Archive, FilePlus2, ScanSearch } from "@lucide/vue";

const route = useRoute();
const isNew = computed(() => route.name === "new");
const isHistory = computed(() => route.name === "history");
</script>

<template>
  <div class="min-h-screen bg-[#f8fafc] text-slate-800">
    <header
      class="sticky top-0 z-30 border-b border-slate-200/80 bg-white/95 backdrop-blur-lg"
    >
      <div
        class="mx-auto flex h-[70px] max-w-[1600px] items-center justify-between gap-4 px-5 sm:px-8 lg:px-12"
      >
        <RouterLink to="/new" class="flex items-center gap-3"
          ><div
            class="relative flex size-9 items-center justify-center rounded-[13px] bg-blue-600 text-white shadow-[0_4px_12px_rgba(26,115,232,.22)]"
          >
            <ScanSearch :size="20" :stroke-width="2.4" /><span
              class="absolute -right-1 -top-1 size-2.5 rounded-full border-2 border-white bg-emerald-400"
            ></span>
          </div>
          <span
            class="text-[18px] font-semibold tracking-[-.055em] text-slate-900"
            >标衡<span
              class="ml-2 text-[11px] font-medium tracking-normal text-slate-400"
              >BID REVIEW</span
            ></span
          ></RouterLink
        >
        <nav
          class="flex items-center gap-1 rounded-full bg-slate-100 p-1 text-[11px] font-medium sm:text-[12px]"
          aria-label="主导航"
        >
          <RouterLink
            to="/new"
            class="flex items-center gap-1.5 rounded-full px-3 py-2 transition-colors sm:px-4"
            :class="
              isNew
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-500 hover:text-blue-700'
            "
            ><FilePlus2 :size="14" class="sm:hidden" /><span
              class="hidden sm:inline"
              >新建检测</span
            ><span class="sm:hidden">新建</span></RouterLink
          ><RouterLink
            to="/history"
            class="flex items-center gap-1.5 rounded-full px-3 py-2 transition-colors sm:px-4"
            :class="
              isHistory
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-500 hover:text-blue-700'
            "
            ><Archive :size="14" class="sm:hidden" /><span
              class="hidden sm:inline"
              >历史记录</span
            ><span class="sm:hidden">历史</span></RouterLink
          >
        </nav>
      </div>
    </header>
    <main class="mx-auto max-w-[1600px] px-5 pb-16 pt-8 sm:px-8 lg:px-12">
      <RouterView />
      <footer
        class="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-5 text-[11px] text-slate-400"
      >
        <span>© 2026 标衡 · 文件相似性核查工作台</span
        ><span>辅助筛查结果 · 请结合原文人工复核</span>
      </footer>
    </main>
  </div>
</template>
