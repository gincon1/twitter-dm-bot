<template>
  <section class="space-y-4 pb-20">
    <div class="card p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <button class="btn-secondary" @click="filterOpen = !filterOpen">
            筛选
            <span
              class="ml-1 inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 py-0.5 text-[11px]"
              style="background: var(--surface); color: var(--text-2)"
            >{{ targets.activeFilterCount }}</span>
          </button>
          <span v-if="route.query.segmentId" class="text-xs" style="color: var(--text-3)">
            当前添加到目标分组：{{ route.query.segmentId }}
          </span>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" @click="showManual = true">+ 添加</button>
          <button class="btn-secondary" @click="showImport = true">导入 CSV</button>
        </div>
      </div>

      <div v-if="filterOpen" class="mt-3 space-y-3">
        <div class="grid grid-cols-1 gap-2 md:grid-cols-5">
          <input v-model="targets.filters.search" class="input" placeholder="关键词搜索" />
          <select v-model="targets.filters.type" class="input">
            <option value="">全部类型</option>
            <option value="KOL">KOL</option>
            <option value="项目方">项目方</option>
          </select>
          <select v-model="targets.filters.status" class="input">
            <option value="">全部状态</option>
            <option value="待发送">待发送</option>
            <option value="已发送">已发送</option>
            <option value="已回复">已回复</option>
            <option value="人工接管">人工处理</option>
            <option value="完成">完成</option>
            <option value="跳过">跳过</option>
            <option value="不可DM">不可DM</option>
          </select>
          <select v-model="targets.filters.priority" class="input">
            <option value="">全部优先级</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
          <select v-model="targets.filters.language" class="input">
            <option value="">全部语言</option>
            <option value="EN">EN</option>
            <option value="CN">CN</option>
            <option value="KR">KR</option>
            <option value="JP">JP</option>
          </select>
        </div>

        <div class="grid grid-cols-1 gap-2 md:grid-cols-5">
          <select v-model="targets.filters.kol_tier" class="input">
            <option value="">KOL量级</option>
            <option value="头部">头部</option>
            <option value="腰部">腰部</option>
            <option value="尾部">尾部</option>
          </select>
          <select v-model="targets.filters.content_type" class="input">
            <option value="">内容方向</option>
            <option value="技术">技术</option>
            <option value="投资">投资</option>
            <option value="交易">交易</option>
            <option value="社区">社区</option>
            <option value="媒体">媒体</option>
          </select>
          <select v-model="targets.filters.track" class="input">
            <option value="">赛道偏好</option>
            <option value="DeFi">DeFi</option>
            <option value="L2">L2</option>
            <option value="NFT">NFT</option>
            <option value="GameFi">GameFi</option>
            <option value="AI">AI</option>
            <option value="其他">其他</option>
          </select>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="targets.filters.followers_min" type="number" class="input" placeholder="粉丝最小值" />
            <input v-model="targets.filters.followers_max" type="number" class="input" placeholder="粉丝最大值" />
          </div>
          <select v-model="targets.filters.cooperation" class="input">
            <option value="">合作意向</option>
            <option value="未知">未知</option>
            <option value="有意向">有意向</option>
            <option value="已合作">已合作</option>
            <option value="拒绝">拒绝</option>
          </select>
        </div>

        <div v-if="showProjectFilters" class="grid grid-cols-1 gap-2 md:grid-cols-3">
          <select v-model="targets.filters.chain" class="input">
            <option value="">所属链</option>
            <option value="ETH">ETH</option>
            <option value="SOL">SOL</option>
            <option value="BNB">BNB</option>
            <option value="其他">其他</option>
          </select>
          <select v-model="targets.filters.stage" class="input">
            <option value="">项目阶段</option>
            <option value="早期">早期</option>
            <option value="测试网">测试网</option>
            <option value="已上线">已上线</option>
            <option value="已上所">已上所</option>
          </select>
          <select v-model="targets.filters.project_type" class="input">
            <option value="">项目类型</option>
            <option value="DeFi">DeFi</option>
            <option value="GameFi">GameFi</option>
            <option value="NFT">NFT</option>
            <option value="基础设施">基础设施</option>
            <option value="钱包">钱包</option>
          </select>
        </div>

        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" @click="searchNow">查询</button>
          <button class="btn-secondary" @click="resetFilters">重置</button>
          <button class="btn-secondary" @click="syncNow">同步飞书数据</button>
        </div>
      </div>
    </div>

    <div v-if="targets.activeFilterTags.length" class="flex flex-wrap gap-2">
      <button
        v-for="tag in targets.activeFilterTags"
        :key="tag.key"
        class="btn-ghost"
        style="background: var(--surface); color: var(--text-2)"
        @click="removeFilterTag(tag.key)"
      >
        {{ tag.label }}: {{ tag.value }} ×
      </button>
    </div>

    <div class="text-sm" style="color: var(--text-2)">
      共 <span class="font-semibold" style="color: var(--text-1)">{{ targets.targets.length }}</span> 条结果
      <span class="ml-3">已选 {{ targets.selectedCount }} 人</span>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="w-[40px]">
              <input type="checkbox" :checked="targets.allPageSelected" @change="toggleSelectAllPage" />
            </th>
            <th>用户名</th>
            <th>归属</th>
            <th>来源</th>
            <th>类型</th>
            <th>项目名</th>
            <th>优先级</th>
            <th>语言</th>
            <th>粉丝数</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in targets.pagedTargets" :key="item.record_id">
            <td>
              <input
                type="checkbox"
                :checked="targets.selectedTargetIds.includes(item.record_id)"
                @change="targets.toggleSelect(item.record_id)"
              />
            </td>
            <td style="color: var(--text-1)">@{{ item.twitter_username }}</td>
            <td>
              <div style="color: var(--text-1)">{{ item.client_group || '-' }}</div>
              <div v-if="item.client_note" class="text-xs" style="color: var(--text-4)">
                {{ item.client_note }}
              </div>
            </td>
            <td style="color: var(--text-2)">{{ item._source === 'feishu' ? '飞书同步' : '本地录入' }}</td>
            <td style="color: var(--text-2)">{{ item.type || '-' }}</td>
            <td style="color: var(--text-2)">{{ item.project_name || '-' }}</td>
            <td style="color: var(--text-2)">{{ item.priority || '-' }}</td>
            <td style="color: var(--text-2)">{{ item.language || '-' }}</td>
            <td style="color: var(--text-2)">{{ item.followers || 0 }}</td>
            <td style="color: var(--text-2)">{{ item.status || '-' }}</td>
            <td>
              <div class="flex flex-wrap gap-1.5">
                <button v-if="item.status === '待发送'" class="btn-ghost" @click="skip(item.record_id)">跳过</button>
                <button
                  v-if="item.status === '跳过' || item.status === '不可DM'"
                  class="btn-secondary"
                  @click="reset(item.record_id)"
                >重置</button>
                <button v-if="item._source === 'local'" class="btn-ghost" @click="remove(item.record_id)">删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!targets.pagedTargets.length">
            <td colspan="11" class="py-8 text-center" style="color: var(--text-3)">暂无目标数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-between rounded-xl border px-4 py-3 text-sm" style="border-color: var(--border); background: var(--surface)">
      <span style="color: var(--text-2)">第 {{ targets.page }} / {{ targets.totalPages }} 页，共 {{ targets.targets.length }} 条</span>
      <div class="flex gap-1.5">
        <button class="btn-ghost" :disabled="targets.page <= 1" @click="targets.setPage(targets.page - 1)">上一页</button>
        <button class="btn-ghost" :disabled="targets.page >= targets.totalPages" @click="targets.setPage(targets.page + 1)">下一页</button>
      </div>
    </div>

    <div v-if="targets.selectedCount > 0" class="fixed bottom-4 left-1/2 z-40 -translate-x-1/2">
      <div class="flex items-center gap-3 rounded-xl border px-4 py-3 shadow-lg" style="background: var(--panel); border-color: var(--border)">
        <span class="text-sm" style="color: var(--text-2)">已选 {{ targets.selectedCount }} 人</span>
        <button class="btn-primary" @click="openAddToSegment">加入目标分组</button>
      </div>
    </div>

    <div v-if="showManual" class="modal-backdrop" @click.self="showManual = false">
      <div class="modal-box">
        <h3 class="mb-4 text-base font-semibold" style="color: var(--text-1)">新增目标</h3>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">X 用户名 *</label>
            <input v-model="manualForm.twitter_username" class="input w-full" placeholder="@username 或 username" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs" style="color: var(--text-3)">类型</label>
              <select v-model="manualForm.type" class="input w-full">
                <option value="">-</option>
                <option value="KOL">KOL</option>
                <option value="项目方">项目方</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-xs" style="color: var(--text-3)">优先级</label>
              <select v-model="manualForm.priority" class="input w-full">
                <option value="高">高</option>
                <option value="中">中</option>
                <option value="低">低</option>
              </select>
            </div>
          </div>
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">项目名</label>
            <input v-model="manualForm.project_name" class="input w-full" placeholder="输入项目名称" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <input v-model="manualForm.client_group" class="input" placeholder="归属，如 Nado" />
            <input v-model="manualForm.client_note" class="input" placeholder="归属备注（可选）" />
          </div>
          <div class="grid grid-cols-3 gap-3">
            <input v-model="manualForm.language" class="input" placeholder="语言 EN/CN" />
            <input v-model="manualForm.source" class="input" placeholder="来源渠道" />
            <input v-model="manualForm.tags" class="input" placeholder="标签,逗号分隔" />
          </div>
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-ghost" @click="showManual = false">取消</button>
          <button class="btn-primary" @click="submitManual">添加</button>
        </div>
      </div>
    </div>

    <div v-if="showImport" class="modal-backdrop" @click.self="showImport = false">
      <div class="modal-box w-full max-w-3xl">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="text-base font-semibold" style="color: var(--text-1)">批量导入目标</h3>
          <button class="btn-secondary" @click="downloadTemplate">下载模板</button>
        </div>
        <textarea
          v-model="csvText"
          class="input h-48 w-full font-mono text-xs"
          placeholder="粘贴 CSV 内容，支持模板全字段"
        />
        <div v-if="parseError" class="mt-2 text-xs" style="color: #ef4444">{{ parseError }}</div>
        <div v-if="parsedRows.length" class="mt-2 text-xs" style="color: #16a34a">已解析 {{ parsedRows.length }} 条</div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-ghost" @click="showImport = false">取消</button>
          <button class="btn-secondary" @click="parseCsv">预览</button>
          <button class="btn-primary" :disabled="!parsedRows.length" @click="submitImport">导入</button>
        </div>
      </div>
    </div>

    <div v-if="showAddSegment" class="modal-backdrop" @click.self="showAddSegment = false">
      <div class="modal-box">
        <h3 class="mb-4 text-base font-semibold" style="color: var(--text-1)">加入目标分组</h3>
        <div class="mb-3 flex gap-2">
          <button class="btn-secondary" :class="segmentMode === 'existing' ? 'segment-tab-active' : ''" @click="segmentMode = 'existing'">选择已有包</button>
          <button class="btn-secondary" :class="segmentMode === 'new' ? 'segment-tab-active' : ''" @click="segmentMode = 'new'">+ 新建包</button>
        </div>
        <div v-if="segmentMode === 'existing'" class="space-y-2">
          <select v-model="selectedSegmentId" class="input w-full">
            <option value="">请选择目标分组</option>
            <option v-for="s in targets.segments" :key="s.id" :value="s.id">
              {{ s.name }}（{{ s.count || 0 }}）
            </option>
          </select>
        </div>
        <div v-else class="space-y-2">
          <input v-model="newSegmentName" class="input" placeholder="新包名称 *" />
          <textarea v-model="newSegmentDesc" class="input h-24" placeholder="描述（可选）" />
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-ghost" @click="showAddSegment = false">取消</button>
          <button class="btn-primary" @click="confirmAddToSegment">确定</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useSystemStore } from '../stores/system'
