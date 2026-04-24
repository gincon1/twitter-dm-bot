<template>
  <section class="settings-page">
    <div class="card settings-panel">
      <div class="settings-head">
        <div>
          <div class="settings-kicker">Execution Policy</div>
          <h2>策略配置</h2>
        </div>
      </div>

      <div v-if="loadingConfig" class="settings-loading">加载中...</div>

      <div v-else class="settings-grid">
        <div class="form-field">
          <label>每日发送上限区间</label>
          <div class="field-inline">
            <input v-model.number="configForm.daily_dm_limit_min" type="number" min="1" max="50" class="input w-24" />
            <span>到</span>
            <input v-model.number="configForm.daily_dm_limit_max" type="number" min="1" max="50" class="input w-24" />
            <span>条/天/账号</span>
          </div>
        </div>

        <div class="form-field">
          <label>最大账号重试次数</label>
          <div class="field-inline">
            <input v-model.number="configForm.max_retry_accounts_per_target" type="number" min="1" max="10" class="input w-32" />
            <span>同目标切换账号上限</span>
          </div>
        </div>

        <div class="form-field">
          <label>发送间隔最小值</label>
          <div class="field-inline">
            <input v-model.number="configForm.min_interval_sec" type="number" min="60" step="60" class="input w-32" />
            <span>秒（{{ toMin(configForm.min_interval_sec) }}）</span>
          </div>
        </div>

        <div class="form-field">
          <label>发送间隔最大值</label>
          <div class="field-inline">
            <input v-model.number="configForm.max_interval_sec" type="number" min="60" step="60" class="input w-32" />
            <span>秒（{{ toMin(configForm.max_interval_sec) }}）</span>
          </div>
        </div>

        <div class="form-field">
          <label>飞书同步间隔</label>
          <div class="field-inline">
            <input v-model.number="configForm.sync_interval_min" type="number" min="5" max="1440" class="input w-32" />
            <span>分钟</span>
          </div>
        </div>

        <div class="form-field">
          <label>账号冷却时长</label>
          <div class="field-inline">
            <input v-model.number="configForm.cooldown_hours" type="number" min="1" max="168" class="input w-32" />
            <span>小时</span>
          </div>
        </div>

        <div class="form-field">
          <label>发送执行时段</label>
          <div class="field-inline">
            <input v-model.number="configForm.business_hours_start" type="number" min="0" max="23" class="input w-24" />
            <span>到</span>
            <input v-model.number="configForm.business_hours_end" type="number" min="1" max="24" class="input w-24" />
            <span>点</span>
          </div>
        </div>

        <div class="form-field">
          <label>熔断窗口</label>
          <div class="field-inline">
            <input v-model.number="configForm.circuit_breaker_window_min" type="number" min="1" max="240" class="input w-24" />
            <span>分钟内累计</span>
            <input v-model.number="configForm.circuit_breaker_threshold" type="number" min="1" max="20" class="input w-24" />
            <span>个账号异常即暂停</span>
          </div>
        </div>

        <div class="form-field">
          <label>自动续跟间隔</label>
          <div class="field-inline">
            <input v-model.number="configForm.followup_days" type="number" min="1" max="30" class="input w-32" />
            <span>天</span>
          </div>
        </div>
      </div>

      <div v-if="!loadingConfig" class="settings-actions">
        <button class="btn btn-primary" @click="saveConfig">保存策略配置</button>
        <button class="btn btn-ghost" @click="loadConfig">重置</button>
        <span v-if="configSaved" class="save-state">已保存</span>
      </div>
    </div>

    <div class="card settings-panel">
      <div class="settings-head">
        <div>
          <div class="settings-kicker">Sync Schedule</div>
          <h3>同步计划</h3>
        </div>
      </div>

      <div class="sync-card-grid">
        <article class="sync-card">
          <div class="sync-card-head">
            <div>
              <div class="sync-card-title">普通同步</div>
              <div class="sync-card-meta">{{ formatSyncWindow(configForm.reply_check_start_hour, configForm.reply_check_end_hour) }}</div>
            </div>
            <span class="pill">{{ configForm.reply_check_normal_interval_min }} 分钟</span>
          </div>
          <div class="sync-card-body">仅检查未标记回复的会话。</div>
          <div class="sync-card-actions">
            <button class="btn btn-secondary btn-sm" @click="openSyncDialog('normal')">编辑计划</button>
          </div>
        </article>

        <article class="sync-card">
          <div class="sync-card-head">
            <div>
              <div class="sync-card-title">全部同步</div>
              <div class="sync-card-meta">{{ formatSyncWindow(configForm.reply_check_full_start_hour, configForm.reply_check_full_end_hour) }}</div>
            </div>
            <span class="pill">{{ configForm.reply_check_full_interval_min }} 分钟</span>
          </div>
          <div class="sync-card-body">复查已回复但未完成流转的会话。</div>
          <div class="sync-card-actions">
            <button class="btn btn-secondary btn-sm" @click="openSyncDialog('full')">编辑计划</button>
          </div>
        </article>
      </div>
    </div>

    <div class="card settings-panel">
      <div class="settings-head">
        <div>
          <div class="settings-kicker">AI Integration</div>
          <h3>AI 配置</h3>
        </div>
      </div>

      <div class="settings-grid">
        <div class="form-field">
          <label>OpenAI API Key</label>
          <input v-model="aiForm.openai_api_key" class="input" placeholder="sk-..." type="password" />
        </div>
        <div class="form-field">
          <label>模型</label>
          <select v-model="aiForm.openai_model" class="input">
            <option value="gpt-4o-mini">GPT-4o-mini（推荐，快速低成本）</option>
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-3.5-turbo">GPT-3.5-turbo</option>
          </select>
        </div>
        <div class="form-field">
          <label>Twitter 二级密码</label>
          <input v-model="aiForm.twitter_password" class="input" placeholder="2580" />
        </div>
        <div class="form-field">
          <label>飞书显示名列名</label>
          <input v-model="aiForm.feishu_display_name_column" class="input" placeholder="显示名" />
        </div>
      </div>

      <div class="settings-actions">
        <button class="btn btn-primary" :disabled="savingAI" @click="saveAIConfig">
          {{ savingAI ? '保存中...' : '保存 AI 配置' }}
        </button>
        <span v-if="aiSaved" class="save-state">已保存</span>
      </div>
    </div>

    <div class="card settings-panel">
      <div class="settings-head">
        <div>
          <div class="settings-kicker">Feishu Integration</div>
          <h3>飞书集成</h3>
        </div>
      </div>

      <div v-if="loadingFeishu" class="settings-loading">加载中...</div>

      <div v-else class="settings-grid">
        <div class="form-field">
          <label>App ID</label>
          <input v-model="feishuForm.feishu_app_id" class="input" placeholder="cli_xxx" />
        </div>

        <div class="form-field">
          <label>App Secret</label>
          <input v-model="feishuForm.feishu_app_secret" class="input" placeholder="请输入或保留 ***" />
        </div>

        <div class="form-field">
          <label>App Token</label>
          <input v-model="feishuForm.feishu_app_token" class="input" placeholder="bascnxxx" />
        </div>

        <div class="form-field">
          <label>目标表 ID</label>
          <input v-model="feishuForm.feishu_table_targets" class="input" placeholder="tbl_xxx" />
        </div>

        <div class="form-field settings-span-2">
          <label>账号表 ID</label>
          <input v-model="feishuForm.feishu_table_accounts" class="input" placeholder="tbl_xxx" />
        </div>

        <div class="form-field settings-span-2">
          <label>飞书通知地址</label>
          <input
            v-model="feishuForm.feishu_notify_webhook"
            class="input"
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
          />
        </div>
      </div>

      <div v-if="!loadingFeishu" class="settings-actions">
        <button class="btn btn-primary" :disabled="savingFeishu" @click="saveFeishuConfig">保存飞书集成</button>
        <button class="btn btn-secondary" :disabled="testingFeishu" @click="testFeishuConfig">连接测试</button>
        <button class="btn btn-secondary" :disabled="testingWebhook" @click="testWebhook">通知地址测试</button>
        <button class="btn btn-ghost" @click="loadFeishuConfig">重置</button>
        <span v-if="feishuSaved" class="save-state">已保存</span>
        <span v-if="testMessage" class="test-state" :style="{ color: testOk ? '#16a34a' : '#ef4444' }">{{ testMessage }}</span>
      </div>
    </div>

    <div class="card settings-panel">
      <div class="settings-head">
        <div>
          <div class="settings-kicker">Data Maintenance</div>
          <h3>数据维护</h3>
        </div>
      </div>

      <div class="settings-grid">
        <div class="form-field">
          <label>日志保留天数</label>
          <div class="field-inline">
            <input v-model.number="maintenanceForm.logRetentionDays" type="number" min="1" max="3650" class="input w-32" />
            <span>天</span>
          </div>
        </div>

        <div class="form-field">
          <label>截图保留天数</label>
          <div class="field-inline">
            <input v-model.number="maintenanceForm.screenshotRetentionDays" type="number" min="1" max="3650" class="input w-32" />
            <span>天</span>
          </div>
        </div>
      </div>

      <div class="settings-actions">
        <button class="btn btn-primary" @click="exportDatabase">导出数据库</button>
        <button class="btn btn-secondary" @click="exportLogs('csv')">导出日志 CSV</button>
        <button class="btn btn-secondary" @click="exportLogs('json')">导出日志 JSON</button>
        <button class="btn btn-ghost" :disabled="cleaningLogs" @click="cleanupLogs">
          {{ cleaningLogs ? '清理中...' : '清理历史日志' }}
        </button>
        <button class="btn btn-ghost" :disabled="cleaningArtifacts" @click="cleanupArtifacts">
          {{ cleaningArtifacts ? '清理中...' : '清理历史截图' }}
        </button>
      </div>
    </div>

    <div class="card settings-panel">
      <h3 class="notes-title">说明</h3>
      <ul class="notes-list">
        <li>配置保存后立即生效，无需重启。</li>
        <li>发送间隔建议 15 到 40 分钟，过短容易触发平台风控。</li>
        <li>随机上限会在每日重置时分配到每个账号，不再固定同一数值。</li>
        <li>熔断触发后需要人工重置，系统不会自动恢复。</li>
        <li>飞书同步间隔用于控制目标与账号数据的拉取频率。</li>
        <li>建议长期保留核心数据库，日志和截图按周期清理。</li>
      </ul>
    </div>

    <div v-if="syncDialog.open" class="modal-backdrop" @click.self="closeSyncDialog">
      <div class="modal-box sync-modal">
        <div class="settings-head sync-modal-head">
          <div>
            <div class="settings-kicker">Schedule Editor</div>
            <h3>{{ syncDialog.title }}</h3>
          </div>
          <button class="btn btn-ghost" @click="closeSyncDialog">关闭</button>
        </div>

        <div class="settings-grid sync-modal-grid">
          <div class="form-field">
            <label>开始时间</label>
            <div class="field-inline">
              <input v-model.number="syncDialog.startHour" type="number" min="0" max="23" class="input w-24" />
              <span>点</span>
            </div>
          </div>

          <div class="form-field">
            <label>结束时间</label>
            <div class="field-inline">
              <input v-model.number="syncDialog.endHour" type="number" min="0" max="24" class="input w-24" />
              <span>点</span>
            </div>
          </div>

          <div class="form-field settings-span-2">
            <label>执行间隔</label>
            <div class="field-inline">
              <input v-model.number="syncDialog.intervalMin" type="number" min="5" max="1440" class="input w-32" />
              <span>分钟</span>
            </div>
          </div>
        </div>

        <div class="field-help">
          跨天时段可直接设置为例如 10 到 2，表示次日凌晨 2 点结束。
        </div>

        <div class="settings-actions">
          <button class="btn btn-primary" :disabled="savingSyncDialog" @click="saveSyncDialog">
            {{ savingSyncDialog ? '保存中...' : '保存计划' }}
          </button>
          <button class="btn btn-ghost" @click="closeSyncDialog">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage, getPlainErrorMessage } from '../utils/errorText'

