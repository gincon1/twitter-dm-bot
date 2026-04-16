import { defineStore } from 'pinia'
import api from '../api'
import { useSystemStore } from './system'

const defaultFilters = () => ({
  search: '',
  type: '',
  status: '',
  priority: '',
  language: '',
  source: '',
  tags: '',
  kol_tier: '',
  content_type: '',
  track: '',
  cooperation: '',
  followers_min: '',
  followers_max: '',
  chain: '',
  stage: '',
  project_type: ''
})

const filterMeta = {
  search: '关键词',
  type: '类型',
  status: '状态',
  priority: '优先级',
  language: '语言',
  source: '来源',
  tags: '标签',
  kol_tier: 'KOL量级',
  content_type: '内容方向',
  track: '赛道',
  cooperation: '合作意向',
  followers_min: '粉丝最小值',
  followers_max: '粉丝最大值',
  chain: '所属链',
  stage: '阶段',
  project_type: '项目类型'
}

export const useTargetsStore = defineStore('targets', {
  state: () => ({
    targets: [],
    loading: false,
    filters: defaultFilters(),
    page: 1,
    pageSize: 20,
    selectedTargetIds: [],
    segments: []
  }),
  getters: {
    pagedTargets(state) {
      const start = (state.page - 1) * state.pageSize
      return state.targets.slice(start, start + state.pageSize)
    },
    totalPages(state) {
      return Math.max(1, Math.ceil(state.targets.length / state.pageSize))
    },
    activeFilterCount(state) {
      return Object.values(state.filters).filter((v) => String(v).trim() !== '').length
    },
    activeFilterTags(state) {
      const tags = []
      for (const [k, v] of Object.entries(state.filters)) {
        if (String(v).trim() === '') continue
        tags.push({ key: k, label: filterMeta[k] || k, value: String(v) })
      }
      return tags
    },
    selectedCount(state) {
      return state.selectedTargetIds.length
    },
    allPageSelected(state) {
      if (!state.targets.length) return false
      const current = state.targets.slice((state.page - 1) * state.pageSize, state.page * state.pageSize)
      if (!current.length) return false
      const selected = new Set(state.selectedTargetIds)
      return current.every((x) => selected.has(x.record_id))
    }
  },
  actions: {
    setFilter(key, value) {
      this.filters[key] = value
    },
    resetFilters() {
      this.filters = defaultFilters()
      this.page = 1
    },
    async fetchTargets() {
      this.loading = true
      try {
        const params = {}
        for (const [k, v] of Object.entries(this.filters)) {
          if (String(v).trim() !== '') {
            params[k] = v
          }
        }
        const { data } = await api.get('/targets', { params })
        this.targets = data
        if (this.page > this.totalPages) {
          this.page = this.totalPages
        }
      } finally {
        this.loading = false
      }
    },
    async fetchSegments() {
      const { data } = await api.get('/segments')
      this.segments = data
    },
    toggleSelect(targetId) {
      if (this.selectedTargetIds.includes(targetId)) {
        this.selectedTargetIds = this.selectedTargetIds.filter((x) => x !== targetId)
      } else {
        this.selectedTargetIds.push(targetId)
      }
    },
    setSelectAllForCurrentPage(enabled) {
      const currentIds = this.pagedTargets.map((x) => x.record_id)
      const selected = new Set(this.selectedTargetIds)
      if (enabled) {
        currentIds.forEach((id) => selected.add(id))
      } else {
        currentIds.forEach((id) => selected.delete(id))
      }
      this.selectedTargetIds = Array.from(selected)
    },
    clearSelection() {
      this.selectedTargetIds = []
    },
    removeFilterTag(key) {
      if (Object.prototype.hasOwnProperty.call(this.filters, key)) {
        this.filters[key] = ''
      }
    },
    async addSelectedToSegment({ segmentId, createNewName = '', createNewDescription = '' }) {
      const system = useSystemStore()
      let sid = segmentId
      let segName = ''
      if (!sid && !createNewName.trim()) {
        throw new Error('请选择或创建目标分组')
      }
      if (!sid) {
        const { data } = await api.post('/segments', {
          name: createNewName.trim(),
          description: createNewDescription.trim()
        })
        sid = data.id
        segName = createNewName.trim()
      } else {
        const existing = this.segments.find((x) => x.id === sid)
        segName = existing?.name || sid
      }

      const selected = new Set(this.selectedTargetIds)
      const targets = this.targets
        .filter((x) => selected.has(x.record_id))
        .map((x) => ({
          id: x.record_id,
          source: x._source || 'local',
          username: x.twitter_username || ''
        }))

      const { data } = await api.post(`/segments/${sid}/targets`, { targets })
      await this.fetchSegments()
      system.notify(`已添加 ${data.inserted ?? targets.length} 人到「${segName}」`, 'success')
      return { segmentId: sid, inserted: data.inserted ?? targets.length }
    },
    async skipTarget(recordId, reason = '人工标记跳过') {
      const system = useSystemStore()
      await api.post(`/targets/${recordId}/skip`, { reason })
      await this.fetchTargets()
      system.notify('目标已标记跳过', 'warn')
    },
    async resetTarget(recordId) {
      const system = useSystemStore()
      await api.post(`/targets/${recordId}/reset`)
      await this.fetchTargets()
      system.notify('目标已重置为待发送', 'success')
    },
    async createTarget(data) {
      const system = useSystemStore()
      await api.post('/targets', data)
      await this.fetchTargets()
      system.notify('目标已添加', 'success')
    },
    async importTargets(rows) {
      const system = useSystemStore()
      const { data } = await api.post('/targets/import', { rows })
      await this.fetchTargets()
      system.notify(`成功导入 ${data.imported} 条目标`, 'success')
    },
    async deleteTarget(recordId) {
      const system = useSystemStore()
      await api.delete(`/targets/${recordId}`)
      await this.fetchTargets()
      this.selectedTargetIds = this.selectedTargetIds.filter((x) => x !== recordId)
      system.notify('目标已删除', 'warn')
    },
    async syncFeishu() {
      const system = useSystemStore()
      await api.post('/sync-feishu')
      await this.fetchTargets()
      system.notify('飞书数据已同步', 'success')
    },
    setPage(page) {
      this.page = page
    }
  }
})
