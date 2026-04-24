<template>
  <section class="contacts-page">
    <div class="contacts-header">
      <div>
        <h2>联系人</h2>
        <p>管理你的人群库，导入不同群体的联系人</p>
      </div>
      <div class="contacts-actions">
        <button class="btn btn-ghost" @click="loadAll">刷新</button>
        <button class="btn btn-secondary" @click="showImport = true">导入</button>
        <button class="btn btn-primary" @click="showAdd = true">添加</button>
      </div>
    </div>

    <!-- 人群选择 -->
    <div class="groups-bar">
      <button class="group-chip" :class="{ active: !selectedGroup }" @click="selectedGroup = ''; loadContacts()">
        全部 ({{ allCount }})
      </button>
      <button v-for="g in groups" :key="g.id" class="group-chip" :class="{ active: selectedGroup === g.id }" @click="selectedGroup = g.id; loadContacts()">
        {{ g.name }} ({{ g.count || 0 }})
      </button>
      <button class="group-chip add-group" @click="showNewGroup = true">+ 新人群</button>
    </div>

    <!-- 搜索 -->
    <div class="contacts-filters">
      <input v-model="search" class="input" placeholder="搜索用户名..." @input="debounceLoad" />
    </div>

    <!-- Table -->
    <div class="contacts-table-wrap">
      <table class="contacts-table">
        <thead>
          <tr>
            <th>用户名</th>
            <th>状态</th>
            <th>人群</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in contacts" :key="c.record_id || c.id">
            <td><strong>@{{ c.twitter_username }}</strong></td>
            <td><span :class="statusClass(c.status)">{{ statusLabel(c.status) }}</span></td>
            <td>{{ c.segment_name || '-' }}</td>
            <td class="actions">
              <button v-if="c.status === '待发送'" class="btn-sm btn-ghost" @click="skipTarget(c)">跳过</button>
              <button v-if="c.status !== '待发送'" class="btn-sm btn-ghost" @click="resetTarget(c)">重置</button>
              <button class="btn-sm btn-ghost" style="color:#f87171" @click="deleteTarget(c)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!contacts.length" class="empty-text">暂无联系人，点击「导入」添加</div>
    </div>

    <!-- Add Modal -->
    <div v-if="showAdd" class="modal-overlay" @click.self="showAdd = false">
      <div class="modal">
        <h3>添加联系人</h3>
        <div class="form-group">
          <label>Twitter 用户名 *</label>
          <input v-model="addForm.twitter_username" class="input w-full" placeholder="@username" />
        </div>
        <div class="form-group">
          <label>加入人群（可选）</label>
          <select v-model="addForm.segment_id" class="input w-full">
            <option value="">不指定</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showAdd = false">取消</button>
          <button class="btn btn-primary" @click="addContact">添加</button>
        </div>
      </div>
    </div>

    <!-- Import Modal -->
    <div v-if="showImport" class="modal-overlay" @click.self="showImport = false">
      <div class="modal">
        <h3>批量导入</h3>
        <div class="form-group">
          <label>粘贴用户名（每行一个）</label>
          <textarea v-model="importText" class="input w-full" rows="8" placeholder="@user1&#10;@user2&#10;@user3"></textarea>
        </div>
        <div class="form-group">
          <label>导入到人群</label>
          <select v-model="importGroup" class="input w-full">
            <option value="">不指定人群</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showImport = false">取消</button>
          <button class="btn btn-primary" @click="importContacts">导入</button>
        </div>
      </div>
    </div>

    <!-- New Group Modal -->
    <div v-if="showNewGroup" class="modal-overlay" @click.self="showNewGroup = false">
      <div class="modal">
        <h3>新建人群</h3>
        <div class="form-group">
          <label>人群名称</label>
          <input v-model="newGroupName" class="input w-full" placeholder="例如：Crypto KOL、VC 列表" />
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
import { onMounted, ref } from 'vue'

const contacts = ref([])
const groups = ref([])
const allCount = ref(0)
const search = ref('')
const selectedGroup = ref('')
const showAdd = ref(false)
const showImport = ref(false)
const showNewGroup = ref(false)
const importText = ref('')
const importGroup = ref('')
const newGroupName = ref('')
let debounceTimer = null

const addForm = ref({ twitter_username: '', segment_id: '', note: '' })

function statusLabel(s) {
  const m = { '待发送': '未联系', '已发送': '已联系', '已回复': '已回复', '人工接管': '我来处理', '完成': '已结束' }
  return m[s] || s
}
function statusClass(s) {
  const m = { '待发送': 'tag-gray', '已发送': 'tag-blue', '已回复': 'tag-green', '人工接管': 'tag-amber', '完成': 'tag-gray' }
  return 'status-tag ' + (m[s] || 'tag-gray')
}

function debounceLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadContacts, 300)
}

async function loadAll() {
  await Promise.all([loadContacts(), loadGroups()])
}

async function loadContacts() {
  try {
    const params = new URLSearchParams()
    if (search.value) params.set('search', search.value)
    if (selectedGroup.value) {
      // Load from segment
      const res = await fetch(`/api/segments/${selectedGroup.value}/targets`)
      const data = await res.json()
      contacts.value = data.items || data || []
    } else {
      const res = await fetch('/api/targets?' + params)
      contacts.value = await res.json()
    }
    allCount.value = contacts.value.length
  } catch { contacts.value = [] }
}

