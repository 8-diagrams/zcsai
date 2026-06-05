<script setup>
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([{ title: t('common.none'), value: null }])
const ready = ref(!!orgId.value)

const loadGroups = async () => {
  if (!orgId.value) return
  const gs = await api.get(`/api/orgs/${orgId.value}/groups`)
  groupOptions.value = [{ title: t('common.none'), value: null }, ...gs.map(g => ({ title: g.name, value: g.id }))]
}

onMounted(async () => {
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
  }
  if (orgId.value) {
    await loadGroups()
    ready.value = true
  }
})

watch(orgId, async () => {
  await loadGroups()
  ready.value = true
})

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('employees.name'), key: 'name' },
  { title: 'AI', key: 'is_ai' },
  { title: t('employees.status'), key: 'status' },
  { title: t('common.group'), key: 'group_id' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const formFields = computed(() => [
  { key: 'name', label: t('employees.nameLabel'), required: true },
  { key: 'group_id', label: t('common.groupLabel'), type: 'select', options: groupOptions.value },
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
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">{{ t('common.company') }}:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
      </VCardText>
    </VCard>

    <CrudTable
      v-if="ready"
      :key="orgId"
      :title="t('nav.employees')"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '', group_id: null, is_ai: false, status: 'offline' }"
      :fetch-fn="() => api.get(`/api/orgs/${orgId}/employees`)"
      :create-fn="body => api.post(`/api/orgs/${orgId}/employees`, body)"
      :update-fn="(id, body) => api.patch(`/api/orgs/${orgId}/employees/${id}`, body)"
      :delete-fn="id => api.delete(`/api/orgs/${orgId}/employees/${id}`)"
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
