<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([{ title: '全部组', value: null }])
const activityOptions = ref([{ title: '全部活动', value: null }])
const statusOptions = [
  { title: '全部状态', value: null },
  { title: 'active', value: 'active' },
  { title: 'closed', value: 'closed' },
  { title: 'transferred', value: 'transferred' },
]

const filters = ref({ group_id: null, activity_id: null, status: null })
const sessions = ref([])
const loading = ref(false)
const selected = ref(null)
const messages = ref([])
const msgLoading = ref(false)

const loadOptions = async () => {
  if (!orgId.value) return
  const [gs, acts] = await Promise.all([
    api.get(`/api/orgs/${orgId.value}/groups`),
    api.get(`/api/orgs/${orgId.value}/activities`),
  ])
  groupOptions.value = [{ title: '全部组', value: null }, ...gs.map(g => ({ title: g.name, value: g.id }))]
  activityOptions.value = [{ title: '全部活动', value: null }, ...acts.map(a => ({ title: a.name, value: a.id }))]
}

const reload = async () => {
  if (!orgId.value) return
  loading.value = true
  try {
    const qs = new URLSearchParams()
    if (filters.value.group_id) qs.set('group_id', filters.value.group_id)
    if (filters.value.activity_id) qs.set('activity_id', filters.value.activity_id)
    if (filters.value.status) qs.set('status', filters.value.status)
    const path = `/api/orgs/${orgId.value}/sessions${qs.toString() ? '?' + qs.toString() : ''}`
    sessions.value = await api.get(path)
  } finally { loading.value = false }
}

const loadMessages = async (s) => {
  selected.value = s
  msgLoading.value = true
  try {
    messages.value = await api.get(`/api/sessions/${s.id}/messages`)
  } finally { msgLoading.value = false }
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

watch(orgId, async () => {
  selected.value = null
  messages.value = []
  await loadOptions()
  await reload()
})

watch(filters, reload, { deep: true })

const fmtTime = (t) => t ? new Date(t).toLocaleString() : ''
const statusColor = (s) => ({ active: 'success', closed: 'default', transferred: 'warning' }[s] || 'default')
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
      <VCardText class="d-flex flex-wrap align-center" style="gap:12px">
        <VSelect v-model="filters.group_id" :items="groupOptions" label="组" density="compact" hide-details style="min-width: 180px" />
        <VSelect v-model="filters.activity_id" :items="activityOptions" label="活动" density="compact" hide-details style="min-width: 220px" />
        <VSelect v-model="filters.status" :items="statusOptions" label="状态" density="compact" hide-details style="min-width: 160px" />
        <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
      </VCardText>
    </VCard>

    <VRow>
      <VCol cols="12" md="5">
        <VCard>
          <VCardItem>
            <VCardTitle>会话 <VChip size="small" class="ms-2">{{ sessions.length }}</VChip></VCardTitle>
          </VCardItem>
          <VDivider />
          <div style="max-height: 70vh; overflow:auto">
            <VList density="compact">
              <VListItem
                v-for="s in sessions"
                :key="s.id"
                :active="selected?.id === s.id"
                @click="loadMessages(s)"
              >
                <template #prepend>
                  <VAvatar size="32" color="primary" variant="tonal">
                    <VIcon icon="ri-chat-3-line" size="18" />
                  </VAvatar>
                </template>
                <VListItemTitle>
                  {{ s.visitor_uid || s.id }}
                  <VChip size="x-small" class="ms-1" :color="statusColor(s.status)">{{ s.status }}</VChip>
                </VListItemTitle>
                <VListItemSubtitle class="text-caption">
                  阶段: {{ s.current_stage || '-' }} · 渠道: {{ s.platform_type || '-' }} · {{ fmtTime(s.created_at) }}
                </VListItemSubtitle>
              </VListItem>
              <VListItem v-if="!loading && !sessions.length">
                <VListItemTitle class="text-center text-medium-emphasis">暂无会话</VListItemTitle>
              </VListItem>
            </VList>
          </div>
        </VCard>
      </VCol>

      <VCol cols="12" md="7">
        <VCard style="min-height: 70vh">
          <VCardItem>
            <VCardTitle>
              {{ selected ? (selected.visitor_uid || selected.id) : '消息流' }}
            </VCardTitle>
            <template v-if="selected" #append>
              <VChip size="small" :color="statusColor(selected.status)">{{ selected.status }}</VChip>
            </template>
          </VCardItem>
          <VDivider />
          <VCardText v-if="!selected" class="text-center text-medium-emphasis py-12">
            请选择左侧会话查看消息
          </VCardText>
          <div v-else style="max-height: 65vh; overflow:auto; padding: 12px">
            <div v-if="msgLoading" class="text-center py-4">
              <VProgressCircular indeterminate size="24" />
            </div>
            <div v-for="m in messages" :key="m.id" class="mb-3">
              <div class="d-flex align-center" style="gap:8px">
                <VChip size="x-small" :color="{
                  visitor: 'default', employee: 'primary', system: 'warning'
                }[m.sender_type] || 'default'">
                  {{ m.sender_type }}
                </VChip>
                <span class="text-caption text-medium-emphasis">{{ m.sender_id }} · {{ fmtTime(m.created_at) }}</span>
              </div>
              <div class="mt-1" style="white-space: pre-wrap">{{ m.content }}</div>
            </div>
            <div v-if="!msgLoading && !messages.length" class="text-center text-medium-emphasis py-4">
              暂无消息
            </div>
          </div>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
