<template>
  <section class="projects-page">
    <div class="projects-hero card">
      <div class="projects-hero-copy">
        <div class="hero-kicker">Project Control Center</div>
        <h2>项目管理面板</h2>
        <div class="hero-actions">
          <button class="btn btn-ghost" @click="reload">刷新列表</button>
          <button class="btn btn-primary" @click="openCreate">创建项目</button>
        </div>
      </div>

      <div class="projects-hero-metrics">
        <div v-for="item in summaryCards" :key="item.label" class="hero-metric-card">
          <span>{{ item.label }}</span>
          <strong :style="{ color: item.color || 'var(--text-1)' }">{{ item.value }}</strong>
          <small v-if="item.note">{{ item.note }}</small>
        </div>
      </div>
    </div>

    <div v-if="system.status.circuit_breaker_tripped" class="breaker-banner">
      <div>
        <div class="breaker-title">系统当前处于熔断状态</div>
        <div class="breaker-copy">
          {{ system.status.circuit_breaker_reason || '请先核查异常账号和发送负载，再决定是否继续执行。' }}
        </div>
      </div>
      <button class="btn btn-danger" @click="resetBreaker">重置熔断状态</button>
    </div>

    <div class="insight-grid">
      <div class="card insight-card">
        <div class="insight-head">
          <div>
            <div class="section-title">项目状态分布</div>
          </div>
          <span class="pill">总计 {{ projects.length }} 个项目</span>
        </div>
        <v-chart class="insight-chart" :option="statusDonutOption" autoresize />
      </div>

      <div class="card insight-card">
        <div class="insight-head">
          <div>
            <div class="section-title">回复率对比</div>
          </div>
          <span class="pill">Top {{ topReplyProjects.length }}</span>
        </div>
        <v-chart class="insight-chart" :option="replyBarOption" autoresize />
      </div>
    </div>

    <div class="card filter-bar">
      <div class="filter-tabs">
        <button
          v-for="status in projectFilters"
          :key="status.value"
          class="filter-tab"
          :class="activeStatus === status.value ? 'filter-tab-active' : ''"
          @click="activeStatus = status.value"
        >
          {{ status.label }}
        </button>
      </div>
      <div class="filter-meta">当前展示 {{ filteredProjects.length }} 个项目</div>
    </div>

    <div v-if="loading" class="project-grid">
      <div v-for="index in 4" :key="index" class="card project-card skeleton project-skeleton" />
    </div>

    <div v-else-if="!filteredProjects.length" class="card empty-card">
      <div class="empty-title">还没有项目</div>
      <div class="empty-copy">
        请先创建项目，并绑定目标分组、账号和触达序列。
      </div>
      <button class="btn btn-primary" @click="openCreate">创建项目</button>
    </div>

    <div v-else class="project-grid">
      <article v-for="project in filteredProjects" :key="project.id" class="card project-card">
        <div class="project-top">
          <div class="project-copy">
            <div class="project-title-row">
              <h3>{{ project.name }}</h3>
              <span class="project-status" :style="statusBadgeStyle(project.status)">{{ statusLabel(project.status) }}</span>
            </div>
            <div class="project-meta">
              <span v-if="project.client_group">归属 {{ project.client_group }}</span>
              <span v-if="project.segment_name">目标分组 {{ project.segment_name }}</span>
              <span v-if="project.last_run_at">最近执行 {{ formatTime(project.last_run_at) }}</span>
            </div>
            <p v-if="project.description" class="project-description">{{ project.description }}</p>
          </div>

          <div class="project-tags">
            <span v-if="project.warming_enabled" class="project-tag">前置互动</span>
            <span class="project-tag">{{ sequenceSummary(project) }}</span>
          </div>
        </div>

        <div class="project-stats">
          <div class="project-stat">
            <span>待发送</span>
            <strong>{{ project.pending_count || 0 }}</strong>
          </div>
          <div class="project-stat">
            <span>已发送</span>
            <strong>{{ project.sent_count || 0 }}</strong>
          </div>
          <div class="project-stat">
            <span>已回复</span>
            <strong class="text-success">{{ project.replied_count || 0 }}</strong>
          </div>
          <div class="project-stat">
            <span>回复率</span>
            <strong>{{ project.reply_rate || 0 }}%</strong>
          </div>
        </div>

        <div class="project-progress-block">
          <div class="project-progress-head">
            <span>项目进度</span>
            <strong>{{ project.progress || 0 }}%</strong>
          </div>
          <div class="project-progress-track">
            <div class="project-progress-bar" :style="{ width: `${project.progress || 0}%` }" />
          </div>
          <div class="project-progress-foot">
            <span>总目标 {{ project.total_targets || 0 }}</span>
            <span>已完成 {{ project.completed_count || 0 }}</span>
          </div>
        </div>

        <div class="project-actions">
          <button
            v-if="project.status === 'ready' || project.status === 'paused'"
            class="btn btn-primary"
            :disabled="project.pending_count <= 0"
            @click="startProject(project.id)"
          >
            {{ project.status === 'paused' ? '恢复执行' : '启动执行' }}
          </button>
          <button
            v-if="project.status === 'running'"
            class="btn btn-secondary"
            @click="pauseProject(project.id)"
          >
            暂停执行
          </button>
          <button class="btn btn-ghost" @click="viewDetail(project.id)">进入详情</button>
        </div>
      </article>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @click.self="closeCreate">
      <div class="modal-box create-modal">
        <div class="create-head">
          <div>
            <div class="hero-kicker">Create Project</div>
            <h3>创建项目</h3>
          </div>
          <button class="btn btn-ghost" @click="closeCreate">关闭</button>
        </div>

        <div class="create-grid">
          <div class="form-field">
            <label>项目名称 *</label>
            <input v-model="form.name" class="input" placeholder="如：Nado 3月 KOL 首轮触达" />
          </div>

          <div class="form-field">
            <label>项目归属 *</label>
            <input v-model="form.client_group" class="input" placeholder="如：Nado / Lighter" />
          </div>

          <div class="form-field form-field-wide">
            <label>项目描述</label>
            <textarea v-model="form.description" class="input h-24" placeholder="简要写一下发送对象、目标和当前阶段。" />
          </div>

          <div class="form-field">
            <label>选择目标分组 *</label>
            <select v-model="form.segment_id" class="input">
              <option value="">请选择目标分组</option>
              <option v-for="seg in segments" :key="seg.id" :value="seg.id">
                {{ seg.name }}（{{ seg.count || 0 }}）
              </option>
            </select>
          </div>

          <div class="form-field">
            <label>第 1 步模板</label>
            <select v-model="form.sequence_step_1_template_id" class="input">
              <option value="">使用默认第 1 步模板</option>
              <option v-for="tpl in sequenceStep1Templates" :key="tpl.id" :value="tpl.id">
                {{ tpl.description || tpl.content.slice(0, 30) }}
              </option>
            </select>
          </div>

          <div class="card-soft form-toggle-block form-field-wide">
            <div class="toggle-row">
              <label class="toggle-line">
                <input v-model="form.warming_enabled" type="checkbox" />
                <span>项目启动前执行前置互动</span>
              </label>
            </div>
            <div class="sequence-grid">
              <div class="sequence-card">
                <div class="sequence-card-head">
                  <strong>第 2 步</strong>
                  <label class="toggle-line">
                    <input v-model="form.sequence_step_2_enabled" type="checkbox" />
                    <span>启用</span>
                  </label>
                </div>
                <select v-model="form.sequence_step_2_template_id" class="input" :disabled="!form.sequence_step_2_enabled">
                  <option value="">使用默认第 2 步模板</option>
                  <option v-for="tpl in sequenceStep2Templates" :key="tpl.id" :value="tpl.id">
                    {{ tpl.description || tpl.content.slice(0, 30) }}
                  </option>
                </select>
                <input
                  v-model.number="form.sequence_step_2_delay_days"
                  class="input"
                  type="number"
                  min="1"
                  :disabled="!form.sequence_step_2_enabled"
                  placeholder="延迟天数"
                />
              </div>

              <div class="sequence-card">
                <div class="sequence-card-head">
                  <strong>第 3 步</strong>
                  <label class="toggle-line">
                    <input v-model="form.sequence_step_3_enabled" type="checkbox" />
                    <span>启用</span>
                  </label>
                </div>
                <select v-model="form.sequence_step_3_template_id" class="input" :disabled="!form.sequence_step_3_enabled">
                  <option value="">使用默认第 3 步模板</option>
                  <option v-for="tpl in sequenceStep3Templates" :key="tpl.id" :value="tpl.id">
                    {{ tpl.description || tpl.content.slice(0, 30) }}
                  </option>
                </select>
                <input
                  v-model.number="form.sequence_step_3_delay_days"
                  class="input"
                  type="number"
                  min="1"
                  :disabled="!form.sequence_step_3_enabled"
                  placeholder="延迟天数"
                />
              </div>
            </div>
          </div>

          <div class="form-field form-field-wide">
            <div class="account-picker-head">
              <label>选择发送账号 *</label>
              <span>仅展示状态正常的账号</span>
            </div>
            <div class="account-picker">
              <label v-for="acc in normalAccounts" :key="acc.record_id" class="account-option">
                <input v-model="form.account_ids" type="checkbox" :value="acc.record_id" />
                <div class="account-option-copy">
                  <div>{{ acc.twitter_username || acc.profile_id }}</div>
                  <small>{{ acc.profile_id }} · 健康分 {{ acc.health_score ?? 100 }} · 当日 {{ acc.today_sent || 0 }}/{{ acc.daily_limit_today || 0 }}</small>
                </div>
              </label>
            </div>
          </div>
        </div>

        <div class="create-actions">
          <button class="btn btn-ghost" @click="closeCreate">取消</button>
          <button class="btn btn-primary" :disabled="submitting || !canSubmit" @click="submitCreate">
            {{ submitting ? '创建中...' : '创建项目' }}
          </button>
        </div>
      </div>
    </div>

    <SecondaryScreenShell
      :open="!!detailProjectId"
      eyebrow="Project Detail"
      :title="detailTitle"
      @close="closeDetail"
    >
      <template #actions>
        <span class="pill" v-if="currentProject">
          <span class="pill-dot" :style="{ background: statusBadgeStyle(currentProject.project.status).color }" />
          {{ statusLabel(currentProject.project.status) }}
        </span>
      </template>

      <div v-if="detailLoading" class="detail-skeleton-grid">
        <div v-for="index in 5" :key="index" class="card skeleton detail-skeleton-card" />
      </div>

      <template v-else-if="currentProject">
        <div class="detail-summary-grid">
          <div class="metric-card detail-summary-card">
            <span>待发送</span>
            <strong>{{ currentProject.stats.pending_count || 0 }}</strong>
          </div>
          <div class="metric-card detail-summary-card">
            <span>已发送</span>
            <strong>{{ currentProject.stats.sent_count || 0 }}</strong>
          </div>
          <div class="metric-card detail-summary-card">
            <span>已回复</span>
            <strong class="text-success">{{ currentProject.stats.replied_count || 0 }}</strong>
          </div>
          <div class="metric-card detail-summary-card">
            <span>人工处理</span>
            <strong>{{ currentProject.stats.manual_takeover_count || 0 }}</strong>
          </div>
          <div class="metric-card detail-summary-card">
            <span>已完成</span>
            <strong>{{ currentProject.stats.completed_count || 0 }}</strong>
          </div>
        </div>

        <div class="detail-main-grid">
          <div class="detail-main-left">
            <div class="card detail-panel">
              <div class="detail-panel-head">
                <div>
                  <div class="section-title">项目配置</div>
                </div>
              </div>
              <div class="detail-config-grid">
                <div>
                  <span>项目归属</span>
                  <strong>{{ currentProject.project.client_group || '-' }}</strong>
                </div>
                <div>
                  <span>目标分组</span>
                  <strong>{{ currentProject.project.segment_name || '-' }}</strong>
                </div>
                <div>
                  <span>第 1 步模板</span>
                  <strong>{{ templateName(currentProject.project.sequence_step_1_template_id, '默认第 1 步模板') }}</strong>
                </div>
                <div>
                  <span>第 2 步</span>
                  <strong>{{ currentProject.project.sequence_step_2_enabled ? `${templateName(currentProject.project.sequence_step_2_template_id, '默认第 2 步模板')} · ${currentProject.project.sequence_step_2_delay_days} 天后` : '未启用' }}</strong>
                </div>
                <div>
                  <span>第 3 步</span>
                  <strong>{{ currentProject.project.sequence_step_3_enabled ? `${templateName(currentProject.project.sequence_step_3_template_id, '默认第 3 步模板')} · ${currentProject.project.sequence_step_3_delay_days} 天后` : '未启用' }}</strong>
                </div>
                <div>
                  <span>前置互动</span>
                  <strong>{{ currentProject.project.warming_enabled ? '已启用' : '未启用' }}</strong>
                </div>
                <div>
                  <span>触达序列</span>
                  <strong>{{ sequenceSummary(currentProject.project) }}</strong>
                </div>
                <div>
                  <span>创建时间</span>
                  <strong>{{ formatTime(currentProject.project.created_at) }}</strong>
                </div>
                <div>
                  <span>总目标</span>
                  <strong>{{ currentProject.project.total_targets || 0 }}</strong>
                </div>
              </div>
            </div>

            <div class="card detail-panel">
              <div class="detail-panel-head">
                <div>
                  <div class="section-title">目标状态分布</div>
                </div>
              </div>
              <v-chart class="detail-chart" :option="detailStatusOption" autoresize />
            </div>
          </div>

          <div class="detail-main-right">
            <div class="card detail-panel">
              <div class="detail-panel-head">
                <div>
                  <div class="section-title">项目账号</div>
                </div>
                <span class="pill">{{ currentProject.accounts.length }} 个</span>
              </div>
              <div class="detail-account-list">
                <div v-for="acc in currentProject.accounts" :key="acc.account_id" class="detail-account-card">
                  <div>{{ acc.twitter_username || acc.profile_id || acc.account_id }}</div>
                  <small>{{ acc.profile_id || acc.account_id }} · 状态 {{ acc.status || '未知' }} · 优先级 {{ acc.priority ?? 0 }}</small>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card detail-panel">
          <div class="detail-panel-head">
            <div>
              <div class="section-title">项目目标</div>
            </div>
          </div>

          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>状态</th>
                  <th>归属</th>
                  <th>触达轮次</th>
                  <th>发送账号</th>
                  <th>最近更新时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="target in currentProject.targets.slice(0, 30)" :key="target.id">
                  <td style="color: var(--text-1)">@{{ target.twitter_username }}</td>
                  <td><span :class="targetStatusClass(target.status)">{{ target.status }}</span></td>
                  <td>{{ target.client_group || currentProject.project.client_group || '-' }}</td>
                  <td>{{ target.contact_count || 0 }}</td>
                  <td>{{ target.sent_by || '-' }}</td>
                  <td>{{ formatTime(target.updated_at || target.sent_time) }}</td>
                </tr>
                <tr v-if="!currentProject.targets.length">
                  <td colspan="6" class="py-8 text-center">项目中暂无已同步目标</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <template #footer>
        <button class="btn btn-ghost" @click="closeDetail">返回项目列表</button>
        <button
          v-if="currentProject && (currentProject.project.status === 'ready' || currentProject.project.status === 'paused')"
          class="btn btn-primary"
          :disabled="currentProject.stats.pending_count <= 0"
          @click="startProject(currentProject.project.id)"
        >
          {{ currentProject.project.status === 'paused' ? '恢复执行' : '启动执行' }}
        </button>
        <button
          v-if="currentProject && currentProject.project.status === 'running'"
          class="btn btn-secondary"
          @click="pauseProject(currentProject.project.id)"
        >
          暂停执行
        </button>
      </template>
    </SecondaryScreenShell>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'

