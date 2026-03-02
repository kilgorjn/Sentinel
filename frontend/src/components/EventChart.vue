<script setup>
import { inject, ref, watch, onMounted, onUnmounted } from 'vue'
import {
  Chart,
  LineController, LineElement, PointElement,
  LinearScale, CategoryScale,
  Tooltip, Legend,
} from 'chart.js'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend)

const props = defineProps({
  timeseries: Object,
  hiddenClasses: Object,
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

function buildChart() {
  if (!canvas.value || !props.timeseries?.labels?.length) return
  if (chart) { chart.destroy() }

  chart = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: props.timeseries.labels.map(fmtLabel),
      datasets: [
        {
          label: 'HIGH',
          data: props.timeseries.high,
          borderColor: '#e05252',
          backgroundColor: 'rgba(224,82,82,0.08)',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
          hidden: props.hiddenClasses?.has('HIGH') ?? false,
        },
        {
          label: 'MEDIUM',
          data: props.timeseries.medium,
          borderColor: '#e0a832',
          backgroundColor: 'rgba(224,168,50,0.08)',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
          hidden: props.hiddenClasses?.has('MEDIUM') ?? false,
        },
        {
          label: 'LOW',
          data: props.timeseries.low,
          borderColor: '#4a9eda',
          backgroundColor: 'rgba(74,158,218,0.08)',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
          hidden: props.hiddenClasses?.has('LOW') ?? false,
        },
      ],
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
        },
      },
      scales: {
        x: {
          ticks: { display: props.expanded, maxTicksLimit: 10 },
          grid: { color: props.expanded ? '#252525' : '#1a1a1a' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: props.expanded ? '#888' : '#555', font: { size: 10 }, precision: 0 },
          grid: { color: props.expanded ? '#252525' : '#1a1a1a' },
        },
      },
    },
  })
}

onMounted(buildChart)
watch(() => props.timeseries, buildChart, { deep: true })
watch(() => props.hiddenClasses, buildChart)
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
