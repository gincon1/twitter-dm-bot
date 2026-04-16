<template>
  <div class="stat-card">
    <div class="stat-label">{{ title }}</div>
    <div class="stat-value" :style="{ color: valueColor }">{{ value }}</div>
    <div v-if="subtitle" class="stat-sub">{{ subtitle }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: String,
  value: [String, Number],
  subtitle: { type: String, default: '' },
  color: { type: String, default: 'default' }
})

const valueColor = computed(() => {
  if (props.color === 'green') return 'var(--accent)'
  if (props.color === 'yellow') return '#f59e0b'
  if (props.color === 'red') return '#f87171'
  if (props.color === 'blue') return 'var(--accent-2)'
  return 'var(--text-1)'
})
</script>

<style scoped>
.stat-card {
  min-height: 152px;
  padding: 18px;
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.018)),
    var(--panel);
  border: 1px solid var(--border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.stat-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-4);
}

.stat-value {
  margin-top: 16px;
  font-size: 40px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.05em;
  font-variant-numeric: tabular-nums;
}

.stat-sub {
  margin-top: 12px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.6;
}
</style>
