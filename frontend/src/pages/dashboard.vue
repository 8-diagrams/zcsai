<script setup>
import { useAuthStore } from '@/stores/authStore'
import DashboardPlatform from '@/views/dashboard/role/DashboardPlatform.vue'
import DashboardOrg from '@/views/dashboard/role/DashboardOrg.vue'
import DashboardGroup from '@/views/dashboard/role/DashboardGroup.vue'
import DashboardAgent from '@/views/dashboard/role/DashboardAgent.vue'

const auth = useAuthStore()
</script>

<template>
  <DashboardPlatform v-if="auth.isPlatformAdmin" />
  <DashboardOrg v-else-if="auth.isOrgAdmin" />
  <DashboardGroup v-else-if="auth.isGroupAdmin" />
  <DashboardAgent v-else-if="auth.isAgent" />
  <VAlert v-else type="info">{{ $t('dashboard.noRole') }}</VAlert>
</template>
