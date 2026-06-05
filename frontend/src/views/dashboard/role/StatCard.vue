<script setup>
// 简洁统计卡: 图标 + 数字 + 标题。无"环比变化"概念, 数字始终显示。
defineProps({
  title: { type: String, required: true },
  stats: { type: [Number, String], required: true },
  icon: { type: String, default: 'ri-bar-chart-line' },
  color: { type: String, default: 'primary' },
})
</script>

<template>
  <VCard>
    <VCardText class="d-flex align-center" style="gap: 12px">
      <VAvatar size="42" :color="color" variant="tonal">
        <VIcon :icon="icon" size="24" />
      </VAvatar>
      <div>
        <h4 class="text-h4">{{ stats }}</h4>
        <div class="text-body-2 text-medium-emphasis">{{ title }}</div>
      </div>
    </VCardText>
  </VCard>
</template>
