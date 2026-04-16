<template>
  <div class="app-frame">
    <div class="app-ambient app-ambient-a" />
    <div class="app-ambient app-ambient-b" />

    <div
      v-if="sidebarOpen"
      class="sidebar-mobile-overlay"
      @click="sidebarOpen = false"
    />

    <aside
      class="app-sidebar"
      :class="sidebarOpen ? 'sidebar-mobile-show' : 'sidebar-mobile-hide'"
    >
      <div class="brand-block">
        <div class="brand-mark">OP</div>
        <div class="brand-copy">
          <div class="brand-kicker">Outreach System</div>
          <div class="brand-title">外联运营后台</div>
        </div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-eyebrow">核心模块</div>
        <nav class="sidebar-nav">
          <router-link
            v-for="item in primaryNavItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="isActive(item.path) ? 'nav-active' : 'nav-inactive'"
            @click="sidebarOpen = false"
          >
            <component :is="item.icon" class="nav-icon" />
            <div class="nav-copy">
              <div class="nav-copy-head">
                <span>{{ item.label }}</span>
                <em v-if="navBadge(item.path)" class="nav-badge">{{ navBadge(item.path) }}</em>
              </div>
              <small>{{ item.note }}</small>
            </div>
          </router-link>
        </nav>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-eyebrow">基础数据</div>
        <nav class="sidebar-nav">
          <router-link
            v-for="item in secondaryNavItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="isActive(item.path) ? 'nav-active' : 'nav-inactive'"
            @click="sidebarOpen = false"
          >
            <component :is="item.icon" class="nav-icon" />
            <div class="nav-copy">
              <div class="nav-copy-head">
                <span>{{ item.label }}</span>
                <em v-if="navBadge(item.path)" class="nav-badge">{{ navBadge(item.path) }}</em>
              </div>
              <small>{{ item.note }}</small>
            </div>
          </router-link>
        </nav>
      </div>

      <div class="sidebar-status">
        <div class="status-chip-row">
          <span class="status-dot" :class="runState.dotClass" />
          <span>{{ runState.label }}</span>
        </div>
        <div class="sidebar-status-title">执行状态</div>
        <div class="sidebar-status-meta">下次执行 {{ system.status.next_run_time || '未安排' }}</div>
      </div>
    </aside>

    <div class="app-main">
      <header class="app-header">
        <div class="header-left">
          <button class="mobile-menu-btn" @click="sidebarOpen = !sidebarOpen">
            <svg class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M2 4h12M2 8h12M2 12h12" stroke-linecap="round" />
            </svg>
          </button>
          <div class="page-title-block">
            <div class="page-kicker">管理后台</div>
            <h1>{{ currentTitle }}</h1>
          </div>
        </div>

        <div class="header-right">
          <div class="header-controls">
            <button
              v-if="!isRunning"
              class="btn btn-primary"
              @click="safeRun(() => system.startSystem())"
            >
              开始
            </button>
            <button
              v-else-if="isPaused"
              class="btn btn-primary"
              @click="safeRun(() => system.resumeSystem())"
            >
              恢复
            </button>
            <button
              v-else
              class="btn btn-secondary"
              @click="safeRun(() => system.pauseSystem())"
            >
              暂停
            </button>
            <button
              v-if="isRunning"
              class="btn btn-ghost"
              @click="safeRun(() => system.stopSystem())"
            >
              停止
            </button>
          </div>
          <div class="header-pill">
            <span class="header-pill-dot" :class="runState.dotClass" />
            {{ runState.label }}
          </div>
          <div class="header-meta">
            {{ system.now.toLocaleString() }}
          </div>
          <button
            v-if="breakerTripped"
            class="btn-danger"
            @click="safeRun(() => system.resetCircuitBreaker('ui'))"
          >
            重置熔断状态
          </button>
          <button
            class="theme-btn"
            :title="theme === 'dark' ? '切换到亮色' : '切换到暗色'"
            @click="toggle"
          >
            <svg v-if="theme === 'dark'" class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4">
              <circle cx="8" cy="8" r="3" />
              <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M11.89 4.11l1.06-1.06M3.05 12.95l1.06-1.06" stroke-linecap="round" />
            </svg>
            <svg v-else class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4">
              <path d="M10.9 2.6a5.4 5.4 0 102.5 9.9A5.8 5.8 0 018.3 14 5.8 5.8 0 015.1 3.3a5.7 5.7 0 015.8-.7z" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
      </header>

      <main class="app-content">
        <div class="page-stage">
          <router-view v-slot="{ Component, route: viewRoute }">
            <transition name="page-shell" mode="out-in">
              <component :is="Component" :key="viewRoute.fullPath" />
            </transition>
          </router-view>
        </div>
      </main>
    </div>

    <ToastList :toasts="system.toasts" @close="system.removeToast" />
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import ToastList from './components/ToastList.vue'
import { useTheme } from './composables/useTheme'
import { useSystemStore } from './stores/system'
import { getActionErrorMessage } from './utils/errorText'

