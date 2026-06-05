<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()

const headers = computed(() => [
  { title: t('users.email'), key: 'email' },
  { title: t('users.displayName'), key: 'display_name' },
  { title: t('users.role'), key: 'role' },
  { title: t('common.company'), key: 'org_id' },
  { title: t('common.group'), key: 'group_id' },
  { title: t('nav.employees'), key: 'employee_id' },
  { title: t('rules.enabled'), key: 'is_active' },
])

const orgOptions = ref([{ title: t('common.none'), value: null }])
const groupOptions = ref([{ title: t('common.none'), value: null }])
const employeeOptions = ref([{ title: t('common.none'), value: null }])

const roleOptions = computed(() => {
  const all = [
    { title: t('roles.platform_admin'), value: 'platform_admin' },
    { title: t('roles.org_admin'), value: 'org_admin' },
    { title: t('roles.group_admin'), value: 'group_admin' },
    { title: t('roles.agent'), value: 'agent' },
  ]
  // 组管理员只能建坐席账号; 平台超管全部; 公司管理员去掉平台超管
  if (auth.isGroupAdmin) return all.slice(3)
  return auth.isPlatformAdmin ? all : all.slice(1)
})

const loadOptions = async () => {
  try {
    if (auth.isPlatformAdmin) {
      const orgs = await api.get('/api/organizations')
      orgOptions.value = [{ title: t('common.none'), value: null }, ...orgs.map(o => ({ title: o.name, value: o.id }))]
    }
    if (auth.orgId || auth.isPlatformAdmin) {
      const targetOrg = auth.orgId || (orgOptions.value[1]?.value)
      if (targetOrg) {
        // 组管理员只列本组坐席, 其余角色列全公司
        const empUrl = auth.isGroupAdmin
          ? `/api/orgs/${targetOrg}/employees?group_id=${auth.groupId}`
          : `/api/orgs/${targetOrg}/employees`
        const [groups, emps] = await Promise.all([
          api.get(`/api/orgs/${targetOrg}/groups`),
          api.get(empUrl),
        ])
        groupOptions.value = [{ title: t('common.none'), value: null }, ...groups.map(g => ({ title: g.name, value: g.id }))]
        employeeOptions.value = [{ title: t('common.none'), value: null }, ...emps.map(e => ({ title: e.name, value: e.id }))]
      }
    }
  } catch { /* ignore */ }
}
onMounted(loadOptions)

const formFields = computed(() => {
  // 组管理员: org/group 由后端强制本组本公司, 隐藏这两个字段, 减少误操作
  const base = [
    { key: 'email', label: t('users.email'), required: true, disableOnEdit: true },
    { key: 'password', label: t('users.passwordHint') },
    { key: 'display_name', label: t('users.displayName') },
    { key: 'role', label: t('users.role'), type: 'select', options: roleOptions.value },
  ]
  if (!auth.isGroupAdmin) {
    base.push(
      { key: 'org_id', label: t('users.orgLabel'), type: 'select', options: orgOptions.value },
      { key: 'group_id', label: t('common.groupLabel'), type: 'select', options: groupOptions.value },
    )
  }
  base.push(
    { key: 'employee_id', label: t('users.bindEmployee'), type: 'select', options: employeeOptions.value },
    { key: 'is_active', label: t('rules.enabled'), type: 'switch' },
  )
  return base
})

const cleanForCreate = (body) => {
  const out = { ...body }
  if (!out.password) throw new Error(t('users.pleaseEnterPassword'))
  return out
}
const cleanForUpdate = (body) => {
  const out = { ...body }
  if (!out.password) delete out.password
  delete out.email
  return out
}
</script>

<template>
  <CrudTable
    :title="t('nav.users')"
    :headers="headers"
    :form-fields="formFields"
    :default-form="{ email: '', password: '', display_name: '', role: 'agent', org_id: null, group_id: null, employee_id: null, is_active: true }"
    :fetch-fn="() => api.get('/api/users')"
    :create-fn="body => api.post('/api/users', cleanForCreate(body))"
    :update-fn="(id, body) => api.patch(`/api/users/${id}`, cleanForUpdate(body))"
    :delete-fn="id => api.delete(`/api/users/${id}`)"
  >
    <template #cell.role="{ item }">
      <VChip size="small" :color="{ platform_admin: 'error', org_admin: 'primary', group_admin: 'info', agent: 'default' }[item.role]">
        {{ item.role }}
      </VChip>
    </template>
    <template #cell.is_active="{ item }">
      <VIcon :icon="item.is_active ? 'ri-checkbox-circle-line' : 'ri-close-circle-line'" :color="item.is_active ? 'success' : 'error'" />
    </template>
  </CrudTable>
</template>
