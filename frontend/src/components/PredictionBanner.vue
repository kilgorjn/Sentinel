<script setup>
defineProps({ prediction: Object })

const AGO_INTERVAL = 10_000 // update "X seconds ago" every 10s

import { ref, onMounted, onUnmounted } from 'vue'
const secondsAgo = ref(0)
let timer

onMounted(() => {
  timer = setInterval(() => { secondsAgo.value += 10 }, AGO_INTERVAL)
})
onUnmounted(() => clearInterval(timer))

// Reset counter whenever the parent updates the prediction prop
import { watch } from 'vue'
watch(() => props?.prediction?.computed_at, () => { secondsAgo.value = 0 })
</script>

<template>
  <div v-if="prediction" class="prediction-banner" :data-level="prediction.label">
    <div class="prediction-left">
      <span class="prediction-label">{{ prediction.label }}</span>
      <span class="prediction-sublabel">{{ prediction.volume }}</span>
    </div>

    <div class="prediction-action">{{ prediction.action }} <span class="tooltip-icon" :title="prediction.tooltip">ⓘ</span></div>

    <div class="prediction-drivers" v-if="prediction.drivers?.length">
      <span v-for="(d, i) in prediction.drivers" :key="i" class="driver-chip">{{ d }}</span>
    </div>

    <div class="prediction-meta">
      score {{ prediction.score }}
      <span v-if="secondsAgo > 0"> &middot; updated {{ secondsAgo }}s ago</span>
    </div>
  </div>
</template>

<style scoped>
.prediction-banner {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 14px 20px;
  border-radius: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* Level colours */
.prediction-banner[data-level="NORMAL"]   { background: #1a3a1a; border-left: 5px solid #4caf50; }
.prediction-banner[data-level="MODERATE"] { background: #3a3000; border-left: 5px solid #ffc107; }
.prediction-banner[data-level="ELEVATED"] { background: #3a1800; border-left: 5px solid #ff9800; }
.prediction-banner[data-level="SURGE"]    { background: #3a0000; border-left: 5px solid #f44336; }

.prediction-left {
  display: flex;
  flex-direction: column;
  min-width: 130px;
}

.prediction-label {
  font-size: 1.4rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  line-height: 1;
}

.prediction-banner[data-level="NORMAL"]   .prediction-label { color: #4caf50; }
.prediction-banner[data-level="MODERATE"] .prediction-label { color: #ffc107; }
.prediction-banner[data-level="ELEVATED"] .prediction-label { color: #ff9800; }
.prediction-banner[data-level="SURGE"]    .prediction-label { color: #f44336; }

.prediction-sublabel {
  font-size: 0.7rem;
  color: #888;
  margin-top: 3px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.prediction-action {
  font-size: 0.85rem;
  font-weight: 600;
  color: #ddd;
  white-space: nowrap;
  padding: 0 16px;
  border-left: 1px solid rgba(255,255,255,0.15);
  border-right: 1px solid rgba(255,255,255,0.15);
}

.prediction-drivers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}

.driver-chip {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 4px;
  padding: 3px 9px;
  font-size: 0.78rem;
  color: #ccc;
  white-space: nowrap;
}

.tooltip-icon {
  cursor: help;
}

.prediction-meta {
  font-size: 0.72rem;
  color: #666;
  white-space: nowrap;
  align-self: flex-end;
}
</style>
