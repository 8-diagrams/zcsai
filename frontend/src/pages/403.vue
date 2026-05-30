<script setup>
const router = useRouter()
</script>

<template>
  <div class="d-flex flex-column align-center justify-center" style="min-height: 100vh; gap: 16px;">
    <VIcon icon="ri-shield-keyhole-line" size="96" color="warning" />
    <h1 class="text-h3">403 · 无权访问</h1>
    <p class="text-medium-emphasis">当前账号角色没有访问该页面的权限</p>
    <VBtn color="primary" @click="router.replace('/')">返回首页</VBtn>
  </div>
</template>
