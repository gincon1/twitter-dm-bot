<template>
  <span class="status-badge" :style="badgeStyle">
    <span class="status-dot" :style="{ background: conf.color }"></span>
    {{ conf.label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useTheme } from '../composables/useTheme'

const props = defineProps({ status: { type: String, default: '' } })
const { theme } = useTheme()

const configs = {
  '已发送': { label: '已发送', color: '#62d99b', darkBg: 'rgba(98,217,155,0.12)', darkBorder: 'rgba(98,217,155,0.18)', lightBg: 'rgba(35,139,90,0.12)', lightBorder: 'rgba(35,139,90,0.2)' },
  sent: { label: '已发送', color: '#62d99b', darkBg: 'rgba(98,217,155,0.12)', darkBorder: 'rgba(98,217,155,0.18)', lightBg: 'rgba(35,139,90,0.12)', lightBorder: 'rgba(35,139,90,0.2)' },
  '待发送': { label: '待发送', color: '#77b7ff', darkBg: 'rgba(119,183,255,0.12)', darkBorder: 'rgba(119,183,255,0.18)', lightBg: 'rgba(37,99,235,0.1)', lightBorder: 'rgba(37,99,235,0.18)' },
  pending: { label: '待发送', color: '#77b7ff', darkBg: 'rgba(119,183,255,0.12)', darkBorder: 'rgba(119,183,255,0.18)', lightBg: 'rgba(37,99,235,0.1)', lightBorder: 'rgba(37,99,235,0.18)' },
  '正常': { label: '正常', color: '#62d99b', darkBg: 'rgba(98,217,155,0.12)', darkBorder: 'rgba(98,217,155,0.18)', lightBg: 'rgba(35,139,90,0.12)', lightBorder: 'rgba(35,139,90,0.2)' },
  '跳过': { label: '跳过', color: '#94a3b8', darkBg: 'rgba(148,163,184,0.12)', darkBorder: 'rgba(148,163,184,0.18)', lightBg: 'rgba(148,163,184,0.1)', lightBorder: 'rgba(148,163,184,0.18)' },
  skipped: { label: '跳过', color: '#94a3b8', darkBg: 'rgba(148,163,184,0.12)', darkBorder: 'rgba(148,163,184,0.18)', lightBg: 'rgba(148,163,184,0.1)', lightBorder: 'rgba(148,163,184,0.18)' },
  '异常': { label: '异常', color: '#f87171', darkBg: 'rgba(248,113,113,0.12)', darkBorder: 'rgba(248,113,113,0.18)', lightBg: 'rgba(248,113,113,0.1)', lightBorder: 'rgba(248,113,113,0.18)' },
  error: { label: '异常', color: '#f87171', darkBg: 'rgba(248,113,113,0.12)', darkBorder: 'rgba(248,113,113,0.18)', lightBg: 'rgba(248,113,113,0.1)', lightBorder: 'rgba(248,113,113,0.18)' },
  '不可DM': { label: '不可DM', color: '#fb923c', darkBg: 'rgba(251,146,60,0.12)', darkBorder: 'rgba(251,146,60,0.18)', lightBg: 'rgba(251,146,60,0.1)', lightBorder: 'rgba(251,146,60,0.18)' },
  '已回复': { label: '已回复', color: '#c084fc', darkBg: 'rgba(192,132,252,0.12)', darkBorder: 'rgba(192,132,252,0.18)', lightBg: 'rgba(168,85,247,0.1)', lightBorder: 'rgba(168,85,247,0.18)' },
}

const conf = computed(() => configs[props.status] || {
  label: props.status || '—',
  color: '#94a3b8',
  darkBg: 'rgba(148,163,184,0.12)',
  darkBorder: 'rgba(148,163,184,0.18)',
  lightBg: 'rgba(148,163,184,0.1)',
  lightBorder: 'rgba(148,163,184,0.18)'
})

const badgeStyle = computed(() => {
  const c = conf.value
  const isLight = theme.value === 'light'
  return {
    color: c.color,
    background: isLight ? c.lightBg : c.darkBg,
    borderColor: isLight ? c.lightBorder : c.darkBorder,
  }
})
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