const system = useSystemStore()

const loadingConfig = ref(true)
const configSaved = ref(false)
const configForm = reactive({
  daily_dm_limit: 5,
  daily_dm_limit_min: 5,
  daily_dm_limit_max: 5,
  min_interval_sec: 900,
  max_interval_sec: 2400,
  sync_interval_min: 30,
  reply_check_interval_min: 120,
  reply_check_normal_interval_min: 120,
  reply_check_start_hour: 10,
  reply_check_end_hour: 2,
  reply_check_full_interval_min: 360,
  reply_check_full_start_hour: 10,
  reply_check_full_end_hour: 2,
  max_retry_accounts_per_target: 3,
  followup_days: 3,
  cooldown_hours: 12,
  business_hours_start: 8,
  business_hours_end: 23,
  circuit_breaker_window_min: 30,
  circuit_breaker_threshold: 3,
})

const loadingFeishu = ref(true)
const savingFeishu = ref(false)
const testingFeishu = ref(false)
const testingWebhook = ref(false)
const savingAI = ref(false)
const feishuSaved = ref(false)
const aiSaved = ref(false)
const testOk = ref(false)
const testMessage = ref('')
const cleaningLogs = ref(false)
const cleaningArtifacts = ref(false)
const savingSyncDialog = ref(false)
const feishuForm = reactive({
  feishu_app_id: '',
  feishu_app_secret: '',
  feishu_app_token: '',
  feishu_table_targets: '',
  feishu_table_accounts: '',
  feishu_notify_webhook: ''
})
const aiForm = reactive({
  openai_api_key: '',
  openai_model: 'gpt-4o-mini',
  twitter_password: '2580',
  feishu_display_name_column: '显示名',
})
const maintenanceForm = reactive({
  logRetentionDays: 30,
  screenshotRetentionDays: 7,
})
const syncDialog = reactive({
  open: false,
  mode: 'normal',
  title: '',
  intervalMin: 120,
  startHour: 10,
  endHour: 2,
})

