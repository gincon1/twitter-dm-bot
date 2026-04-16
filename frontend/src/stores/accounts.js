import { defineStore } from 'pinia'
import api from '../api'
import { useSystemStore } from './system'

const accountSelectionKey = (acc) => String(acc?.record_id || acc?.id || acc?.profile_id || '').trim()

export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    accounts: [],
    loading: false,
    filter: '全部',
    segments: [],
    selectedSegmentId: null,
    selectedAccountIds: []
  }),
  getters: {
    filteredAccounts(state) {
      if (state.filter === '全部') {
        return state.accounts
      }
      return state.accounts.filter((x) => x.status === state.filter)
    },
    selectedAccounts(state) {
      const selected = new Set(state.selectedAccountIds)
      return state.accounts.filter((x) => selected.has(accountSelectionKey(x)))
    }
  },
  actions: {
    setFilter(v) {
      this.filter = v
    },
    async fetchAccounts() {
      this.loading = true
      try {
        const { data } = await api.get('/accounts')
        this.accounts = data
      } finally {
        this.loading = false
      }
    },
    async fetchSegments() {
      const { data } = await api.get('/segments')
      this.segments = data
    },
    setSelectedSegment(id) {
      this.selectedSegmentId = id || null
      this.clearSelection()
    },
    selectAccount(id) {
      const key = String(id || '').trim()
      if (!key) return
      if (!this.selectedAccountIds.includes(key)) {
        this.selectedAccountIds.push(key)
      }
    },
    unselectAccount(id) {
      const key = String(id || '').trim()
      this.selectedAccountIds = this.selectedAccountIds.filter((x) => x !== key)
    },
    toggleAccountSelection(id) {
      if (this.selectedAccountIds.includes(id)) {
        this.unselectAccount(id)
      } else {
        this.selectAccount(id)
      }
    },
    clearSelection() {
      this.selectedAccountIds = []
    },
    selectAllFiltered() {
      const ids = this.filteredAccounts.map((x) => accountSelectionKey(x)).filter(Boolean)
      if (!ids.length) return
      this.selectedAccountIds = Array.from(new Set(ids))
    },
    async runSegment(segmentId, accountIds, waitBetween = false, clientGroup = '') {
      const system = useSystemStore()
      await api.post(`/segments/${segmentId}/run`, {
        account_ids: accountIds,
        wait_between: waitBetween,
        client_group: clientGroup
      })
      system.notify('目标分组分发已启动', 'success')
    },
    async toggleAccount(recordId, status) {
      const system = useSystemStore()
      await api.post(`/accounts/${recordId}/toggle`, { status })
      await this.fetchAccounts()
      system.notify(`账号状态已改为 ${status}`, 'success')
    },
    async testAccount(recordId) {
      const system = useSystemStore()
      const { data } = await api.post(`/accounts/${recordId}/test`)
      if (data.ok) {
        system.notify(`连接测试成功: ${data.message}`, 'success')
      } else {
        system.notify(`连接测试失败: ${data.message}`, 'error')
      }
      return data
    },
    async createAccount(data) {
      const system = useSystemStore()
      await api.post('/accounts', data)
      await this.fetchAccounts()
      system.notify('账号已添加', 'success')
    },
    async deleteAccount(recordId) {
      const system = useSystemStore()
      await api.delete(`/accounts/${recordId}`)
      await this.fetchAccounts()
      system.notify('账号已删除', 'warn')
    }
  }
})
