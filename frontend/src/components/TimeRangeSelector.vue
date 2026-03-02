<script setup>
const props = defineProps({
  modelValue: { type: Number, default: 24 },
})

const emit = defineEmits(['update:modelValue'])

const presets = [
  { label: 'Last 1h', hours: 1 },
  { label: 'Last 4h', hours: 4 },
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7d', hours: 168 },
  { label: 'Last 30d', hours: 720 },
]

function select(hours) {
  emit('update:modelValue', hours)
}
</script>

<template>
  <div class="time-range-selector">
    <span class="label">Time Range:</span>
    <div class="preset-group">
      <button
        v-for="preset in presets"
        :key="preset.hours"
        :class="{ active: modelValue === preset.hours }"
        @click="select(preset.hours)"
      >
        {{ preset.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.time-range-selector {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 12px 0;
  border-bottom: 1px solid #222;
}

.label {
  color: #999;
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
}

.preset-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

button {
  padding: 6px 12px;
  background: #222;
  color: #aaa;
  border: 1px solid #333;
  border-radius: 4px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover {
  background: #2a2a2a;
  color: #ccc;
  border-color: #444;
}

button.active {
  background: #4a9eda;
  color: #fff;
  border-color: #4a9eda;
  font-weight: 600;
}
</style>
