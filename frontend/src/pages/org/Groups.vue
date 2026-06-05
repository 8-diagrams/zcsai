<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const ready = ref(!!orgId.value)

onMounted(async () => {
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
    ready.value = !!orgId.value
  }
})

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('groups.name'), key: 'name' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const formFields = computed(() => [
  { key: 'name', label: t('groups.name'), required: true },
])
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">{{ t('common.selectCompany') }}:</span>
        <VSelect
          v-model="orgId"
          :items="orgOptions"
          density="compact"
          hide-details
          style="max-width: 360px"
          @update:model-value="ready = true"
        />
      </VCardText>
    </VCard>

    <CrudTable
      v-if="ready"
      :key="orgId"
      :title="t('nav.groups')"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '' }"
      :fetch-fn="() => api.get(`/api/orgs/${orgId}/groups`)"
      :create-fn="body => api.post(`/api/orgs/${orgId}/groups`, body)"
      :update-fn="(id, body) => api.patch(`/api/orgs/${orgId}/groups/${id}`, body)"
      :delete-fn="id => api.delete(`/api/orgs/${orgId}/groups/${id}`)"
    />
    <VAlert v-else type="info">{{ t('common.pleaseSelectCompany') }}</VAlert>
  </div>
</template>
