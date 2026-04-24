import { createRouter, createWebHistory } from 'vue-router'

const Dashboard = () => import('../views/Dashboard.vue')
const Contacts = () => import('../views/Contacts.vue')
const Send = () => import('../views/Send.vue')
const Conversations = () => import('../views/Conversations.vue')
const Templates = () => import('../views/Templates.vue')
const Accounts = () => import('../views/Accounts.vue')
const Settings = () => import('../views/Settings.vue')

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: Dashboard, meta: { title: '总览' } },
  { path: '/contacts', name: 'contacts', component: Contacts, meta: { title: '联系人' } },
  { path: '/send', name: 'send', component: Send, meta: { title: '发送' } },
  { path: '/conversations', name: 'conversations', component: Conversations, meta: { title: '对话与跟进' } },
  { path: '/templates', name: 'templates', component: Templates, meta: { title: '消息模板' } },
  { path: '/accounts', name: 'accounts', component: Accounts, meta: { title: '账号管理' } },
  { path: '/settings', name: 'settings', component: Settings, meta: { title: '设置' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
