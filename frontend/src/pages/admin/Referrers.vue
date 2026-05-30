<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'

const headers = [
  { title: 'ID', key: 'id' },
  { title: '代理商名称', key: 'name' },
  { title: '分佣比例', key: 'commission_rate' },
  { title: '创建时间', key: 'created_at' },
]

const formFields = [
  { key: 'name', label: '代理商名称', required: true },
  { key: 'commission_rate', label: '分佣比例 (0~1)', type: 'number' },
]
</script>

<template>
  <CrudTable
    title="代理商"
    :headers="headers"
    :form-fields="formFields"
    :default-form="{ name: '', commission_rate: 0 }"
    :fetch-fn="() => api.get('/api/referrers')"
    :create-fn="body => api.post('/api/referrers', { name: body.name, commission_rate: Number(body.commission_rate) || 0 })"
    :update-fn="(id, body) => api.patch(`/api/referrers/${id}`, { name: body.name, commission_rate: Number(body.commission_rate) || 0 })"
    :delete-fn="id => api.delete(`/api/referrers/${id}`)"
  />
</template>
