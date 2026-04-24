<template>
  <section class="dashboard-page">
    <div class="dashboard-hero card">
      <div class="dashboard-hero-copy">
        <div class="dashboard-kicker">Operations Overview</div>
        <h2>私信外联总览</h2>
        <div class="dashboard-hero-actions">
          <button class="btn btn-ghost" @click="reloadAccounts">刷新账号数据</button>
          <button class="btn btn-secondary" @click="checkReplies">同步回复状态</button>
          <button class="btn btn-secondary" :disabled="!canRunFollowups" @click="runFollowups">
            {{ followupSubmitting ? '执行中...' : '执行续跟任务' }}
          </button>
        </div>
      </div>

      <div class="dashboard-status card-soft">
        <div class="dashboard-status-head">
          <span class="pill">
            <span class="pill-dot" :style="{ background: runIndicator.color }" />
            {{ runIndicator.label }}
          </span>
          <span class="dashboard-status-time">下次执行 {{ system.status.next_run_time || '未安排' }}</span>
        </div>

        <div class="dashboard-status-grid">
          <div>
            <span>活跃账号</span>
            <strong>{{ system.status.active_accounts || 0 }}</strong>
          </div>
          <div>
            <span>待联系</span>
            <strong>{{ system.status.pending_targets || 0 }}</strong>
          </div>
          <div>
            <span>当日发送量</span>
            <strong>{{ system.stats.today.sent || 0 }}</strong>
          </div>
          <div>
            <span>当日回复量</span>
            <strong>{{ system.stats.today.replies || 0 }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div class="dashboard-stats">
      <StatCard title="当日发送量" :value="system.stats.today.sent" color="green" />
      <StatCard title="当日回复量" :value="system.stats.today.replies" color="green" />
      <StatCard title="可用账号数" :value="system.status.active_accounts" color="blue" />
      <StatCard title="待联系数" :value="system.status.pending_targets" color="yellow" />
      <StatCard title="当日异常数" :value="system.stats.today.errors" color="red" />
      <StatCard
        title="熔断状态"
        :value="system.status.circuit_breaker_tripped ? '已触发' : '正常'"
        :color="system.status.circuit_breaker_tripped ? 'red' : 'blue'"
      />
    </div>

    <div class="dashboard-main-grid">
      <div class="card dashboard-panel dashboard-log-panel">
        <div class="dashboard-panel-head">
          <div>
            <div class="section-title">实时日志</div>
          </div>
          <span class="pill">SSE 推送</span>
        </div>
        <LogViewer :logs="system.logs" />
      </div>

      <div class="dashboard-side-stack">
        <div class="card dashboard-panel">
          <div class="dashboard-panel-head">
            <div>
              <div class="section-title">账号状态概览</div>
            </div>
          </div>

          <div class="account-list">
            <div v-for="acc in visibleAccounts" :key="acc.record_id" class="account-card">
              <div class="account-card-top">
                <div>
                  <div class="account-name">{{ acc.twitter_username || acc.profile_id }}</div>
                  <div class="account-id">{{ acc.profile_id }}</div>
                </div>
                <StatusBadge :status="acc.status" />
              </div>

              <div class="account-progress-meta">
                <span>当日发送量</span>
                <span>{{ acc.today_sent || 0 }} / {{ acc.daily_limit_today || 0 }}</span>
              </div>
              <div class="account-progress-track">
                <div class="account-progress-bar" :style="{ width: progressWidth(acc) }" />
              </div>
              <div class="account-foot">
                <span :style="{ color: healthColor(acc.health_score) }">健康分 {{ acc.health_score ?? 100 }}</span>
                <span>{{ formatCooldown(acc.cooldown_until) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card dashboard-panel">
          <div class="dashboard-panel-head">
            <div>
              <div class="section-title">待处理回复</div>
            </div>
            <span class="pill">{{ system.stats.pending_replies?.length || 0 }} 条</span>
          </div>

          <div v-if="system.stats.pending_replies?.length" class="reply-list">
            <div v-for="item in system.stats.pending_replies" :key="item.id" class="reply-card">
              <div class="reply-card-head">
                <strong>@{{ item.target_username || '-' }}</strong>
                <span>{{ formatReplyTime(item.reply_at) }}</span>
              </div>
              <div class="reply-meta">
                {{ item.client_group || '未归属' }} / {{ item.account_username || item.account_profile_id || '-' }}
              </div>
              <div class="reply-preview">{{ item.last_reply_preview || '-' }}</div>
            </div>
          </div>
          <div v-else class="dashboard-empty">暂无待处理回复</div>
        </div>
      </div>
    </div>

    <div class="dashboard-chart-grid">
      <div class="card dashboard-panel">
        <div class="dashboard-panel-head">
          <div>
            <div class="section-title">发送漏斗</div>
          </div>
        </div>
        <div class="funnel-grid">
          <div v-for="item in funnelCards" :key="item.label" class="metric-card funnel-card">
            <span>{{ item.label }}</span>
            <strong :style="{ color: item.color }">{{ item.value }}</strong>
          </div>
        </div>
      </div>

      <div class="card dashboard-panel">
        <div class="dashboard-panel-head">
          <div>
            <div class="section-title">7天发送趋势</div>
          </div>
        </div>
        <v-chart class="trend-chart" :option="trendOption" autoresize />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'

import LogViewer from '../components/LogViewer.vue'
import StatCard from '../components/StatCard.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useTheme } from '../composables/useTheme'
import { useAccountsStore } from '../stores/accounts'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent])

const system = useSystemStore()
const accounts = useAccountsStore()
const { theme } = useTheme()
const followupSubmitting = ref(false)

const visibleAccounts = computed(() => accounts.accounts.slice(0, 6))

const runIndicator = computed(() => {
  if (system.status.circuit_breaker_tripped) {
    return { label: '已熔断', color: '#f87171' }
  }
  if (system.status.running && !system.status.paused) {
    return { label: '执行中', color: '#62d99b' }
  }
  if (system.status.running && system.status.paused) {
    return { label: '暂停中', color: '#f59e0b' }
  }
  return { label: '待执行', color: '#94a3b8' }
})

const canRunFollowups = computed(() => system.pageRunning && !followupSubmitting.value)

const chartPalette = computed(() => {
  if (theme.value === 'light') {
    return {
      label: '#a99a88',
      split: 'rgba(65,53,35,0.08)',
      line: '#238b5a',
      dotBorder: '#fbf7f1',
      area: 'rgba(35,139,90,0.08)',
      tooltipBg: '#fffaf2',
      tooltipBorder: 'rgba(65,53,35,0.1)',
      tooltipText: '#1e1a15',
    }
  }
  return {
    label: '#655d53',
    split: 'rgba(255,255,255,0.04)',
    line: '#62d99b',
    dotBorder: '#171613',
    area: 'rgba(98,217,155,0.08)',
    tooltipBg: '#1d1b18',
    tooltipBorder: 'rgba(255,255,255,0.08)',
    tooltipText: '#f4f2ee',
  }
})

const reloadAccounts = async () => {
  try {
    await accounts.fetchAccounts()
  } catch (e) {
    system.notify(getActionErrorMessage('刷新账号数据', e), 'error')
  }
}

const checkReplies = async () => {
  try {
    await system.checkReplies()
  } catch (e) {
    system.notify(getActionErrorMessage('同步回复状态', e), 'error')
  }
}

const runFollowups = async () => {
  if (!system.pageRunning) {
    system.notify('系统未启动或已暂停，无法执行续跟任务', 'warn')
    return
  }
  try {
    followupSubmitting.value = true
    const preview = await system.previewFollowups()
    const ready = Number(preview.ready_count || 0)
    const total = Number(preview.total_candidates || 0)
    if (!ready) {
      system.notify(preview.message || '暂无满足条件的续跟对象', 'info')
      return
    }
    const confirmed = window.confirm(`本次预计执行 ${ready} 条续跟任务（候选 ${total} 条）。是否继续？`)
    if (!confirmed) {
      return
    }
    const trigger = await system.runFollowups()
    const runId = Number(trigger.run_id || 0)
    system.notify('续跟任务已提交，正在执行', 'info')
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      const status = await system.getFollowupRunStatus()
      if (Number(status.run_id || 0) !== runId) continue
      if (status.running) continue
      const summary = status.summary || {}
      system.notify(summary.message || `续跟完成：发送 ${summary.sent || 0} 条`, 'success')
      await Promise.all([system.refreshStats(), accounts.fetchAccounts()])
      return
    }
    system.notify('续跟任务仍在执行，可在实时日志查看进度', 'info')
  } catch (e) {
    system.notify(formatFollowupSubmitError(e), 'error')
  } finally {
    followupSubmitting.value = false
  }
}