import api from '../api'
import SecondaryScreenShell from '../components/SecondaryScreenShell.vue'
import { useTheme } from '../composables/useTheme'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

use([CanvasRenderer, PieChart, BarChart, GridComponent, LegendComponent, TooltipComponent])

const route = useRoute()
const router = useRouter()
const system = useSystemStore()
const { theme } = useTheme()

const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const projects = ref([])
const segments = ref([])
const templates = ref([])
const accounts = ref([])
const showCreate = ref(false)
const currentProject = ref(null)
const activeStatus = ref('all')

const form = ref(defaultForm())

function defaultForm() {
  return {
    name: '',
    client_group: '',
    description: '',
    segment_id: '',
    template_id: '',
    followup_template_id: '',
    sequence_step_1_template_id: '',
    sequence_step_2_template_id: '',
    sequence_step_3_template_id: '',
    sequence_step_2_delay_days: 3,
    sequence_step_3_delay_days: 5,
    sequence_step_2_enabled: true,
    sequence_step_3_enabled: true,
    account_ids: [],
    warming_enabled: false,
    followup_enabled: true,
  }
}

const projectFilters = [
  { label: '全部', value: 'all' },
  { label: '待启动', value: 'ready' },
  { label: '进行中', value: 'running' },
  { label: '暂停中', value: 'paused' },
  { label: '已完成', value: 'completed' },
]

