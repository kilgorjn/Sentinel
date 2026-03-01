<script setup>
defineProps({ events: Array })

const COLORS = { HIGH: '#e05252', MEDIUM: '#e0a832', LOW: '#4a9eda' }

function fmt(ts) {
  if (!ts) return ''
  return ts.slice(0, 16).replace('T', ' ') + ' UTC'
}
</script>

<template>
  <div class="feed">
    <div v-if="!events.length" class="empty">No events yet — monitor is running.</div>
    <div v-for="ev in events" :key="ev.id" class="event-row">
      <span class="badge" :style="{ background: COLORS[ev.classification] }">
        {{ ev.classification }}
      </span>
      <div class="body">
        <a :href="ev.url" target="_blank" rel="noopener">{{ ev.title }}</a>
        <small>{{ ev.source }} &mdash; {{ fmt(ev.created_at) }}
          <span v-if="ev.confidence"> &mdash; {{ Math.round(ev.confidence * 100) }}% confidence</span>
        </small>
        <p v-if="ev.reason" class="reason">{{ ev.reason }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feed { padding: 8px 20px; }
.empty { color: #555; padding: 24px 0; font-style: italic; }
.event-row { display: flex; gap: 14px; padding: 12px 0; border-bottom: 1px solid #1a1a1a; align-items: flex-start; }
.badge { color: #fff; font-weight: 700; font-size: 0.7rem; padding: 4px 10px; border-radius: 4px;
         white-space: nowrap; margin-top: 2px; letter-spacing: 0.05em; }
.body { flex: 1; min-width: 0; }
.body a { font-weight: 600; color: #ddd; text-decoration: none; display: block;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.body a:hover { color: #fff; text-decoration: underline; }
small { display: block; color: #555; font-size: 0.78rem; margin-top: 3px; }
.reason { margin: 5px 0 0; font-size: 0.83rem; color: #888; }
</style>
