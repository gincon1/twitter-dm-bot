import { defineStore } from 'pinia'
import api from '../api'

export const useSystemStore = defineStore('system', {
  state: () => ({
    status: {
      running: false,
      paused: false,
      pause_reason: '',
      active_accounts: 0,
      today_total_sent: 0,
      pending_targets: 0,
      next_run_time: null,
      last_sync_time: null,
      circuit_breaker_tripped: false,
      circuit_breaker_tripped_at: null,
      circuit_breaker_recent_failures: 0,
      circuit_breaker_reason: '',
      circuit_breaker_last_reset_by: ''
    },
    stats: {
      today: { sent: 0, skipped: 0, errors: 0, replies: 0 },
      by_account: {},
      conversations: { total: 0, contacted: 0, replied: 0, manual_takeover: 0, completed: 0, replied_today: 0 },
      recent_replies: [],
      pending_replies: [],
      funnel: { pending: 0, contacted: 0, replied: 0, manual_takeover: 0, completed: 0 }
    },
    logs: [],
    toasts: [],
    now: new Date(),
    sse: null,
    statusTimer: null,
    clockTimer: null
  }),
  getters: {
    pageRunning(state) {
      return state.status.running && !state.status.paused
    }
  },
  actions: {
    notify(message, type = 'info') {
      const id = Date.now() + Math.random()
      this.toasts.push({ id, message, type })
      setTimeout(() => {
        this.toasts = this.toasts.filter((x) => x.id !== id)
      }, 3200)
    },
    removeToast(id) {
      this.toasts = this.toasts.filter((x) => x.id !== id)
    },
    async refreshStatus() {
      const { data } = await api.get('/status')
      this.status = data
    },
    async refreshStats() {
      const { data } = await api.get('/stats')
      this.stats = data
    },
    async fetchLogs() {
      const { data } = await api.get('/logs', { params: { limit: 200 } })
      this.logs = [...data].reverse()
    },
    async clearLogs(statuses = []) {
      const payload = Array.isArray(statuses) ? statuses : []
      const { data } = await api.post('/logs/clear', { statuses: payload })
      await this.fetchLogs()
      return data
    },
    connectLogs() {
      if (this.sse) {
        return
      }
      this.sse = new EventSource('/api/logs/stream')
      this.sse.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          this.logs.push(payload)
          if (this.logs.length > 800) {
            this.logs = this.logs.slice(-800)
          }
        } catch (e) {
          // noop
        }
      }
      this.sse.onerror = () => {
        this.notify('日志流连接中断，正在重连', 'warn')
        this.disconnectLogs()
        setTimeout(() => this.connectLogs(), 2500)
      }
    },
    disconnectLogs() {
      if (this.sse) {
        this.sse.close()
        this.sse = null
      }
    },
    async startSystem() {
      await api.post('/start')
      await this.refreshStatus()
      this.notify('系统已启动', 'success')
    },
    async pauseSystem() {
      await api.post('/pause')
      await this.refreshStatus()
      this.notify('系统已暂停执行', 'warn')
    },
    async resumeSystem() {
      await api.post('/resume')
      await this.refreshStatus()
      this.notify('系统已恢复', 'success')
    },
    async stopSystem() {
      await api.post('/stop')
      await this.refreshStatus()
      this.notify('系统已停止', 'warn')
    },
    async runNow() {
      await api.post('/run-now')
      await this.refreshStatus()
      this.notify('已触发立即执行', 'info')
    },
    async checkReplies() {
      await api.post('/check-replies')
      await this.refreshStats()
      this.notify('已触发普通同步', 'info')
    },
    async checkRepliesFull() {
      await api.post('/check-replies-full')
      await this.refreshStats()
      this.notify('已触发全部同步', 'info')
    },
    async runFollowups() {
      const { data } = await api.post('/run-followups')
      await this.refreshStats()
      return data
    },
    async previewFollowups() {
      const { data } = await api.get('/followups/preview')
      return data
    },
    async getFollowupRunStatus() {
      const { data } = await api.get('/followups/status')
      return data
    },
    async resetCircuitBreaker(resetBy = 'manual') {
      const { data } = await api.post('/circuit-breaker/reset', { reset_by: resetBy })
      await this.refreshStatus()
      this.notify('熔断已解除', 'success')
      return data
    },
    startPolling() {
      if (!this.statusTimer) {
        this.statusTimer = setInterval(async () => {
          try {
            await Promise.all([this.refreshStatus(), this.refreshStats()])
          } catch (e) {
            // noop
          }
        }, 10000)
      }
      if (!this.clockTimer) {
        this.clockTimer = setInterval(() => {
          this.now = new Date()
        }, 1000)
      }
    },
    stopPolling() {
      if (this.statusTimer) {
        clearInterval(this.statusTimer)
        this.statusTimer = null
      }
      if (this.clockTimer) {
        clearInterval(this.clockTimer)
        this.clockTimer = null
      }
    },
    async initRealtime() {
      await Promise.all([this.refreshStatus(), this.refreshStats(), this.fetchLogs()])
      this.connectLogs()
      this.startPolling()
    },
    cleanupRealtime() {
      this.disconnectLogs()
      this.stopPolling()
    }
  }
})
