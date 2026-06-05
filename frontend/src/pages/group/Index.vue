<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const auth = useAuthStore()
const loading = ref(false)
const stats = ref({ employees: 0, activities: 0, active_sessions: 0 })

const load = async () => {
  if (!auth.orgId || !auth.groupId) return
  loading.value = true
  try {
    const [emps, acts, sess] = await Promise.all([
      api.get(`/api/orgs/${auth.orgId}/employees?group_id=${auth.groupId}`),
      api.get(`/api/orgs/${auth.orgId}/activities?group_id=${auth.groupId}`),
      api.get(`/api/orgs/${auth.orgId}/sessions?group_id=${auth.groupId}&status=active`),
    ])
    stats.value = {
      employees: emps.length,
      activities: acts.length,
      active_sessions: sess.length,
    }
  } finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="mb-4">{{ t('groupIndex.title') }}</h2>
    <p class="text-medium-emphasis mb-4">
      {{ t('groupIndex.welcome', { name: auth.displayName }) }}{{ t('groupIndex.groupIdLabel') }}: {{ auth.groupId || '-' }}
    </p>

    <VRow>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>{{ t('nav.groupEmployees') }}</VCardTitle>
            <VCardSubtitle>{{ t('groupIndex.employeeCount') }}</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.employees }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/employees">{{ t('groupIndex.view') }}</VBtn>
          </VCardText>
        </VCard>
      </VCol>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>{{ t('nav.groupActivities') }}</VCardTitle>
            <VCardSubtitle>{{ t('groupIndex.activityCount') }}</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.activities }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/activities">{{ t('groupIndex.view') }}</VBtn>
          </VCardText>
        </VCard>
      </VCol>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>{{ t('groupIndex.activeSessions') }}</VCardTitle>
            <VCardSubtitle>{{ t('groupIndex.activeSessionsSub') }}</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.active_sessions }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/sessions">{{ t('groupIndex.monitor') }}</VBtn>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
