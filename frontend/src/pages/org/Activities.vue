<script setup>
import { useRouter } from 'vue-router'
import CrudTable from '@/components/CrudTable.vue'
import { api, ApiError } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([])
const ready = ref(false)

const loadGroups = async () => {
  if (!orgId.value) return
  const gs = await api.get(`/api/orgs/${orgId.value}/groups`)
  groupOptions.value = gs.map(g => ({ title: g.name, value: g.id }))
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
  { title: t('activities.name'), key: 'name' },
  { title: t('common.group'), key: 'group_id' },
  { title: t('activities.stagesCount'), key: 'stages_count' },
  { title: t('common.createdAt'), key: 'created_at' },
])

const formFields = computed(() => [
  { key: 'name', label: t('activities.name'), required: true },
  { key: 'group_id', label: t('activities.execGroup'), type: 'select', options: groupOptions.value, required: true },
  { key: 'welcome_message', label: t('activities.welcomeMessage'), type: 'textarea', rows: 2 },
  { key: 'closing_message', label: t('activities.closingMessage'), type: 'textarea', rows: 2 },
  { key: 'global_guideline', label: t('activities.globalGuideline'), type: 'textarea', rows: 3 },
  { key: 'stages_json', label: t('activities.stagesConfig'), type: 'textarea', rows: 8 },
])

const detailDialog = ref(false)
const currentActivity = ref(null)
const kbMounts = ref([])
const allKbs = ref([])
const mountForm = ref({ kb_id: null, priority: 0, mount_guideline: '' })
const mountErr = ref('')

const openDetail = async (item) => {
  currentActivity.value = item
  mountErr.value = ''
  detailDialog.value = true
  try {
    const [mounts, kbs] = await Promise.all([
      api.get(`/api/activities/${item.id}/kb-mounts`),
      api.get(`/api/orgs/${orgId.value}/kbs`),
    ])
    kbMounts.value = mounts
    allKbs.value = kbs
  } catch (e) {
    mountErr.value = e.detail || e.message
  }
}

const submitMount = async () => {
  if (!mountForm.value.kb_id) {
    mountErr.value = t('activities.pleaseSelectKb')
    return
  }
  try {
    await api.post('/api/kb/mount', {
      activity_id: currentActivity.value.id,
      kb_id: mountForm.value.kb_id,
      priority: Number(mountForm.value.priority) || 0,
      mount_guideline: mountForm.value.mount_guideline,
    })
    kbMounts.value = await api.get(`/api/activities/${currentActivity.value.id}/kb-mounts`)
    mountForm.value = { kb_id: null, priority: 0, mount_guideline: '' }
  } catch (e) {
    mountErr.value = e.detail || e.message
  }
}

const unmount = async (kbId) => {
  if (!confirm(t('activities.confirmUnmount'))) return
  try {
    await api.delete(`/api/activities/${currentActivity.value.id}/kb-mounts/${kbId}`)
    kbMounts.value = await api.get(`/api/activities/${currentActivity.value.id}/kb-mounts`)
  } catch (e) {
    mountErr.value = e.detail || e.message
  }
}

// 把后端返回的 stages_config (object) 在表单里显示成 JSON 文本
const beforeSave = (body) => {
  const out = { ...body }
  if (out.stages_json) {
    try { out.stages_config = JSON.parse(out.stages_json) } catch { throw new ApiError(0, t('activities.invalidStagesJson'), null) }
  } else {
    out.stages_config = null
  }
  delete out.stages_json
  return out
}
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">{{ t('common.company') }}:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
        <VSpacer />
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          {{ t('activities.manageRules') }}
        </VBtn>
      </VCardText>
    </VCard>
    <VCard v-else class="mb-4">
      <VCardText class="d-flex align-center justify-end">
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          {{ t('activities.manageRules') }}
        </VBtn>
      </VCardText>
    </VCard>

    <CrudTable
      v-if="ready"
      :key="orgId"
      :title="t('nav.activities')"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '', group_id: null, welcome_message: '', closing_message: '', global_guideline: '', stages_json: '' }"
      :fetch-fn="async () => {
        const list = await api.get(`/api/orgs/${orgId}/activities`);
        return list.map(a => ({
          ...a,
          stages_count: a.stages_config ? Object.keys(a.stages_config).length : 0,
          stages_json: a.stages_config ? JSON.stringify(a.stages_config, null, 2) : '',
        }));
      }"
      :create-fn="body => api.post(`/api/orgs/${orgId}/activities`, beforeSave(body))"
      :update-fn="(id, body) => api.patch(`/api/orgs/${orgId}/activities/${id}`, beforeSave(body))"
      :delete-fn="id => api.delete(`/api/orgs/${orgId}/activities/${id}`)"
      @row-click="openDetail"
    />

    <VDialog v-model="detailDialog" max-width="720">
      <VCard v-if="currentActivity">
        <VCardItem>
          <VCardTitle>{{ t('activities.mountKbTitle', { name: currentActivity.name }) }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VTable density="compact">
            <thead>
              <tr><th>{{ t('nav.kbs') }}</th><th>{{ t('activities.priority') }}</th><th>{{ t('activities.mountGuideline') }}</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="m in kbMounts" :key="m.kb_id">
                <td>{{ m.kb_name || m.kb_id }}</td>
                <td>{{ m.priority }}</td>
                <td style="max-width: 220px; white-space: pre-wrap;">{{ m.mount_guideline }}</td>
                <td>
                  <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="unmount(m.kb_id)" />
                </td>
              </tr>
              <tr v-if="!kbMounts.length"><td colspan="4" class="text-center text-medium-emphasis">{{ t('activities.noMounts') }}</td></tr>
            </tbody>
          </VTable>

          <VDivider class="my-4" />
          <h4 class="mb-2">{{ t('activities.mountNewKb') }}</h4>
          <VRow dense>
            <VCol cols="12" md="5">
              <VSelect
                v-model="mountForm.kb_id"
                :items="allKbs.map(k => ({ title: k.name, value: k.id }))"
                :label="t('activities.selectKb')"
                density="compact"
              />
            </VCol>
            <VCol cols="6" md="3">
              <VTextField v-model.number="mountForm.priority" type="number" :label="t('activities.priority')" density="compact" />
            </VCol>
            <VCol cols="12">
              <VTextarea v-model="mountForm.mount_guideline" :label="t('activities.mountGuidelineOptional')" rows="2" auto-grow />
            </VCol>
          </VRow>
          <VAlert v-if="mountErr" type="error" density="compact" class="mt-2">{{ mountErr }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="detailDialog = false">{{ t('general.close') }}</VBtn>
          <VBtn color="primary" @click="submitMount">{{ t('activities.mount') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
