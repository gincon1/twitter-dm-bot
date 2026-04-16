<template>
  <div class="toast-list">
    <div v-for="item in toasts" :key="item.id" class="toast" :style="toastStyle(item.type)">
      <span class="toast-dot" :style="{ background: dotColor(item.type) }"></span>
      <span class="toast-msg">{{ item.message }}</span>
      <button class="toast-close" @click="$emit('close', item.id)">✕</button>
    </div>
  </div>
</template>

<script setup>
defineProps({ toasts: { type: Array, default: () => [] } })
defineEmits(['close'])

const toastStyle = (type) => {
  const base = { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' }
  if (type === 'success') return { ...base, borderColor: 'rgba(62,207,142,0.3)',  background: 'color-mix(in srgb, var(--panel) 90%, #052e16 10%)',  color: '#6ee7b7' }
  if (type === 'warn')    return { ...base, borderColor: 'rgba(245,158,11,0.3)',  background: 'color-mix(in srgb, var(--panel) 90%, #451a03 10%)',  color: '#fcd34d' }
  if (type === 'error')   return { ...base, borderColor: 'rgba(248,113,113,0.3)', background: 'color-mix(in srgb, var(--panel) 90%, #450a0a 10%)', color: '#fca5a5' }
  return { ...base, borderColor: 'rgba(147,197,253,0.25)', background: 'color-mix(in srgb, var(--panel) 90%, #0c1a2e 10%)', color: '#93c5fd' }
}

const dotColor = (type) => {
  if (type === 'success') return '#3ecf8e'
  if (type === 'warn')    return '#f59e0b'
  if (type === 'error')   return '#f87171'
  return '#60a5fa'
}
</script>

<style scoped>
.toast-list {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: calc(100vw - 32px);
}
.toast {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 240px;
  max-width: 360px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid;
  font-size: 13px;
}
.toast-dot  { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.toast-msg  { flex: 1; line-height: 1.4; }
.toast-close { font-size: 10px; opacity: 0.4; cursor: pointer; padding: 2px 4px; transition: opacity 0.15s; background: none; border: none; color: inherit; }
.toast-close:hover { opacity: 0.8; }
</style>
