<template>
  <section class="space-y-4">
    <!-- 自定义模板 -->
    <div class="card p-4">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold" style="color: var(--text-1)">自定义模板</h2>
        <button class="btn-primary" @click="openAdd">+ 新建</button>
      </div>

      <div v-if="!customTemplates.length" class="rounded-lg border py-8 text-center text-sm" style="border-color: var(--border); background: var(--surface); color: var(--text-3)">
        暂无自定义模板，系统将使用内置默认模板
      </div>

      <div class="space-y-2">
        <div
          v-for="tpl in customTemplates"
          :key="tpl.id"
          class="flex items-start gap-3 rounded-lg border p-3"
          style="border-color: var(--border); background: var(--surface)"
        >
          <div class="flex-1 min-w-0">
            <div class="mb-2">
              <span
                class="rounded-full px-2 py-1 text-[11px]"
                :style="templateTypeStyle(tpl.template_type)"
              >
                {{ templateTypeLabel(tpl.template_type) }}
              </span>
            </div>
            <p class="text-sm break-words" style="color: var(--text-1)">{{ tpl.content }}</p>
            <p v-if="tpl.description" class="mt-1 text-xs" style="color: var(--text-3)">{{ tpl.description }}</p>
          </div>
          <div class="flex shrink-0 items-center gap-1.5">
            <button
              class="btn-ghost"
              style="padding: 3px 8px; font-size: 11px;"
              :class="tpl.active ? 'text-emerald-400' : 'text-zinc-500'"
              @click="toggleActive(tpl)"
            >
              {{ tpl.active ? '禁用' : '启用' }}
            </button>
            <button class="btn-ghost" style="padding: 3px 8px; font-size: 11px;" @click="openEdit(tpl)">编辑</button>
            <button class="btn-ghost" style="padding: 3px 8px; font-size: 11px;" @click="remove(tpl.id)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 变量说明 & 预览 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div class="card p-4">
        <h2 class="mb-3 text-sm font-semibold" style="color: var(--text-1)">变量说明</h2>
        <ul class="space-y-2 text-sm" style="color: var(--text-2)">
          <li><code class="rounded px-1 py-0.5" style="background: var(--surface)">{name}</code>：称呼（bro/空）</li>
          <li><code class="rounded px-1 py-0.5" style="background: var(--surface)">{handle}</code>：目标用户名</li>
          <li><code class="rounded px-1 py-0.5" style="background: var(--surface)">{project}</code>：项目名</li>
          <li><code class="rounded px-1 py-0.5" style="background: var(--surface)">{hook}</code> / <code class="rounded px-1 py-0.5" style="background: var(--surface)">{personalized_hook}</code>：兴趣切入语（随机）</li>
        </ul>
        <div class="mt-4 rounded-lg border p-3 text-xs" style="border-color: var(--border); background: var(--surface); color: var(--text-3)">
          {{ customTemplates.length ? '当前步骤会优先使用已启用的自定义模板' : '当前步骤会使用系统内置模板' }}。
        </div>
      </div>

      <div class="card p-4">
        <h2 class="mb-3 text-sm font-semibold" style="color: var(--text-1)">生成预览</h2>
        <div class="flex flex-wrap items-center gap-3">
          <input v-model="project" class="input max-w-[320px]" placeholder="输入项目名称" />
          <select v-model="previewType" class="input max-w-[140px]">
            <option v-for="option in templateTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <button class="btn-secondary" @click="preview">生成预览</button>
        </div>
        <div class="mt-4 rounded-lg border p-4 text-sm" style="border-color: var(--border); background: var(--bg); color: var(--text-1)">
          {{ previewText || '点击“生成预览”查看当前步骤文案' }}
        </div>
      </div>
    </div>

    <!-- 内置默认模板（只读参考） -->
    <div class="card p-4">
      <h2 class="mb-3 text-sm font-semibold" style="color: var(--text-3)">内置默认模板（参考，不可编辑）</h2>
      <div class="space-y-2">
        <div v-for="(tpl, idx) in defaults" :key="idx" class="rounded-lg border p-3 text-sm" style="border-color: var(--border); background: rgba(255,255,255,0.02); color: var(--text-3)">
          {{ tpl }}
        </div>
      </div>
    </div>

    <!-- 新建/编辑弹窗 -->
    <div v-if="showForm" class="modal-backdrop" @click.self="showForm = false">
      <div class="modal-box">
        <h3 class="mb-4 text-base font-semibold" style="color: var(--text-1)">{{ editingId ? '编辑模板' : '新建模板' }}</h3>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">模板内容 *（可使用 {name} {project} {hook}）</label>
            <textarea v-model="form.content" class="input h-24 w-full text-sm" placeholder="Hi {name}，{hook}，关于 {project} 想聊聊" />
          </div>
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">备注说明（可选）</label>
            <input v-model="form.description" class="input w-full" placeholder="用途或场景备注" />
          </div>
          <div>
            <label class="mb-1 block text-xs" style="color: var(--text-3)">模板类型</label>
            <select v-model="form.template_type" class="input w-full">
              <option v-for="option in templateTypeOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <label class="flex cursor-pointer items-center gap-2 text-sm" style="color: var(--text-2)">
            <input type="checkbox" v-model="form.active" class="h-4 w-4 accent-blue-500" />
            <span>立即启用</span>
          </label>
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-ghost" @click="showForm = false">取消</button>
          <button class="btn-primary" @click="submitForm">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import api from '../api'
