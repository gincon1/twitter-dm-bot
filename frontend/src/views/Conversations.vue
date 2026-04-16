<template>
  <section class="conversations-page">
    <div class="conversation-hero card">
      <div class="conversation-hero-copy">
        <div class="conversation-kicker">Conversation Hub</div>
        <h2>会话管理</h2>
      </div>
      <div class="conversation-hero-actions">
        <button class="btn btn-ghost" @click="load">刷新</button>
        <button class="btn btn-secondary" @click="triggerCheck">普通同步</button>
        <button class="btn btn-secondary" @click="triggerCheckFull">全部同步</button>
        <button class="btn btn-secondary" :disabled="!canRunFollowups" @click="triggerFollowups">
          {{ followupSubmitting ? '执行中...' : '执行续跟任务' }}
        </button>
      </div>
    </div>

    <div class="card conversation-filters-panel">
      <div class="conversation-panel-head">
        <div>
          <div class="section-title">筛选条件</div>
        </div>
      </div>

      <div class="conversation-filters-grid">
        <select v-model="clientGroupFilter" class="input" @change="load">
          <option value="">全部归属</option>
          <option v-for="g in clientGroups" :key="g" :value="g">{{ g }}</option>
        </select>
        <select v-model="replyFilter" class="input" @change="load">
          <option value="">全部会话</option>
          <option value="1">仅已回复</option>
          <option value="0">仅待回复</option>
        </select>
        <select v-model="statusFilter" class="input" @change="load">
          <option value="">全部状态</option>
          <option value="contacted">已触达</option>
          <option value="replied">已回复</option>
          <option value="manual_takeover">人工处理</option>
          <option value="completed">已完成</option>
        </select>
        <input v-model="search" class="input" placeholder="搜索用户名 / 账号 / 包名 / 归属" @keyup.enter="load" />
      </div>
    </div>

    <div class="conversation-summary-grid">
      <div class="metric-card conversation-summary-card">
        <span>总会话数</span>
        <strong>{{ summary.total }}</strong>
      </div>
      <div class="metric-card conversation-summary-card">
        <span>已触达</span>
        <strong class="blue">{{ summary.contacted }}</strong>
      </div>
      <div class="metric-card conversation-summary-card">
        <span>已回复</span>
        <strong class="green">{{ summary.replied }}</strong>
      </div>
      <div class="metric-card conversation-summary-card">
        <span>人工处理</span>
        <strong class="amber">{{ summary.manual_takeover }}</strong>
      </div>
      <div class="metric-card conversation-summary-card">
        <span>待处理回复</span>
        <strong class="amber">{{ pendingReplies.length }}</strong>
      </div>
    </div>

    <div class="card conversation-pending-panel">
      <div class="conversation-panel-head">
        <div>
          <div class="section-title">待处理回复</div>
        </div>
        <span class="pill">{{ pendingReplies.length }} 条</span>
      </div>

      <div v-if="pendingReplies.length" class="pending-reply-grid">
        <article v-for="item in pendingReplies" :key="item.id" class="pending-reply-card">
          <div class="pending-reply-head">
            <strong>@{{ item.target_username || '-' }}</strong>
            <span>{{ formatTime(item.reply_at) }}</span>
          </div>
          <div class="pending-reply-meta">
            <span>{{ item.client_group || '未归属' }}</span>
            <span>{{ item.segment_name || '未分组' }}</span>
            <span>{{ item.account_username || item.account_profile_id || '-' }}</span>
          </div>
          <div class="pending-reply-preview">{{ item.last_reply_preview || item.last_message_preview || '-' }}</div>
          <div class="conversation-row-actions">
            <button class="btn btn-ghost btn-sm" @click="openMessages(item)">消息记录</button>
            <button class="btn btn-ghost btn-sm" @click="takeover(item)">转人工处理</button>
            <button class="btn btn-secondary btn-sm" @click="complete(item)">完成</button>
          </div>
        </article>
      </div>
      <div v-else class="dashboard-empty">暂无待处理回复</div>
    </div>

    <div v-if="clientGroupStats.length" class="card conversation-group-panel">
      <div class="conversation-panel-head">
        <div>
          <div class="section-title">各归属会话概览</div>
        </div>
      </div>

      <div class="group-grid">
        <button
          v-for="g in clientGroupStats"
          :key="g.client_group"
          class="group-card"
          :class="clientGroupFilter === g.client_group ? 'group-card-active' : ''"
          @click="toggleClientGroupFilter(g.client_group)"
        >
          <div class="group-card-head">
            <strong>{{ g.client_group }}</strong>
            <span v-if="clientGroupFilter === g.client_group">筛选中</span>
          </div>
          <div class="group-card-meta">
            <span>共 {{ g.total }}</span>
            <span class="green">回复 {{ g.replied }} ({{ replyRate(g) }})</span>
            <span v-if="g.manual_takeover" class="amber">人工处理 {{ g.manual_takeover }}</span>
          </div>
        </button>
      </div>
    </div>

    <div class="card conversation-table-panel">
      <div class="conversation-panel-head">
        <div>
          <div class="section-title">会话列表</div>
        </div>
        <span class="pill">当前 {{ conversations.length }} 条</span>
      </div>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>目标</th>
              <th>项目</th>
              <th>目标分组</th>
              <th>归属</th>
              <th>发送账号</th>
              <th>状态</th>
              <th>最后触达</th>
              <th>已发条数</th>
              <th>回复时间</th>
              <th>最新预览</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in conversations" :key="item.id">
              <td style="color: var(--text-1)">@{{ item.target_username || '-' }}</td>
              <td>
                <div style="color: var(--text-1)">{{ item.project_name || '-' }}</div>
                <div v-if="item.project_id" class="text-xs font-mono" style="color: var(--text-4)">{{ item.project_id }}</div>
              </td>
              <td>
                <span v-if="item.segment_name || item.segment_id" class="segment-chip">
                  {{ item.segment_name || item.segment_id }}
                </span>
                <span v-else class="text-xs" style="color: var(--text-4)">-</span>
              </td>
              <td>
                <div style="color: var(--text-1)">{{ item.client_group || '-' }}</div>
                <div v-if="item.client_note" class="text-xs" style="color: var(--text-4)">{{ item.client_note }}</div>
              </td>
              <td>
                <div style="color: var(--text-1)">{{ item.account_username || '-' }}</div>
                <div class="text-xs font-mono" style="color: var(--text-4)">{{ item.account_profile_id || '-' }}</div>
              </td>
              <td>
                <span class="status-chip" :style="statusStyle(item)">
                  {{ statusLabel(item) }}
                </span>
              </td>
              <td style="color: var(--text-2)">{{ formatTime(item.last_contact_time) }}</td>
              <td style="color: var(--text-2)">{{ item.contact_count || 0 }}</td>
              <td style="color: var(--text-2)">{{ formatTime(item.reply_at) }}</td>
              <td class="max-w-[320px] truncate" :title="item.last_reply_preview || item.last_message_preview" style="color: var(--text-2)">
                {{ item.last_reply_preview || item.last_message_preview || '-' }}
              </td>
              <td>
                <div class="conversation-row-actions">
                  <button class="btn btn-ghost btn-sm" @click="openMessages(item)">消息记录</button>
                  <button v-if="item.status !== 'manual_takeover'" class="btn btn-ghost btn-sm" @click="takeover(item)">转人工处理</button>
                  <button v-if="item.status !== 'completed'" class="btn btn-secondary btn-sm" @click="complete(item)">完成</button>
                  <button v-if="item.status === 'manual_takeover' || item.status === 'completed'" class="btn btn-ghost btn-sm" @click="resumeAuto(item)">恢复自动流程</button>
                </div>
              </td>
            </tr>
            <tr v-if="!conversations.length">
              <td colspan="11" class="py-8 text-center" style="color: var(--text-3)">暂无会话记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="messageDialog.open" class="modal-backdrop" @click.self="closeMessages">
      <div class="modal-box conversation-modal">
        <div class="conversation-panel-head">
          <div>
            <div class="conversation-kicker">Message Detail</div>
            <h3 class="conversation-modal-title">@{{ messageDialog.conversation?.target_username || '-' }}</h3>
            <div class="conversation-modal-meta">
              <span v-if="messageDialog.conversation?.segment_name">{{ messageDialog.conversation.segment_name }}</span>
              <span v-if="messageDialog.conversation?.project_name">{{ messageDialog.conversation.project_name }}</span>
              <span>{{ messageDialog.conversation?.client_group || '-' }}</span>
              <span>{{ messageDialog.conversation?.account_profile_id || '-' }}</span>
              <span>{{ messageDialog.messages.length }} 条消息</span>
            </div>
          </div>
          <button class="btn btn-ghost" @click="closeMessages">关闭</button>
        </div>

        <div class="conversation-modal-body">
          <div v-if="messageDialog.loading" class="dashboard-empty">正在加载消息...</div>
          <div v-else-if="!messageDialog.messages.length" class="dashboard-empty">暂无消息记录</div>
          <div v-else class="message-list">
            <div
              v-for="message in messageDialog.messages"
              :key="message.id"
              class="message-row"
              :class="message.direction === 'outbound' ? 'outbound' : 'inbound'"
            >
              <div class="message-bubble" :style="messageBubbleStyle(message)">
                <div class="message-content">{{ message.content || '-' }}</div>
                <div class="message-meta">
                  {{ message.direction === 'outbound' ? '我方发送' : '对方回复' }} · {{ formatTime(message.detected_at || message.created_at) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import api from '../api'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

const system = useSystemStore()
const conversations = ref([])
const clientGroups = ref([])
const clientGroupStats = ref([])
const pendingReplies = ref([])
const summary = ref({ total: 0, contacted: 0, replied: 0, manual_takeover: 0, completed: 0, replied_today: 0 })
const replyFilter = ref('')
const statusFilter = ref('')
const clientGroupFilter = ref('')
const search = ref('')
const messageDialog = ref({
  open: false,
  loading: false,
  conversation: null,
  messages: []
})
const followupSubmitting = ref(false)

const repliedStyle = { background: 'rgba(98,217,155,0.12)', color: '#62d99b', border: '1px solid rgba(98,217,155,0.18)' }
const pendingStyle = { background: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.18)' }
const takeoverStyle = { background: 'rgba(245,158,11,0.14)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.18)' }
const completedStyle = { background: 'rgba(192,132,252,0.14)', color: '#c084fc', border: '1px solid rgba(192,132,252,0.18)' }
const outboundBubbleStyle = { background: 'rgba(119,183,255,0.08)', border: '1px solid rgba(119,183,255,0.12)' }
const inboundBubbleStyle = { background: 'rgba(98,217,155,0.08)', border: '1px solid rgba(98,217,155,0.12)' }

const replyRate = (g) => {
  if (!g.total) return '0%'
  return Math.round((g.replied / g.total) * 100) + '%'
}

const toggleClientGroupFilter = (group) => {
  clientGroupFilter.value = clientGroupFilter.value === group ? '' : group
  load()
}

const formatTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

const statusLabel = (item) => {
  if (item.status === 'manual_takeover') return '人工处理'
  if (item.status === 'completed') return '已完成'
  if (item.has_reply || item.status === 'replied') return '已回复'
  return '已触达'
}

const statusStyle = (item) => {
  if (item.status === 'manual_takeover') return takeoverStyle
  if (item.status === 'completed') return completedStyle
  if (item.has_reply || item.status === 'replied') return repliedStyle
  return pendingStyle
}

const messageBubbleStyle = (message) => (message.direction === 'outbound' ? outboundBubbleStyle : inboundBubbleStyle)
const canRunFollowups = computed(() => system.pageRunning && !followupSubmitting.value)

const load = async () => {
  try {
    const params = { limit: 500 }
    if (replyFilter.value !== '') params.has_reply = replyFilter.value === '1'
    if (statusFilter.value) params.status = statusFilter.value
    if (clientGroupFilter.value) params.client_group = clientGroupFilter.value
    if (search.value.trim()) params.search = search.value.trim()

    const [convResp, statsResp, cgStatsResp] = await Promise.all([
      api.get('/conversations', { params }),
      api.get('/stats'),
      api.get('/conversations/by-client-group'),
    ])
    conversations.value = convResp.data || []
    summary.value = statsResp.data?.conversations || { total: 0, contacted: 0, replied: 0, manual_takeover: 0, completed: 0, replied_today: 0 }
    pendingReplies.value = statsResp.data?.pending_replies || []
    clientGroupStats.value = cgStatsResp.data || []
    clientGroups.value = clientGroupStats.value.map((g) => g.client_group).filter(Boolean)
  } catch (e) {
    system.notify(getActionErrorMessage('加载会话', e), 'error')
  }
}

const triggerCheck = async () => {
  try {
    await system.checkReplies()
    setTimeout(load, 1200)
  } catch (e) {
    system.notify(getActionErrorMessage('触发普通同步', e), 'error')
  }
}

const triggerCheckFull = async () => {
  try {
    await system.checkRepliesFull()
    setTimeout(load, 1200)
  } catch (e) {
    system.notify(getActionErrorMessage('触发全部同步', e), 'error')
  }
}

const triggerFollowups = async () => {
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
      await load()
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

const openMessages = async (item) => {
  messageDialog.value = { open: true, loading: true, conversation: item, messages: [] }
  try {
    const { data } = await api.get(`/conversations/${item.id}/messages`)
    messageDialog.value = {
      open: true,
      loading: false,
      conversation: data?.conversation || item,
      messages: data?.messages || []
    }
  } catch (e) {
    messageDialog.value.loading = false
    system.notify(getActionErrorMessage('加载消息记录', e), 'error')
  }
}

const closeMessages = () => {
  messageDialog.value = { open: false, loading: false, conversation: null, messages: [] }
}

const takeover = async (item) => {
  try {
    const note = window.prompt('可选备注：例如"已进入报价阶段"', '') || ''
    await api.post(`/conversations/${item.id}/takeover`, { note })
    system.notify('已转入人工处理', 'success')
    await load()
  } catch (e) {
    system.notify(getActionErrorMessage('转人工处理', e), 'error')
  }
}

const complete = async (item) => {
  try {
    const note = window.prompt('可选备注：例如"合作已确认"', '') || ''
    await api.post(`/conversations/${item.id}/complete`, { note })
    system.notify('会话已标记完成', 'success')
    await load()
  } catch (e) {
    system.notify(getActionErrorMessage('标记完成', e), 'error')
  }
}

const resumeAuto = async (item) => {
  try {
    await api.post(`/conversations/${item.id}/resume-auto`)
    system.notify('该会话已恢复自动流程', 'success')
    await load()
  } catch (e) {
    system.notify(getActionErrorMessage('恢复自动流程', e), 'error')
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.conversations-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.conversation-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
}

.conversation-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.conversation-hero-copy h2 {
  margin-top: 10px;
  font-size: clamp(34px, 5vw, 52px);
  line-height: 0.98;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: var(--text-1);
}

.conversation-hero-copy p {
  margin-top: 14px;
  max-width: 620px;
  color: var(--text-3);
  font-size: 14px;
  line-height: 1.75;
}

.conversation-hero-actions,
.conversation-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.conversation-filters-panel,
.conversation-pending-panel,
.conversation-group-panel,
.conversation-table-panel {
  padding: 18px;
}

.conversation-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.conversation-filters-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.conversation-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.conversation-summary-card {
  min-height: 132px;
  padding: 16px;
}

.conversation-summary-card span {
  color: var(--text-4);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.conversation-summary-card strong {
  display: block;
  margin-top: 16px;
  color: var(--text-1);
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.conversation-summary-card strong.blue {
  color: #77b7ff;
}

.conversation-summary-card strong.green {
  color: var(--accent);
}

.conversation-summary-card strong.amber {
  color: #f59e0b;
}

.pending-reply-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.pending-reply-card {
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 16px;
  background: rgba(98, 217, 155, 0.05);
}

.pending-reply-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.pending-reply-head strong {
  color: var(--text-1);
  font-size: 15px;
  font-weight: 700;
}

.pending-reply-head span {
  color: var(--text-4);
  font-size: 11px;
}

.pending-reply-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  color: var(--text-4);
  font-size: 11px;
}

.pending-reply-meta span {
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
}

.pending-reply-preview {
  margin-top: 12px;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.7;
  min-height: 44px;
}

.group-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.group-card {
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.group-card:hover {
  transform: translateY(-1px);
  border-color: rgba(98, 217, 155, 0.16);
}

.group-card-active {
  border-color: rgba(98, 217, 155, 0.18);
  background: rgba(98, 217, 155, 0.08);
}

.group-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.group-card-head strong {
  color: var(--text-1);
  font-size: 14px;
  font-weight: 700;
}

.group-card-head span {
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
}

.group-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 12px;
  color: var(--text-3);
  font-size: 12px;
}

.group-card-meta .green {
  color: var(--accent);
}

.group-card-meta .amber {
  color: #f59e0b;
}

.conversation-table-panel .conversation-panel-head {
  margin-bottom: 16px;
}

.segment-chip,
.status-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.segment-chip {
  background: rgba(119, 183, 255, 0.12);
  color: #77b7ff;
}

.conversation-modal {
  max-width: min(980px, calc(100vw - 36px));
}

.conversation-modal-title {
  margin-top: 10px;
  color: var(--text-1);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.conversation-modal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 12px;
  color: var(--text-4);
  font-size: 12px;
}

.conversation-modal-body {
  margin-top: 18px;
  max-height: 68vh;
  overflow-y: auto;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-row {
  display: flex;
}

.message-row.outbound {
  justify-content: flex-end;
}

.message-row.inbound {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 85%;
  border-radius: 24px;
  padding: 14px 16px;
}

.message-content {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-1);
  font-size: 14px;
  line-height: 1.7;
}

.message-meta {
  margin-top: 10px;
  color: var(--text-4);
  font-size: 11px;
}

@media (max-width: 1180px) {
  .conversation-summary-grid,
  .pending-reply-grid,
  .group-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 920px) {
  .conversation-hero,
  .conversation-panel-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .conversation-filters-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .conversation-filters-grid,
  .conversation-summary-grid,
  .pending-reply-grid,
  .group-grid {
    grid-template-columns: 1fr;
  }
}
</style>
