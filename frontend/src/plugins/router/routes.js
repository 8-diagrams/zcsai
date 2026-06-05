export const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/',
    component: () => import('@/layouts/default.vue'),
    children: [
      // 通用
      {
        path: 'dashboard',
        component: () => import('@/pages/dashboard.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin', 'agent'] },
      },
      {
        path: 'account-settings',
        component: () => import('@/pages/account-settings.vue'),
      },

      // 平台管理员
      {
        path: 'admin/referrers',
        component: () => import('@/pages/admin/Referrers.vue'),
        meta: { roles: ['platform_admin'] },
      },
      {
        path: 'admin/organizations',
        component: () => import('@/pages/admin/Organizations.vue'),
        meta: { roles: ['platform_admin'] },
      },
      {
        path: 'admin/users',
        component: () => import('@/pages/admin/Users.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin'] },
      },

      // 公司管理员
      {
        path: 'org/groups',
        component: () => import('@/pages/org/Groups.vue'),
        meta: { roles: ['platform_admin', 'org_admin'] },
      },
      {
        path: 'org/employees',
        component: () => import('@/pages/org/Employees.vue'),
        meta: { roles: ['platform_admin', 'org_admin'] },
      },
      {
        path: 'org/activities',
        component: () => import('@/pages/org/Activities.vue'),
        meta: { roles: ['platform_admin', 'org_admin'] },
      },
      {
        path: 'org/kbs',
        component: () => import('@/pages/org/Kbs.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin'] },
      },
      {
        path: 'org/materials',
        component: () => import('@/pages/org/Materials.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin'] },
      },
      {
        path: 'org/sessions',
        component: () => import('@/pages/org/Sessions.vue'),
        meta: { roles: ['platform_admin', 'org_admin'] },
      },
      {
        path: 'org/event-rules',
        component: () => import('@/pages/org/EventRules.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin'] },
      },
      {
        path: 'org/event-rules/edit/:id?',
        component: () => import('@/pages/org/EventRuleEditor.vue'),
        meta: { roles: ['platform_admin', 'org_admin', 'group_admin'] },
      },

      // 组管理员
      {
        path: 'group',
        component: () => import('@/pages/group/Index.vue'),
        meta: { roles: ['group_admin'] },
      },
      {
        path: 'group/employees',
        component: () => import('@/pages/group/Employees.vue'),
        meta: { roles: ['group_admin'] },
      },
      {
        path: 'group/activities',
        component: () => import('@/pages/group/Activities.vue'),
        meta: { roles: ['group_admin'] },
      },
      {
        path: 'group/sessions',
        component: () => import('@/pages/group/Sessions.vue'),
        meta: { roles: ['group_admin'] },
      },

      // 坐席 (Agent)
      {
        path: 'me/sessions',
        component: () => import('@/pages/me/Sessions.vue'),
        meta: { roles: ['agent', 'group_admin'] },
      },
      {
        path: 'me/session/:sid',
        component: () => import('@/pages/me/Session.vue'),
        meta: { roles: ['agent', 'group_admin', 'org_admin', 'platform_admin'] },
      },

      // 旧 demo 页保留 (内部参考)
      { path: 'typography', component: () => import('@/pages/typography.vue') },
      { path: 'icons', component: () => import('@/pages/icons.vue') },
      { path: 'cards', component: () => import('@/pages/cards.vue') },
      { path: 'tables', component: () => import('@/pages/tables.vue') },
      { path: 'form-layouts', component: () => import('@/pages/form-layouts.vue') },
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/blank.vue'),
    children: [
      { path: 'login', component: () => import('@/pages/login.vue') },
      { path: 'register', component: () => import('@/pages/register.vue') },
      { path: '403', component: () => import('@/pages/403.vue') },
      {
        path: '/:pathMatch(.*)*',
        component: () => import('@/pages/[...error].vue'),
      },
    ],
  },
]