const detailProjectId = computed(() => route.params.id ? String(route.params.id) : '')

const normalAccounts = computed(() => accounts.value.filter((item) => item.status === '正常' || !item.status))
const sequenceStep1Templates = computed(() => templates.value.filter((tpl) => (tpl.template_type || 'sequence_step_1') === 'sequence_step_1'))
const sequenceStep2Templates = computed(() => templates.value.filter((tpl) => (tpl.template_type || 'sequence_step_1') === 'sequence_step_2'))
const sequenceStep3Templates = computed(() => templates.value.filter((tpl) => (tpl.template_type || 'sequence_step_1') === 'sequence_step_3'))

const filteredProjects = computed(() => {
  if (activeStatus.value === 'all') return projects.value
  return projects.value.filter((item) => item.status === activeStatus.value)
})

const summaryCards = computed(() => {
  const total = projects.value.length
  const running = projects.value.filter((item) => item.status === 'running').length
  const pending = projects.value.reduce((sum, item) => sum + Number(item.pending_count || 0), 0)
  const replied = projects.value.reduce((sum, item) => sum + Number(item.replied_count || 0), 0)
  return [
    { label: '项目总数', value: total, note: '' },
    { label: '进行中项目', value: running, note: '', color: running ? 'var(--accent)' : 'var(--text-1)' },
    { label: '待发送目标', value: pending, note: '' },
    { label: '累计回复', value: replied, note: '', color: replied ? 'var(--accent)' : 'var(--text-1)' },
  ]
})