import { useTargetsStore } from '../stores/targets'
import { getActionErrorMessage } from '../utils/errorText'

const route = useRoute()
const system = useSystemStore()
const targets = useTargetsStore()

const filterOpen = ref(false)
const showManual = ref(false)
const showImport = ref(false)
const showAddSegment = ref(false)

const manualForm = ref({
  twitter_username: '',
  type: '',
  project_name: '',
  client_group: '',
  client_note: '',
  priority: '中',
  language: '',
  source: '',
  tags: ''
})

const csvText = ref('')
const parsedRows = ref([])
const parseError = ref('')

const segmentMode = ref('existing')
const selectedSegmentId = ref('')
const newSegmentName = ref('')
const newSegmentDesc = ref('')

const showProjectFilters = computed(() => {
  return (
    targets.filters.type === '项目方' ||
    !!targets.filters.chain ||
    !!targets.filters.stage ||
    !!targets.filters.project_type
  )
})

const searchNow = async () => {
  targets.setPage(1)
  try {
    await targets.fetchTargets()
  } catch (e) {
    system.notify(getActionErrorMessage('查询目标', e), 'error')
  }
}

const resetFilters = async () => {
  targets.resetFilters()
  await searchNow()
}

const syncNow = async () => {
  try {
    await targets.syncFeishu()
  } catch (e) {
    system.notify(getActionErrorMessage('同步目标数据', e), 'error')
  }
}

