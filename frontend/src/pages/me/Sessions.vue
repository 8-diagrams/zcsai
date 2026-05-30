<script setup>
import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

const sessions = ref([])
const loading = ref(false)
const statusFilter = ref('active')
const statusOptions = [
  { title: '进行中', value: 'active' },
  { title: '已关闭', value: 'closed' },
  { title: '已转接', value: 'transferred' },
  { title: '全部', value: null },
]

const reload = async () => {
  loading.value = true
  try {
    const qs = statusFilter.value ? `?status=${statusFilter.value}` : ''
    sessions.value = await api.get(`/api/me/sessions${qs}`)
  } finally { loading.value = false }
}

onMounted(reload)
watch(statusFilter, reload)

let timer = null
onMounted(() => {
  timer = setInterval(() => {
    if (statusFilter.value === 'active') reload()
  }, 5000)
})
onUnmounted(() => timer && clearInterval(timer))

const open = (s) => router.push(`/me/session/${s.id}`)
const fmtTime = (t) => t ? new Date(t).toLocaleString() : ''
const statusColor = (s) => ({ active: 'success', closed: 'default', transferred: 'warning' }[s] || 'default')
</script>

<template>
  <div>
    <VCard>
      <VCardItem>
        <VCardTitle>我的会话 <VChip size="small" class="ms-2">{{ sessions.length }}</VChip></VCardTitle>
        <template #append>
          <VSelect
            v-model="statusFilter"
            :items="statusOptions"
            density="compact"
            hide-details
            style="max-width: 180px"
          />
          <VBtn icon="ri-refresh-line" variant="text" @click="reload" />
        </template>
      </VCardItem>
      <VDivider />
      <VDataTable
        :headers="[
          { title: '访客', key: 'visitor', sortable: false },
          { title: '阶段', key: 'current_stage' },
          { title: '状态', key: 'status' },
          { title: '创建时间', key: 'created_at' },
          { title: '', key: 'actions', sortable: false, width: 100 },
        ]"
        :items="sessions.map(s => ({ ...s, visitor: s.visitor_uid || s.id }))"
        :loading="loading"
        item-value="id"
        @click:row="(e, { item }) => open(item)"
      >
        <template #item.status="{ item }">
          <VChip size="small" :color="statusColor(item.status)">{{ item.status }}</VChip>
        </template>
        <template #item.created_at="{ item }">{{ fmtTime(item.created_at) }}</template>
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" color="primary" @click.stop="open(item)">进入</VBtn>
        </template>
      </VDataTable>
    </VCard>
  </div>
</template>
