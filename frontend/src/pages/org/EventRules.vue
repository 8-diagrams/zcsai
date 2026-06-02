<script setup>
// 规则列表 — 复用 CrudTable;额外加 "is_active 切换" 与 "去编辑器" 跳转。
import { useRouter } from 'vue-router'
import CrudTable from '@/components/CrudTable.vue'
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const activityOptions = ref([])
const ready = ref(false)

const loadActivities = async () => {
  if (!orgId.value) return
  const acts = await api.get(`/api/orgs/${orgId.value}/activities`)
  activityOptions.value = [
    { title: '(全部 activity 共用)', value: null },
    ...acts.map(a => ({ title: a.name, value: a.id })),
  ]
}

onMounted(async () => {
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
  }
  if (orgId.value) {
    await loadActivities()
    ready.value = true
  }
})

watch(orgId, async () => {
  await loadActivities()
  ready.value = true
})

const headers = [
  { title: 'ID', key: 'id', sortable: false },
  { title: '名称', key: 'name' },
  { title: '阶段', key: 'phase' },
  { title: '适用 activity', key: 'activity_id' },
  { title: '优先级', key: 'priority' },
  { title: 'fire_policy', key: 'fire_policy' },
  { title: '启用', key: 'is_active_switch', sortable: false },
  { title: '操作', key: 'go_edit', sortable: false },
]

const tableRef = ref(null)
const refreshList = async () => {
  if (tableRef.value && tableRef.value.reload) await tableRef.value.reload()
}

const toggleActive = async (item) => {
  await api.post(`/api/orgs/${orgId.value}/event-rules/${item.id}/toggle`, {
    is_active: !item.is_active,
  })
  await refreshList()
}

const goEdit = (id) => {
  router.push(`/org/event-rules/edit/${id || ''}`)
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

    <VCard class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <h3 class="text-h6 me-auto">事件规则</h3>
        <VBtn color="primary" prepend-icon="ri-add-line" @click="goEdit(null)">
          新建规则
        </VBtn>
      </VCardText>
    </VCard>

    <CrudTable
      v-if="ready"
      ref="tableRef"
      :key="orgId"
      title=""
      :headers="headers"
      :form-fields="[]"
      :default-form="{}"
      :create-fn="null"
      :update-fn="null"
      :fetch-fn="async () => api.get(`/api/orgs/${orgId}/event-rules`)"
      :delete-fn="id => api.delete(`/api/orgs/${orgId}/event-rules/${id}`)"
      @row-click="item => goEdit(item.id)"
    >
      <template #cell.is_active_switch="{ item }">
        <VSwitch
          :model-value="item.is_active"
          density="compact"
          color="primary"
          hide-details
          inset
          @update:model-value="toggleActive(item)"
        />
      </template>
      <template #cell.go_edit="{ item }">
        <VBtn size="small" variant="text" prepend-icon="ri-edit-line" @click="goEdit(item.id)">
          编辑
        </VBtn>
      </template>
    </CrudTable>
  </div>
</template>