import { useSystemStore } from '../stores/system'
import { getActionErrorMessage } from '../utils/errorText'

const system = useSystemStore()

const allTemplates = ref([])
const defaults = ref([])
const project = ref('示例项目')
const previewText = ref('')
const previewType = ref('sequence_step_1')

const templateTypeOptions = [
  { value: 'sequence_step_1', label: '第 1 步触达' },
  { value: 'sequence_step_2', label: '第 2 步触达' },
  { value: 'sequence_step_3', label: '第 3 步触达' },
]

const showForm = ref(false)
const editingId = ref(null)
const form = ref({ content: '', description: '', active: true, template_type: 'sequence_step_1' })

const customTemplates = computed(() => allTemplates.value)

const loadTemplates = async () => {
  try {
    const { data } = await api.get('/templates')
    allTemplates.value = data.templates || []
    defaults.value = data.defaults || []
  } catch (e) {
    system.notify(getActionErrorMessage('加载模板', e), 'error')
  }
}

const openAdd = () => {
  editingId.value = null
  form.value = { content: '', description: '', active: true, template_type: 'sequence_step_1' }
  showForm.value = true
}

const openEdit = (tpl) => {
  editingId.value = tpl.id
  form.value = {
    content: tpl.content,
    description: tpl.description || '',
    active: !!tpl.active,
    template_type: tpl.template_type || 'sequence_step_1'
  }
  showForm.value = true
}

const submitForm = async () => {
  if (!form.value.content.trim()) {
    system.notify('模板内容不能为空', 'error')
    return
  }
  try {
    if (editingId.value) {
      await api.put(`/templates/${editingId.value}`, form.value)
      system.notify('模板已更新', 'success')
    } else {
      await api.post('/templates', form.value)
      system.notify('模板已创建', 'success')
    }
    showForm.value = false
    await loadTemplates()
  } catch (e) {
    system.notify(getActionErrorMessage('保存模板', e), 'error')
  }
}

const toggleActive = async (tpl) => {
  try {
    await api.put(`/templates/${tpl.id}`, { active: !tpl.active })
    await loadTemplates()
  } catch (e) {
    system.notify(getActionErrorMessage('切换模板状态', e), 'error')
  }
}

const remove = async (id) => {
  try {
    await api.delete(`/templates/${id}`)
    system.notify('模板已删除', 'warn')
    await loadTemplates()
  } catch (e) {
    system.notify(getActionErrorMessage('删除模板', e), 'error')
  }
}

const preview = async () => {
  try {
    const { data } = await api.get('/templates/preview', {
      params: {
        project: project.value || '示例项目',
        template_type: previewType.value
      }
    })
    previewText.value = data.preview || ''
  } catch (e) {
    system.notify(getActionErrorMessage('生成模板预览', e), 'error')
  }
}

const templateTypeStyle = (templateType) => {
  const styleMap = {
    sequence_step_1: { background: 'rgba(62, 207, 142, 0.12)', color: '#3ecf8e' },
    sequence_step_2: { background: 'rgba(119, 183, 255, 0.14)', color: '#77b7ff' },
    sequence_step_3: { background: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b' },
  }
  return styleMap[templateType] || styleMap.sequence_step_1
}

const templateTypeLabel = (templateType) => {
  return templateTypeOptions.find((item) => item.value === templateType)?.label || '第 1 步触达'
}

onMounted(loadTemplates)
</script>
