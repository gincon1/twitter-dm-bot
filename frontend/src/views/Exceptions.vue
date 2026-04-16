<template>
  <section class="space-y-4">
    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div class="card p-4">
        <div class="text-xs" style="color: var(--text-3)">验证码异常</div>
        <div class="mt-2 text-2xl font-semibold text-amber-300">{{ captchaLogs.length }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs" style="color: var(--text-3)">发送失败</div>
        <div class="mt-2 text-2xl font-semibold text-red-300">{{ errorLogs.length }}</div>
      </div>
      <div class="card p-4">
        <div class="text-xs" style="color: var(--text-3)">总异常</div>
        <div class="mt-2 text-2xl font-semibold" style="color: var(--text-1)">{{ exceptionLogs.length }}</div>
      </div>
    </div>

    <div class="card p-3">
      <div class="flex flex-wrap items-center gap-2">
        <button class="btn-secondary" @click="clearAllHandled">一键清除全部异常</button>
        <button class="btn-ghost" @click="clearCaptchaHandled">清除验证码异常</button>
        <button class="btn-ghost" @click="clearErrorHandled">清除发送失败</button>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div class="card p-4">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold" style="color: var(--text-1)">账号异常（captcha）</h2>
          <button v-if="captchaLogs.length" class="btn-ghost" style="padding: 3px 8px; font-size: 11px;" @click="clearCaptchaHandled">
            一键清除
          </button>
        </div>
        <div class="space-y-3">
          <div v-for="log in captchaLogs" :key="log.id" class="rounded-lg border p-3" style="border-color: var(--border); background: var(--surface)">
            <div class="text-sm" style="color: var(--text-1)">账号：{{ log.account || '-' }}</div>
            <div class="mt-1 text-xs" style="color: var(--text-3)">{{ log.timestamp }} / {{ log.message }}</div>
            <button class="btn-ghost mt-2" style="padding: 3px 8px; font-size: 11px;" @click="markHandled(log.id)">标记已处理</button>
          </div>
          <div v-if="!captchaLogs.length" class="text-sm" style="color: var(--text-3)">暂无 captcha 异常</div>
        </div>
      </div>

      <div class="card p-4">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold" style="color: var(--text-1)">发送失败/限制</h2>
          <button v-if="errorLogs.length" class="btn-ghost" style="padding: 3px 8px; font-size: 11px;" @click="clearErrorHandled">
            一键清除
          </button>
        </div>
        <div class="space-y-3">
          <div v-for="log in errorLogs" :key="log.id" class="rounded-lg border p-3" style="border-color: var(--border); background: var(--surface)">
            <div class="text-sm" style="color: var(--text-1)">目标：@{{ log.target || '-' }}</div>
            <div class="mt-1 text-xs" style="color: var(--text-3)">{{ log.status }} / {{ log.message }}</div>
            <div class="mt-2 flex gap-1.5">
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 11px;" @click="requeue(log)">重新加入队列</button>
              <button class="btn-ghost" style="padding: 3px 8px; font-size: 11px;" @click="markHandled(log.id)">标记已处理</button>
            </div>
          </div>
          <div v-if="!errorLogs.length" class="text-sm" style="color: var(--text-3)">暂无发送失败记录</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { useSystemStore } from '../stores/system'
import { useTargetsStore } from '../stores/targets'
import { getActionErrorMessage } from '../utils/errorText'

const system = useSystemStore()
const targets = useTargetsStore()
const handled = ref(new Set())

const exceptionStatuses = ['error', 'captcha', 'cannot_dm', 'blocked_verification']

const exceptionLogs = computed(() =>
  system.logs.filter((x) => exceptionStatuses.includes(String(x.status || '')) && !handled.value.has(x.id))
)
const captchaLogs = computed(() => exceptionLogs.value.filter((x) => x.status === 'captcha'))
const errorLogs = computed(() => exceptionLogs.value.filter((x) => x.status !== 'captcha'))

const markHandled = (id) => {
  handled.value.add(id)
  system.notify('已标记处理', 'success')
}

const clearByStatuses = async (statuses, label) => {
  try {
    const { deleted = 0 } = await system.clearLogs(statuses)
    handled.value = new Set()
    if (!deleted) {
      system.notify(`当前没有可清除的${label}`, 'warn')
      return
    }
    system.notify(`已清除 ${deleted} 条${label}`, 'success')
  } catch (e) {
    system.notify(getActionErrorMessage('清除异常记录', e), 'error')
  }
}

const clearAllHandled = async () => clearByStatuses(exceptionStatuses, '异常')
const clearCaptchaHandled = async () => clearByStatuses(['captcha'], '验证码异常')
const clearErrorHandled = async () =>
  clearByStatuses(['error', 'cannot_dm', 'blocked_verification', 'target_not_found', 'skipped'], '发送失败异常')

const requeue = async (log) => {
  try {
    await targets.fetchTargets()
    const target = targets.targets.find((x) => x.twitter_username === log.target)
    if (!target) {
      system.notify('未找到对应目标记录，无法重置', 'warn')
      return
    }
    await targets.resetTarget(target.record_id)
  } catch (e) {
    system.notify(getActionErrorMessage('重入队列', e), 'error')
  }
}

onMounted(async () => {
  try {
    await system.fetchLogs()
  } catch (e) {
    system.notify(getActionErrorMessage('加载异常日志', e), 'error')
  }
})
</script>
