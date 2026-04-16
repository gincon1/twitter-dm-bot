<template>
  <section class="accounts-page">
    <div class="accounts-hero card">
      <div class="accounts-hero-copy">
        <div class="accounts-kicker">Account Pool</div>
        <h2>账号管理</h2>
      </div>

      <div class="accounts-hero-stats">
        <div class="metric-card accounts-stat-card">
          <span>账号总数</span>
          <strong>{{ accounts.accounts.length }}</strong>
        </div>
        <div class="metric-card accounts-stat-card">
          <span>正常账号</span>
          <strong class="good">{{ normalCount }}</strong>
        </div>
        <div class="metric-card accounts-stat-card">
          <span>异常账号</span>
          <strong class="bad">{{ abnormalCount }}</strong>
        </div>
      </div>
    </div>

    <div class="card accounts-toolbar-panel">
      <div class="accounts-toolbar-head">
        <div>
          <div class="section-title">筛选与操作</div>
        </div>
        <div class="accounts-actions">
          <button class="btn btn-ghost" @click="reload">刷新</button>
          <button class="btn btn-primary" @click="showAdd = true">新增账号</button>
        </div>
      </div>

      <div class="accounts-filters">
        <button
          v-for="s in filters"
          :key="s"
          class="filter-chip"
          :class="accounts.filter === s ? 'filter-chip-active' : ''"
          @click="accounts.setFilter(s)"
        >
          {{ s }}
        </button>
      </div>
    </div>

    <div class="card accounts-table-panel">
      <div class="table-panel-head">
        <div>
          <div class="section-title">账号列表</div>
        </div>
        <span class="pill">当前 {{ accounts.filteredAccounts.length }} 个</span>
      </div>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>AdsPower ID</th>
              <th>X 用户名</th>
              <th>来源</th>
              <th>状态</th>
              <th>健康分</th>
              <th>当日发送量/上限</th>
              <th>累计发送</th>
              <th>冷却到</th>
              <th>绑定 IP</th>
              <th>最后操作时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="acc in accounts.filteredAccounts" :key="acc.record_id">
              <td class="font-mono text-xs" style="color: var(--text-3)">{{ acc.profile_id }}</td>
              <td style="color: var(--text-1)">{{ acc.twitter_username || '-' }}</td>
              <td>
                <span class="source-badge" :class="acc._source === 'local' ? 'source-local' : 'source-feishu'">
                  {{ acc._source === 'local' ? '本地录入' : '飞书同步' }}
                </span>
              </td>
              <td><StatusBadge :status="acc.status" /></td>
              <td><span :style="{ color: healthColor(acc.health_score) }">{{ acc.health_score ?? 100 }}</span></td>
              <td style="color: var(--text-2)">{{ acc.today_sent || 0 }}/{{ acc.daily_limit_today || 0 }}</td>
              <td style="color: var(--text-2)">{{ acc.total_sent || 0 }}</td>
              <td style="color: var(--text-2)">{{ formatCooldown(acc.cooldown_until) }}</td>
              <td style="color: var(--text-2)">{{ acc.bound_ip || '-' }}</td>
              <td style="color: var(--text-3)">{{ formatTime(acc.last_action_time) }}</td>
              <td>
                <div class="accounts-row-actions">
                  <button class="btn btn-ghost btn-sm" @click="toggle(acc)">{{ acc.status === '正常' ? '标记异常' : '恢复正常' }}</button>
                  <button class="btn btn-ghost btn-sm" @click="test(acc)">连接测试</button>
                  <button v-if="acc._source === 'local'" class="btn btn-ghost btn-sm" @click="remove(acc.record_id)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!accounts.filteredAccounts.length">
              <td colspan="11" class="py-8 text-center" style="color: var(--text-3)">暂无账号数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showAdd" class="modal-backdrop" @click.self="showAdd = false">
      <div class="modal-box">
        <div class="modal-head">
          <div>
            <div class="accounts-kicker">New Account</div>
            <h3>新增账号</h3>
          </div>
          <button class="btn btn-ghost" @click="showAdd = false">关闭</button>
        </div>
        <div class="modal-form">
          <div class="form-field">
            <label>AdsPower Profile ID *</label>
            <input v-model="addForm.profile_id" class="input font-mono" placeholder="如 krmihf0" />
          </div>
          <div class="form-field">
            <label>X 用户名</label>
            <input v-model="addForm.twitter_username" class="input" placeholder="@username 或 username" />
          </div>
          <div class="form-field">
            <label>绑定 IP（可选）</label>
            <input v-model="addForm.bound_ip" class="input" placeholder="如 192.168.1.100" />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showAdd = false">取消</button>
          <button class="btn btn-primary" @click="submitAdd">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAccountsStore } from '../stores/accounts'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