const formatFollowupSubmitError = (error) => {
  return getActionErrorMessage('提交续跟任务', error, '续跟任务提交未完成，请稍后重试')
}

const progressWidth = (acc) => {
  const limit = Number(acc?.daily_limit_today || 0) || 1
  const sent = Number(acc?.today_sent || 0) || 0
  return `${Math.min(100, (sent / limit) * 100)}%`
}

const formatCooldown = (value) => {
  if (!value) return '无冷却'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  if (date.getTime() <= Date.now()) return '冷却结束'
  return `冷却至 ${date.toLocaleTimeString()}`
}

const formatReplyTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

const healthColor = (score) => {
  const value = Number(score ?? 100)
  if (value < 20) return '#ef4444'
  if (value < 40) return '#f59e0b'
  return 'var(--text-2)'
}

const funnelCards = computed(() => [
  { label: '未联系', value: system.stats.funnel?.pending || 0, color: 'var(--text-1)' },
  { label: '已联系', value: system.stats.funnel?.contacted || 0, color: '#77b7ff' },
  { label: '已回复', value: system.stats.funnel?.replied || 0, color: '#62d99b' },
  { label: '我来处理', value: system.stats.funnel?.manual_takeover || 0, color: '#f59e0b' },
])

const trendOption = computed(() => {
  const days = []
  const sentMap = {}

  const today = new Date()
  for (let i = 6; i >= 0; i -= 1) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    days.push(key)
    sentMap[key] = 0
  }

  for (const log of system.logs) {
    if (log.status !== 'sent') continue
    const ts = String(log.timestamp || '')
    const key = ts.slice(0, 10)
    if (key in sentMap) {
      sentMap[key] += 1
    }
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: chartPalette.value.tooltipBg,
      borderColor: chartPalette.value.tooltipBorder,
      textStyle: { color: chartPalette.value.tooltipText, fontSize: 12 },
    },
    grid: { top: 20, left: 24, right: 16, bottom: 24 },
    xAxis: {
      type: 'category',
      data: days.map((d) => d.slice(5)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chartPalette.value.label, fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: chartPalette.value.split } },
      axisLabel: { color: chartPalette.value.label, fontSize: 11 }
    },
    series: [{
      name: '发送量',
      type: 'line',
      smooth: 0.4,
      data: days.map((d) => sentMap[d]),
      symbolSize: 6,
      symbol: 'circle',
      lineStyle: { color: chartPalette.value.line, width: 2 },
      itemStyle: { color: chartPalette.value.line, borderWidth: 2, borderColor: chartPalette.value.dotBorder },
      areaStyle: { color: chartPalette.value.area }
    }]
  }
})