const canSubmit = computed(() => form.value.name.trim() && form.value.client_group.trim() && form.value.segment_id && form.value.account_ids.length > 0)

const topReplyProjects = computed(() => {
  return [...projects.value]
    .sort((a, b) => Number(b.reply_rate || 0) - Number(a.reply_rate || 0))
    .slice(0, 6)
})

const detailTitle = computed(() => currentProject.value?.project?.name || '项目详情')

const chartPalette = computed(() => {
  if (theme.value === 'light') {
    return {
      textSoft: '#7b6f62',
      textMuted: '#a99a88',
      split: 'rgba(65,53,35,0.08)',
      panel: '#fbf7f1',
    }
  }
  return {
    textSoft: '#9a9082',
    textMuted: '#655d53',
    split: 'rgba(255,255,255,0.05)',
    panel: '#171613',
  }
})

const statusDonutOption = computed(() => {
  const buckets = [
    { label: '待启动', value: projects.value.filter((item) => item.status === 'ready').length, color: '#77b7ff' },
    { label: '进行中', value: projects.value.filter((item) => item.status === 'running').length, color: '#62d99b' },
    { label: '暂停中', value: projects.value.filter((item) => item.status === 'paused').length, color: '#f59e0b' },
    { label: '已完成', value: projects.value.filter((item) => item.status === 'completed').length, color: '#c084fc' },
  ]
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: {
      bottom: 0,
      icon: 'circle',
      textStyle: { color: chartPalette.value.textSoft },
    },
    series: [{
      type: 'pie',
      radius: ['58%', '76%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: false,
      label: { show: false },
      itemStyle: { borderWidth: 3, borderColor: chartPalette.value.panel },
      data: buckets.map((item) => ({ value: item.value, name: item.label, itemStyle: { color: item.color } })),
    }],
  }
})

