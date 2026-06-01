import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes'
import { useAuthStore } from '@/stores/authStore'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

const PUBLIC_PATHS = new Set(['/login', '/register', '/403'])

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // 1. 401 事件触发的强制登出 → 已在 api.js 里 dispatch,这里只处理路由跳转
  if (PUBLIC_PATHS.has(to.path)) {
    if (to.path === '/login' && auth.isLogin) return '/'
    return true
  }

  // 2. 未登录 → 推到登录页,带 redirect
  if (!auth.token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 3. 有 token 但 user 缺失(刷新页面后) → 拉一次 /me
  if (!auth.user) {
    try { await auth.fetchMe() } catch {
      auth.logout()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // 4. 角色守卫:meta.roles 限制时校验
  const roles = to.meta?.roles
  if (roles && roles.length && !auth.canAccess(roles)) {
    return '/403'
  }

  return true
})

// 全局监听 401 事件 → 清登录态 + 跳登录(带 redirect 回跳)
if (typeof window !== 'undefined') {
  window.addEventListener('auth:unauthorized', () => {
    try {
      // pinia 已在前一个 plugin 注册,此处可安全取 store
      const auth = useAuthStore()
      auth.logout()
    } catch (e) {
      console.warn('[auth:unauthorized] logout 失败:', e)
    }

    const current = router.currentRoute.value
    if (current.path === '/login') return // 已经在登录页,不重复跳

    const redirect = current.fullPath && current.fullPath !== '/' ? current.fullPath : undefined
    router.replace({ path: '/login', query: redirect ? { redirect } : {} })
  })
}

export default function (app) {
  app.use(router)
}
export { router }
