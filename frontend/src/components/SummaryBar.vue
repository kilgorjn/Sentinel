<script setup>
import EventChart     from './EventChart.vue'
import SentimentChart from './SentimentChart.vue'

const props = defineProps({ summary: Object, hiddenClasses: Object, timeseries: Object, sentimentTimeseries: Object })
const emit  = defineEmits(['filter'])

const COLORS = { HIGH: '#e05252', MEDIUM: '#e0a832', LOW: '#4a9eda' }

const SENTIMENT_META = {
  POSITIVE: { symbol: '▲', color: '#3a7d5a' },
  NEGATIVE: { symbol: '▼', color: '#a05060' },
  NEUTRAL:  { symbol: '~', color: '#555' },
}

const OVERALL_META = {
  POSITIVE: { symbol: '▲', color: '#3a7d5a', label: 'Positive' },
  NEGATIVE: { symbol: '▼', color: '#a05060', label: 'Negative' },
  NEUTRAL:  { symbol: '~', color: '#555',    label: 'Neutral'  },
}

function countFor(cls) {
  const entry = props.summary.counts?.find(c => c.classification === cls)
  return entry ? entry.count : 0
}

function sentimentFor(cls) {
  const entry = props.summary.counts?.find(c => c.classification === cls)
  return entry?.sentiment || { positive: 0, negative: 0, neutral: 0 }
}

function getOverall() {
  return OVERALL_META[props.summary.overall_sentiment] || OVERALL_META.NEUTRAL
}

// Score in [-1, 1] → fill bar anchored at the 50% centre line
function scoreBarStyle() {
  const score = props.summary.overall_sentiment_score ?? 0
  const pct   = Math.abs(score) * 50   // 0–50% of the track
  const meta  = getOverall()
  return score >= 0
    ? { left: '50%', width: `${pct}%`, background: meta.color }
    : { right: '50%', width: `${pct}%`, background: meta.color }
}
</script>

