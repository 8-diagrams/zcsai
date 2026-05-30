<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

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
    <h2 class="mb-4">本组工作台</h2>
    <p class="text-medium-emphasis mb-4">
      欢迎,{{ auth.displayName }}。所属组 ID: {{ auth.groupId || '-' }}
    </p>

    <VRow>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>组内坐席</VCardTitle>
            <VCardSubtitle>当前坐席数量</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.employees }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/employees">查看</VBtn>
          </VCardText>
        </VCard>
      </VCol>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>组内活动</VCardTitle>
            <VCardSubtitle>活动剧本数量</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.activities }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/activities">查看</VBtn>
          </VCardText>
        </VCard>
      </VCol>
      <VCol cols="12" md="4">
        <VCard>
          <VCardItem>
            <VCardTitle>进行中会话</VCardTitle>
            <VCardSubtitle>实时活跃会话</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <div class="text-h3">{{ stats.active_sessions }}</div>
            <VBtn class="mt-2" variant="text" color="primary" to="/group/sessions">监控</VBtn>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
