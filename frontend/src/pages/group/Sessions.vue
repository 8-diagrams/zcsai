<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const activityOptions = ref([{ title: '全部活动', value: null }])
const statusOptions = [
  { title: '全部状态', value: null },
  { title: 'active', value: 'active' },
  { title: 'closed', value: 'closed' },
  { title: 'transferred', value: 'transferred' },
]

const filters = ref({ activity_id: null, status: 'active' })
const sessions = ref([])
const loading = ref(false)
const selected = ref(null)
const messages = ref([])
const msgLoading = ref(false)
const stagesByActivity = ref({})

const loadOptions = async () => {
  if (!auth.orgId || !auth.groupId) return
  const acts = await api.get(`/api/orgs/${auth.orgId}/activities?group_id=${auth.groupId}`)
  activityOptions.value = [{ title: '全部活动', value: null }, ...acts.map(a => ({ title: a.name, value: a.id }))]
  stagesByActivity.value = Object.fromEntries(acts.map(a => [a.id, a.stages_config || {}]))
}

const reload = async () => {
  if (!auth.orgId || !auth.groupId) return
  loading.value = true
  try {
    const qs = new URLSearchParams()
    qs.set('group_id', auth.groupId)
    if (filters.value.activity_id) qs.set('activity_id', filters.value.activity_id)
    if (filters.value.status) qs.set('status', filters.value.status)
    sessions.value = await api.get(`/api/orgs/${auth.orgId}/sessions?${qs.toString()}`)
  } finally { loading.value = false }
}

const loadMessages = async (s) => {
  selected.value = s
  msgLoading.value = true
  try { messages.value = await api.get(`/api/sessions/${s.id}/messages`) }
  finally { msgLoading.value = false }
}

const transfer = async () => {
  if (!selected.value) return
  const target = prompt('转接到目标坐席 ID(可填 AI 坐席 ID):')
  if (!target) return
  try {
    await api.post(`/api/sessions/${selected.value.id}/transfer`, { target_employee_id: target.trim() })
    await reload()
    await loadMessages(sessions.value.find(s => s.id === selected.value.id) || selected.value)
  } catch (e) { alert(e.detail || e.message) }
}

let timer = null
onMounted(async () => {
  await loadOptions()
  await reload()
  timer = setInterval(() => {
    if (filters.value.status === 'active') {
      reload()
      if (selected.value) loadMessages(selected.value)
    }
  }, 5000)
})
onUnmounted(() => timer && clearInterval(timer))
watch(filters, reload, { deep: true })

const fmtTime = (t) => t ? new Date(t).toLocaleString() : ''
const statusColor = (s) => ({ active: 'success', closed: 'default', transferred: 'warning' }[s] || 'default')
// 访客展示名: 优先昵称, 其次平台ID, 最后会话ID
const visitorName = (s) => s?.visitor_nickname || s?.visitor_uid || s?.id || ''
// 单条消息发送方标签: 访客优先用发出时昵称快照, 退回当前会话昵称/平台ID
const senderLabel = (m) => {
  if (m.sender_type === 'visitor') {
    return m.visitor_nickname_at_send || m.visitor_platform_id_at_send || visitorName(selected.value)
  }
  return m.sender_id || ''
}
const EMOTION_META = {
  calm:       { label: '平静', color: 'default' },
  joy:        { label: '喜悦', color: 'success' },
  excited:    { label: '兴奋', color: 'success' },
  hesitation: { label: '犹豫', color: 'info' },
  impatience: { label: '急躁', color: 'warning' },
  anger:      { label: '愤怒', color: 'error' },
}
const emotionMeta = (e) => EMOTION_META[e] || null
const stageLabel = (code) => {
  if (!code) return ''
  const aid = selected.value?.activity_id
  const cfg = aid && stagesByActivity.value[aid]
  return cfg?.[code]?.name || code
}
</script>

<template>
  <div>
    <VAlert v-if="!auth.groupId" type="warning" class="mb-4">
      你尚未绑定到任何组。
    </VAlert>

    <VCard class="mb-4">
      <VCardText class="d-flex flex-wrap align-center" style="gap:12px">
        <VSelect v-model="filters.activity_id" :items="activityOptions" label="活动" density="compact" hide-details style="min-width: 220px" />
        <VSelect v-model="filters.status" :items="statusOptions" label="状态" density="compact" hide-details style="min-width: 160px" />
        <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        <span class="text-caption text-medium-emphasis">活跃会话每 5 秒自动刷新</span>
      </VCardText>
    </VCard>

    <VRow>
      <VCol cols="12" md="5">
        <VCard>
          <VCardItem>
            <VCardTitle>本组会话 <VChip size="small" class="ms-2">{{ sessions.length }}</VChip></VCardTitle>
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
                <VListItemTitle>
                  {{ visitorName(s) }}
                  <VChip size="x-small" class="ms-1" :color="statusColor(s.status)">{{ s.status }}</VChip>
                </VListItemTitle>
                <VListItemSubtitle class="text-caption">
                  <span v-if="s.visitor_nickname && s.visitor_uid">ID: {{ s.visitor_uid }} · </span>坐席: {{ s.employee_id || '-' }} · 阶段: {{ s.current_stage || '-' }} · {{ fmtTime(s.created_at) }}
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
              {{ selected ? visitorName(selected) : '消息流' }}
            </VCardTitle>
            <template v-if="selected" #append>
              <VBtn size="small" variant="text" color="warning" @click="transfer">转接</VBtn>
              <VChip size="small" class="ms-2" :color="statusColor(selected.status)">{{ selected.status }}</VChip>
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
              <div class="d-flex align-center flex-wrap" style="gap:8px">
                <VChip size="x-small" :color="{
                  visitor: 'default', employee: 'primary', system: 'warning'
                }[m.sender_type] || 'default'">
                  {{ m.sender_type }}
                </VChip>
                <VChip
                  v-if="m.stage_at_send"
                  size="x-small"
                  variant="outlined"
                  color="info"
                >
                  {{ stageLabel(m.stage_at_send) }}
                </VChip>
                <VChip
                  v-if="m.sender_type === 'visitor' && emotionMeta(m.emotion_at_send)"
                  size="x-small"
                  variant="tonal"
                  :color="emotionMeta(m.emotion_at_send).color"
                >
                  {{ emotionMeta(m.emotion_at_send).label }}
                </VChip>
                <span class="text-caption text-medium-emphasis">{{ senderLabel(m) }} · {{ fmtTime(m.created_at) }}</span>
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
