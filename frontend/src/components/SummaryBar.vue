<script setup>
import EventChart from './EventChart.vue'

const props = defineProps({ summary: Object, activeFilter: String, timeseries: Object })
const emit  = defineEmits(['filter'])

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
      :class="{ active: activeFilter === cls, dimmed: activeFilter && activeFilter !== cls }"
      :style="{ borderColor: COLORS[cls] }"
      @click="emit('filter', cls)"
    >
      <span class="label" :style="{ color: COLORS[cls] }">{{ cls }}</span>
      <span class="count">{{ countFor(cls) }}</span>
    </div>
    <div
      class="tile total"
      :class="{ active: !activeFilter }"
      @click="emit('filter', null)"
    >
      <span class="label">TOTAL 24h</span>
      <span class="count">{{ summary.total ?? 0 }}</span>
    </div>
    <div class="chart-area">
      <EventChart :timeseries="timeseries" :active-filter="activeFilter" />
    </div>
  </div>
</template>

<style scoped>
.summary-bar { display: flex; gap: 12px; align-items: stretch;
               padding: 16px 20px; border-bottom: 1px solid #1e1e1e; }
.tile { border: 2px solid #333; border-radius: 6px; padding: 10px 20px; text-align: center;
        min-width: 100px; cursor: pointer; transition: opacity 0.15s, background 0.15s; }
.tile:hover { background: #1a1a1a; }
.tile.active { background: #1a1a1a; }
.tile.dimmed { opacity: 0.35; }
.total { border-color: #444; }
.label { display: block; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 4px; }
.count { font-size: 2rem; font-weight: 700; }
.chart-area { width: 270px; flex-shrink: 0; margin-left: auto; }
</style>
