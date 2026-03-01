<script setup>
defineProps({ surge: Object })
</script>

<template>
  <div v-if="surge.surge_active" class="surge-banner">
    ⚡ NEWS SURGE — {{ surge.high_count_in_window }} HIGH events in the last
    {{ surge.window_minutes }} min &mdash; expect elevated login volume
  </div>
</template>

<style scoped>
.surge-banner {
  background: #6a00c8;
  color: #fff;
  font-weight: bold;
  padding: 12px 20px;
  text-align: center;
  font-size: 1rem;
  letter-spacing: 0.03em;
}
</style>
