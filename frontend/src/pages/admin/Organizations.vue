<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'

const headers = [
  { title: 'ID', key: 'id' },
  { title: '公司名称', key: 'name' },
  { title: '套餐', key: 'plan_type' },
  { title: 'API Key', key: 'api_key' },
  { title: '代理商', key: 'referrer_id' },
  { title: '创建时间', key: 'created_at' },
]

const referrerOptions = ref([])
onMounted(async () => {
  try {
    const list = await api.get('/api/referrers')
    referrerOptions.value = [
      { title: '(无)', value: null },
      ...list.map(r => ({ title: `${r.name} (${r.id})`, value: r.id })),
    ]
  } catch { /* ignore */ }
})

const formFields = computed(() => [
  { key: 'name', label: '公司名称', required: true },
  {
    key: 'plan_type', label: '套餐', type: 'select',
    options: [
      { title: 'Free', value: 'free' },
      { title: 'Pro', value: 'pro' },
      { title: 'Enterprise', value: 'enterprise' },
    ],
  },
  { key: 'api_key', label: 'API Key (留空自动生成)' },
  { key: 'referrer_id', label: '归属代理商', type: 'select', options: referrerOptions.value },
])
</script>

<template>
  <CrudTable
    title="公司/租户"
    :headers="headers"
    :form-fields="formFields"
    :default-form="{ name: '', plan_type: 'free', api_key: '', referrer_id: null }"
    :fetch-fn="() => api.get('/api/organizations')"
    :create-fn="body => api.post('/api/organizations', body)"
    :update-fn="(id, body) => api.patch(`/api/organizations/${id}`, body)"
    :delete-fn="id => api.delete(`/api/organizations/${id}`)"
  >
    <template #cell.plan_type="{ item }">
      <VChip
        size="small"
        :color="{ free: 'default', pro: 'primary', enterprise: 'warning' }[item.plan_type]"
      >
        {{ item.plan_type }}
      </VChip>
    </template>
  </CrudTable>
</template>
