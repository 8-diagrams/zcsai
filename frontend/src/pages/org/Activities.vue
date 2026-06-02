<script setup>
import { useRouter } from 'vue-router'
import CrudTable from '@/components/CrudTable.vue'
import { api, ApiError } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

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

const headers = [
  { title: 'ID', key: 'id' },
  { title: '活动名称', key: 'name' },
  { title: '组', key: 'group_id' },
  { title: '阶段数', key: 'stages_count' },
  { title: '创建时间', key: 'created_at' },
]

const formFields = computed(() => [
  { key: 'name', label: '活动名称', required: true },
  { key: 'group_id', label: '执行组', type: 'select', options: groupOptions.value, required: true },
  { key: 'welcome_message', label: '进线欢迎语', type: 'textarea', rows: 2 },
  { key: 'closing_message', label: '结束语', type: 'textarea', rows: 2 },
  { key: 'global_guideline', label: '全局基础指引', type: 'textarea', rows: 3 },
  { key: 'stages_json', label: '阶段配置 (JSON: {"破冰":"...","探求":"..."})', type: 'textarea', rows: 8 },
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
    mountErr.value = '请选择知识库'
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
  if (!confirm('确定卸载该知识库?')) return
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
    try { out.stages_config = JSON.parse(out.stages_json) } catch { throw new ApiError(0, '阶段配置 JSON 不合法', null) }
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
        <span class="text-body-2">公司:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
        <VSpacer />
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          管理事件规则
        </VBtn>
      </VCardText>
    </VCard>
    <VCard v-else class="mb-4">
      <VCardText class="d-flex align-center justify-end">
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          管理事件规则
        </VBtn>
      </VCardText>
    </VCard>

    <CrudTable
      v-if="ready"
      :key="orgId"
      title="活动剧本"
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
          <VCardTitle>挂载知识库 — {{ currentActivity.name }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VTable density="compact">
            <thead>
              <tr><th>知识库</th><th>优先级</th><th>挂载指引</th><th></th></tr>
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
              <tr v-if="!kbMounts.length"><td colspan="4" class="text-center text-medium-emphasis">尚未挂载</td></tr>
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
          <VAlert v-if="mountErr" type="error" density="compact" class="mt-2">{{ mountErr }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="detailDialog = false">关闭</VBtn>
          <VBtn color="primary" @click="submitMount">挂载</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
