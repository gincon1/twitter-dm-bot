<template>
  <section class="conv-page">
    <div class="conv-header">
      <div>
        <h2>对话</h2>
        <p>查看谁回复了你，AI 帮你提取关键信息</p>
      </div>
      <div class="conv-actions">
        <button class="btn btn-ghost" @click="load">刷新</button>
        <button class="btn btn-secondary" @click="syncReplies">同步回复</button>
        <button class="btn btn-secondary" @click="exportCSV">导出</button>
      </div>
    </div>

    <!-- Stats -->
    <div class="conv-stats">
      <div class="stat-chip"><span class="stat-label">总对话</span><strong>{{ stats.total }}</strong></div>
      <div class="stat-chip"><span class="stat-label">已联系</span><strong class="blue">{{ stats.contacted }}</strong></div>
      <div class="stat-chip"><span class="stat-label">已回复</span><strong class="green">{{ stats.replied }}</strong></div>
      <div class="stat-chip"><span class="stat-label">我来处理</span><strong class="amber">{{ stats.manual }}</strong></div>
    </div>

    <!-- Filters -->
    <div class="conv-filters">
      <input v-model="search" class="input" placeholder="搜索用户名..." @input="debounceLoad" />
      <div class="filter-tabs">
        <button class="filter-tab" :class="{ active: filter === '' }" @click="filter = ''; load()">全部</button>
        <button class="filter-tab" :class="{ active: filter === 'replied' }" @click="filter = 'replied'; load()">已回复</button>
        <button class="filter-tab" :class="{ active: filter === 'contacted' }" @click="filter = 'contacted'; load()">未回复</button>
        <button class="filter-tab" :class="{ active: filter === 'manual_takeover' }" @click="filter = 'manual_takeover'; load()">我来处理</button>
      </div>
    </div>

    <!-- List + Detail -->
    <div class="conv-main">
      <!-- Left: list -->
      <div class="conv-list">
        <div v-for="item in conversations" :key="item.id"
          class="conv-item" :class="{ selected: selected?.id === item.id }"
          @click="selectConv(item)">
          <div class="conv-item-top">
            <strong>@{{ item.target_username }}</strong>
            <span class="conv-time">{{ shortTime(item.updated_at) }}</span>
          </div>
          <div class="conv-item-msg">{{ item.last_message_preview || '无消息' }}</div>
          <div class="conv-item-tags">
            <span :class="statusClass(item)">{{ statusText(item) }}</span>
            <span v-if="item.extracted_email" class="tag-sm tag-blue">邮箱</span>
            <span v-if="item.extracted_telegram" class="tag-sm tag-blue">TG</span>
            <span v-if="item.extracted_pricing" class="tag-sm tag-amber">报价</span>
          </div>
        </div>
        <div v-if="!conversations.length" class="empty-text">暂无对话</div>
      </div>

      <!-- Right: detail -->
      <div class="conv-detail">
        <div v-if="!selected" class="conv-empty">点击左侧对话查看详情</div>
        <template v-else>
          <div class="detail-head">
            <div>
              <h3>@{{ selected.target_username }}</h3>
              <span :class="statusClass(selected)">{{ statusText(selected) }}</span>
            </div>
            <div class="detail-actions">
              <button class="btn btn-sm btn-ghost" @click="markTakeover">我来处理</button>
              <button class="btn btn-sm btn-ghost" @click="markDone">搞定了</button>
            </div>
          </div>

          <!-- AI Analysis -->
          <div v-if="hasAnalysis" class="ai-box">
            <div class="ai-title">AI 分析</div>
            <div class="ai-fields">
              <div class="ai-field">
                <span class="ai-label">邮箱</span>
                <span class="ai-val">{{ selected.extracted_email || analysis?.email || '-' }}</span>
              </div>
              <div class="ai-field">
                <span class="ai-label">Telegram</span>
                <span class="ai-val">{{ selected.extracted_telegram || analysis?.telegram || '-' }}</span>
              </div>
              <div class="ai-field">
                <span class="ai-label">报价</span>
                <span class="ai-val">{{ selected.extracted_pricing || analysis?.pricing || '-' }}</span>
              </div>
              <div class="ai-field">
                <span class="ai-label">意向</span>
                <span :class="intentStyle">{{ intentText }}</span>
              </div>
            </div>
            <div v-if="analysis?.summary" class="ai-summary">{{ analysis.summary }}</div>
          </div>

          <!-- Messages -->
          <div class="msg-section">
            <div v-if="selected.last_reply_preview" class="msg-row reply">
              <span class="msg-dir">对方回复</span>
              <p>{{ selected.last_reply_preview }}</p>
              <span class="msg-time">{{ fmtTime(selected.reply_at) }}</span>
            </div>
            <div v-if="selected.last_message_preview" class="msg-row sent">
              <span class="msg-dir">我发的</span>
              <p>{{ selected.last_message_preview }}</p>
            </div>
          </div>

          <!-- Full history -->
          <div v-if="messages.length" class="msg-history">
            <div class="history-label">完整对话</div>
            <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="msg.direction === 'inbound' ? 'reply' : 'sent'">
              <span class="msg-dir">{{ msg.direction === 'inbound' ? '对方' : '我方' }}</span>
              <p>{{ msg.content }}</p>
              <span class="msg-time">{{ fmtTime(msg.detected_at) }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const conversations = ref([])
const selected = ref(null)
const messages = ref([])
const analysis = ref(null)
const stats = ref({ total: 0, contacted: 0, replied: 0, manual: 0 })
const search = ref('')
const filter = ref('')
let debounceTimer = null

function statusText(item) {
  if (item.status === 'manual_takeover') return '我来处理'
  if (item.status === 'completed') return '已结束'
  if (item.has_reply || item.status === 'replied') return '已回复'
  return '已联系'
}

function statusClass(item) {
  const s = item.status
  if (s === 'manual_takeover') return 'status-tag tag-amber'
  if (s === 'completed') return 'status-tag tag-gray'
  if (item.has_reply || s === 'replied') return 'status-tag tag-green'
  return 'status-tag tag-blue'
}

const hasAnalysis = computed(() =>
  analysis.value || selected.value?.extracted_email || selected.value?.extracted_telegram || selected.value?.extracted_pricing
)

const intentText = computed(() => {
  const i = analysis.value?.intent
  const m = { interested: '感兴趣', not_interested: '不感兴趣', pending: '待定' }
  return m[i] || '待分析'
})

const intentStyle = computed(() => {
  const i = analysis.value?.intent
  const m = { interested: 'ai-val green', not_interested: 'ai-val red', pending: 'ai-val amber' }
  return m[i] || 'ai-val'
})

function shortTime(v) {
  if (!v) return ''
  const d = new Date(v)
  if (isNaN(d.getTime())) return v
  const now = new Date()
  const diffMs = now - d
  if (diffMs < 60000) return '刚刚'
  if (diffMs < 3600000) return Math.floor(diffMs / 60000) + ' 分钟前'
  if (diffMs < 86400000) return Math.floor(diffMs / 3600000) + ' 小时前'
  return (d.getMonth() + 1) + '/' + d.getDate()
}

function fmtTime(v) {
  if (!v) return ''
  const d = new Date(v)
  return isNaN(d.getTime()) ? v : d.toLocaleString()
}

function debounceLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(load, 300)
}