const skip = async (recordId) => {
  try {
    await targets.skipTarget(recordId, '人工标记跳过')
  } catch (e) {
    system.notify(getActionErrorMessage('标记跳过', e), 'error')
  }
}

const reset = async (recordId) => {
  try {
    await targets.resetTarget(recordId)
  } catch (e) {
    system.notify(getActionErrorMessage('重置目标状态', e), 'error')
  }
}

const remove = async (recordId) => {
  try {
    await targets.deleteTarget(recordId)
  } catch (e) {
    system.notify(getActionErrorMessage('删除目标', e), 'error')
  }
}

const submitManual = async () => {
  try {
    await targets.createTarget(manualForm.value)
    manualForm.value = {
      twitter_username: '',
      type: '',
      project_name: '',
      client_group: '',
      client_note: '',
      priority: '中',
      language: '',
      source: '',
      tags: ''
    }
    showManual.value = false
  } catch (e) {
    system.notify(getActionErrorMessage('添加目标', e), 'error')
  }
}

const normalizeHeader = (h) => String(h || '').trim().toLowerCase()

const parseCsv = () => {
  parseError.value = ''
  parsedRows.value = []
  const text = csvText.value.trim()
  if (!text) {
    parseError.value = '请先粘贴内容'
    return
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!lines.length) {
    parseError.value = '内容为空'
    return
  }
  const first = lines[0]
  const isCsv = first.includes(',')

  if (!isCsv) {
    parsedRows.value = lines.map((x) => ({
      twitter_username: x.replace(/^@/, ''),
      type: '',
      client_group: '',
      client_note: '',
      priority: '中',
      language: '',
      source: '',
      tags: '',
      followers: 0,
      kol_tier: '',
      content_type: '',
      track: '',
      cooperation: '',
      project_name: '',
      chain: '',
      stage: '',
      project_type: '',
      contact_role: '',
      note: ''
    }))
    return
  }

  const headers = first.split(',').map(normalizeHeader)
  const rows = []
  for (const line of lines.slice(1)) {
    const cols = line.split(',').map((c) => c.trim())
    const data = {}
    headers.forEach((h, idx) => {
      data[h] = cols[idx] || ''
    })
    const username = String(data.twitter_username || '').replace(/^@/, '').trim()
    if (!username) continue
    rows.push({
      twitter_username: username,
      type: data.type || '',
      client_group: data.client_group || '',
      client_note: data.client_note || '',
      priority: data.priority || '中',
      language: data.language || '',
      source: data.source || '',
      tags: data.tags || '',
      followers: Number(data.followers || 0) || 0,
      kol_tier: data.kol_tier || '',
      content_type: data.content_type || '',
      track: data.track || '',
      cooperation: data.cooperation || '',
      project_name: data.project_name || '',
      chain: data.chain || '',
      stage: data.stage || '',
      project_type: data.project_type || '',
      contact_role: data.contact_role || '',
      note: data.note || ''
    })
  }
  if (!rows.length) {
    parseError.value = '未解析到有效记录'
    return
  }
  parsedRows.value = rows
}