async function loadGroups() {
  try {
    const res = await fetch('/api/segments')
    groups.value = await res.json()
  } catch {}
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

async function addContact() {
  const username = addForm.value.twitter_username.replace('@', '').trim()
  if (!username) return

  // Create target
  await fetch('/api/targets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ twitter_username: username }),
  })

  // Add to segment if selected
  if (addForm.value.segment_id) {
    // Find the newly created target
    const findRes = await fetch('/api/targets?search=' + encodeURIComponent(username))
    const targets = await findRes.json()
    const target = targets.find(t => t.twitter_username === username)
    if (target) {
      await fetch(`/api/segments/${addForm.value.segment_id}/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          targets: [{ id: target.record_id || target.id, source: 'local', username: username }]
        }),
      })
    }
  }

  showAdd.value = false
  addForm.value = { twitter_username: '', segment_id: '', note: '' }
  await loadAll()
}

async function importContacts() {
  const lines = importText.value.split('\n').map(l => l.trim()).filter(Boolean)
  if (!lines.length) return

  const rows = lines.map(line => {
    const parts = line.split(',')
    return { twitter_username: parts[0].replace('@', '').trim() }
  })

  // Import targets
  const res = await fetch('/api/targets/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  })
  const data = await res.json()
  const imported = data.imported || 0

  // Add to segment if selected
  if (importGroup.value && imported > 0) {
    // Find the newly imported targets
    const usernames = rows.map(r => r.twitter_username)
    for (const username of usernames) {
      const findRes = await fetch('/api/targets?search=' + encodeURIComponent(username))
      const targets = await findRes.json()
      const target = targets.find(t => t.twitter_username === username)
      if (target) {
        await fetch(`/api/segments/${importGroup.value}/targets`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            targets: [{ id: target.record_id || target.id, source: 'local', username: username }]
          }),
        })
      }
    }
  }

  alert(`成功导入 ${imported} 条`)
  showImport.value = false
  importText.value = ''
  importGroup.value = ''
  await loadAll()
}

async function skipTarget(c) {
  const id = c.record_id || c.id
  await fetch(`/api/targets/${encodeURIComponent(id)}/skip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: '手动跳过' }),
  })
  await loadContacts()
}

async function resetTarget(c) {
  const id = c.record_id || c.id
  await fetch(`/api/targets/${encodeURIComponent(id)}/reset`, { method: 'POST' })
  await loadContacts()
}

async function deleteTarget(c) {
  const id = c.record_id || c.id
  if (!id.startsWith('local_')) { alert('只能删除本地联系人'); return }
  if (!confirm('确认删除？')) return
  await fetch(`/api/targets/${encodeURIComponent(id)}`, { method: 'DELETE' })
  await loadContacts()
}

onMounted(loadAll)
</script>

<style scoped>
.contacts-page { display: flex; flex-direction: column; gap: 18px; }
.contacts-header { display: flex; justify-content: space-between; align-items: flex-start; }
.contacts-header h2 { font-size: 28px; font-weight: 800; letter-spacing: -0.04em; }
.contacts-header p { color: var(--text-3); margin-top: 4px; font-size: 14px; }
.contacts-actions { display: flex; gap: 8px; }

/* Groups bar */
.groups-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.group-chip {
  padding: 8px 16px; border-radius: 999px; border: 1px solid var(--border);
  background: transparent; color: var(--text-3); font-size: 13px; cursor: pointer;
  transition: all 0.15s;
}
.group-chip:hover { color: var(--text-1); border-color: rgba(74,222,128,0.3); }
.group-chip.active { background: rgba(74,222,128,0.12); color: #4ade80; border-color: rgba(74,222,128,0.3); font-weight: 600; }
.add-group { border-style: dashed; color: var(--text-4); }
.add-group:hover { color: #4ade80; border-color: rgba(74,222,128,0.3); }

/* Filters */
.contacts-filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

/* Table */
.contacts-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 20px; }
.contacts-table { width: 100%; border-collapse: collapse; }
.contacts-table th {
  text-align: left; padding: 14px 16px; font-size: 11px; font-weight: 700;
  color: var(--text-4); letter-spacing: 0.08em; text-transform: uppercase;
  border-bottom: 1px solid var(--border);
}
.contacts-table td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.contacts-table tr:hover td { background: rgba(255,255,255,0.02); }

/* Status tags */
.status-tag { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.tag-blue { background: rgba(96,165,250,0.15); color: #60a5fa; }
.tag-green { background: rgba(74,222,128,0.15); color: #4ade80; }
.tag-amber { background: rgba(245,158,11,0.15); color: #f59e0b; }
.tag-gray { background: rgba(148,163,184,0.15); color: #94a3b8; }
.tag-red { background: rgba(248,113,113,0.15); color: #f87171; }

.actions { display: flex; gap: 4px; }
.btn-sm { padding: 4px 10px; font-size: 12px; border-radius: 10px; border: 1px solid var(--border); background: transparent; cursor: pointer; color: var(--text-3); }
.btn-sm:hover { color: var(--text-1); }
.empty-text { color: var(--text-4); text-align: center; padding: 24px; font-size: 13px; }

/* Modals */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: grid; place-items: center; z-index: 50; }
.modal { width: 90%; max-width: 480px; background: var(--panel); border: 1px solid var(--border); border-radius: 28px; padding: 28px; }
.modal h3 { font-size: 20px; font-weight: 800; margin-bottom: 20px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-4); margin-bottom: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
.w-full { width: 100%; }
</style>
