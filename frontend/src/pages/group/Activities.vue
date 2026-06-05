<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const current = ref(null)
const mounts = ref([])
const allKbs = ref([])
const mountForm = ref({ kb_id: null, priority: 0, mount_guideline: '' })
const errorMsg = ref('')

const reload = async () => {
  if (!auth.orgId || !auth.groupId) return
  loading.value = true
  try {
    items.value = await api.get(`/api/orgs/${auth.orgId}/activities?group_id=${auth.groupId}`)
  } finally { loading.value = false }
}

const openDetail = async (item) => {
  current.value = item
  errorMsg.value = ''
  dialog.value = true
  try {
    const [m, kbs] = await Promise.all([
      api.get(`/api/activities/${item.id}/kb-mounts`),
      api.get(`/api/orgs/${auth.orgId}/kbs`),
    ])
    mounts.value = m
    allKbs.value = kbs
  } catch (e) { errorMsg.value = e.detail || e.message }
}

const submitMount = async () => {
  if (!mountForm.value.kb_id) {
    errorMsg.value = t('activities.pleaseSelectKb')
    return
  }
  try {
    await api.post('/api/kb/mount', {
      activity_id: current.value.id,
      kb_id: mountForm.value.kb_id,
      priority: Number(mountForm.value.priority) || 0,
      mount_guideline: mountForm.value.mount_guideline,
    })
    mounts.value = await api.get(`/api/activities/${current.value.id}/kb-mounts`)
    mountForm.value = { kb_id: null, priority: 0, mount_guideline: '' }
  } catch (e) { errorMsg.value = e.detail || e.message }
}

const unmount = async (kbId) => {
  if (!confirm(t('activities.confirmUnmount'))) return
  try {
    await api.delete(`/api/activities/${current.value.id}/kb-mounts/${kbId}`)
    mounts.value = await api.get(`/api/activities/${current.value.id}/kb-mounts`)
  } catch (e) { errorMsg.value = e.detail || e.message }
}

onMounted(reload)
</script>

<template>
  <div>
    <VAlert v-if="!auth.groupId" type="warning" class="mb-4">
      {{ t('groupActivities.noGroupBound') }}
    </VAlert>

    <VCard v-else>
      <VCardItem>
        <VCardTitle>{{ t('nav.groupActivities') }} <VChip size="small" class="ms-2">{{ items.length }}</VChip></VCardTitle>
        <template #append>
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDataTable
        :headers="[
          { title: 'ID', key: 'id' },
          { title: t('activities.name'), key: 'name' },
          { title: t('activities.welcomeMessageShort'), key: 'welcome_message' },
          { title: t('activities.stagesCount'), key: 'stages_count' },
          { title: t('crud.actions'), key: 'actions', sortable: false, width: 140 },
        ]"
        :items="items.map(a => ({ ...a, stages_count: a.stages_config ? Object.keys(a.stages_config).length : 0 }))"
        :loading="loading"
        item-value="id"
      >
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" @click="openDetail(item)">{{ t('activities.mountKb') }}</VBtn>
        </template>
      </VDataTable>
    </VCard>

    <VDialog v-model="dialog" max-width="720">
      <VCard v-if="current">
        <VCardItem>
          <VCardTitle>{{ t('activities.mountKbTitle', { name: current.name }) }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VTable density="compact">
            <thead>
              <tr><th>{{ t('nav.kbs') }}</th><th>{{ t('activities.priority') }}</th><th>{{ t('activities.mountGuideline') }}</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="m in mounts" :key="m.kb_id">
                <td>{{ m.kb_name || m.kb_id }}</td>
                <td>{{ m.priority }}</td>
                <td style="max-width: 220px; white-space: pre-wrap;">{{ m.mount_guideline }}</td>
                <td>
                  <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="unmount(m.kb_id)" />
                </td>
              </tr>
              <tr v-if="!mounts.length"><td colspan="4" class="text-center text-medium-emphasis">{{ t('activities.noMounts') }}</td></tr>
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
          <VAlert v-if="errorMsg" type="error" density="compact" class="mt-2">{{ errorMsg }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialog = false">{{ t('general.close') }}</VBtn>
          <VBtn color="primary" @click="submitMount">{{ t('activities.mount') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