const route = useRoute()
const system = useSystemStore()
const { theme, toggle } = useTheme()

const sidebarOpen = ref(false)

watch(() => route.path, () => { sidebarOpen.value = false })

const mkIcon = (paths) => defineComponent({
  render: () => h('svg', { viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.4', 'stroke-linecap': 'round' }, paths)
})

const IconDashboard = mkIcon([
  h('rect', { x: '1.5', y: '1.5', width: '5', height: '5', rx: '1' }),
  h('rect', { x: '9.5', y: '1.5', width: '5', height: '5', rx: '1' }),
  h('rect', { x: '1.5', y: '9.5', width: '5', height: '5', rx: '1' }),
  h('rect', { x: '9.5', y: '9.5', width: '5', height: '5', rx: '1' }),
])
const IconProjects = mkIcon([
  h('path', { d: 'M2 4.5h12M2 8h12M2 11.5h8' }),
  h('circle', { cx: '13', cy: '11.5', r: '1', fill: 'currentColor', stroke: 'none' }),
])
const IconConversations = mkIcon([
  h('path', { d: 'M2.5 4.5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H8l-3.5 2v-2H4.5a2 2 0 01-2-2v-4z', 'stroke-linejoin': 'round' }),
  h('path', { d: 'M5 6.5h6M5 8.8h4' }),
])
const IconTargets = mkIcon([
  h('circle', { cx: '8', cy: '8', r: '6' }),
  h('circle', { cx: '8', cy: '8', r: '3' }),
  h('circle', { cx: '8', cy: '8', r: '0.8', fill: 'currentColor', stroke: 'none' }),
])
const IconSegments = mkIcon([
  h('circle', { cx: '5', cy: '5', r: '1.5' }),
  h('circle', { cx: '11', cy: '5', r: '1.5' }),
  h('circle', { cx: '8', cy: '10.5', r: '1.5' }),
  h('path', { d: 'M6.2 6.2l1 2.2M9.8 6.2l-1 2.2M6.6 10.9h2.8' }),
])
const IconAccounts = mkIcon([
  h('circle', { cx: '8', cy: '5', r: '2.5' }),
  h('path', { d: 'M2.5 13.5c0-3 2.5-4.5 5.5-4.5s5.5 1.5 5.5 4.5' }),
])
const IconTemplates = mkIcon([h('path', { d: 'M2 4h12M2 8h8M2 12h5' })])
const IconSettings = mkIcon([
  h('circle', { cx: '8', cy: '8', r: '2' }),
  h('path', { d: 'M8 1v2M8 13v2M1 8h2M13 8h2M2.93 2.93l1.41 1.41M11.66 11.66l1.41 1.41M2.93 13.07l1.41-1.41M11.66 4.34l1.41-1.41' }),
])

const primaryNavItems = [
  { path: '/dashboard', label: '监控概览', note: '系统状态与执行指标', icon: IconDashboard },
  { path: '/projects', label: '项目管理', note: '项目清单与执行入口', icon: IconProjects },
  { path: '/conversations', label: '会话管理', note: '回复流转与人工处理', icon: IconConversations },
]

const secondaryNavItems = [
  { path: '/targets', label: '目标数据', note: '目标名单与去重结果', icon: IconTargets },
  { path: '/segments', label: '目标分组', note: '筛选后的执行集合', icon: IconSegments },
  { path: '/accounts', label: '账号管理', note: '账号健康与资源分配', icon: IconAccounts },
  { path: '/templates', label: '模板管理', note: '触达序列模板', icon: IconTemplates },
  { path: '/settings', label: '策略配置', note: '全局策略与阈值', icon: IconSettings },
]

const titleMap = {
  dashboard: '监控概览',
  projects: '项目管理',
  'project-detail': '项目详情',
  conversations: '会话管理',
  targets: '目标数据',
  segments: '目标分组',
  accounts: '账号管理',
  templates: '模板管理',
  settings: '策略配置',
}

const currentTitle = computed(() => titleMap[route.name] || route.meta?.title || '触达管理平台')

const isRunning = computed(() => !!system.status.running)
const isPaused = computed(() => !!system.status.paused)
const breakerTripped = computed(() => !!system.status.circuit_breaker_tripped)
const isRunningActive = computed(() => isRunning.value && !isPaused.value)

const runState = computed(() => {
  if (breakerTripped.value) {
    return { key: 'breaker', label: '已熔断', dotClass: 'dot-danger' }
  }
  if (isRunningActive.value) {
    return { key: 'running', label: '执行中', dotClass: 'dot-success' }
  }
  if (isRunning.value && isPaused.value) {
    return { key: 'paused', label: '暂停中', dotClass: 'dot-warn' }
  }
  return { key: 'stopped', label: '待执行', dotClass: 'dot-muted' }
})

const isActive = (path) => {
  if (path === '/projects') {
    return route.path === '/projects' || route.path.startsWith('/projects/')
  }
  return route.path === path || route.path.startsWith(`${path}/`)
}

const navBadge = (path) => {
  if (path === '/conversations') {
    return Math.max(0, Number(system.stats.pending_replies?.length || 0))
  }
  return 0
}

const safeRun = async (fn) => {
  try { await fn() }
  catch (e) { system.notify(getActionErrorMessage('操作', e), 'error') }
}

onMounted(async () => {
  try { await system.initRealtime() }
  catch (e) { system.notify(getActionErrorMessage('初始化', e), 'error') }
})

onUnmounted(() => { system.cleanupRealtime() })
</script>

<style scoped>
.app-frame {
  position: relative;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text-1);
  overflow: hidden;
}

.app-ambient {
  position: fixed;
  inset: auto;
  pointer-events: none;
  filter: blur(90px);
  opacity: 0.35;
}

.app-ambient-a {
  top: -120px;
  left: 14%;
  width: 320px;
  height: 320px;
  background: rgba(78, 173, 121, 0.16);
}

.app-ambient-b {
  right: -120px;
  bottom: -80px;
  width: 360px;
  height: 360px;
  background: rgba(156, 163, 175, 0.12);
}

.app-sidebar {
  position: fixed;
  inset: 18px auto 18px 18px;
  z-index: 50;
  display: flex;
  width: 248px;
  flex-direction: column;
  gap: 18px;
  border: 1px solid var(--border);
  border-radius: 28px;
  background: color-mix(in srgb, var(--sidebar-bg) 88%, transparent);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(20px);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 20px 0;
}

.brand-mark {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 14px;
  border: 1px solid rgba(104, 211, 145, 0.22);
  background:
    linear-gradient(135deg, rgba(104, 211, 145, 0.28), rgba(45, 212, 191, 0.12)),
    rgba(255, 255, 255, 0.03);
  color: #f5f5f5;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.brand-kicker,
.sidebar-eyebrow,
.page-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.brand-title {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.sidebar-section {
  padding: 0 14px;
}

.sidebar-nav {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 13px;
  border-radius: 18px;
  border: 1px solid transparent;
  text-decoration: none;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, color 0.18s ease;
}

.nav-item:hover {
  transform: translateX(2px);
}

.nav-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.nav-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.nav-copy-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.nav-copy span {
  font-size: 13px;
  font-weight: 600;
}

.nav-badge {
  display: inline-flex;
  min-width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(98, 217, 155, 0.14);
  border: 1px solid rgba(98, 217, 155, 0.2);
  color: var(--accent);
  font-style: normal;
  font-size: 11px;
  font-weight: 700;
}

.nav-copy small {
  color: var(--text-4);
  font-size: 11px;
  line-height: 1.4;
}

.nav-inactive {
  color: var(--text-3);
}

.nav-inactive:hover {
  color: var(--text-1);
  border-color: var(--border);
  background: var(--surface-elevated);
}

.nav-active {
  color: var(--text-1);
  border-color: rgba(111, 214, 152, 0.18);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.sidebar-status {
  margin: auto 14px 14px;
  padding: 16px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.02));
}

.status-chip-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  color: var(--text-2);
}

.status-dot,
.header-pill-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.dot-success {
  background: #4ade80;
  box-shadow: 0 0 0 6px rgba(74, 222, 128, 0.12);
}

.dot-warn {
  background: #f59e0b;
  box-shadow: 0 0 0 6px rgba(245, 158, 11, 0.12);
}

.dot-danger {
  background: #f87171;
  box-shadow: 0 0 0 6px rgba(248, 113, 113, 0.12);
}

.dot-muted {
  background: #71717a;
}

.sidebar-status-title {
  margin-top: 14px;
  font-size: 14px;
  font-weight: 600;
}

.sidebar-status-meta {
  margin-top: 4px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.5;
}

.app-main {
  margin-left: 284px;
  min-height: 100vh;
  padding: 18px 18px 22px 0;
}

.app-header {
  position: sticky;
  top: 18px;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 22px;
  border: 1px solid var(--border);
  border-radius: 28px;
  background: color-mix(in srgb, var(--panel) 80%, transparent);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow-soft);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-right {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.page-title-block h1 {
  margin-top: 6px;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.05em;
}

.page-title-block p {
  margin-top: 10px;
  color: var(--text-3);
  font-size: 13px;
}

.header-pill,
.header-meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-2);
  font-size: 12px;
}

