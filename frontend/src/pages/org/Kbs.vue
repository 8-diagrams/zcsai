<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([{ title: t('common.allGroups'), value: null }])
const kbs = ref([])
const loading = ref(false)

const dialog = ref(false)
const mode = ref('create') // create | append | replace
const editing = ref(null)
const form = ref({ name: '', group_id: null, usage_guideline: '', raw_text: '', is_shared_to_groups: false })
const submitting = ref(false)
const errorMsg = ref('')

const loadOptions = async () => {
  if (!orgId.value) return
  const gs = await api.get(`/api/orgs/${orgId.value}/groups`)
  groupOptions.value = [{ title: t('common.allGroups'), value: null }, ...gs.map(g => ({ title: g.name, value: g.id }))]
}

const reload = async () => {
  if (!orgId.value) return
  loading.value = true
  try { kbs.value = await api.get(`/api/orgs/${orgId.value}/kbs`) }
  finally { loading.value = false }
}

onMounted(async () => {
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
  }
  await loadOptions()
  await reload()
})

watch(orgId, async () => { await loadOptions(); await reload() })

const openCreate = () => {
  mode.value = 'create'
  editing.value = null
  form.value = { name: '', group_id: null, usage_guideline: '', raw_text: '', is_shared_to_groups: false }
  errorMsg.value = ''
  dialog.value = true
}

const openAppend = (kb) => {
  mode.value = 'append'
  editing.value = kb
  form.value = { raw_text: '' }
  errorMsg.value = ''
  dialog.value = true
}

const openReplace = (kb) => {
  mode.value = 'replace'
  editing.value = kb
  form.value = { raw_text: '' }
  errorMsg.value = ''
  dialog.value = true
}

const submit = async () => {
  errorMsg.value = ''
  submitting.value = true
  try {
    if (mode.value === 'create') {
      await api.post('/api/kb/create', {
        name: form.value.name,
        org_id: orgId.value,
        group_id: form.value.group_id,
        is_shared_to_groups: form.value.is_shared_to_groups,
        usage_guideline: form.value.usage_guideline,
        raw_text: form.value.raw_text,
      })
    } else if (mode.value === 'append') {
      await api.post('/api/kb/append', { kb_id: editing.value.id, raw_text: form.value.raw_text })
    } else {
      await api.post('/api/kb/replace', { kb_id: editing.value.id, new_raw_text: form.value.raw_text })
    }
    dialog.value = false
    await reload()
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { submitting.value = false }
}

const removeKb = async (kb) => {
  if (!confirm(t('kbs.confirmDelete', { name: kb.name }))) return
  try { await api.delete(`/api/kbs/${kb.id}`); await reload() }
  catch (e) { alert(e.detail || e.message) }
}
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">{{ t('common.company') }}:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
      </VCardText>
    </VCard>

    <VCard>
      <VCardItem>
        <VCardTitle>{{ t('nav.kbs') }} <VChip size="small" class="ms-2">{{ kbs.length }}</VChip></VCardTitle>
        <template #append>
          <VBtn color="primary" prepend-icon="ri-add-line" @click="openCreate">{{ t('kbs.create') }}</VBtn>
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDataTable
        :headers="[
          { title: 'ID', key: 'id' },
          { title: t('kbs.name'), key: 'name' },
          { title: t('kbs.usageGuideline'), key: 'usage_guideline' },
          { title: t('common.group'), key: 'group_id' },
          { title: t('common.shared'), key: 'is_shared_to_groups' },
          { title: 'Qdrant Collection', key: 'vector_collection_name' },
          { title: t('crud.actions'), key: 'actions', sortable: false, width: 220 },
        ]"
        :items="kbs"
        :loading="loading"
        item-value="id"
      >
        <template #item.is_shared_to_groups="{ item }">
          <VIcon :icon="item.is_shared_to_groups ? 'ri-checkbox-circle-line' : 'ri-close-circle-line'" :color="item.is_shared_to_groups ? 'success' : 'default'" />
        </template>
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" @click="openAppend(item)">{{ t('kbs.append') }}</VBtn>
          <VBtn size="small" variant="text" color="warning" @click="openReplace(item)">{{ t('kbs.replace') }}</VBtn>
          <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="removeKb(item)" />
        </template>
      </VDataTable>
    </VCard>

    <VDialog v-model="dialog" max-width="720">
      <VCard>
        <VCardItem>
          <VCardTitle>
            {{ { create: t('kbs.create'), append: t('kbs.appendTo', { name: editing?.name || '' }), replace: t('kbs.replaceTitle', { name: editing?.name || '' }) }[mode] }}
          </VCardTitle>
        </VCardItem>
        <VCardText>
          <VRow dense>
            <template v-if="mode === 'create'">
              <VCol cols="12" md="6"><VTextField v-model="form.name" :label="t('kbs.nameLabel')" /></VCol>
              <VCol cols="12" md="6">
                <VSelect v-model="form.group_id" :items="groupOptions" :label="t('common.groupOptional')" />
              </VCol>
              <VCol cols="12"><VTextField v-model="form.usage_guideline" :label="t('kbs.usageGuidelineLabel')" /></VCol>
              <VCol cols="12"><VSwitch v-model="form.is_shared_to_groups" :label="t('kbs.shareToGroups')" inset color="primary" /></VCol>
            </template>
            <VCol cols="12">
              <VTextarea
                v-model="form.raw_text"
                :label="mode === 'replace' ? t('kbs.newFullText') : t('kbs.rawText')"
                rows="10"
                auto-grow
              />
            </VCol>
          </VRow>
          <VAlert v-if="errorMsg" type="error" density="compact" class="mt-2">{{ errorMsg }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialog = false">{{ t('general.cancel') }}</VBtn>
          <VBtn color="primary" :loading="submitting" @click="submit">{{ t('general.save') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
