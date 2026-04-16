<template>
  <div ref="box" class="log-wrap">
    <div v-if="!logs.length" class="log-empty">等待日志推送...</div>
    <div v-for="log in logs" :key="log.id" class="log-row">
      <span class="log-time">{{ shortTime(log.timestamp) }}</span>
      <span class="log-level" :style="{ color: levelColor(log.level) }">{{ log.level }}</span>
      <span class="log-account">{{ log.account || 'system' }}</span>
      <span class="log-arrow">→</span>
      <div class="log-main">
        <div class="log-meta">
          <span v-if="log.status" class="log-chip">{{ log.status }}</span>
          <span v-if="log.target" class="log-chip">@{{ log.target }}</span>
        </div>
        <span class="log-msg">{{ log.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({ logs: { type: Array, default: () => [] } })
const box = ref(null)

const shortTime = (value) => {
  if (!value) return '--:--:--'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? (value.slice(11, 19) || value) : d.toTimeString().slice(0, 8)
}

const levelColor = (level) => {
  if (level === 'SUCCESS') return '#62d99b'
  if (level === 'WARN') return '#f59e0b'
  if (level === 'ERROR') return '#f87171'
  return '#77b7ff'
}

watch(() => props.logs.length, async () => {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
})
</script>

<style scoped>
.log-wrap {
  height: 400px;
  overflow-y: auto;
  font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
  font-size: 11.5px;
  line-height: 1.75;
  padding: 14px;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.01)),
    var(--log-bg);
  border: 1px solid var(--border);
}

.log-empty {
  padding: 10px;
  color: var(--text-4);
}

.log-row {
  display: grid;
  grid-template-columns: 70px 62px 120px 16px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 6px 8px;
  border-radius: 12px;
}

.log-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.log-time {
  color: var(--text-4);
}

.log-level {
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.log-account {
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-arrow {
  color: var(--text-4);
}

.log-msg {
  color: var(--text-2);
  word-break: break-word;
}

.log-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.log-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.log-chip {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.03);
  font-size: 10px;
  line-height: 1;
}

@media (max-width: 720px) {
  .log-row {
    grid-template-columns: 64px 54px 1fr;
  }

  .log-arrow {
    display: none;
  }

  .log-account {
    grid-column: 3;
  }

  .log-msg {
    grid-column: 1 / -1;
  }
}
</style>
