export function getActionErrorMessage(action, error, fallback = '') {
  const detail = normalizeDetail(error)
  const status = Number(error?.response?.status || 0)
  const prefix = action ? `${action}失败` : '操作失败'

  if (status === 400) return detail || `${prefix}，请检查输入内容`
  if (status === 401) return '服务连接已失效，请重新登录或重新连接后再试'
  if (status === 403) return detail || `${prefix}，当前无权执行`
  if (status === 404) return detail || `${prefix}，相关记录不存在`
  if (status === 409) return detail || `${action || '当前任务'}已在执行，请稍后再试`
  if (status === 422) return detail || `${prefix}，请检查必填项`
  if (status === 429) return `${prefix}，操作过于频繁，请稍后再试`
  if (status >= 500) return detail || `${prefix}，服务处理异常，请查看实时日志`
  if (error?.code === 'ECONNABORTED') return `${prefix}，请求超时，请稍后重试`
  if (error && !error?.response) return `${prefix}，无法连接到服务`
  return detail || fallback || `${prefix}，请稍后重试`
}

export function getPlainErrorMessage(error, fallback = '操作未完成，请稍后重试') {
  const detail = normalizeDetail(error)
  if (!error?.response && error?.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试'
  }
  if (!error?.response) {
    return '无法连接到服务，请确认后端状态'
  }
  return detail || fallback
}

function normalizeDetail(error) {
  const detail = error?.response?.data?.detail || error?.response?.data?.message || error?.message || ''
  const text = String(detail || '').trim()
  if (!text) return ''
  if (/^Request failed with status code \d+$/i.test(text)) return ''
  return text
}