const replyBarOption = computed(() => {
  return {
    backgroundColor: 'transparent',
    grid: { left: 12, right: 12, top: 10, bottom: 16, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: chartPalette.value.split } },
      axisLabel: { color: chartPalette.value.textMuted },
    },
    yAxis: {
      type: 'category',
      data: topReplyProjects.value.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chartPalette.value.textSoft, width: 110, overflow: 'truncate' },
    },
    series: [{
      type: 'bar',
      data: topReplyProjects.value.map((item) => ({
        value: Number(item.reply_rate || 0),
        itemStyle: { color: '#62d99b', borderRadius: [0, 8, 8, 0] },
      })),
      barWidth: 12,
    }],
  }
})

const detailStatusOption = computed(() => {
  const targets = currentProject.value?.targets || []
  const counts = new Map()
  for (const item of targets) {
    const key = item.status || '未知'
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: {
      bottom: 0,
      icon: 'circle',
      textStyle: { color: chartPalette.value.textSoft },
    },
    series: [{
      type: 'pie',
      radius: ['50%', '72%'],
      center: ['50%', '42%'],
      label: { color: chartPalette.value.textSoft },
      itemStyle: { borderWidth: 3, borderColor: chartPalette.value.panel },
      data: Array.from(counts.entries()).map(([name, value], index) => ({
        name,
        value,
        itemStyle: {
          color: ['#77b7ff', '#62d99b', '#f59e0b', '#c084fc', '#fb7185', '#94a3b8'][index % 6],
        },
      })),
    }],
  }
})

