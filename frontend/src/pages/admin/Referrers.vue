<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('referrers.name'), key: 'name' },
  { title: t('referrers.commissionRate'), key: 'commission_rate' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const formFields = computed(() => [
  { key: 'name', label: t('referrers.name'), required: true },
  { key: 'commission_rate', label: t('referrers.commissionRateLabel'), type: 'number' },
])
</script>

<template>
  <CrudTable
    :title="t('nav.referrers')"
    :headers="headers"
    :form-fields="formFields"
    :default-form="{ name: '', commission_rate: 0 }"
    :fetch-fn="() => api.get('/api/referrers')"
    :create-fn="body => api.post('/api/referrers', { name: body.name, commission_rate: Number(body.commission_rate) || 0 })"
    :update-fn="(id, body) => api.patch(`/api/referrers/${id}`, { name: body.name, commission_rate: Number(body.commission_rate) || 0 })"
    :delete-fn="id => api.delete(`/api/referrers/${id}`)"
  />
</template>
