<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import HistoryPanel from "../../components/HistoryPanel.vue";
import { getHistory } from "../../scripts/api";
import type { HistoryItem } from "../../scripts/types";

const router = useRouter();
const items = ref<HistoryItem[]>([]);
const cursor = ref<string | null>(null);
const loading = ref(false);
const error = ref("");

async function load(reset: boolean) {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const page = await getHistory(reset ? null : cursor.value);
    items.value = reset ? page.items : [...items.value, ...page.items];
    cursor.value = page.next_cursor;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "历史记录加载失败";
  } finally {
    loading.value = false;
  }
}
onMounted(() => void load(true));
</script>

<template>
  <HistoryPanel
    :items="items"
    :loading="loading"
    :error="error"
    :has-more="Boolean(cursor)"
    @back="router.push('/new')"
    @refresh="load(true)"
    @load-more="load(false)"
    @open="router.push({ name: 'job', params: { id: $event } })"
  />
</template>
