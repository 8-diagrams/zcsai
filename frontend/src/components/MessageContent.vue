<script setup>
import { mediaUrl } from '@/utils/api'

const props = defineProps({
  m: { type: Object, required: true },
})

const type = computed(() => props.m?.content_type || 'text')
const url = computed(() => mediaUrl(props.m?.media_url))
const caption = computed(() => props.m?.media_caption || '')
</script>

<template>
  <!-- 图片 -->
  <div v-if="type === 'image'">
    <a :href="url" target="_blank" rel="noopener">
      <img :src="url" :alt="caption" style="max-width: 240px; max-height: 240px; border-radius: 8px; display: block" />
    </a>
    <div v-if="caption" class="text-caption text-medium-emphasis mt-1">{{ caption }}</div>
  </div>

  <!-- 视频 -->
  <div v-else-if="type === 'video'">
    <video :src="url" controls style="max-width: 320px; max-height: 240px; border-radius: 8px; display: block" />
    <div v-if="caption" class="text-caption text-medium-emphasis mt-1">{{ caption }}</div>
  </div>

  <!-- 链接卡片 -->
  <div v-else-if="type === 'link'">
    <a :href="url || m.content" target="_blank" rel="noopener">
      {{ caption || m.content || url }}
    </a>
  </div>

  <!-- 纯文本 (默认) -->
  <div v-else style="white-space: pre-wrap">{{ m.content }}</div>
</template>
