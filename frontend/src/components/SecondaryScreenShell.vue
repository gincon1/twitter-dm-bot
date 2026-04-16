<template>
  <transition name="secondary-screen">
    <div v-if="open" class="secondary-screen-backdrop" @click.self="$emit('close')">
      <section class="secondary-screen-panel">
        <header class="secondary-screen-header">
          <div class="secondary-screen-copy">
            <div class="secondary-screen-eyebrow">{{ eyebrow }}</div>
            <h3>{{ title }}</h3>
            <p v-if="description">{{ description }}</p>
          </div>

          <div class="secondary-screen-actions">
            <slot name="actions" />
            <button class="btn-ghost" @click="$emit('close')">关闭</button>
          </div>
        </header>

        <div class="secondary-screen-body">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="secondary-screen-footer">
          <slot name="footer" />
        </footer>
      </section>
    </div>
  </transition>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  eyebrow: { type: String, default: '详情页' },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
})

defineEmits(['close'])
</script>

<style scoped>
.secondary-screen-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  justify-content: flex-end;
  background: rgba(7, 8, 10, 0.56);
  backdrop-filter: blur(10px);
}

.secondary-screen-panel {
  display: flex;
  height: 100vh;
  width: min(1120px, 100vw);
  flex-direction: column;
  border-left: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  box-shadow: -32px 0 90px rgba(0, 0, 0, 0.3);
}

.secondary-screen-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 28px 18px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel) 82%, transparent);
  backdrop-filter: blur(16px);
}

.secondary-screen-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  text-transform: uppercase;
  letter-spacing: 0.16em;
}

.secondary-screen-copy h3 {
  margin-top: 8px;
  font-size: clamp(24px, 3vw, 34px);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.04em;
  color: var(--text-1);
}

.secondary-screen-copy p {
  margin-top: 10px;
  color: var(--text-3);
  font-size: 13px;
}

.secondary-screen-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.secondary-screen-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px 112px;
}

.secondary-screen-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 18px 28px 24px;
  border-top: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(24, 24, 27, 0.78), rgba(24, 24, 27, 0.96));
  backdrop-filter: blur(14px);
}

.secondary-screen-enter-active,
.secondary-screen-leave-active {
  transition: opacity 0.24s ease;
}

.secondary-screen-enter-active .secondary-screen-panel,
.secondary-screen-leave-active .secondary-screen-panel {
  transition: transform 0.24s ease;
}

.secondary-screen-enter-from,
.secondary-screen-leave-to {
  opacity: 0;
}

.secondary-screen-enter-from .secondary-screen-panel,
.secondary-screen-leave-to .secondary-screen-panel {
  transform: translateX(42px);
}

@media (max-width: 720px) {
  .secondary-screen-panel {
    width: 100vw;
  }

  .secondary-screen-header,
  .secondary-screen-body,
  .secondary-screen-footer {
    padding-left: 18px;
    padding-right: 18px;
  }
}
</style>
