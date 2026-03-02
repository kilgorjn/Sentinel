<script setup>
import { ref, provide, onMounted, onUnmounted, watch } from 'vue'
import TimeRangeSelector from '../components/TimeRangeSelector.vue'
import EventChart from '../components/EventChart.vue'
import SentimentChart from '../components/SentimentChart.vue'

const selectedHours = ref(24)
const timeseries = ref({ labels: [], high: [], medium: [], low: [] })
const sentimentTimeseries = ref({ labels: [], scores: [] })
const selectedChart = ref(null)  // null | 'events' | 'sentiment'
const timezone = ref('America/New_York')
const lastRefresh = ref(null)

provide('timezone', timezone)

async function refresh() {
  try {
    const [tsRes, stRes] = await Promise.all([
      fetch(`/api/events/timeseries?hours=${selectedHours.value}`),
      fetch(`/api/events/sentiment-timeseries?hours=${selectedHours.value}`),
    ])
    timeseries.value = await tsRes.json()
    sentimentTimeseries.value = await stRes.json()
    lastRefresh.value = new Date().toLocaleTimeString('en-US', { timeZone: timezone.value, hour: '2-digit', minute: '2-digit' }) + ' ET'
  } catch (e) {
    console.error('Refresh failed:', e)
  }
}

let timer
onMounted(async () => {
  const cfgRes = await fetch('/api/config').catch(() => null)
  if (cfgRes?.ok) {
    const cfg = await cfgRes.json()
    if (cfg.display_timezone) timezone.value = cfg.display_timezone
  }
  refresh()
  timer = setInterval(refresh, 30_000)
})
onUnmounted(() => clearInterval(timer))

watch(selectedHours, refresh)

function selectChart(chart) {
  selectedChart.value = selectedChart.value === chart ? null : chart
}

function closeDetail() {
  selectedChart.value = null
}
</script>

<template>
  <h1>Charts
    <span v-if="lastRefresh" style="font-weight:normal; font-size:0.8rem; margin-left:16px; color:#555;">
      last updated {{ lastRefresh }}
    </span>
  </h1>

  <TimeRangeSelector v-model="selectedHours" />

  <!-- Mini Chart Row -->
  <div class="mini-charts-row">
    <div class="mini-chart-panel" :class="{ active: selectedChart === 'events' }" @click="selectChart('events')">
      <span class="chart-label">Events per Hour</span>
      <div class="chart-area">
        <EventChart :timeseries="timeseries" :hidden-classes="new Set()" :hours="selectedHours" />
      </div>
      <span class="expand-hint">▶</span>
    </div>

    <div class="mini-chart-panel" :class="{ active: selectedChart === 'sentiment' }" @click="selectChart('sentiment')">
      <span class="chart-label">Sentiment Score per Hour</span>
      <div class="chart-area">
        <SentimentChart :sentiment-timeseries="sentimentTimeseries" :hours="selectedHours" />
      </div>
      <span class="expand-hint">▶</span>
    </div>
  </div>

  <!-- Expanded Chart Detail -->
  <div v-if="selectedChart === 'events'" class="chart-detail">
    <div class="detail-header">
      <h2>Events per Hour — {{ selectedHours }} hour{{ selectedHours !== 1 ? 's' : '' }} view</h2>
      <button class="close-btn" @click="closeDetail">✕</button>
    </div>
    <div class="expanded-chart">
      <EventChart :timeseries="timeseries" :hidden-classes="new Set()" :hours="selectedHours" expanded />
    </div>
  </div>

  <div v-if="selectedChart === 'sentiment'" class="chart-detail">
    <div class="detail-header">
      <h2>Sentiment Score per Hour — {{ selectedHours }} hour{{ selectedHours !== 1 ? 's' : '' }} view</h2>
      <button class="close-btn" @click="closeDetail">✕</button>
    </div>
    <div class="expanded-chart">
      <SentimentChart :sentiment-timeseries="sentimentTimeseries" :hours="selectedHours" expanded />
    </div>
  </div>
</template>

<style scoped>
h1 {
  padding: 20px 20px 0;
  font-size: 1.4rem;
  font-weight: 600;
  margin-bottom: 0;
}

.mini-charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 20px 20px;
  margin-bottom: 20px;
}

.mini-chart-panel {
  display: flex;
  flex-direction: column;
  background: #1a1a1a;
  border: 2px solid #222;
  border-radius: 6px;
  padding: 12px;
  min-height: 200px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.mini-chart-panel:hover {
  background: #222;
  border-color: #333;
}

.mini-chart-panel.active {
  background: #252525;
  border-color: #4a9eda;
}

.chart-label {
  font-size: 0.85rem;
  color: #999;
  font-weight: 500;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.chart-area {
  flex: 1;
  min-height: 0;
}

.expand-hint {
  position: absolute;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  font-size: 1.2rem;
  color: #666;
  opacity: 0;
  transition: opacity 0.2s;
}

.mini-chart-panel:hover .expand-hint {
  opacity: 1;
  color: #999;
}

/* Expanded Chart Detail */
.chart-detail {
  background: #1a1a1a;
  border: 2px solid #222;
  border-top: 2px solid #4a9eda;
  border-radius: 6px;
  margin: 0 20px 20px;
  padding: 16px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #222;
}

.detail-header h2 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  color: #999;
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
  transition: color 0.2s;
}

.close-btn:hover {
  color: #ccc;
}

.expanded-chart {
  height: 380px;
}
</style>
