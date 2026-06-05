<script setup>
import { api, mediaUrl } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
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

// silent=true 用于定时轮询: 不显示 loading、内容无变化不重渲染、
// 仅在用户原本就贴着底部且有新消息时才自动滚到底 (避免往上翻看历史时被拽回去)。
const reload = async ({ silent = false } = {}) => {
  if (!silent) loading.value = true
  errorMsg.value = ''
  try {
    const list = await api.get('/api/me/sessions')
    session.value = list.find(s => s.id === sid.value) || null
    if (!session.value) {
      const all = await api.get('/api/me/sessions?status=closed')
      session.value = all.find(s => s.id === sid.value) || null
    }
    await loadStages()

    const el = scrollerRef.value
    const wasNearBottom = el ? (el.scrollHeight - el.scrollTop - el.clientHeight < 80) : true
    const newMsgs = await api.get(`/api/sessions/${sid.value}/messages`)
    const prev = messages.value
    // 内容无变化 (条数相同且末条 id 相同) 就不重赋值, 避免无谓重渲染
    const changed = newMsgs.length !== prev.length || newMsgs.at(-1)?.id !== prev.at(-1)?.id
    if (changed) messages.value = newMsgs

    await nextTick()
    if (el && (!silent || (changed && wasNearBottom))) {
      el.scrollTop = el.scrollHeight
    }
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { if (!silent) loading.value = false }
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
  if (!confirm(t('meSession.confirmClose'))) return
  try {
    await api.post(`/api/sessions/${sid.value}/close`, {})
    await reload()
  } catch (e) { errorMsg.value = e.detail || e.message }
}

// ===== 媒体发送 (走 agent-reply, 需会话处于人工接管中) =====
const fileInput = ref(null)
const uploading = ref(false)
const matDialog = ref(false)
const materials = ref([])
const matLoading = ref(false)

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
    await api.post(`/api/sessions/${sid.value}/agent-reply`, { content_type: kind, media_url: url })
    await reload()
  } catch (err) {
    errorMsg.value = err.detail || err.message
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

const openMaterials = async () => {
  matDialog.value = true
  matLoading.value = true
  try {
    const aid = session.value?.activity_id
    materials.value = await api.get(`/api/orgs/${auth.orgId}/materials`, aid ? { activity_id: aid } : {})
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { matLoading.value = false }
}

const sendMaterial = async (mat) => {
  try {
    await api.post(`/api/sessions/${sid.value}/agent-reply`, { material_id: mat.id })
    matDialog.value = false
    await reload()
  } catch (e) { errorMsg.value = e.detail || e.message }
}

onMounted(() => reload())
watch(sid, () => reload())

let timer = null
onMounted(() => {
  timer = setInterval(() => {
    if (session.value?.status === 'active') reload({ silent: true })
  }, 4000)
})
onUnmounted(() => timer && clearInterval(timer))

const fmtTime = (t) => t ? new Date(t).toLocaleTimeString() : ''
const statusColor = (s) => ({ active: 'success', closed: 'default', transferred: 'warning' }[s] || 'default')

// 访客展示名: 优先昵称, 其次平台ID, 最后会话ID
const visitorName = computed(() =>
  session.value?.visitor_nickname || session.value?.visitor_uid || sid.value
)
// 单条消息的发送方标签: 访客优先用发出时的昵称快照, 退回当前会话昵称/平台ID
const senderLabel = (m) => {
  if (m.sender_type === 'visitor') {
    return m.visitor_nickname_at_send || m.visitor_platform_id_at_send || visitorName.value
  }
  return m.sender_id ? `${m.sender_type} · ${m.sender_id}` : m.sender_type
}
const EMOTION_COLOR = {
  calm: 'default', joy: 'success', excited: 'success',
  hesitation: 'info', impatience: 'warning', anger: 'error',
}
const emotionMeta = (e) => e && EMOTION_COLOR[e] ? { label: t(`session.emotion.${e}`), color: EMOTION_COLOR[e] } : null
const stageLabel = (code) => {
  if (!code) return ''
  return stagesCfg.value?.[code]?.name || code
}
</script>

<template>
  <div>
    <VBtn variant="text" prepend-icon="ri-arrow-left-line" class="mb-2" @click="router.push('/me/sessions')">{{ t('meSession.backToList') }}</VBtn>

    <VCard>
      <VCardItem>
        <VCardTitle>
          {{ t('meSession.sessionLabel') }}: {{ visitorName }}
        </VCardTitle>
        <VCardSubtitle v-if="session">
          <span v-if="session.visitor_nickname && session.visitor_uid">ID: {{ session.visitor_uid }} · </span>{{ t('sessions.stage') }}: {{ session.current_stage || '-' }} · {{ t('sessions.activity') }}: {{ session.activity_id || '-' }} · {{ t('sessions.channel') }}: {{ session.platform_type || '-' }}
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
            {{ t('general.close') }}
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
              <span>{{ senderLabel(m) }} · {{ fmtTime(m.created_at) }}</span>
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
            <MessageContent :m="m" />
          </div>
        </div>
        <div v-if="!loading && !messages.length" class="text-center text-medium-emphasis py-4">
          {{ t('sessions.noMessages') }}
        </div>
      </div>

      <VDivider />
      <VCardText>
        <VAlert v-if="errorMsg" type="error" density="compact" class="mb-2">{{ errorMsg }}</VAlert>
        <div class="d-flex" style="gap:8px">
          <VTextarea
            v-model="input"
            :placeholder="t('meSession.inputPlaceholder')"
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
            {{ t('session.send') }}
          </VBtn>
        </div>
        <div class="d-flex mt-2" style="gap:8px">
          <input ref="fileInput" type="file" accept="image/*,video/*" style="display:none" @change="onFilePicked" />
          <VBtn
            size="small"
            variant="tonal"
            prepend-icon="ri-image-add-line"
            :loading="uploading"
            :disabled="session?.status !== 'active'"
            @click="triggerUpload"
          >
            {{ t('meSession.uploadMedia') }}
          </VBtn>
          <VBtn
            size="small"
            variant="tonal"
            prepend-icon="ri-folder-image-line"
            :disabled="session?.status !== 'active'"
            @click="openMaterials"
          >
            {{ t('meSession.pickFromLibrary') }}
          </VBtn>
        </div>
        <div class="text-caption text-medium-emphasis mt-1">
          {{ t('meSession.mediaNeedsTakeover') }}
        </div>
      </VCardText>
    </VCard>

    <!-- 素材库选择 -->
    <VDialog v-model="matDialog" max-width="640">
      <VCard :title="t('meSession.pickFromLibraryTitle')">
        <VCardText>
          <div v-if="matLoading" class="text-center py-4">{{ t('common.loading') }}</div>
          <div v-else-if="!materials.length" class="text-center text-medium-emphasis py-4">{{ t('meSession.noMaterials') }}</div>
          <VRow v-else>
            <VCol v-for="mat in materials" :key="mat.id" cols="6" md="4">
              <VCard variant="outlined" class="pa-2" style="cursor:pointer" @click="sendMaterial(mat)">
                <img v-if="mat.kind === 'image'" :src="mediaUrl(mat.media_url)" style="width:100%; height:96px; object-fit:cover; border-radius:6px" />
                <video v-else-if="mat.kind === 'video'" :src="mediaUrl(mat.media_url)" style="width:100%; height:96px; object-fit:cover; border-radius:6px" />
                <div v-else class="text-truncate text-caption pa-2" style="height:96px; overflow:hidden">{{ mat.text_content }}</div>
                <div class="text-caption font-weight-medium text-truncate mt-1">{{ mat.title }}</div>
                <VChip size="x-small" variant="tonal">{{ mat.kind }}</VChip>
              </VCard>
            </VCol>
          </VRow>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn @click="matDialog = false">{{ t('general.close') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
