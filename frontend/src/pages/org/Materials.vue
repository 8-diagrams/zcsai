<script setup>
import { api, mediaUrl } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([{ title: t('common.allGroups'), value: null }])
const activityOptions = ref([{ title: t('materials.generalActivity'), value: null }])
const materials = ref([])
const loading = ref(false)

const dialog = ref(false)
const editing = ref(null)
const form = ref({ title: '', kind: 'image', group_id: null, activity_id: null, description: '', media_url: '', text_content: '', is_shared_to_groups: false })
const submitting = ref(false)
const uploading = ref(false)
const errorMsg = ref('')
const fileInput = ref(null)

const loadOptions = async () => {
  if (!orgId.value) return
  const gs = await api.get(`/api/orgs/${orgId.value}/groups`)
  groupOptions.value = [{ title: t('common.allGroups'), value: null }, ...gs.map(g => ({ title: g.name, value: g.id }))]
  try {
    const acts = await api.get(`/api/orgs/${orgId.value}/activities`)
    activityOptions.value = [{ title: t('materials.generalActivity'), value: null }, ...acts.map(a => ({ title: a.name, value: a.id }))]
  } catch { activityOptions.value = [{ title: t('materials.generalActivity'), value: null }] }
}

const reload = async () => {
  if (!orgId.value) return
  loading.value = true
  try { materials.value = await api.get(`/api/orgs/${orgId.value}/materials`) }
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
  editing.value = null
  form.value = { title: '', kind: 'image', group_id: null, activity_id: null, description: '', media_url: '', text_content: '', is_shared_to_groups: false }
  errorMsg.value = ''
  dialog.value = true
}

const openEdit = (mat) => {
  editing.value = mat
  form.value = {
    title: mat.title, kind: mat.kind, group_id: mat.group_id, activity_id: mat.activity_id,
    description: mat.description || '', media_url: mat.media_url || '', text_content: mat.text_content || '',
    is_shared_to_groups: mat.is_shared_to_groups,
  }
  errorMsg.value = ''
  dialog.value = true
}

const triggerUpload = () => fileInput.value?.click()

const onFilePicked = async (e) => {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  errorMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { url, kind } = await api.postFile('/api/uploads', fd)
    form.value.media_url = url
    form.value.kind = kind
  } catch (err) {
    errorMsg.value = err.detail || err.message
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

const submit = async () => {
  errorMsg.value = ''
  submitting.value = true
  try {
    const payload = {
      title: form.value.title,
      kind: form.value.kind,
      group_id: form.value.group_id,
      activity_id: form.value.activity_id,
      description: form.value.description,
      media_url: form.value.media_url || null,
      text_content: form.value.text_content || null,
      is_shared_to_groups: form.value.is_shared_to_groups,
    }
    if (editing.value) {
      await api.patch(`/api/materials/${editing.value.id}`, payload)
    } else {
      await api.post(`/api/orgs/${orgId.value}/materials`, payload)
    }
    dialog.value = false
    await reload()
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { submitting.value = false }
}

const removeMaterial = async (mat) => {
  if (!confirm(t('materials.confirmDelete', { title: mat.title }))) return
  try { await api.delete(`/api/materials/${mat.id}`); await reload() }
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
        <VCardTitle>{{ t('nav.materials') }} <VChip size="small" class="ms-2">{{ materials.length }}</VChip></VCardTitle>
        <template #append>
          <VBtn color="primary" prepend-icon="ri-add-line" @click="openCreate">{{ t('materials.create') }}</VBtn>
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDataTable
        :headers="[
          { title: t('materials.preview'), key: 'preview', sortable: false, width: 90 },
          { title: t('materials.title'), key: 'title' },
          { title: t('materials.kind'), key: 'kind' },
          { title: t('materials.description'), key: 'description' },
          { title: t('common.group'), key: 'group_id' },
          { title: t('materials.activity'), key: 'activity_id' },
          { title: t('common.shared'), key: 'is_shared_to_groups' },
          { title: t('crud.actions'), key: 'actions', sortable: false, width: 160 },
        ]"
        :items="materials"
        :loading="loading"
        item-value="id"
      >
        <template #item.preview="{ item }">
          <img v-if="item.kind === 'image'" :src="mediaUrl(item.media_url)" style="width:56px; height:56px; object-fit:cover; border-radius:6px" />
          <VIcon v-else-if="item.kind === 'video'" icon="ri-video-line" />
          <VIcon v-else icon="ri-file-text-line" />
        </template>
        <template #item.kind="{ item }">
          <VChip size="x-small" variant="tonal">{{ item.kind }}</VChip>
        </template>
        <template #item.is_shared_to_groups="{ item }">
          <VIcon :icon="item.is_shared_to_groups ? 'ri-checkbox-circle-line' : 'ri-close-circle-line'" :color="item.is_shared_to_groups ? 'success' : 'default'" />
        </template>
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" @click="openEdit(item)">{{ t('general.edit') }}</VBtn>
          <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="removeMaterial(item)" />
        </template>
      </VDataTable>
    </VCard>

    <VDialog v-model="dialog" max-width="720">
      <VCard>
        <VCardItem>
          <VCardTitle>{{ editing ? t('materials.editTitle') : t('materials.create') }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VRow dense>
            <VCol cols="12" md="6"><VTextField v-model="form.title" :label="t('materials.titleLabel')" /></VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.kind" :items="['image', 'video', 'text']" :label="t('materials.kind')" />
            </VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.group_id" :items="groupOptions" :label="t('common.groupOptional')" />
            </VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.activity_id" :items="activityOptions" :label="t('materials.activityOptional')" />
            </VCol>
            <VCol cols="12">
              <VTextField v-model="form.description" :label="t('materials.descriptionLabel')" />
            </VCol>

            <template v-if="form.kind !== 'text'">
              <VCol cols="12" class="d-flex align-center" style="gap:8px">
                <input ref="fileInput" type="file" accept="image/*,video/*" style="display:none" @change="onFilePicked" />
                <VBtn size="small" variant="tonal" prepend-icon="ri-upload-2-line" :loading="uploading" @click="triggerUpload">{{ t('materials.uploadFile') }}</VBtn>
                <VTextField v-model="form.media_url" :label="t('materials.mediaUrlLabel')" density="compact" hide-details />
              </VCol>
              <VCol v-if="form.media_url" cols="12">
                <img v-if="form.kind === 'image'" :src="mediaUrl(form.media_url)" style="max-width:200px; max-height:160px; border-radius:8px" />
                <video v-else :src="mediaUrl(form.media_url)" controls style="max-width:280px; max-height:160px; border-radius:8px" />
              </VCol>
            </template>
            <template v-else>
              <VCol cols="12"><VTextarea v-model="form.text_content" :label="t('materials.textContent')" rows="6" auto-grow /></VCol>
            </template>

            <VCol cols="12"><VSwitch v-model="form.is_shared_to_groups" :label="t('materials.shareToOtherGroups')" inset color="primary" /></VCol>
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