const toMin = (sec) => {
  if (!sec) return ''
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s ? `${m}分${s}秒` : `${m}分钟`
}

const formatHour = (hour) => {
  const val = Number(hour)
  if (!Number.isFinite(val)) return '-'
  if (val === 24) return '24:00'
  return `${String(val).padStart(2, '0')}:00`
}

const formatSyncWindow = (start, end) => `${formatHour(start)} - ${formatHour(end)}`

const loadConfig = async () => {
  loadingConfig.value = true
  try {
    const { data } = await api.get('/config')
    Object.assign(configForm, data)
    Object.assign(aiForm, {
      openai_api_key: data.openai_api_key || '',
      openai_model: data.openai_model || 'gpt-4o-mini',
      twitter_password: data.twitter_password || '',
      feishu_display_name_column: data.feishu_display_name_column || '显示名',
    })
  } catch (e) {
    system.notify(getActionErrorMessage('加载策略配置', e), 'error')
  } finally {
    loadingConfig.value = false
  }
}

const loadFeishuConfig = async () => {
  loadingFeishu.value = true
  testMessage.value = ''
  try {
    const { data } = await api.get('/feishu-config')
    feishuForm.feishu_app_id = data.feishu_app_id || ''
    feishuForm.feishu_app_secret = data.feishu_app_secret || ''
    feishuForm.feishu_app_token = data.feishu_app_token || ''
    feishuForm.feishu_table_targets = data.feishu_table_targets || ''
    feishuForm.feishu_table_accounts = data.feishu_table_accounts || ''
    feishuForm.feishu_notify_webhook = data.feishu_notify_webhook || ''
  } catch (e) {
    system.notify(getActionErrorMessage('加载飞书集成配置', e), 'error')
  } finally {
    loadingFeishu.value = false
  }
}

