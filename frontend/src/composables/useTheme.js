import { ref, watch } from 'vue'

const theme = ref(localStorage.getItem('dm-theme') || 'dark')

const apply = (val) => {
  document.documentElement.setAttribute('data-theme', val)
  localStorage.setItem('dm-theme', val)
}

apply(theme.value)

watch(theme, apply)

export function useTheme() {
  const toggle = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }
  return { theme, toggle }
}
