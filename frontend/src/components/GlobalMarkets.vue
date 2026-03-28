<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const marketData = ref({ snapshots: [], signals: [], fetched_at: null, market_data_enabled: false })
const loading = ref(true)
const error = ref(null)

const regions = computed(() => {
  const grouped = {}
  for (const snap of marketData.value.snapshots) {
    if (!grouped[snap.region]) grouped[snap.region] = []
    grouped[snap.region].push(snap)
  }
  return grouped
})

const regionOrder = ['europe', 'asia', 'futures']
const regionLabels = { europe: 'Europe', asia: 'Asia', futures: 'US Futures' }

const sortedRegions = computed(() =>
  regionOrder.filter(r => regions.value[r]?.length)
)

const highSignals = computed(() =>
  marketData.value.signals.filter(s => s.severity === 'HIGH')
)

function changeColor(pct) {
  if (pct > 0) return '#3a7d5a'
  if (pct < 0) return '#a05060'
  return '#555'
}

function formatChange(pct) {
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function formatPrice(p) {
  if (p == null) return '—'
  return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function fetchMarketData() {
  try {
    const res = await fetch('/api/market/indices')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    marketData.value = await res.json()
    error.value = null
  } catch (e) {
    console.error('Market data fetch failed:', e)
    error.value = e.message
  } finally {
    loading.value = false
  }
}

let timer
onMounted(() => {
  fetchMarketData()
  timer = setInterval(fetchMarketData, 60_000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="global-markets">
    <div class="gm-header">
      <span class="gm-title">Global Markets</span>
      <span v-if="marketData.fetched_at" class="gm-updated">
        {{ new Date(marketData.fetched_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) }}
      </span>
    </div>

    <!-- Not configured -->
    <div v-if="!loading && !marketData.market_data_enabled" class="gm-notice">
      Market data is disabled.
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="gm-notice">Loading market data...</div>

    <!-- Error -->
    <div v-else-if="error" class="gm-notice gm-error">Market data unavailable: {{ error }}</div>

    <!-- Data display -->
    <template v-else>
      <!-- Volatility signals -->
      <div v-for="sig in highSignals" :key="sig.message" class="gm-signal">
        ⚠ {{ sig.message }}
      </div>

      <!-- No data yet -->
      <div v-if="marketData.snapshots.length === 0 && marketData.market_data_enabled" class="gm-notice">
        No market data yet — waiting for first fetch cycle.
      </div>

      <!-- Region groups -->
      <div v-for="region in sortedRegions" :key="region" class="gm-region">
        <div class="gm-region-label">{{ regionLabels[region] || region }}</div>
        <div class="gm-grid">
          <div v-for="snap in regions[region]" :key="snap.symbol" class="gm-card">
            <div class="gm-card-name">{{ snap.name }}</div>
            <div class="gm-card-price">{{ formatPrice(snap.price) }}</div>
            <div class="gm-card-change" :style="{ color: changeColor(snap.change_pct) }">
              {{ snap.change_pct > 0 ? '▲' : snap.change_pct < 0 ? '▼' : '—' }}
              {{ formatChange(snap.change_pct) }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.global-markets {
  border: 1px solid #1e1e1e;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
}

.gm-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}

.gm-title {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #888;
}

.gm-updated {
  font-size: 0.68rem;
  color: #555;
}

.gm-notice {
  font-size: 0.8rem;
  color: #555;
  padding: 8px 0;
}

.gm-notice code {
  background: #1a1a1a;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.75rem;
}

.gm-error {
  color: #a05060;
}

.gm-signal {
  background: #2a1a00;
  border: 1px solid #664400;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #e0a832;
  margin-bottom: 8px;
}

.gm-region {
  margin-bottom: 8px;
}

.gm-region-label {
  font-size: 0.65rem;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}

.gm-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gm-card {
  border: 1px solid #222;
  border-radius: 5px;
  padding: 8px 12px;
  min-width: 120px;
  flex: 1;
  max-width: 180px;
}

.gm-card-name {
  font-size: 0.7rem;
  color: #888;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gm-card-price {
  font-size: 1rem;
  font-weight: 700;
}

.gm-card-change {
  font-size: 0.78rem;
  font-weight: 600;
  margin-top: 2px;
}
</style>
