<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

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
    errorMsg.value = '请选择知识库'
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
  if (!confirm('确定卸载该知识库?')) return
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
      你尚未绑定到任何组,无法查看组内活动。
    </VAlert>

    <VCard v-else>
      <VCardItem>
        <VCardTitle>组内活动 <VChip size="small" class="ms-2">{{ items.length }}</VChip></VCardTitle>
        <template #append>
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDataTable
        :headers="[
          { title: 'ID', key: 'id' },
          { title: '活动名称', key: 'name' },
          { title: '欢迎语', key: 'welcome_message' },
          { title: '阶段数', key: 'stages_count' },
          { title: '操作', key: 'actions', sortable: false, width: 140 },
        ]"
        :items="items.map(a => ({ ...a, stages_count: a.stages_config ? Object.keys(a.stages_config).length : 0 }))"
        :loading="loading"
        item-value="id"
      >
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" @click="openDetail(item)">挂载知识库</VBtn>
        </template>
      </VDataTable>
    </VCard>

    <VDialog v-model="dialog" max-width="720">
      <VCard v-if="current">
        <VCardItem>
          <VCardTitle>挂载知识库 — {{ current.name }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VTable density="compact">
            <thead>
              <tr><th>知识库</th><th>优先级</th><th>挂载指引</th><th></th></tr>
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
              <tr v-if="!mounts.length"><td colspan="4" class="text-center text-medium-emphasis">尚未挂载</td></tr>
            </tbody>
          </VTable>

          <VDivider class="my-4" />
          <h4 class="mb-2">挂载新的知识库</h4>
          <VRow dense>
            <VCol cols="12" md="5">
              <VSelect
                v-model="mountForm.kb_id"
                :items="allKbs.map(k => ({ title: k.name, value: k.id }))"
                label="选择知识库"
                density="compact"
              />
            </VCol>
            <VCol cols="6" md="3">
              <VTextField v-model.number="mountForm.priority" type="number" label="优先级" density="compact" />
            </VCol>
            <VCol cols="12">
              <VTextarea v-model="mountForm.mount_guideline" label="挂载专属指引 (可选)" rows="2" auto-grow />
            </VCol>
          </VRow>
          <VAlert v-if="errorMsg" type="error" density="compact" class="mt-2">{{ errorMsg }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dialog = false">关闭</VBtn>
          <VBtn color="primary" @click="submitMount">挂载</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
