<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="d-flex flex-column align-center justify-center" style="min-height: 100vh; gap: 16px;">
    <VIcon icon="ri-shield-keyhole-line" size="96" color="warning" />
    <h1 class="text-h3">{{ t('page403.title') }}</h1>
    <p class="text-medium-emphasis">{{ t('page403.desc') }}</p>
    <VBtn color="primary" @click="router.replace('/')">{{ t('page403.backHome') }}</VBtn>
  </div>
</template>
