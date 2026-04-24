<template>
  <section class="send-page">
    <div class="send-header">
      <h2>发消息</h2>
      <p>选模板、选人、选账号，一键发送</p>
    </div>

    <div class="send-grid">
      <!-- Left: template + who -->
      <div class="send-left">
        <!-- Template -->
        <div class="send-block">
          <h3>选模板</h3>
          <select v-model="selectedTemplate" class="input w-full" @change="loadPreview">
            <option value="">默认模板</option>
            <option v-for="t in templates" :key="t.id" :value="t.id">
              {{ t.description || t.content?.slice(0, 50) + '...' }}
            </option>
          </select>
          <div v-if="previewText" class="preview-box">{{ previewText }}</div>
        </div>

        <!-- Who to send -->
        <div class="send-block">
          <h3>发给谁</h3>
          <div class="who-options">
            <div class="who-option" :class="{ active: sendTarget === 'all' }" @click="sendTarget = 'all'">
              <div class="who-radio"><span v-if="sendTarget === 'all'" class="radio-dot" /></div>
              <div class="who-info">
                <strong>所有未联系的人</strong>
                <span>{{ pendingAll }} 人</span>
              </div>
            </div>
            <div v-for="g in groups" :key="g.id" class="who-option" :class="{ active: sendTarget === g.id }" @click="sendTarget = g.id">
              <div class="who-radio"><span v-if="sendTarget === g.id" class="radio-dot" /></div>
              <div class="who-info">
                <strong>{{ g.name }}</strong>
                <span>{{ g.count || 0 }} 人</span>
              </div>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" @click="showNewGroup = true" style="margin-top:8px">+ 新建人群</button>
        </div>
      </div>

      <!-- Right: accounts -->
      <div class="send-right">
        <div class="send-block">
          <h3>用哪些账号发 <span class="text-sm" style="color:var(--text-4)">（已选 {{ selectedAccounts.length }} 个）</span></h3>
          <div class="account-list">
            <label v-for="acc in accounts" :key="acc.record_id" class="account-row" :class="{ disabled: acc.status !== '正常' }">
              <input type="checkbox" :value="acc.record_id" v-model="selectedAccounts" :disabled="acc.status !== '正常'" />
              <div class="account-info">
                <span class="account-name">{{ acc.twitter_username || acc.profile_id || '账号' }}</span>
                <span class="account-meta">
                  <span :style="{ color: acc.status === '正常' ? '#4ade80' : '#f87171' }">{{ acc.status }}</span>
                </span>
              </div>
            </label>
            <div v-if="!accounts.length" class="empty-text">暂无账号，请先在「账号管理」添加</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom bar -->
    <div class="send-bar">
      <div class="send-summary">
        将发给 <strong>{{ pendingCount }}</strong> 人，使用 <strong>{{ selectedAccounts.length }}</strong> 个账号
      </div>
      <button class="btn btn-primary btn-lg" :disabled="sending || !canSend" @click="confirmSend">
        {{ sending ? '发送中...' : '开始发送' }}
      </button>
    </div>

    <!-- New Group Modal -->
    <div v-if="showNewGroup" class="modal-overlay" @click.self="showNewGroup = false">
      <div class="modal">
        <h3>新建人群</h3>
        <div class="form-group">
          <label>人群名称</label>
          <input v-model="newGroupName" class="input w-full" placeholder="例如：Crypto KOL" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showNewGroup = false">取消</button>
          <button class="btn btn-primary" @click="createGroup">创建</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const groups = ref([])
const templates = ref([])
const accounts = ref([])
const selectedTemplate = ref('')
const selectedAccounts = ref([])
const previewText = ref('')
const pendingAll = ref(0)
const sendTarget = ref('all')
const sending = ref(false)
const showNewGroup = ref(false)
const newGroupName = ref('')

const pendingCount = computed(() => {
  if (sendTarget.value === 'all') return pendingAll.value
  const g = groups.value.find(g => g.id === sendTarget.value)
  return g?.count || 0
})

const canSend = computed(() => selectedAccounts.value.length > 0 && pendingCount.value > 0)

async function loadGroups() {
  try {
    const res = await fetch('/api/segments')
    groups.value = await res.json()
  } catch {}
}

async function loadTemplates() {
  try {
    const res = await fetch('/api/templates')
    const data = await res.json()
    templates.value = data.templates || []
  } catch {}
}

async function loadAccounts() {
  try {
    const res = await fetch('/api/accounts')
    accounts.value = await res.json()
    selectedAccounts.value = accounts.value.filter(a => a.status === '正常').map(a => a.record_id)
  } catch {}
}

async function loadPendingAll() {
  try {
    const res = await fetch('/api/targets?status=' + encodeURIComponent('待发送'))
    const data = await res.json()
    pendingAll.value = Array.isArray(data) ? data.length : 0
  } catch { pendingAll.value = 0 }
}

