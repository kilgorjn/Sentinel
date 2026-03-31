<script setup>
import { ref, onMounted } from 'vue'
import FeedManager from '../components/FeedManager.vue'

const readOnly = ref(false)

onMounted(async () => {
  const res = await fetch('/api/config').catch(() => null)
  if (res?.ok) {
    const cfg = await res.json()
    readOnly.value = cfg.read_only ?? false
  }
})
</script>

<template>
  <div class="feeds-page">
    <FeedManager :read-only="readOnly" />
  </div>
</template>

<style scoped>
.feeds-page {
  min-height: 100vh;
  background: #0d0d0d;
  color: #e0e0e0;
}
</style>
