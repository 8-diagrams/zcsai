<script setup>
import { api } from '@/utils/api'
import { useI18n } from 'vue-i18n'
import MiniChart from './MiniChart.vue'
import StatCard from './StatCard.vue'

const { t } = useI18n()
const loading = ref(false)
const data = ref(null)

const load = async () => {
  loading.value = true
  try { data.value = await api.get('/api/dashboard/summary') }
  finally { loading.value = false }
}
onMounted(load)

const c = computed(() => data.value?.counts || {})
const statusData = computed(() => Object.entries(data.value?.session_status || {})
  .map(([k, v]) => ({ label: t(`session.status.${k}`), value: v })))
const emotionData = computed(() => Object.entries(data.value?.emotion_distribution || {})
  .map(([k, v]) => ({ label: t(`session.emotion.${k}`), value: v })))

const cards = computed(() => [
  { title: t('nav.groupEmployees'), icon: 'ri-customer-service-2-line', color: 'success', stats: c.value.employees ?? 0 },
  { title: t('nav.groupActivities'), icon: 'ri-flag-line', color: 'warning', stats: c.value.activities ?? 0 },
  { title: t('dashboard.sessionsTotal'), icon: 'ri-chat-3-line', color: 'primary', stats: c.value.sessions_total ?? 0 },
  { title: t('dashboard.sessionsActive'), icon: 'ri-chat-poll-line', color: 'success', stats: c.value.sessions_active ?? 0 },
  { title: t('dashboard.sessionsTakeover'), icon: 'ri-user-shared-line', color: 'warning', stats: c.value.sessions_human_takeover ?? 0 },
])
</script>

<template>
  <div>
    <h2 class="text-h5 mb-4">{{ t('dashboard.groupTitle') }}</h2>
    <VRow>
      <VCol v-for="card in cards" :key="card.title" cols="6" sm="4" md="3">
        <StatCard v-bind="card" />
      </VCol>
    </VRow>
    <VRow class="mt-2">
      <VCol cols="12" md="5">
        <VCard :title="t('dashboard.sessionStatus')">
          <VCardText><MiniChart type="donut" :data="statusData" /></VCardText>
        </VCard>
      </VCol>
      <VCol cols="12" md="7">
        <VCard :title="t('dashboard.emotionDistribution')">
          <VCardText><MiniChart type="bar" :data="emotionData" /></VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
