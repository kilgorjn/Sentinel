<script setup>
import { inject, ref, watch, onMounted, onUnmounted } from 'vue'
import {
  Chart,
  BarController, BarElement,
  LinearScale, CategoryScale,
  Tooltip,
} from 'chart.js'

Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip)

const props = defineProps({
  sentimentTimeseries: Object,
  expanded: { type: Boolean, default: false },
  hours: { type: Number, default: 24 },
})
const timezone = inject('timezone', { value: 'America/New_York' })
const canvas = ref(null)
let chart = null

function fmtLabel(iso) {
  const d = new Date(iso)
  if (props.hours > 24) {
    // Show "MM/DD HH:MM" for multi-day views
    return d.toLocaleDateString('en-US', {
      timeZone: timezone.value,
      month: 'numeric',
      day: 'numeric',
    }) + ' ' + d.toLocaleTimeString('en-US', {
      timeZone: timezone.value,
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  return d.toLocaleTimeString('en-US', {
    timeZone: timezone.value,
    hour: '2-digit',
    minute: '2-digit',
  })
}

function barColor(score) {
  if (score === null || score === undefined) return 'rgba(60,60,60,0.3)'
  if (score > 0.10)  return 'rgba(58,125,90,0.75)'
  if (score < -0.10) return 'rgba(160,80,96,0.75)'
  return 'rgba(80,80,80,0.45)'
}

function buildChart() {
  if (!canvas.value || !props.sentimentTimeseries?.labels?.length) return
  if (chart) chart.destroy()

  const scores = props.sentimentTimeseries.scores
  const colors = scores.map(barColor)

  chart = new Chart(canvas.value, {
    type: 'bar',
    data: {
      labels: props.sentimentTimeseries.labels.map(fmtLabel),
      datasets: [{
        label: 'Sentiment',
        data: scores,
        backgroundColor: colors,
        borderWidth: 0,
        borderRadius: 2,
        borderSkipped: false,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: props.expanded },
        tooltip: {
          backgroundColor: '#1a1a1a',
          borderColor: '#333',
          borderWidth: 1,
          titleColor: '#ccc',
          bodyColor: '#aaa',
          displayColors: false,
          callbacks: {
            label(ctx) {
              const v = ctx.parsed.y
              if (v === null || v === undefined) return 'No data'
              return `Score: ${v >= 0 ? '+' : ''}${v.toFixed(3)}`
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { display: props.expanded, maxTicksLimit: 10 },
          grid: { color: props.expanded ? '#252525' : '#1a1a1a' },
        },
        y: {
          min: -1,
          max: 1,
          ticks: {
            color: props.expanded ? '#888' : '#555',
            font: { size: 9 },
            stepSize: 1,
            callback: v => v === 1 ? '+1' : v === -1 ? '−1' : '0',
          },
          grid: {
            color: ctx => ctx.tick.value === 0 ? '#333' : (props.expanded ? '#252525' : '#1a1a1a'),
          },
        },
      },
    },
  })
}

onMounted(buildChart)
watch(() => props.sentimentTimeseries, buildChart, { deep: true })
watch(() => props.expanded, buildChart)
watch(() => props.hours, buildChart)
onUnmounted(() => { if (chart) chart.destroy() })
</script>

<template>
  <div class="chart-wrap">
    <canvas ref="canvas" />
  </div>
</template>

<style scoped>
.chart-wrap { width: 100%; height: 100%; }
</style>
