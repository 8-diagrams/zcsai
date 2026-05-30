<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()

const headers = [
  { title: '邮箱', key: 'email' },
  { title: '昵称', key: 'display_name' },
  { title: '角色', key: 'role' },
  { title: '公司', key: 'org_id' },
  { title: '组', key: 'group_id' },
  { title: '坐席', key: 'employee_id' },
  { title: '启用', key: 'is_active' },
]

const orgOptions = ref([{ title: '(无)', value: null }])
const groupOptions = ref([{ title: '(无)', value: null }])
const employeeOptions = ref([{ title: '(无)', value: null }])

const roleOptions = computed(() => {
  const all = [
    { title: '平台超管', value: 'platform_admin' },
    { title: '公司管理员', value: 'org_admin' },
    { title: '组管理员', value: 'group_admin' },
    { title: '坐席', value: 'agent' },
  ]
  return auth.isPlatformAdmin ? all : all.slice(1)
})

const loadOptions = async () => {
  try {
    if (auth.isPlatformAdmin) {
      const orgs = await api.get('/api/organizations')
      orgOptions.value = [{ title: '(无)', value: null }, ...orgs.map(o => ({ title: o.name, value: o.id }))]
    }
    if (auth.orgId || auth.isPlatformAdmin) {
      const targetOrg = auth.orgId || (orgOptions.value[1]?.value)
      if (targetOrg) {
        const [groups, emps] = await Promise.all([
          api.get(`/api/orgs/${targetOrg}/groups`),
          api.get(`/api/orgs/${targetOrg}/employees`),
        ])
        groupOptions.value = [{ title: '(无)', value: null }, ...groups.map(g => ({ title: g.name, value: g.id }))]
        employeeOptions.value = [{ title: '(无)', value: null }, ...emps.map(e => ({ title: e.name, value: e.id }))]
      }
    }
  } catch { /* ignore */ }
}
onMounted(loadOptions)

const formFields = computed(() => [
  { key: 'email', label: '邮箱', required: true, disableOnEdit: true },
  { key: 'password', label: '密码 (编辑时留空则不变)' },
  { key: 'display_name', label: '昵称' },
  { key: 'role', label: '角色', type: 'select', options: roleOptions.value },
  { key: 'org_id', label: '所属公司', type: 'select', options: orgOptions.value },
  { key: 'group_id', label: '所属组', type: 'select', options: groupOptions.value },
  { key: 'employee_id', label: '绑定坐席 (agent)', type: 'select', options: employeeOptions.value },
  { key: 'is_active', label: '启用', type: 'switch' },
])

const cleanForCreate = (body) => {
  const out = { ...body }
  if (!out.password) throw new Error('请填写密码')
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
    title="用户账号"
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
