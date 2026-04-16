<template>
  <section class="space-y-4">
    <div v-if="!isDetail" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold" style="color: var(--text-1)">目标分组</h2>
        <button class="btn-primary" @click="showCreate = true">+ 新建目标分组</button>
      </div>

      <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="seg in segments" :key="seg.id" class="card p-4">
          <div class="text-base font-semibold" style="color: var(--text-1)">{{ seg.name }}</div>
          <div class="mt-1 line-clamp-2 text-xs" style="color: var(--text-3)">{{ seg.description || '—' }}</div>
          <div class="mt-3 flex items-center justify-between text-xs" style="color: var(--text-2)">
            <span>人数：{{ seg.count || 0 }}</span>
            <span>{{ formatTime(seg.created_at) }}</span>
          </div>
          <div class="mt-3 flex gap-2">
            <button class="btn-secondary" @click="goDetail(seg.id)">查看详情</button>
            <button class="btn-ghost" @click="removeSegment(seg.id)">删除</button>
          </div>
        </div>
        <div v-if="!segments.length" class="card p-6 text-center text-sm" style="color: var(--text-3)">
          暂无目标分组
        </div>
      </div>
    </div>

    <div v-else class="space-y-4">
      <div class="card p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="text-base font-semibold" style="color: var(--text-1)">{{ detail.name || '-' }}</div>
            <div class="mt-1 text-xs" style="color: var(--text-3)">
              人数：{{ detail.count || 0 }} ｜ {{ detail.description || '无描述' }}
            </div>
          </div>
          <div class="flex gap-2">
            <button class="btn-secondary" @click="continueAdd">继续添加</button>
            <button class="btn-ghost" @click="backToList">返回列表</button>
          </div>
        </div>
      </div>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>类型</th>
              <th>量级</th>
              <th>赛道</th>
              <th>优先级</th>
              <th>来源</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in detailTargets" :key="item.target_id">
              <td style="color: var(--text-1)">@{{ item.target.twitter_username || item.twitter_username || '-' }}</td>
              <td style="color: var(--text-2)">{{ item.target.type || '-' }}</td>
              <td style="color: var(--text-2)">{{ item.target.kol_tier || '-' }}</td>
              <td style="color: var(--text-2)">{{ item.target.track || '-' }}</td>
              <td style="color: var(--text-2)">{{ item.target.priority || '-' }}</td>
              <td style="color: var(--text-2)">{{ item.target_source === 'feishu' ? '飞书同步' : '本地录入' }}</td>
              <td style="color: var(--text-2)">{{ item.target.status || '-' }}</td>
              <td><button class="btn-ghost" @click="removeMember(item.target_id)">移除</button></td>
            </tr>
            <tr v-if="!detailTargets.length">
              <td colspan="8" class="py-8 text-center" style="color: var(--text-3)">包内暂无目标</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-between rounded-xl border px-4 py-3 text-sm" style="border-color: var(--border); background: var(--surface)">
        <span style="color: var(--text-2)">第 {{ page }} / {{ totalPages }} 页，共 {{ total }} 条</span>
        <div class="flex gap-1.5">
          <button class="btn-ghost" :disabled="page <= 1" @click="page -= 1">上一页</button>
          <button class="btn-ghost" :disabled="page >= totalPages" @click="page += 1">下一页</button>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false">
      <div class="modal-box">
        <h3 class="mb-4 text-base font-semibold" style="color: var(--text-1)">新建目标分组</h3>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">包名 *</label>
            <input v-model="createForm.name" class="input" placeholder="例如 KOL_A轮_高优先级" />
          </div>
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">描述</label>
            <textarea v-model="createForm.description" class="input h-24" placeholder="可选" />
          </div>
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" @click="createSegment">创建</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()

const segments = ref([])
const showCreate = ref(false)
const createForm = reactive({ name: '', description: '' })

const detail = ref({})
const detailTargets = ref([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const isDetail = computed(() => !!route.params.id)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const formatTime = (value) => {
  if (!value) return '-'
  return String(value)
}

const fetchSegments = async () => {
  const { data } = await api.get('/segments')
  segments.value = data
}

const fetchDetail = async () => {
  const id = route.params.id
  if (!id) return
  const [segResp, targetsResp] = await Promise.all([
    api.get(`/segments/${id}`),
    api.get(`/segments/${id}/targets`, { params: { page: page.value, page_size: pageSize.value } })
  ])
  detail.value = segResp.data
  detailTargets.value = targetsResp.data.items || []
  total.value = targetsResp.data.total || 0
}

const createSegment = async () => {
  if (!createForm.name.trim()) {
    system.notify('目标分组名称不能为空', 'error')
    return
  }
  try {
    const { data } = await api.post('/segments', {
      name: createForm.name.trim(),
      description: createForm.description.trim()
    })
    showCreate.value = false
    createForm.name = ''
    createForm.description = ''
    await fetchSegments()
    system.notify('目标分组已创建', 'success')
    goDetail(data.id)
  } catch (e) {
    system.notify(getActionErrorMessage('创建目标分组', e), 'error')
  }
}

const removeSegment = async (id) => {
  try {
    await api.delete(`/segments/${id}`)
    await fetchSegments()
    system.notify('目标分组已删除', 'warn')
  } catch (e) {
    system.notify(getActionErrorMessage('删除目标分组', e), 'error')
  }
}

const removeMember = async (targetId) => {
  try {
    await api.delete(`/segments/${route.params.id}/targets/${targetId}`)
    await fetchDetail()
    system.notify('已从目标分组移除', 'warn')
  } catch (e) {
    system.notify(getActionErrorMessage('移除分组成员', e), 'error')
  }
}

const goDetail = (id) => {
  router.push(`/segments/${id}`)
}

const backToList = () => {
  router.push('/segments')
}

const continueAdd = () => {
  router.push({ path: '/targets', query: { segmentId: route.params.id } })
}

watch(
  () => [route.params.id, page.value],
  async () => {
    try {
      if (isDetail.value) {
        await fetchDetail()
      } else {
        await fetchSegments()
      }
    } catch (e) {
      system.notify(getActionErrorMessage('加载目标分组', e), 'error')
    }
  },
  { immediate: true }
)

onMounted(async () => {
  if (!isDetail.value) {
    await fetchSegments()
  }
})
</script>