const statusLabel = (status) => {
  const map = {
    ready: '待启动',
    running: '进行中',
    paused: '暂停中',
    completed: '已完成',
    archived: '已归档',
  }
  return map[status] || status || '未知'
}

const statusBadgeStyle = (status) => {
  const map = {
    ready: { color: '#77b7ff', background: 'rgba(119,183,255,0.14)', borderColor: 'rgba(119,183,255,0.18)' },
    running: { color: '#62d99b', background: 'rgba(98,217,155,0.14)', borderColor: 'rgba(98,217,155,0.18)' },
    paused: { color: '#f59e0b', background: 'rgba(245,158,11,0.14)', borderColor: 'rgba(245,158,11,0.18)' },
    completed: { color: '#c084fc', background: 'rgba(192,132,252,0.14)', borderColor: 'rgba(192,132,252,0.18)' },
    archived: { color: 'var(--text-3)', background: 'rgba(148,163,184,0.12)', borderColor: 'rgba(148,163,184,0.18)' },
  }
  return map[status] || { color: 'var(--text-2)', background: 'rgba(148,163,184,0.12)', borderColor: 'rgba(148,163,184,0.18)' }
}

const targetStatusClass = (status) => {
  const map = {
    '待发送': 'text-blue-300',
    '已发送': 'text-sky-300',
    '已回复': 'text-emerald-300',
    '人工接管': 'text-amber-300',
    '人工处理': 'text-amber-300',
    '完成': 'text-violet-300',
    '跳过': 'text-orange-300',
    '不可DM': 'text-rose-300',
  }
  return map[status] || 'text-zinc-400'
}

const formatTime = (value) => {
  if (!value) return '-'
  const dt = new Date(value)
  return Number.isNaN(dt.getTime()) ? String(value) : dt.toLocaleString()
}

const templateName = (id, fallback = '-') => {
  if (!id) return fallback
  const found = templates.value.find((tpl) => tpl.id === id)
  if (!found) return id
  return found.description || found.content?.slice(0, 24) || id
}

const sequenceSummary = (project) => {
  const stepCount = 1 + (project?.sequence_step_2_enabled ? 1 : 0) + (project?.sequence_step_3_enabled ? 1 : 0)
  return `${stepCount} 步触达`
}

const openCreate = () => {
  form.value = defaultForm()
  showCreate.value = true
}

const closeCreate = () => {
  showCreate.value = false
}

const closeDetail = () => {
  router.push('/projects')
}

const loadProjects = async () => {
  loading.value = true
  try {
    const { data } = await api.get('/projects')
    projects.value = data.items || data.projects || []
  } catch (e) {
    system.notify(getActionErrorMessage('加载项目列表', e), 'error')
  } finally {
    loading.value = false
  }
}

const loadOptions = async () => {
  try {
    const [segmentsRes, templatesRes, accountsRes] = await Promise.all([
      api.get('/segments'),
      api.get('/templates'),
      api.get('/accounts'),
    ])
    segments.value = segmentsRes.data || []
    templates.value = templatesRes.data.templates || []
    accounts.value = accountsRes.data || []
  } catch (e) {
    system.notify(getActionErrorMessage('加载项目配置项', e), 'error')
  }
}

