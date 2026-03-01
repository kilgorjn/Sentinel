<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import SurgeAlert  from './components/SurgeAlert.vue'
import SummaryBar  from './components/SummaryBar.vue'
import EventFeed   from './components/EventFeed.vue'

const events  = ref([])
const summary = ref({ counts: [], total: 0 })
const surge   = ref({ surge_active: false, high_count_in_window: 0, window_minutes: 30 })
const lastRefresh = ref(null)

async function refresh() {
  try {
    const [evRes, sumRes, surRes] = await Promise.all([
      fetch('/api/events?limit=50'),
      fetch('/api/events/summary'),
      fetch('/api/surge'),
    ])
    events.value  = await evRes.json()
    summary.value = await sumRes.json()
    surge.value   = await surRes.json()
    lastRefresh.value = new Date().toLocaleTimeString()
  } catch (e) {
    console.error('Refresh failed:', e)
  }
}

let timer
onMounted(() => { refresh(); timer = setInterval(refresh, 30_000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <h1>Sentinel — Financial News Monitor
    <span v-if="lastRefresh" style="font-weight:normal; font-size:0.8rem; margin-left:16px; color:#555;">
      last updated {{ lastRefresh }}
    </span>
  </h1>
  <SurgeAlert :surge="surge" />
  <SummaryBar :summary="summary" />
  <EventFeed  :events="events" />
</template>