<template>
  <div class="summary-bar">
    <div
      v-for="cls in ['HIGH', 'MEDIUM', 'LOW']"
      :key="cls"
      class="tile"
      :class="{ dimmed: hiddenClasses.has(cls) }"
      :style="{ borderColor: COLORS[cls] }"
      @click="emit('filter', cls)"
    >
      <span class="label" :style="{ color: COLORS[cls] }">{{ cls }}</span>
      <span class="count">{{ countFor(cls) }}</span>
      <div class="sentiment-row">
        <span class="s-chip" :style="{ color: SENTIMENT_META.POSITIVE.color }">
          ▲{{ sentimentFor(cls).positive }}
        </span>
        <span class="s-chip" :style="{ color: SENTIMENT_META.NEGATIVE.color }">
          ▼{{ sentimentFor(cls).negative }}
        </span>
        <span class="s-chip" :style="{ color: SENTIMENT_META.NEUTRAL.color }">
          ~{{ sentimentFor(cls).neutral }}
        </span>
      </div>
    </div>

    <div
      class="tile total"
      :class="{ active: hiddenClasses.size === 0 }"
      @click="emit('filter', null)"
    >
      <span class="label">TOTAL 24h</span>
      <div class="total-count-row">
        <span class="count">{{ summary.total ?? 0 }}</span>
        <span
          v-if="summary.overall_sentiment"
          class="overall-symbol"
          :style="{ color: getOverall().color }"
          :title="`Weighted market sentiment: ${getOverall().label} (score ${summary.overall_sentiment_score})`"
        >{{ getOverall().symbol }}</span>
      </div>
      <div v-if="summary.overall_sentiment" class="score-wrap">
        <div class="score-track">
          <div class="score-center" />
          <div class="score-fill" :style="scoreBarStyle()" />
        </div>
        <div class="score-tooltip">
          <div class="tt-title" :style="{ color: getOverall().color }">
            {{ getOverall().symbol }} {{ getOverall().label }} sentiment
          </div>
          <div class="tt-score">
            Weighted score: {{ summary.overall_sentiment_score >= 0 ? '+' : '' }}{{ summary.overall_sentiment_score }}
          </div>
          <div class="tt-divider" />
          <div class="tt-row">
            <span class="tt-cls">HIGH &times;3</span>
            <span :style="{ color: '#3a7d5a' }">▲{{ sentimentFor('HIGH').positive }}</span>
            <span :style="{ color: '#a05060' }">▼{{ sentimentFor('HIGH').negative }}</span>
            <span :style="{ color: '#444' }">~{{ sentimentFor('HIGH').neutral }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-cls">MEDIUM &times;2</span>
            <span :style="{ color: '#3a7d5a' }">▲{{ sentimentFor('MEDIUM').positive }}</span>
            <span :style="{ color: '#a05060' }">▼{{ sentimentFor('MEDIUM').negative }}</span>
            <span :style="{ color: '#444' }">~{{ sentimentFor('MEDIUM').neutral }}</span>
          </div>
          <div class="tt-row">
            <span class="tt-cls">LOW &times;1</span>
            <span :style="{ color: '#3a7d5a' }">▲{{ sentimentFor('LOW').positive }}</span>
            <span :style="{ color: '#a05060' }">▼{{ sentimentFor('LOW').negative }}</span>
            <span :style="{ color: '#444' }">~{{ sentimentFor('LOW').neutral }}</span>
          </div>
        </div>
      </div>
      <div v-if="summary.overall_sentiment" class="overall-label" :style="{ color: getOverall().color }">
        {{ getOverall().label }}
      </div>
    </div>

    <div class="charts-group">
      <div class="chart-panel">
        <span class="chart-label">Events / hr</span>
        <div class="chart-area">
          <EventChart :timeseries="timeseries" :hidden-classes="hiddenClasses" />
        </div>
      </div>
      <div class="chart-panel">
        <span class="chart-label">Sentiment / hr</span>
        <div class="chart-area">
          <SentimentChart :sentiment-timeseries="sentimentTimeseries" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.summary-bar { display: flex; gap: 12px; align-items: stretch;
               padding: 16px 20px; border-bottom: 1px solid #1e1e1e;
               overflow-x: auto; -webkit-overflow-scrolling: touch;
               scrollbar-width: none; }
.summary-bar::-webkit-scrollbar { display: none; }

.tile { border: 2px solid #333; border-radius: 6px; padding: 10px 16px; text-align: center;
        min-width: 96px; flex-shrink: 0; cursor: pointer; transition: opacity 0.15s, background 0.15s; }
.tile:hover { background: #1a1a1a; }
.tile.active { background: #1a1a1a; }
.tile.dimmed { opacity: 0.35; }
.label { display: block; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 4px; }
.count { font-size: 2rem; font-weight: 700; }

/* Per-tile sentiment sub-counts */
.sentiment-row { display: flex; justify-content: center; gap: 8px; margin-top: 6px; }
.s-chip { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.02em; }

/* Total tile */
.total { border-color: #444; min-width: 112px; flex-shrink: 0; }
.total-count-row { display: flex; align-items: baseline; justify-content: center; gap: 6px; }
.overall-symbol { font-size: 1.4rem; font-weight: 700; line-height: 1; }
.overall-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em;
                 text-transform: uppercase; margin-top: 4px; }

/* Weighted score bar + tooltip */
.score-wrap { position: relative; margin: 6px 4px 2px; }
.score-track { position: relative; height: 3px; background: #1e1e1e;
               border-radius: 2px; overflow: hidden; cursor: default; }
.score-center { position: absolute; left: 50%; top: 0; bottom: 0;
                width: 1px; background: #333; }
.score-fill { position: absolute; top: 0; bottom: 0; border-radius: 2px;
              transition: width 0.4s ease; }

.score-tooltip { display: none; position: absolute; bottom: calc(100% + 8px); left: 50%;
                 transform: translateX(-50%); background: #111; border: 1px solid #2a2a2a;
                 border-radius: 5px; padding: 8px 12px; white-space: nowrap;
                 font-size: 0.72rem; z-index: 200; text-align: left; pointer-events: none; }
.score-tooltip::after { content: ''; position: absolute; top: 100%; left: 50%;
                         transform: translateX(-50%); border: 5px solid transparent;
                         border-top-color: #2a2a2a; }
.score-wrap:hover .score-tooltip { display: block; }

.tt-title { font-weight: 700; letter-spacing: 0.04em; margin-bottom: 4px; }
.tt-score { color: #555; font-size: 0.68rem; margin-bottom: 6px; }
.tt-divider { border-top: 1px solid #222; margin-bottom: 6px; }
.tt-row { display: flex; gap: 10px; align-items: center; margin-bottom: 3px; }
.tt-cls { color: #555; min-width: 72px; font-size: 0.68rem; }

.charts-group { display: flex; gap: 10px; margin-left: auto; flex-shrink: 0; align-self: stretch; }
.chart-panel { display: flex; flex-direction: column; width: 210px; flex-shrink: 0; }
.chart-label { font-size: 0.58rem; color: #444; text-transform: uppercase;
               letter-spacing: 0.08em; margin-bottom: 3px; text-align: center; }
.chart-area { flex: 1; min-height: 0; }
</style>
