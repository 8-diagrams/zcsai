<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const activityOptions = ref([{ title: t('sessions.allActivities'), value: null }])
const statusOptions = computed(() => [
  { title: t('sessions.allStatus'), value: null },
  { title: 'active', value: 'active' },
  { title: 'closed', value: 'closed' },
  { title: 'transferred', value: 'transferred' },
])

const filters = ref({ activity_id: null, status: 'active' })
const sessions = ref([])
const loading = ref(false)
const selected = ref(null)
const messages = ref([])
const msgLoading = ref(false)
const stagesByActivity = ref({})
const employees = ref([])

const loadOptions = async () => {
  if (!auth.orgId || !auth.groupId) return
  const [acts, emps] = await Promise.all([
    api.get(`/api/orgs/${auth.orgId}/activities?group_id=${auth.groupId}`),
    api.get(`/api/orgs/${auth.orgId}/employees?group_id=${auth.groupId}`),
  ])
  activityOptions.value = [{ title: t('sessions.allActivities'), value: null }, ...acts.map(a => ({ title: a.name, value: a.id }))]
  stagesByActivity.value = Object.fromEntries(acts.map(a => [a.id, a.stages_config || {}]))
  employees.value = emps
}

// 转接目标可选项: 仅组内真人坐席 (转接=转人工接管, AI 坐席无意义), 排除会话当前坐席
const transferOptions = computed(() =>
  employees.value
    .filter(e => !e.is_ai)
    .filter(e => !selected.value || e.id !== selected.value.employee_id)
    .map(e => ({
      title: `${e.name} · ${e.status}`,
      value: e.id,
    })),
)

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

// silent=true 用于定时轮询: 不显示 spinner、内容无变化不重赋值, 避免每 5 秒闪烁/跳动
const loadMessages = async (s, { silent = false } = {}) => {
  selected.value = s
  if (!silent) msgLoading.value = true
  try {
    const newMsgs = await api.get(`/api/sessions/${s.id}/messages`)
    const prev = messages.value
    const changed = newMsgs.length !== prev.length || newMsgs.at(-1)?.id !== prev.at(-1)?.id
    if (changed) messages.value = newMsgs
  } finally { if (!silent) msgLoading.value = false }
}

const transferDialog = ref(false)
const transferTarget = ref(null)
const transferErr = ref('')
const transferring = ref(false)

const openTransfer = () => {
  if (!selected.value) return
  transferTarget.value = null
  transferErr.value = ''
  transferDialog.value = true
}

const submitTransfer = async () => {
  if (!selected.value || !transferTarget.value) return
  transferring.value = true
  transferErr.value = ''
  try {
    await api.post(`/api/sessions/${selected.value.id}/transfer`, { target_employee_id: transferTarget.value })
    transferDialog.value = false
    await reload()
    await loadMessages(sessions.value.find(s => s.id === selected.value.id) || selected.value)
  } catch (e) {
    transferErr.value = e.detail || e.message
  } finally { transferring.value = false }
}

onMounted(async () => {
  await loadOptions()
  await reload()
})
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
const EMOTION_COLOR = {
  calm: 'default', joy: 'success', excited: 'success',
  hesitation: 'info', impatience: 'warning', anger: 'error',
}
const emotionMeta = (e) => e && EMOTION_COLOR[e] ? { label: t(`session.emotion.${e}`), color: EMOTION_COLOR[e] } : null
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
      {{ t('groupSessions.noGroupBound') }}
    </VAlert>

    <VCard class="mb-4">
      <VCardText class="d-flex flex-wrap align-center" style="gap:12px">
        <VSelect v-model="filters.activity_id" :items="activityOptions" :label="t('sessions.activity')" density="compact" hide-details style="min-width: 220px" />
        <VSelect v-model="filters.status" :items="statusOptions" :label="t('sessions.status')" density="compact" hide-details style="min-width: 160px" />
        <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
      </VCardText>
    </VCard>

    <VRow>
      <VCol cols="12" md="5">
        <VCard>
          <VCardItem>
            <VCardTitle>{{ t('groupSessions.title') }} <VChip size="small" class="ms-2">{{ sessions.length }}</VChip></VCardTitle>
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
                  <span v-if="s.visitor_nickname && s.visitor_uid">ID: {{ s.visitor_uid }} · </span>{{ t('nav.employees') }}: {{ s.employee_id || '-' }} · {{ t('sessions.stage') }}: {{ s.current_stage || '-' }} · {{ fmtTime(s.created_at) }}
                </VListItemSubtitle>
              </VListItem>
              <VListItem v-if="!loading && !sessions.length">
                <VListItemTitle class="text-center text-medium-emphasis">{{ t('sessions.noSessions') }}</VListItemTitle>
              </VListItem>
            </VList>
          </div>
        </VCard>
      </VCol>

      <VCol cols="12" md="7">
        <VCard style="min-height: 70vh">
          <VCardItem>
            <VCardTitle>
              {{ selected ? visitorName(selected) : t('sessions.messageFlow') }}
            </VCardTitle>
            <template v-if="selected" #append>
              <VBtn size="small" variant="text" color="warning" @click="openTransfer">{{ t('session.transfer') }}</VBtn>
              <VChip size="small" class="ms-2" :color="statusColor(selected.status)">{{ selected.status }}</VChip>
            </template>
          </VCardItem>
          <VDivider />
          <VCardText v-if="!selected" class="text-center text-medium-emphasis py-12">
            {{ t('sessions.selectToView') }}
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
              <div class="mt-1"><MessageContent :m="m" /></div>
            </div>
            <div v-if="!msgLoading && !messages.length" class="text-center text-medium-emphasis py-4">
              {{ t('sessions.noMessages') }}
            </div>
          </div>
        </VCard>
      </VCol>
    </VRow>

    <!-- 转接对话框: 从组内坐席中选择 -->
    <VDialog v-model="transferDialog" max-width="420">
      <VCard>
        <VCardItem>
          <VCardTitle>{{ t('groupSessions.transferTitle') }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VSelect
            v-model="transferTarget"
            :items="transferOptions"
            :label="t('groupSessions.transferTargetLabel')"
            :no-data-text="t('groupSessions.noTransferTarget')"
            density="compact"
          />
          <VAlert v-if="transferErr" type="error" density="compact" class="mt-2">{{ transferErr }}</VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="transferDialog = false">{{ t('general.cancel') }}</VBtn>
          <VBtn color="primary" :loading="transferring" :disabled="!transferTarget" @click="submitTransfer">
            {{ t('session.transfer') }}
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
