<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useRoute, useRouter } from 'vue-router'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const sid = computed(() => route.params.sid)
const session = ref(null)
const messages = ref([])
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const errorMsg = ref('')
const scrollerRef = ref(null)
const stagesCfg = ref({})
let stagesLoadedFor = null

const loadStages = async () => {
  const aid = session.value?.activity_id
  if (!aid || aid === stagesLoadedFor) return
  if (!auth.orgId) return
  try {
    const acts = await api.get(`/api/orgs/${auth.orgId}/activities`)
    const a = acts.find(x => x.id === aid)
    stagesCfg.value = a?.stages_config || {}
    stagesLoadedFor = aid
  } catch { stagesCfg.value = {} }
}

const reload = async () => {
  loading.value = true
  errorMsg.value = ''
  try {
    const list = await api.get('/api/me/sessions')
    session.value = list.find(s => s.id === sid.value) || null
    if (!session.value) {
      const all = await api.get('/api/me/sessions?status=closed')
      session.value = all.find(s => s.id === sid.value) || null
    }
    await loadStages()
    messages.value = await api.get(`/api/sessions/${sid.value}/messages`)
    await nextTick()
    if (scrollerRef.value) scrollerRef.value.scrollTop = scrollerRef.value.scrollHeight
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { loading.value = false }
}

const send = async () => {
  const text = input.value.trim()
  if (!text) return
  sending.value = true
  try {
    await api.post(`/api/sessions/${sid.value}/messages`, { content: text })
    input.value = ''
    await reload()
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { sending.value = false }
}

const close = async () => {
  if (!confirm('确定关闭该会话?')) return
  try {
    await api.post(`/api/sessions/${sid.value}/close`, {})
    await reload()
  } catch (e) { errorMsg.value = e.detail || e.message }
}

onMounted(reload)
watch(sid, reload)

let timer = null
onMounted(() => {
  timer = setInterval(() => {
    if (session.value?.status === 'active') reload()
  }, 4000)
})
onUnmounted(() => timer && clearInterval(timer))

const fmtTime = (t) => t ? new Date(t).toLocaleTimeString() : ''
const statusColor = (s) => ({ active: 'success', closed: 'default', transferred: 'warning' }[s] || 'default')
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
  return stagesCfg.value?.[code]?.name || code
}
</script>

<template>
  <div>
    <VBtn variant="text" prepend-icon="ri-arrow-left-line" class="mb-2" @click="router.push('/me/sessions')">返回会话列表</VBtn>

    <VCard>
      <VCardItem>
        <VCardTitle>
          会话: {{ session?.visitor_uid || sid }}
        </VCardTitle>
        <VCardSubtitle v-if="session">
          阶段: {{ session.current_stage || '-' }} · 活动: {{ session.activity_id || '-' }} · 渠道: {{ session.platform_type || '-' }}
        </VCardSubtitle>
        <template v-if="session" #append>
          <VChip size="small" :color="statusColor(session.status)">{{ session.status }}</VChip>
          <VBtn
            v-if="session.status === 'active'"
            size="small"
            variant="text"
            color="error"
            class="ms-2"
            @click="close"
          >
            关闭
          </VBtn>
        </template>
      </VCardItem>
      <VDivider />

      <div ref="scrollerRef" style="height: 60vh; overflow:auto; padding: 12px; background: rgba(0,0,0,0.02)">
        <div v-if="loading && !messages.length" class="text-center py-4">
          <VProgressCircular indeterminate size="24" />
        </div>
        <div
          v-for="m in messages"
          :key="m.id"
          class="mb-3 d-flex"
          :class="m.sender_type === 'visitor' ? 'justify-start' : 'justify-end'"
        >
          <div :style="{
            maxWidth: '70%',
            padding: '8px 12px',
            borderRadius: '8px',
            background: m.sender_type === 'visitor' ? '#fff' : (m.sender_type === 'system' ? '#fff8e1' : '#dcedc8'),
            border: '1px solid rgba(0,0,0,0.08)'
          }">
            <div class="text-caption text-medium-emphasis mb-1 d-flex align-center flex-wrap" style="gap:6px">
              <span>{{ m.sender_type }}{{ m.sender_id ? ' · ' + m.sender_id : '' }} · {{ fmtTime(m.created_at) }}</span>
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
            </div>
            <div style="white-space: pre-wrap">{{ m.content }}</div>
          </div>
        </div>
        <div v-if="!loading && !messages.length" class="text-center text-medium-emphasis py-4">
          暂无消息
        </div>
      </div>

      <VDivider />
      <VCardText>
        <VAlert v-if="errorMsg" type="error" density="compact" class="mb-2">{{ errorMsg }}</VAlert>
        <div class="d-flex" style="gap:8px">
          <VTextarea
            v-model="input"
            placeholder="输入回复内容,Ctrl/Cmd + Enter 发送"
            rows="2"
            auto-grow
            hide-details
            :disabled="session?.status !== 'active'"
            @keydown.enter.exact.ctrl.prevent="send"
            @keydown.enter.exact.meta.prevent="send"
          />
          <VBtn
            color="primary"
            :loading="sending"
            :disabled="session?.status !== 'active' || !input.trim()"
            @click="send"
          >
            发送
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>