onMounted(async () => {
  await reloadAccounts()
})
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.dashboard-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 18px;
  padding: 22px;
}

.dashboard-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.dashboard-hero-copy h2 {
  margin-top: 10px;
  font-size: clamp(34px, 5vw, 54px);
  line-height: 0.98;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: var(--text-1);
}

.dashboard-hero-copy p {
  margin-top: 14px;
  max-width: 620px;
  color: var(--text-3);
  font-size: 14px;
  line-height: 1.75;
}

.dashboard-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.dashboard-status {
  padding: 18px;
}

.dashboard-status-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dashboard-status-time {
  color: var(--text-3);
  font-size: 12px;
}

.dashboard-status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.dashboard-status-grid div {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
}

.dashboard-status-grid span,
.funnel-card span {
  display: block;
  color: var(--text-4);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.dashboard-status-grid strong,
.funnel-card strong {
  display: block;
  margin-top: 10px;
  color: var(--text-1);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.dashboard-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.dashboard-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(360px, 0.8fr);
  gap: 18px;
}

.dashboard-side-stack,
.dashboard-log-panel {
  min-height: 0;
}

.dashboard-side-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.dashboard-panel {
  padding: 18px;
}

.dashboard-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.account-list,
.reply-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.account-card,
.reply-card {
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
}

.account-card-top,
.reply-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.account-name,
.reply-card strong {
  color: var(--text-1);
  font-size: 14px;
  font-weight: 700;
}

.account-id,
.reply-card-head span,
.reply-meta {
  color: var(--text-4);
  font-size: 11px;
}

.account-progress-meta,
.account-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  color: var(--text-3);
  font-size: 11px;
}

.account-progress-track {
  height: 8px;
  margin-top: 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.account-progress-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(119, 183, 255, 0.5), rgba(98, 217, 155, 0.95));
}

.reply-preview {
  margin-top: 10px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.6;
}

.dashboard-empty {
  color: var(--text-3);
  font-size: 13px;
}

.dashboard-chart-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 18px;
}

.funnel-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.funnel-card {
  min-height: 132px;
  padding: 16px;
}

.trend-chart {
  height: 300px;
}

@media (max-width: 1280px) {
  .dashboard-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .dashboard-hero,
  .dashboard-main-grid,
  .dashboard-chart-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 840px) {
  .dashboard-stats,
  .funnel-grid,
  .dashboard-status-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .dashboard-stats,
  .funnel-grid,
  .dashboard-status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