async function load() {
  try {
    const params = new URLSearchParams()
    if (filter.value) params.set('status', filter.value)
    if (search.value) params.set('search', search.value)
    params.set('limit', '500')
    const res = await fetch('/api/conversations?' + params)
    conversations.value = await res.json()
  } catch {}
  await loadStats()
}

async function loadStats() {
  try {
    const res = await fetch('/api/stats')
    const data = await res.json()
    const c = data.conversations || {}
    stats.value = {
      total: c.total || 0,
      contacted: c.contacted || 0,
      replied: c.replied || 0,
      manual: c.manual_takeover || 0,
    }
  } catch {}
}

async function selectConv(item) {
  selected.value = item
  analysis.value = null
  messages.value = []
  try {
    const res = await fetch(`/api/conversations/${item.id}/detail`)
    const data = await res.json()
    messages.value = data.messages || []
    analysis.value = data.analysis || null
  } catch {}
}

async function markTakeover() {
  if (!selected.value) return
  await fetch(`/api/conversations/${selected.value.id}/takeover`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  await load()
  if (selected.value) await selectConv(selected.value)
}

async function markDone() {
  if (!selected.value) return
  await fetch(`/api/conversations/${selected.value.id}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  await load()
  if (selected.value) await selectConv(selected.value)
}

async function syncReplies() {
  await fetch('/api/check-replies', { method: 'POST' })
  alert('同步已触发')
  await load()
}

async function exportCSV() {
  window.open('/api/conversations/export?format=csv', '_blank')
}

onMounted(load)
</script>

<style scoped>
.conv-page { display: flex; flex-direction: column; gap: 18px; }
.conv-header { display: flex; justify-content: space-between; align-items: flex-start; }
.conv-header h2 { font-size: 28px; font-weight: 800; letter-spacing: -0.04em; }
.conv-header p { color: var(--text-3); margin-top: 4px; font-size: 14px; }
.conv-actions { display: flex; gap: 8px; }

/* Stats */
.conv-stats { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-chip {
  display: flex; flex-direction: column; align-items: center;
  padding: 12px 20px; border-radius: 18px; min-width: 100px;
  border: 1px solid var(--border); background: rgba(255,255,255,0.025);
}
.stat-label { font-size: 11px; color: var(--text-4); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
.stat-chip strong { font-size: 24px; font-weight: 800; margin-top: 4px; }
.blue { color: #60a5fa; }
.green { color: #4ade80; }
.amber { color: #f59e0b; }
.red { color: #f87171; }

/* Filters */
.conv-filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  padding: 6px 14px; border-radius: 999px; border: 1px solid var(--border);
  background: transparent; color: var(--text-3); font-size: 13px; cursor: pointer;
}
.filter-tab:hover { color: var(--text-1); }
.filter-tab.active { background: rgba(74,222,128,0.12); color: #4ade80; border-color: rgba(74,222,128,0.3); }

/* Main layout */
.conv-main { display: grid; grid-template-columns: 360px 1fr; gap: 18px; min-height: 480px; }
.conv-list {
  display: flex; flex-direction: column; gap: 6px;
  max-height: 70vh; overflow-y: auto;
  border: 1px solid var(--border); border-radius: 20px; padding: 10px;
}
.conv-item {
  padding: 12px 14px; border-radius: 14px; border: 1px solid transparent;
  cursor: pointer; transition: all 0.15s;
}
.conv-item:hover { background: rgba(255,255,255,0.03); border-color: var(--border); }
.conv-item.selected { background: rgba(74,222,128,0.08); border-color: rgba(74,222,128,0.2); }
.conv-item-top { display: flex; justify-content: space-between; align-items: center; }
.conv-item-top strong { font-size: 14px; }
.conv-time { font-size: 11px; color: var(--text-4); }
.conv-item-msg { margin-top: 4px; font-size: 12px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-item-tags { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }

/* Tags */
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.tag-sm { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 600; }
.tag-blue { background: rgba(96,165,250,0.15); color: #60a5fa; }
.tag-green { background: rgba(74,222,128,0.15); color: #4ade80; }
.tag-amber { background: rgba(245,158,11,0.15); color: #f59e0b; }
.tag-gray { background: rgba(148,163,184,0.15); color: #94a3b8; }
.tag-red { background: rgba(248,113,113,0.15); color: #f87171; }

/* Detail */
.conv-detail { border: 1px solid var(--border); border-radius: 20px; padding: 20px; background: rgba(255,255,255,0.015); }
.conv-empty { display: grid; place-items: center; height: 300px; color: var(--text-4); }
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.detail-head h3 { font-size: 20px; font-weight: 800; display: inline; margin-right: 8px; }
.detail-actions { display: flex; gap: 6px; }
.btn-sm { padding: 6px 14px; font-size: 12px; border-radius: 12px; }

/* AI Box */
.ai-box {
  border: 1px solid rgba(96,165,250,0.2); border-radius: 16px;
  padding: 14px; margin-bottom: 16px; background: rgba(96,165,250,0.04);
}
.ai-title { font-size: 11px; font-weight: 700; color: #60a5fa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
.ai-fields { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.ai-field { display: flex; flex-direction: column; gap: 2px; }
.ai-label { font-size: 11px; color: var(--text-4); font-weight: 600; }
.ai-val { font-size: 13px; font-weight: 700; color: var(--text-1); word-break: break-all; }
.ai-summary { margin-top: 10px; font-size: 12px; color: var(--text-2); line-height: 1.5; }

/* Messages */
.msg-section { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.msg-row {
  padding: 10px 14px; border-radius: 14px; max-width: 85%;
}
.msg-row.reply { background: rgba(74,222,128,0.06); border: 1px solid rgba(74,222,128,0.12); align-self: flex-start; }
.msg-row.sent { background: rgba(255,255,255,0.03); border: 1px solid var(--border); align-self: flex-end; }
.msg-dir { display: block; font-size: 10px; font-weight: 700; color: var(--text-4); margin-bottom: 4px; }
.msg-row p { font-size: 13px; color: var(--text-1); line-height: 1.5; margin: 0; }
.msg-time { display: block; margin-top: 4px; font-size: 10px; color: var(--text-4); }
.empty-text { color: var(--text-4); text-align: center; padding: 24px; font-size: 13px; }

/* Full history */
.msg-history { border-top: 1px solid var(--border); padding-top: 14px; display: flex; flex-direction: column; gap: 6px; max-height: 280px; overflow-y: auto; }
.history-label { font-size: 11px; font-weight: 700; color: var(--text-4); margin-bottom: 8px; text-transform: uppercase; }

@media (max-width: 900px) { .conv-main { grid-template-columns: 1fr; } .ai-fields { grid-template-columns: 1fr 1fr; } }
</style>
