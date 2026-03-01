<script setup>
import { inject } from 'vue'

defineProps({ events: Array, hiddenClasses: Object })

const COLORS = { HIGH: '#e05252', MEDIUM: '#e0a832', LOW: '#4a9eda' }
const timezone = inject('timezone', { value: 'America/New_York' })

const SENTIMENT_META = {
  POSITIVE: { symbol: '▲', color: '#3a7d5a', border: 'rgba(58,125,90,0.55)' },
  NEGATIVE: { symbol: '▼', color: '#a05060', border: 'rgba(160,80,96,0.55)' },
  NEUTRAL:  { symbol: '—', color: '#484848', border: 'transparent' },
}

function sentimentMeta(s) {
  return SENTIMENT_META[s] || null
}

function fmt(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString('en-US', {
    timeZone: timezone.value,
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }) + ' ET'
}
</script>

<template>
  <div class="feed">
    <div v-if="hiddenClasses.size" class="filter-bar">
      Hiding: {{ [...hiddenClasses].join(', ') }} &mdash; click tiles to toggle
    </div>
    <div v-if="!events.length" class="empty">No events yet — monitor is running.</div>
    <div
      v-for="ev in events"
      :key="ev.id"
      class="event-row"
      :style="sentimentMeta(ev.sentiment) ? { borderLeft: `3px solid ${sentimentMeta(ev.sentiment).border}` } : { borderLeft: '3px solid transparent' }"
    >
      <span class="badge" :style="{ background: COLORS[ev.classification] }">
        {{ ev.classification }}
      </span>
      <div class="body">
        <a :href="ev.url" target="_blank" rel="noopener">{{ ev.title }}</a>
        <small>
          {{ ev.source }} &mdash; {{ fmt(ev.created_at) }}
          <span v-if="ev.confidence"> &mdash; {{ Math.round(ev.confidence * 100) }}% confidence</span>
          <span
            v-if="sentimentMeta(ev.sentiment)"
            class="sentiment-chip"
            :style="{ color: sentimentMeta(ev.sentiment).color }"
          >
            {{ sentimentMeta(ev.sentiment).symbol }} {{ ev.sentiment }}
          </span>
        </small>
        <p v-if="ev.reason" class="reason">{{ ev.reason }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feed { padding: 8px 20px; }
.filter-bar { font-size: 0.8rem; color: #666; padding: 8px 0 4px; font-style: italic; }
.empty { color: #555; padding: 24px 0; font-style: italic; }
.event-row {
  display: flex;
  gap: 14px;
  padding: 12px 0 12px 10px;
  border-bottom: 1px solid #1a1a1a;
  align-items: flex-start;
  transition: border-color 0.2s;
}
.badge { color: #fff; font-weight: 700; font-size: 0.7rem; padding: 4px 10px; border-radius: 4px;
         white-space: nowrap; margin-top: 2px; letter-spacing: 0.05em; }
.body { flex: 1; min-width: 0; }
.body a { font-weight: 600; color: #ddd; text-decoration: none; display: block;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.body a:hover { color: #fff; text-decoration: underline; }
small { display: block; color: #555; font-size: 0.78rem; margin-top: 3px; }
.sentiment-chip {
  margin-left: 8px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.reason { margin: 5px 0 0; font-size: 0.83rem; color: #888; }
</style>
