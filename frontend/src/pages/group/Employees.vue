<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()

const headers = [
  { title: 'ID', key: 'id' },
  { title: '姓名', key: 'name' },
  { title: 'AI', key: 'is_ai' },
  { title: '状态', key: 'status' },
  { title: '创建时间', key: 'created_at' },
]

const formFields = [
  { key: 'name', label: '坐席名称', required: true },
  { key: 'is_ai', label: 'AI 坐席', type: 'switch' },
  {
    key: 'status', label: '状态', type: 'select',
    options: [
      { title: 'online', value: 'online' },
      { title: 'offline', value: 'offline' },
      { title: 'busy', value: 'busy' },
    ],
  },
]

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
      你尚未绑定到任何组,无法管理组内坐席。
    </VAlert>
    <CrudTable
      v-else
      title="组内坐席"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '', is_ai: false, status: 'offline' }"
      :fetch-fn="fetchFn"
      :create-fn="createFn"
      :update-fn="updateFn"
      :delete-fn="deleteFn"
    >
      <template #cell.is_ai="{ item }">
        <VChip size="small" :color="item.is_ai ? 'primary' : 'default'">{{ item.is_ai ? 'AI' : '真人' }}</VChip>
      </template>
      <template #cell.status="{ item }">
        <VChip size="small" :color="{ online: 'success', busy: 'warning', offline: 'default' }[item.status]">{{ item.status }}</VChip>
      </template>
    </CrudTable>
  </div>
</template>
