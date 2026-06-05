<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('employees.name'), key: 'name' },
  { title: 'AI', key: 'is_ai' },
  { title: t('employees.status'), key: 'status' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const formFields = computed(() => [
  { key: 'name', label: t('employees.nameLabel'), required: true },
  { key: 'is_ai', label: t('employees.aiEmployee'), type: 'switch' },
  {
    key: 'status', label: t('employees.status'), type: 'select',
    options: [
      { title: 'online', value: 'online' },
      { title: 'offline', value: 'offline' },
      { title: 'busy', value: 'busy' },
    ],
  },
])

const fetchFn = async () => {
  const list = await api.get(`/api/orgs/${auth.orgId}/employees?group_id=${auth.groupId}`)
  return list
}
const createFn = (body) => api.post(`/api/orgs/${auth.orgId}/employees`, { ...body, group_id: auth.groupId })
const updateFn = (id, body) => api.patch(`/api/orgs/${auth.orgId}/employees/${id}`, body)
const deleteFn = (id) => api.delete(`/api/orgs/${auth.orgId}/employees/${id}`)
</script>

<template>
  <div>
    <VAlert v-if="!auth.groupId" type="warning" class="mb-4">
      {{ t('groupEmployees.noGroupBound') }}
    </VAlert>
    <CrudTable
      v-else
      :title="t('nav.groupEmployees')"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '', is_ai: false, status: 'offline' }"
      :fetch-fn="fetchFn"
      :create-fn="createFn"
      :update-fn="updateFn"
      :delete-fn="deleteFn"
    >
      <template #cell.is_ai="{ item }">
        <VChip size="small" :color="item.is_ai ? 'primary' : 'default'">{{ item.is_ai ? 'AI' : t('employees.human') }}</VChip>
      </template>
      <template #cell.status="{ item }">
        <VChip size="small" :color="{ online: 'success', busy: 'warning', offline: 'default' }[item.status]">{{ item.status }}</VChip>
      </template>
    </CrudTable>
  </div>
</template>
