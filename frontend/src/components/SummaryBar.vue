<script setup>
const props = defineProps({ summary: Object })

const COLORS = { HIGH: '#e05252', MEDIUM: '#e0a832', LOW: '#4a9eda' }

function countFor(cls) {
  const entry = props.summary.counts?.find(c => c.classification === cls)
  return entry ? entry.count : 0
}
</script>

<template>
  <div class="summary-bar">
    <div
      v-for="cls in ['HIGH', 'MEDIUM', 'LOW']"
      :key="cls"
      class="tile"
      :style="{ borderColor: COLORS[cls] }"
    >
      <span class="label" :style="{ color: COLORS[cls] }">{{ cls }}</span>
      <span class="count">{{ countFor(cls) }}</span>
    </div>
    <div class="tile total">
      <span class="label">TOTAL 24h</span>
      <span class="count">{{ summary.total ?? 0 }}</span>
    </div>
  </div>
</template>

<style scoped>
.summary-bar { display: flex; gap: 12px; padding: 16px 20px; border-bottom: 1px solid #1e1e1e; }
.tile { border: 2px solid #333; border-radius: 6px; padding: 10px 20px; text-align: center; min-width: 100px; }
.total { border-color: #444; }
.label { display: block; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 4px; }
.count { font-size: 2rem; font-weight: 700; }
</style>
