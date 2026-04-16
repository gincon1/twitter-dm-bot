import { createRouter, createWebHistory } from 'vue-router'

const Dashboard = () => import('../views/Dashboard.vue')
const Accounts = () => import('../views/Accounts.vue')
const Targets = () => import('../views/Targets.vue')
const Templates = () => import('../views/Templates.vue')
const Exceptions = () => import('../views/Exceptions.vue')
const Settings = () => import('../views/Settings.vue')
const Segments = () => import('../views/Segments.vue')
const Conversations = () => import('../views/Conversations.vue')
const Projects = () => import('../views/Projects.vue')

const routes = [
  { path: '/', redirect: '/projects' },
  { path: '/dashboard', name: 'dashboard', component: Dashboard, meta: { title: '监控概览' } },
  { path: '/projects', name: 'projects', component: Projects, meta: { title: '项目管理' } },
  { path: '/projects/:id', name: 'project-detail', component: Projects, meta: { title: '项目详情' } },
  { path: '/accounts', name: 'accounts', component: Accounts, meta: { title: '账号管理' } },
  { path: '/targets', name: 'targets', component: Targets, meta: { title: '目标数据' } },
  { path: '/templates', name: 'templates', component: Templates, meta: { title: '模板管理' } },
  { path: '/conversations', name: 'conversations', component: Conversations, meta: { title: '会话管理' } },
  { path: '/exceptions', name: 'exceptions', component: Exceptions, meta: { title: '异常处理' } },
  { path: '/segments', name: 'segments', component: Segments, meta: { title: '目标分组' } },
  { path: '/segments/:id', name: 'segment-detail', component: Segments, meta: { title: '目标分组详情' } },
  { path: '/feishu-config', redirect: '/settings' },
  { path: '/settings', name: 'settings', component: Settings, meta: { title: '策略配置' } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