const saveConfig = async () => {
  try {
    if ((configForm.daily_dm_limit_min || 0) > (configForm.daily_dm_limit_max || 0)) {
      system.notify('每日上限最小值不能大于最大值', 'error')
      return
    }
    const payload = { ...configForm, daily_dm_limit: configForm.daily_dm_limit_max }
    delete payload.feishu_notify_webhook
    await api.post('/config', payload)
    configSaved.value = true
    system.notify('策略配置已保存', 'success')
    setTimeout(() => { configSaved.value = false }, 3000)
  } catch (e) {
    system.notify(getActionErrorMessage('保存策略配置', e), 'error')
  }
}

const openSyncDialog = (mode) => {
  syncDialog.mode = mode
  syncDialog.title = mode === 'full' ? '全部同步计划' : '普通同步计划'
  if (mode === 'full') {
    syncDialog.intervalMin = Number(configForm.reply_check_full_interval_min || 360)
    syncDialog.startHour = Number(configForm.reply_check_full_start_hour ?? 10)
    syncDialog.endHour = Number(configForm.reply_check_full_end_hour ?? 2)
  } else {
    syncDialog.intervalMin = Number(configForm.reply_check_normal_interval_min || configForm.reply_check_interval_min || 120)
    syncDialog.startHour = Number(configForm.reply_check_start_hour ?? 10)
    syncDialog.endHour = Number(configForm.reply_check_end_hour ?? 2)
  }
  syncDialog.open = true
}