.theme-btn,
.mobile-menu-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-2);
  overflow: hidden;
  transition: transform 0.18s ease, border-color 0.18s ease, color 0.18s ease, background 0.18s ease;
}

.theme-btn svg,
.mobile-menu-btn svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: block;
}

.theme-btn:hover,
.mobile-menu-btn:hover {
  color: var(--text-1);
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.app-content {
  padding-top: 18px;
}

.page-stage {
  position: relative;
  min-height: calc(100vh - 148px);
  border: 1px solid var(--border);
  border-radius: 32px;
  background: color-mix(in srgb, var(--panel) 88%, transparent);
  box-shadow: var(--shadow-soft);
  padding: 24px;
  overflow: hidden;
}

.page-shell-enter-active,
.page-shell-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.page-shell-enter-from,
.page-shell-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.sidebar-mobile-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
}

@media (max-width: 1180px) {
  .app-sidebar {
    inset: 14px auto 14px 14px;
    width: min(248px, calc(100vw - 32px));
    transform: translateX(-120%);
    transition: transform 0.22s ease;
  }

  .sidebar-mobile-show {
    transform: translateX(0);
  }

  .app-main {
    margin-left: 0;
    padding: 14px;
  }

  .app-header {
    top: 14px;
  }
}

@media (min-width: 1181px) {
  .mobile-menu-btn,
  .sidebar-mobile-overlay {
    display: none;
  }

  .sidebar-mobile-hide {
    transform: translateX(0);
  }
}

@media (max-width: 720px) {
  .app-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-left,
  .header-right {
    width: 100%;
  }

  .page-stage {
    border-radius: 24px;
    padding: 18px;
  }

  .page-title-block h1 {
    font-size: 30px;
  }

  .header-meta {
    display: none;
  }
}
</style>
