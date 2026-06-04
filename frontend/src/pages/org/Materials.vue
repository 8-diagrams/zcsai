<script setup>
import { api, mediaUrl } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([{ title: '所有组', value: null }])
const activityOptions = ref([{ title: '通用 (不限活动)', value: null }])
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
  groupOptions.value = [{ title: '所有组', value: null }, ...gs.map(g => ({ title: g.name, value: g.id }))]
  try {
    const acts = await api.get(`/api/orgs/${orgId.value}/activities`)
    activityOptions.value = [{ title: '通用 (不限活动)', value: null }, ...acts.map(a => ({ title: a.name, value: a.id }))]
  } catch { activityOptions.value = [{ title: '通用 (不限活动)', value: null }] }
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
  if (!confirm(`确定删除素材 "${mat.title}"?`)) return
  try { await api.delete(`/api/materials/${mat.id}`); await reload() }
  catch (e) { alert(e.detail || e.message) }
}
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">公司:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
      </VCardText>
    </VCard>

    <VCard>
      <VCardItem>
        <VCardTitle>素材库 <VChip size="small" class="ms-2">{{ materials.length }}</VChip></VCardTitle>
        <template #append>
          <VBtn color="primary" prepend-icon="ri-add-line" @click="openCreate">新建素材</VBtn>
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDataTable
        :headers="[
          { title: '预览', key: 'preview', sortable: false, width: 90 },
          { title: '标题', key: 'title' },
          { title: '类型', key: 'kind' },
          { title: '描述', key: 'description' },
          { title: '组', key: 'group_id' },
          { title: '活动', key: 'activity_id' },
          { title: '共享', key: 'is_shared_to_groups' },
          { title: '操作', key: 'actions', sortable: false, width: 160 },
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
          <VBtn size="small" variant="text" @click="openEdit(item)">编辑</VBtn>
          <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="removeMaterial(item)" />
        </template>
      </VDataTable>
    </VCard>

    <VDialog v-model="dialog" max-width="720">
      <VCard>
        <VCardItem>
          <VCardTitle>{{ editing ? '编辑素材' : '新建素材' }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VRow dense>
            <VCol cols="12" md="6"><VTextField v-model="form.title" label="素材标题" /></VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.kind" :items="['image', 'video', 'text']" label="类型" />
            </VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.group_id" :items="groupOptions" label="所属组 (可空)" />
            </VCol>
            <VCol cols="12" md="6">
              <VSelect v-model="form.activity_id" :items="activityOptions" label="所属活动 (可空=通用)" />
            </VCol>
            <VCol cols="12">
              <VTextField v-model="form.description" label="选材描述 (给 LLM 看的依据)" />
            </VCol>

            <template v-if="form.kind !== 'text'">
              <VCol cols="12" class="d-flex align-center" style="gap:8px">
                <input ref="fileInput" type="file" accept="image/*,video/*" style="display:none" @change="onFilePicked" />
                <VBtn size="small" variant="tonal" prepend-icon="ri-upload-2-line" :loading="uploading" @click="triggerUpload">上传文件</VBtn>
                <VTextField v-model="form.media_url" label="媒体 URL (或粘贴外链)" density="compact" hide-details />
              </VCol>
              <VCol v-if="form.media_url" cols="12">
                <img v-if="form.kind === 'image'" :src="mediaUrl(form.media_url)" style="max-width:200px; max-height:160px; border-radius:8px" />
                <video v-else :src="mediaUrl(form.media_url)" controls style="max-width:280px; max-height:160px; border-radius:8px" />
              </VCol>
            </template>
            <template v-else>
              <VCol cols="12"><VTextarea v-model="form.text_content" label="文本内容" rows="6" auto-grow /></VCol>
            </template>

            <VCol cols="12"><VSwitch v-model="form.is_shared_to_groups" label="共享给同公司其他组" inset color="primary" /></VCol>
          </VRow>
          <VAlert v-if="errorMsg" type="error" density="compact" class="mt-2">{{ errorMsg }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialog = false">取消</VBtn>
          <VBtn color="primary" :loading="submitting" @click="submit">保存</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