const closeSyncDialog = () => {
  syncDialog.open = false
}

const saveSyncDialog = async () => {
  const intervalMin = Math.max(5, Number(syncDialog.intervalMin || 0))
  const startHour = Number(syncDialog.startHour)
  const endHour = Number(syncDialog.endHour)
  if (Number.isNaN(startHour) || startHour < 0 || startHour > 23) {
    system.notify('开始时间仅支持 0 到 23 点', 'error')
    return
  }
  if (Number.isNaN(endHour) || endHour < 0 || endHour > 24) {
    system.notify('结束时间仅支持 0 到 24 点', 'error')
    return
  }
  const payload = syncDialog.mode === 'full'
    ? {
        reply_check_full_interval_min: intervalMin,
        reply_check_full_start_hour: startHour,
        reply_check_full_end_hour: endHour,
      }
    : {
        reply_check_interval_min: intervalMin,
        reply_check_normal_interval_min: intervalMin,
        reply_check_start_hour: startHour,
        reply_check_end_hour: endHour,
      }
  savingSyncDialog.value = true
  try {
    await api.post('/config', payload)
    Object.assign(configForm, payload)
    configSaved.value = true
    syncDialog.open = false
    system.notify('同步计划已保存', 'success')
    setTimeout(() => { configSaved.value = false }, 3000)
  } catch (e) {
    system.notify(getActionErrorMessage('保存同步计划', e), 'error')
  } finally {
    savingSyncDialog.value = false
  }
}

const saveAIConfig = async () => {
  savingAI.value = true
  try {
    await api.post('/config', { ...aiForm })
    aiSaved.value = true
    system.notify('AI 配置已保存', 'success')
    setTimeout(() => { aiSaved.value = false }, 3000)
  } catch (e) {
    system.notify(getActionErrorMessage('保存 AI 配置', e), 'error')
  } finally {
    savingAI.value = false
  }
}

const saveFeishuConfig = async () => {
  savingFeishu.value = true
  try {
    await api.post('/feishu-config', { ...feishuForm })
    feishuSaved.value = true
    system.notify('飞书集成配置已保存', 'success')
    setTimeout(() => { feishuSaved.value = false }, 3000)
  } catch (e) {
    system.notify(getActionErrorMessage('保存飞书集成配置', e), 'error')
  } finally {
    savingFeishu.value = false
  }
}

const testFeishuConfig = async () => {
  testingFeishu.value = true
  testMessage.value = ''
  try {
    const { data } = await api.post('/feishu-config/test')
    testOk.value = !!data.ok
    testMessage.value = data.message || (data.ok ? '连接测试成功' : '连接测试失败')
  } catch (e) {
    testOk.value = false
    testMessage.value = getPlainErrorMessage(e, '连接测试未通过，请检查飞书应用配置')
  } finally {
    testingFeishu.value = false
  }
}