const accounts = useAccountsStore()
const system = useSystemStore()

const filters = ['全部', '正常', '异常']
const showAdd = ref(false)
const addForm = ref({ profile_id: '', twitter_username: '', bound_ip: '' })

const normalCount = computed(() => accounts.accounts.filter((x) => x.status === '正常').length)
const abnormalCount = computed(() => accounts.accounts.filter((x) => x.status !== '正常').length)

const formatTime = (value) => {
  if (!value) return '-'
  if (typeof value === 'number') return new Date(value).toLocaleString()
  const dt = new Date(value)
  return Number.isNaN(dt.getTime()) ? String(value) : dt.toLocaleString()
}

const formatCooldown = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  if (date.getTime() <= Date.now()) return '已结束'
  return date.toLocaleString()
}

const healthColor = (score) => {
  const value = Number(score ?? 100)
  if (value < 20) return '#ef4444'
  if (value < 40) return '#f59e0b'
  return 'var(--text-1)'
}

const reload = async () => {
  try {
    await accounts.fetchAccounts()
  } catch (e) {
    system.notify(getActionErrorMessage('加载账号', e), 'error')
  }
}

const toggle = async (acc) => {
  try {
    const next = acc.status === '正常' ? '异常' : '正常'
    await accounts.toggleAccount(acc.record_id, next)
  } catch (e) {
    system.notify(getActionErrorMessage('切换账号状态', e), 'error')
  }
}

const test = async (acc) => {
  try {
    await accounts.testAccount(acc.record_id)
  } catch (e) {
    system.notify(getActionErrorMessage('账号连接测试', e), 'error')
  }
}

const remove = async (recordId) => {
  try {
    await accounts.deleteAccount(recordId)
  } catch (e) {
    system.notify(getActionErrorMessage('删除账号', e), 'error')
  }
}

const submitAdd = async () => {
  try {
    await accounts.createAccount(addForm.value)
    addForm.value = { profile_id: '', twitter_username: '', bound_ip: '' }
    showAdd.value = false
  } catch (e) {
    system.notify(getActionErrorMessage('新增账号', e), 'error')
  }
}

onMounted(async () => {
  await reload()
})
</script>

<style scoped>
.accounts-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.accounts-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 18px;
  padding: 22px;
}

.accounts-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.accounts-hero-copy h2,
.modal-head h3 {
  margin-top: 10px;
  font-size: clamp(34px, 5vw, 52px);
  line-height: 0.98;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: var(--text-1);
}

.modal-head h3 {
  font-size: 28px;
}

.accounts-hero-copy p {
  margin-top: 14px;
  color: var(--text-3);
  font-size: 14px;
  line-height: 1.75;
  max-width: 620px;
}

.accounts-hero-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.accounts-stat-card {
  min-height: 156px;
  padding: 16px;
}

.accounts-stat-card span {
  color: var(--text-4);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.accounts-stat-card strong {
  display: block;
  margin-top: 16px;
  color: var(--text-1);
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.accounts-stat-card strong.good {
  color: var(--accent);
}

.accounts-stat-card strong.bad {
  color: #f87171;
}

.accounts-toolbar-panel,
.accounts-table-panel {
  padding: 18px;
}

.accounts-toolbar-head,
.table-panel-head,
.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.accounts-actions,
.modal-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.accounts-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.filter-chip {
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

.filter-chip:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.035);
}

.filter-chip-active {
  color: var(--text-1);
  border-color: rgba(98, 217, 155, 0.18);
  background: rgba(98, 217, 155, 0.08);
}

.table-panel-head {
  margin-bottom: 16px;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.source-local {
  background: rgba(119, 183, 255, 0.14);
  color: #77b7ff;
}

.source-feishu {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-3);
}

.accounts-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.modal-form {
  display: grid;
  gap: 14px;
  margin-top: 18px;
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

.modal-actions {
  justify-content: flex-end;
  margin-top: 18px;
}

@media (max-width: 980px) {
  .accounts-hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .accounts-hero-stats {
    grid-template-columns: 1fr;
  }

  .accounts-toolbar-head,
  .table-panel-head,
  .modal-head {
    flex-direction: column;
  }
}
</style>
