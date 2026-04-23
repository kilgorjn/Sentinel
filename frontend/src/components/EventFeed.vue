<script setup>
import { inject, ref, watch, nextTick } from 'vue'

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

// --- Modal state ---
const dialogEl    = ref(null)
const modalOpen   = ref(false)
const modalDetail = ref(null)
const modalLoading = ref(false)
const modalError  = ref(null)

// Drive native <dialog> open/close from modalOpen
watch(modalOpen, async (val) => {
  await nextTick()
  if (val) dialogEl.value?.showModal()
  else dialogEl.value?.close()
})

async function openModal(ev) {
  modalDetail.value  = null
  modalError.value   = null
  modalLoading.value = true
  modalOpen.value    = true
  try {
    const res = await fetch(`/api/events/${ev.id}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    modalDetail.value = await res.json()
  } catch (e) {
    console.error('Event detail fetch failed:', e)
    modalError.value = 'Failed to load event detail.'
  } finally {
    modalLoading.value = false
  }
}

function closeModal() {
  modalOpen.value = false
}

// Clicking the <dialog> element itself means the backdrop was clicked
function onDialogClick(e) {
  if (e.target === dialogEl.value) closeModal()
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
      @click="openModal(ev)"
    >
      <span class="badge" :style="{ background: COLORS[ev.classification] }">
        {{ ev.classification }}
      </span>
      <div class="body">
        <span class="event-title">{{ ev.title }}</span>
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

  <!-- Event Detail Modal — uses native <dialog> for accessibility and built-in Escape handling -->
  <Teleport to="body">
    <dialog ref="dialogEl" class="modal" @click="onDialogClick" @cancel="closeModal">
      <button class="modal-close" @click="closeModal" aria-label="Close">&times;</button>

      <div v-if="modalLoading" class="modal-loading">Loading&hellip;</div>
      <div v-else-if="modalError" class="modal-error">{{ modalError }}</div>

      <template v-else-if="modalDetail">
        <!-- Header: badge + title -->
        <div class="modal-header">
          <span class="badge" :style="{ background: COLORS[modalDetail.classification] }">
            {{ modalDetail.classification }}
          </span>
          <h2 class="modal-title">{{ modalDetail.title }}</h2>
        </div>

        <!-- Meta row -->
        <div class="modal-meta">
          <span>{{ modalDetail.source }}</span>
          <span v-if="modalDetail.source">&mdash;</span>
          <span>{{ fmt(modalDetail.created_at) }}</span>
          <span v-if="modalDetail.confidence" class="conf-chip">
            {{ Math.round(modalDetail.confidence * 100) }}% confidence
          </span>
          <span
            v-if="sentimentMeta(modalDetail.sentiment)"
            class="sentiment-chip"
            :style="{ color: sentimentMeta(modalDetail.sentiment).color }"
          >
            {{ sentimentMeta(modalDetail.sentiment).symbol }} {{ modalDetail.sentiment }}
          </span>
        </div>

        <!-- RSS Summary -->
        <section v-if="modalDetail.summary" class="modal-section">
          <h3 class="section-label">Summary</h3>
          <p class="section-body">{{ modalDetail.summary }}</p>
        </section>

        <!-- LLM Analysis -->
        <section v-if="modalDetail.reason" class="modal-section">
          <h3 class="section-label">Analysis</h3>
          <p class="section-body">{{ modalDetail.reason }}</p>
        </section>

        <!-- Article link -->
        <div v-if="modalDetail.url" class="modal-footer">
          <a :href="modalDetail.url" target="_blank" rel="noopener" class="article-link">
            Open article &rarr;
          </a>
          <span class="paywall-note">(may be paywalled)</span>
        </div>
      </template>
    </dialog>
  </Teleport>
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
  transition: border-color 0.2s, background 0.15s;
  cursor: pointer;
}
.event-row:hover { background: rgba(255,255,255,0.03); }
.badge { color: #fff; font-weight: 700; font-size: 0.7rem; padding: 4px 10px; border-radius: 4px;
         white-space: nowrap; margin-top: 2px; letter-spacing: 0.05em; }
.body { flex: 1; min-width: 0; }
.event-title {
  font-weight: 600; color: #ddd; display: block;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.event-row:hover .event-title { color: #fff; }
small { display: block; color: #555; font-size: 0.78rem; margin-top: 3px; }
.sentiment-chip {
  margin-left: 8px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.reason { margin: 5px 0 0; font-size: 0.83rem; color: #888; }

/* Modal */
.modal {
  background: #1c1c1c;
  border: 1px solid #2e2e2e;
  border-radius: 8px;
  width: min(640px, calc(100vw - 40px));
  max-height: 80vh;
  overflow-y: auto;
  padding: 24px 28px;
  position: relative;
  color: #ddd;
}
.modal::backdrop {
  background: rgba(0,0,0,0.65);
}
.modal-close {
  position: absolute;
  top: 14px;
  right: 16px;
  background: none;
  border: none;
  color: #666;
  font-size: 1.4rem;
  cursor: pointer;
  line-height: 1;
}
.modal-close:hover { color: #ccc; }
.modal-loading, .modal-error { color: #888; font-style: italic; padding: 20px 0; text-align: center; }
.modal-error { color: #e05252; }
.modal-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; padding-right: 24px; }
.modal-title { font-size: 1.05rem; font-weight: 700; color: #e8e8e8; margin: 0; line-height: 1.4; }
.modal-meta { font-size: 0.8rem; color: #555; margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.conf-chip { color: #777; margin-left: 4px; }
.modal-section { margin-bottom: 18px; }
.section-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #555; margin: 0 0 6px; }
.section-body { font-size: 0.88rem; color: #aaa; line-height: 1.6; margin: 0; }
.modal-footer { margin-top: 20px; border-top: 1px solid #2a2a2a; padding-top: 14px; display: flex; align-items: center; gap: 10px; }
.article-link { font-size: 0.85rem; color: #4a9eda; text-decoration: none; font-weight: 600; }
.article-link:hover { text-decoration: underline; }
.paywall-note { font-size: 0.75rem; color: #444; font-style: italic; }
</style>