const testWebhook = async () => {
  testingWebhook.value = true
  testMessage.value = ''
  try {
    const { data } = await api.post('/feishu-config/test-webhook', {
      feishu_notify_webhook: feishuForm.feishu_notify_webhook
    })
    testOk.value = !!data.ok
    testMessage.value = data.message || (data.ok ? '通知地址测试成功' : '通知地址测试失败')
  } catch (e) {
    testOk.value = false
    testMessage.value = getPlainErrorMessage(e, '通知地址测试未通过，请检查通知地址')
  } finally {
    testingWebhook.value = false
  }
}

const exportDatabase = () => {
  window.open('/api/maintenance/export/database', '_blank')
}

const exportLogs = (format) => {
  const days = Math.max(1, Number(maintenanceForm.logRetentionDays || 30))
  window.open(`/api/maintenance/export/logs?format=${format}&days=${days}`, '_blank')
}

const cleanupLogs = async () => {
  cleaningLogs.value = true
  try {
    const { data } = await api.post('/logs/clear', {
      older_than_days: Math.max(1, Number(maintenanceForm.logRetentionDays || 30)),
      statuses: []
    })
    system.notify(`已清理 ${data.deleted || 0} 条历史日志`, 'success')
    await system.fetchLogs()
  } catch (e) {
    system.notify(getActionErrorMessage('清理日志', e), 'error')
  } finally {
    cleaningLogs.value = false
  }
}

const cleanupArtifacts = async () => {
  cleaningArtifacts.value = true
  try {
    const { data } = await api.post('/maintenance/cleanup/artifacts', {
      older_than_days: Math.max(1, Number(maintenanceForm.screenshotRetentionDays || 7))
    })
    system.notify(`已清理 ${data.deleted || 0} 个截图文件`, 'success')
  } catch (e) {
    system.notify(getActionErrorMessage('清理截图', e), 'error')
  } finally {
    cleaningArtifacts.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadConfig(), loadFeishuConfig()])
})
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.settings-panel {
  padding: 20px;
}

.settings-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.settings-kicker {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.settings-head h2,
.settings-head h3 {
  margin-top: 10px;
  color: var(--text-1);
  font-size: 30px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.settings-head p {
  margin-top: 12px;
  max-width: 720px;
  color: var(--text-3);
  font-size: 14px;
  line-height: 1.7;
}

.settings-loading {
  padding: 28px 0;
  text-align: center;
  color: var(--text-3);
  font-size: 14px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.sync-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.sync-card {
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 18px;
  background: rgba(255, 255, 255, 0.025);
}

.sync-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sync-card-title {
  color: var(--text-1);
  font-size: 16px;
  font-weight: 700;
}

.sync-card-meta {
  margin-top: 8px;
  color: var(--text-4);
  font-size: 12px;
}

.sync-card-body {
  margin-top: 14px;
  color: var(--text-3);
  font-size: 13px;
}

.sync-card-actions {
  margin-top: 16px;
  display: flex;
}

.settings-span-2 {
  grid-column: 1 / -1;
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

.field-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--text-3);
  font-size: 12px;
}

.field-help {
  color: var(--text-4);
  font-size: 12px;
  line-height: 1.6;
}

.settings-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 20px;
}

.save-state {
  color: #16a34a;
  font-size: 12px;
  font-weight: 600;
}

.test-state {
  font-size: 12px;
  font-weight: 600;
}

.notes-title {
  color: var(--text-2);
  font-size: 14px;
  font-weight: 700;
}

.notes-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.7;
}

.sync-modal {
  max-width: min(640px, calc(100vw - 36px));
}

.sync-modal-head {
  margin-bottom: 14px;
}

.sync-modal-grid {
  margin-top: 0;
}

@media (max-width: 900px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .sync-card-grid {
    grid-template-columns: 1fr;
  }

  .settings-span-2 {
    grid-column: auto;
  }
}
</style>
