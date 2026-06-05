<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('organizations.name'), key: 'name' },
  { title: t('organizations.plan'), key: 'plan_type' },
  { title: 'API Key', key: 'api_key' },
  { title: t('nav.referrers'), key: 'referrer_id' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const referrerOptions = ref([])
onMounted(async () => {
  try {
    const list = await api.get('/api/referrers')
    referrerOptions.value = [
      { title: t('common.none'), value: null },
      ...list.map(r => ({ title: `${r.name} (${r.id})`, value: r.id })),
    ]
  } catch { /* ignore */ }
})

const formFields = computed(() => [
  { key: 'name', label: t('organizations.name'), required: true },
  {
    key: 'plan_type', label: t('organizations.plan'), type: 'select',
    options: [
      { title: 'Free', value: 'free' },
      { title: 'Pro', value: 'pro' },
      { title: 'Enterprise', value: 'enterprise' },
    ],
  },
  { key: 'api_key', label: t('organizations.apiKeyHint') },
  { key: 'referrer_id', label: t('organizations.referrer'), type: 'select', options: referrerOptions.value },
])
</script>

<template>
  <CrudTable
    :title="t('nav.organizations')"
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
