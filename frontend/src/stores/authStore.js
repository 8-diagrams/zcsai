// src/stores/authStore.js — 登录态、当前用户、角色 getters
import { defineStore } from 'pinia'
import { api, clearToken, getToken, setToken } from '@/utils/api'

const USER_CACHE_KEY = 'auth_user'

const cachedUser = (() => {
  try {
    const raw = localStorage.getItem(USER_CACHE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
})()

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken() || '',
    user: cachedUser,
    loading: false,
  }),

  getters: {
    isLogin: (s) => !!s.token && !!s.user,
    role: (s) => s.user?.role || '',
    isPlatformAdmin: (s) => s.user?.role === 'platform_admin',
    isOrgAdmin: (s) => s.user?.role === 'org_admin',
    isGroupAdmin: (s) => s.user?.role === 'group_admin',
    isAgent: (s) => s.user?.role === 'agent',
    orgId: (s) => s.user?.org_id || '',
    groupId: (s) => s.user?.group_id || '',
    employeeId: (s) => s.user?.employee_id || '',
    displayName: (s) => s.user?.display_name || s.user?.email || '',
    /** 角色等级,数值越大权限越高 */
    rank: (s) => ({
      agent: 1, group_admin: 2, org_admin: 3, platform_admin: 4,
    }[s.user?.role] || 0),
  },

  actions: {
    async login(email, password) {
      this.loading = true
      try {
        const data = await api.postForm('/api/auth/login', { username: email, password })
        this.token = data.access_token
        setToken(data.access_token)
        this.user = data.user
        localStorage.setItem(USER_CACHE_KEY, JSON.stringify(data.user))
        return data.user
      } finally {
        this.loading = false
      }
    },

    async fetchMe() {
      if (!this.token) return null
      const u = await api.get('/api/auth/me')
      this.user = u
      localStorage.setItem(USER_CACHE_KEY, JSON.stringify(u))
      return u
    },

    logout() {
      this.token = ''
      this.user = null
      clearToken()
      localStorage.removeItem(USER_CACHE_KEY)
    },

    /** 路由 meta.roles 是否允许当前用户访问 */
    canAccess(roles) {
      if (!roles || roles.length === 0) return true
      return roles.includes(this.role)
    },
  },
})