const fetchProjectDetail = async (projectId) => {
  detailLoading.value = true
  try {
    const { data } = await api.get(`/projects/${projectId}`)
    currentProject.value = data
  } catch (e) {
    currentProject.value = null
    system.notify(getActionErrorMessage('加载项目详情', e), 'error')
  } finally {
    detailLoading.value = false
  }
}

const reload = async () => {
  await Promise.all([loadProjects(), loadOptions()])
  if (detailProjectId.value) {
    await fetchProjectDetail(detailProjectId.value)
  }
}

const submitCreate = async () => {
  if (!canSubmit.value) {
    system.notify('请先补全项目名称、归属、目标分组和账号', 'warn')
    return
  }
  submitting.value = true
  try {
    await api.post('/projects', {
      ...form.value,
      template_id: form.value.sequence_step_1_template_id,
      followup_template_id: form.value.sequence_step_2_template_id,
      followup_enabled: !!(form.value.sequence_step_2_enabled || form.value.sequence_step_3_enabled),
    })
    system.notify('项目创建成功', 'success')
    closeCreate()
    await loadProjects()
  } catch (e) {
    system.notify(getActionErrorMessage('创建项目', e), 'error')
  } finally {
    submitting.value = false
  }
}

const startProject = async (projectId) => {
  try {
    const { data } = await api.post(`/projects/${projectId}/start`)
    system.notify(data.message || '项目已启动', 'success')
    await Promise.all([loadProjects(), system.refreshStatus()])
    if (String(detailProjectId.value) === String(projectId)) {
      await fetchProjectDetail(projectId)
    }
  } catch (e) {
    system.notify(getActionErrorMessage('启动项目', e), 'error')
  }
}

const pauseProject = async (projectId) => {
  try {
    const { data } = await api.post(`/projects/${projectId}/pause`)
    system.notify(data.message || '项目已暂停执行', 'warn')
    await loadProjects()
    if (String(detailProjectId.value) === String(projectId)) {
      await fetchProjectDetail(projectId)
    }
  } catch (e) {
    system.notify(getActionErrorMessage('暂停项目', e), 'error')
  }
}

const viewDetail = async (projectId) => {
  await router.push(`/projects/${projectId}`)
}

const resetBreaker = async () => {
  try {
    await system.resetCircuitBreaker('project_page')
  } catch (e) {
    system.notify(getActionErrorMessage('重置熔断状态', e), 'error')
  }
}

watch(detailProjectId, async (projectId) => {
  if (!projectId) {
    currentProject.value = null
    return
  }
  await fetchProjectDetail(projectId)
}, { immediate: true })

onMounted(async () => {
  await reload()
})
</script>

<style scoped>
.projects-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.projects-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
  gap: 18px;
  padding: 22px;
}

.hero-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.projects-hero-copy h2,
.create-head h3 {
  margin-top: 10px;
  font-size: clamp(34px, 5vw, 56px);
  line-height: 0.98;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: var(--text-1);
}

.create-head h3 {
  font-size: 32px;
}

.projects-hero-copy p,
.create-head p {
  margin-top: 14px;
  max-width: 620px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-3);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

.projects-hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.hero-metric-card {
  display: flex;
  min-height: 150px;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.015));
}

.hero-metric-card span,
.detail-summary-card span,
.project-stat span,
.detail-config-grid span {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-metric-card strong,
.detail-summary-card strong {
  font-size: 34px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.hero-metric-card small {
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.6;
}

.breaker-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-radius: 24px;
  border: 1px solid rgba(248, 113, 113, 0.18);
  background: rgba(248, 113, 113, 0.08);
  padding: 18px 20px;
}

.breaker-title {
  color: #fecaca;
  font-size: 14px;
  font-weight: 700;
}

.breaker-copy {
  margin-top: 6px;
  color: rgba(254, 226, 226, 0.82);
  font-size: 13px;
  line-height: 1.6;
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.insight-card,
.detail-panel {
  padding: 18px;
}

.insight-head,
.detail-panel-head,
.create-head,
.account-picker-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.insight-chart,
.detail-chart {
  height: 290px;
  margin-top: 8px;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
}

.filter-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-tab {
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-3);
  font-size: 12px;
  font-weight: 600;
  transition: all 0.18s ease;
}

.filter-tab:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.035);
}

