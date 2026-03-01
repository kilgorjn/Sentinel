<script setup>
import { inject } from 'vue'

defineProps({ narrative: Object })

const timezone = inject('timezone', { value: 'America/New_York' })

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('en-US', { timeZone: timezone.value, hour: '2-digit', minute: '2-digit' }) + ' ET'
}
</script>

<template>
  <div v-if="narrative.text" class="narrative" :class="{ surge: narrative.surge_active }">
    <div class="header">
      <span class="label">{{ narrative.surge_active ? '⚡ Surge Analysis' : '📰 Situation Summary' }}</span>
      <span class="meta" v-if="narrative.generated_at">updated {{ fmtTime(narrative.generated_at) }}</span>
    </div>
    <p class="text">{{ narrative.text }}</p>
  </div>
</template>

<style scoped>
.narrative { padding: 12px 20px; border-bottom: 1px solid #1e1e1e; background: #0f0f0f; }
.narrative.surge { background: #1a0a2e; border-left: 3px solid #6a00c8; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.label { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em; color: #888; text-transform: uppercase; }
.narrative.surge .label { color: #a040ff; }
.meta { font-size: 0.72rem; color: #444; }
.text { color: #bbb; font-size: 0.88rem; line-height: 1.55; margin: 0; }
</style>
