<script setup>
import { ref, computed, provide, onMounted, onUnmounted, watch } from 'vue'
import PredictionBanner  from '../components/PredictionBanner.vue'
import SurgeAlert        from '../components/SurgeAlert.vue'
import SummaryBar        from '../components/SummaryBar.vue'
import NarrativeSummary  from '../components/NarrativeSummary.vue'
import GlobalMarkets     from '../components/GlobalMarkets.vue'
import EventFeed         from '../components/EventFeed.vue'
import TimeRangeSelector from '../components/TimeRangeSelector.vue'

const events      = ref([])
const summary     = ref({ counts: [], total: 0, overall_sentiment: null, overall_sentiment_score: 0 })
const surge       = ref({ surge_active: false, high_count_in_window: 0, window_minutes: 30 })
const narrative   = ref({ text: '', generated_at: null, surge_active: false })
const prediction  = ref(null)
const timeseries          = ref({ labels: [], high: [], medium: [], low: [] })
const sentimentTimeseries = ref({ labels: [], scores: [] })
const lastRefresh = ref(null)
const hiddenClasses = ref(new Set())
const selectedHours = ref(24)

const timezone = ref('America/New_York')
provide('timezone', timezone)

const filteredEvents = computed(() =>
  hiddenClasses.value.size
    ? events.value.filter(e => !hiddenClasses.value.has(e.classification))
    : events.value
)

function setFilter(cls) {
  if (cls === null) {
    hiddenClasses.value = new Set()
    return
  }
  const next = new Set(hiddenClasses.value)
  if (next.has(cls)) next.delete(cls)
  else next.add(cls)
  hiddenClasses.value = next
}

async function refresh() {
  // Fetch narrative separately — it may block on Ollama inference.
  // All other endpoints are fast and update the UI immediately.
  fetch('/api/events/narrative')
    .then(r => r.json())
    .then(data => { narrative.value = data })
    .catch(e => console.error('Narrative fetch failed:', e))

  try {
    const [evRes, sumRes, surRes, tsRes, stRes, predRes] = await Promise.all([
      fetch('/api/events?limit=200'),
      fetch(`/api/events/summary?hours=${selectedHours.value}`),
      fetch('/api/surge'),
      fetch(`/api/events/timeseries?hours=${selectedHours.value}`),
      fetch(`/api/events/sentiment-timeseries?hours=${selectedHours.value}`),
      fetch('/api/prediction'),
    ])
    events.value              = await evRes.json()
    summary.value             = await sumRes.json()
    surge.value               = await surRes.json()
    timeseries.value          = await tsRes.json()
    sentimentTimeseries.value = await stRes.json()
    prediction.value          = await predRes.json()
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
</script>

<template>
  <h1>Sentinel — Financial News Monitor
    <span v-if="lastRefresh" style="font-weight:normal; font-size:0.8rem; margin-left:16px; color:#555;">
      last updated {{ lastRefresh }}
    </span>
  </h1>
  <PredictionBanner  :prediction="prediction" />
  <SurgeAlert        :surge="surge" />
  <TimeRangeSelector v-model="selectedHours" />
  <SummaryBar        :summary="summary" :hidden-classes="hiddenClasses" :timeseries="timeseries" :sentiment-timeseries="sentimentTimeseries" :hours="selectedHours" @filter="setFilter" />
  <NarrativeSummary  :narrative="narrative" />
  <GlobalMarkets />
  <EventFeed         :events="filteredEvents" :hidden-classes="hiddenClasses" />
</template>