.filter-tab-active {
  color: var(--text-1);
  border-color: rgba(98, 217, 155, 0.18);
  background: rgba(98, 217, 155, 0.08);
}

.filter-meta {
  color: var(--text-3);
  font-size: 12px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.project-card {
  display: flex;
  min-height: 320px;
  flex-direction: column;
  padding: 20px;
}

.project-skeleton {
  min-height: 320px;
}

.project-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.project-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.project-title-row h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.03em;
}

.project-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-top: 10px;
  color: var(--text-4);
  font-size: 12px;
}

.project-description {
  margin-top: 12px;
  color: var(--text-3);
  font-size: 13px;
  line-height: 1.7;
}

.project-status,
.project-tag {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 11px;
  font-weight: 700;
}

.project-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.project-tag {
  color: var(--text-2);
  border-color: var(--border);
  background: rgba(255, 255, 255, 0.03);
}

.project-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 18px;
}

.project-stat {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
}

.project-stat strong {
  display: block;
  margin-top: 10px;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--text-1);
}

.text-success {
  color: var(--accent);
}

.project-progress-block {
  margin-top: 18px;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.project-progress-head,
.project-progress-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.project-progress-head span,
.project-progress-foot {
  color: var(--text-3);
}

.project-progress-head strong {
  color: var(--text-1);
}

.project-progress-track {
  position: relative;
  height: 10px;
  margin-top: 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  overflow: hidden;
}

.project-progress-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(98, 217, 155, 0.42), rgba(98, 217, 155, 0.92));
  box-shadow: 0 0 20px rgba(98, 217, 155, 0.22);
}

.project-progress-foot {
  margin-top: 10px;
}

.project-actions,
.create-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
  padding-top: 18px;
}

.empty-card {
  display: flex;
  min-height: 260px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 24px;
  text-align: center;
}

.empty-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.empty-copy {
  max-width: 520px;
  color: var(--text-3);
  font-size: 14px;
  line-height: 1.7;
}

.create-modal {
  max-width: min(980px, calc(100vw - 36px));
}

.create-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 20px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-field label {
  color: var(--text-3);
  font-size: 12px;
  font-weight: 600;
}

.form-field-wide {
  grid-column: 1 / -1;
}

.form-toggle-block {
  padding: 16px;
}

.toggle-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}

.sequence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.sequence-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
}

.sequence-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sequence-card-head strong {
  color: var(--text-1);
  font-size: 13px;
  font-weight: 700;
}

.toggle-line {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text-2);
  font-size: 13px;
}

.toggle-line input,
.account-option input {
  accent-color: var(--accent);
}

.account-picker-head span {
  color: var(--text-4);
  font-size: 11px;
}

.account-picker {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.account-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.025);
}

.account-option-copy {
  min-width: 0;
}

.account-option-copy div {
  color: var(--text-1);
  font-size: 13px;
  font-weight: 600;
}

.account-option-copy small,
.detail-account-card small {
  display: block;
  margin-top: 6px;
  color: var(--text-4);
  font-size: 11px;
  line-height: 1.5;
}

.detail-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.detail-skeleton-card {
  min-height: 180px;
}

.detail-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.detail-summary-card {
  padding: 16px;
  min-height: 120px;
}

.detail-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
  margin-top: 18px;
}

.detail-main-left,
.detail-main-right {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.detail-config-grid div {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
}

.detail-config-grid strong {
  display: block;
  margin-top: 8px;
  color: var(--text-1);
  font-size: 13px;
  line-height: 1.6;
}

.detail-account-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 18px;
}

.detail-account-card {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-1);
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 1180px) {
  .projects-hero,
  .insight-grid,
  .project-grid,
  .detail-main-grid {
    grid-template-columns: 1fr;
  }

  .detail-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 840px) {
  .projects-hero-metrics,
  .project-stats,
  .create-grid,
  .sequence-grid,
  .account-picker,
  .detail-config-grid,
  .detail-skeleton-grid {
    grid-template-columns: 1fr;
  }

  .filter-bar,
  .breaker-banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .detail-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