async function loadPreview() {
  try {
    const params = new URLSearchParams({ project: 'Example', handle: 'testuser' })
    if (selectedTemplate.value) params.set('template_id', selectedTemplate.value)
    const res = await fetch('/api/templates/preview?' + params)
    const data = await res.json()
    previewText.value = data.preview || ''
  } catch { previewText.value = '' }
}

async function createGroup() {
  if (!newGroupName.value.trim()) return
  await fetch('/api/segments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newGroupName.value.trim() }),
  })
  newGroupName.value = ''
  showNewGroup.value = false
  await loadGroups()
}

async function confirmSend() {
  if (!canSend.value) return
  const whoName = sendTarget.value === 'all'
    ? '所有未联系的人'
    : (groups.value.find(g => g.id === sendTarget.value)?.name || '选中人群')
  if (!confirm(`确认发送？\n\n发给：${whoName}\n人数：${pendingCount.value}\n账号：${selectedAccounts.value.length} 个`)) return

  sending.value = true
  try {
    if (sendTarget.value !== 'all') {
      // Send to specific group
      await fetch(`/api/segments/${sendTarget.value}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_ids: selectedAccounts.value, wait_between: true }),
      })
    } else {
      // Send to all pending
      await fetch('/api/run-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
    }
    alert('发送任务已启动！')
  } catch (e) {
    alert('启动失败: ' + e.message)
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadGroups(), loadTemplates(), loadAccounts(), loadPendingAll(), loadPreview()])
})
</script>

<style scoped>
.send-page { display: flex; flex-direction: column; gap: 24px; }
.send-header h2 { font-size: 28px; font-weight: 800; letter-spacing: -0.04em; }
.send-header p { color: var(--text-3); margin-top: 4px; font-size: 14px; }

.send-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.send-left { display: flex; flex-direction: column; gap: 18px; }
.send-right { }

.send-block {
  border: 1px solid var(--border); border-radius: 20px; padding: 20px;
  background: rgba(255,255,255,0.025);
}
.send-block h3 { font-size: 15px; font-weight: 700; margin-bottom: 12px; }

/* Who options */
.who-options { display: flex; flex-direction: column; gap: 6px; }
.who-option {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: 14px;
  border: 1px solid var(--border); cursor: pointer;
  transition: all 0.15s;
}
.who-option:hover { border-color: rgba(74,222,128,0.3); }
.who-option.active { border-color: rgba(74,222,128,0.4); background: rgba(74,222,128,0.08); }
.who-radio {
  width: 18px; height: 18px; border-radius: 999px;
  border: 2px solid var(--border); display: grid; place-items: center; flex-shrink: 0;
  transition: border-color 0.15s;
}
.who-option.active .who-radio { border-color: #4ade80; }
.radio-dot { width: 8px; height: 8px; border-radius: 999px; background: #4ade80; }
.who-info { display: flex; justify-content: space-between; flex: 1; }
.who-info strong { font-size: 13px; font-weight: 600; }
.who-info span { font-size: 12px; color: var(--text-4); }

/* Preview */
.preview-box {
  margin-top: 12px; padding: 12px; border-radius: 14px;
  background: rgba(255,255,255,0.04); border: 1px solid var(--border);
  color: var(--text-2); font-size: 13px; line-height: 1.6;
}

/* Accounts */
.account-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
.account-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 12px;
  border: 1px solid var(--border); cursor: pointer;
}
.account-row:hover { background: rgba(255,255,255,0.03); }
.account-row.disabled { opacity: 0.4; cursor: not-allowed; }
.account-info { flex: 1; display: flex; justify-content: space-between; align-items: center; }
.account-name { font-weight: 600; font-size: 13px; }
.account-meta { display: flex; gap: 10px; font-size: 11px; color: var(--text-4); }

/* Bottom bar */
.send-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px; border-radius: 20px;
  border: 1px solid var(--border); background: rgba(255,255,255,0.025);
}
.send-summary { color: var(--text-3); font-size: 14px; }
.send-summary strong { color: var(--text-1); }
.btn-lg { padding: 12px 32px; font-size: 16px; font-weight: 700; border-radius: 16px; }
.btn-sm { font-size: 12px; padding: 6px 14px; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: grid; place-items: center; z-index: 50; }
.modal { width: 90%; max-width: 420px; background: var(--panel); border: 1px solid var(--border); border-radius: 24px; padding: 24px; }
.modal h3 { font-size: 18px; font-weight: 800; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-4); margin-bottom: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.w-full { width: 100%; }
.empty-text { color: var(--text-4); text-align: center; padding: 18px; font-size: 13px; }

@media (max-width: 900px) { .send-grid { grid-template-columns: 1fr; } }
</style>