const submitImport = async () => {
  try {
    await targets.importTargets(parsedRows.value)
    csvText.value = ''
    parsedRows.value = []
    showImport.value = false
  } catch (e) {
    system.notify(getActionErrorMessage('导入目标', e), 'error')
  }
}

const downloadTemplate = () => {
  const link = document.createElement('a')
  link.href = '/api/targets/template'
  link.download = '目标导入模板.csv'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

const removeFilterTag = async (key) => {
  targets.removeFilterTag(key)
  await searchNow()
}

const toggleSelectAllPage = () => {
  targets.setSelectAllForCurrentPage(!targets.allPageSelected)
}

const openAddToSegment = async () => {
  try {
    await targets.fetchSegments()
    selectedSegmentId.value = String(route.query.segmentId || '')
    segmentMode.value = selectedSegmentId.value ? 'existing' : 'existing'
    showAddSegment.value = true
  } catch (e) {
    system.notify(getActionErrorMessage('加载目标分组', e), 'error')
  }
}

const confirmAddToSegment = async () => {
  try {
    const result = await targets.addSelectedToSegment({
      segmentId: segmentMode.value === 'existing' ? selectedSegmentId.value : '',
      createNewName: segmentMode.value === 'new' ? newSegmentName.value : '',
      createNewDescription: segmentMode.value === 'new' ? newSegmentDesc.value : ''
    })
    showAddSegment.value = false
    if (result?.segmentId) {
      selectedSegmentId.value = result.segmentId
    }
  } catch (e) {
    system.notify(getActionErrorMessage('加入目标分组', e), 'error')
  }
}

watch(
  () => route.query.segmentId,
  (v) => {
    if (v) selectedSegmentId.value = String(v)
  }
)

onMounted(async () => {
  await searchNow()
  await targets.fetchSegments()
  if (route.query.segmentId) {
    selectedSegmentId.value = String(route.query.segmentId)
  }
})
</script>

<style scoped>
.segment-tab-active {
  background: var(--surface) !important;
  color: var(--text-1) !important;
}
</style>
