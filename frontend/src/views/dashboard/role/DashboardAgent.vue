<script setup>
import { api } from '@/utils/api'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import StatCard from './StatCard.vue'

const { t } = useI18n()
const router = useRouter()

const summary = ref(null)
const mySessions = ref([])
const myNotifications = ref([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const [s, sessions, notis] = await Promise.all([
      api.get('/api/dashboard/summary'),
      api.get('/api/me/sessions', { status: 'active', limit: 10 }),
      api.get('/api/me/notifications', { unread_only: true, limit: 10 }),
    ])
    summary.value = s
    mySessions.value = sessions
    myNotifications.value = notis
  } finally { loading.value = false }
}
onMounted(load)

const my = computed(() => summary.value?.my || {})
const cards = computed(() => [
  { title: t('dashboard.myActiveSessions'), icon: 'ri-chat-poll-line', color: 'success', stats: my.value.active_sessions ?? 0 },
  { title: t('dashboard.myTakeover'), icon: 'ri-user-shared-line', color: 'warning', stats: my.value.takeover_sessions ?? 0 },
  { title: t('dashboard.unreadNotifications'), icon: 'ri-notification-3-line', color: 'error', stats: my.value.unread_notifications ?? 0 },
])

const visitorName = (s) => s.visitor_nickname || s.visitor_uid || s.id
const openSession = (s) => router.push(`/me/session/${s.id}`)
const levelColor = (lv) => ({ info: 'info', warning: 'warning', urgent: 'error' }[lv] || 'default')
const fmtTime = (d) => d ? new Date(d).toLocaleString() : ''
</script>

<template>
  <div>
    <h2 class="text-h5 mb-4">{{ t('dashboard.agentTitle') }}</h2>
    <VRow>
      <VCol v-for="card in cards" :key="card.title" cols="12" sm="4">
        <StatCard v-bind="card" />
      </VCol>
    </VRow>

    <VRow class="mt-2">
      <!-- 我的近期会话 -->
      <VCol cols="12" md="7">
        <VCard :title="t('dashboard.myRecentSessions')">
          <VDivider />
          <VList v-if="mySessions.length">
            <VListItem
              v-for="s in mySessions"
              :key="s.id"
              @click="openSession(s)"
              style="cursor:pointer"
            >
              <template #prepend>
                <VAvatar size="32" color="primary" variant="tonal">
                  <VIcon icon="ri-chat-3-line" size="18" />
                </VAvatar>
              </template>
              <VListItemTitle>
                {{ visitorName(s) }}
                <VChip v-if="s.is_human_takeover" size="x-small" color="warning" class="ms-1">
                  {{ t('dashboard.takeoverTag') }}
                </VChip>
              </VListItemTitle>
              <VListItemSubtitle class="text-caption">
                {{ t('sessions.stage') }}: {{ s.current_stage || '-' }} · {{ fmtTime(s.created_at) }}
              </VListItemSubtitle>
            </VListItem>
          </VList>
          <VCardText v-else class="text-center text-medium-emphasis py-6">
            {{ t('dashboard.noActiveSessions') }}
          </VCardText>
        </VCard>
      </VCol>

      <!-- 我的待办 -->
      <VCol cols="12" md="5">
        <VCard :title="t('dashboard.myTodos')">
          <VDivider />
          <VList v-if="myNotifications.length">
            <VListItem
              v-for="n in myNotifications"
              :key="n.id"
              @click="n.session_id && openSession({ id: n.session_id })"
              :style="n.session_id ? 'cursor:pointer' : ''"
            >
              <template #prepend>
                <VIcon :icon="'ri-notification-3-line'" :color="levelColor(n.level)" class="me-2" />
              </template>
              <VListItemTitle>{{ n.title }}</VListItemTitle>
              <VListItemSubtitle class="text-caption">{{ fmtTime(n.created_at) }}</VListItemSubtitle>
            </VListItem>
          </VList>
          <VCardText v-else class="text-center text-medium-emphasis py-6">
            {{ t('dashboard.noTodos') }}
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
