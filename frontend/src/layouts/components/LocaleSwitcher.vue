<script setup>
import { useI18nStore } from '@/stores/i18nStore' // 导入 Pinia Store
import { useI18n } from 'vue-i18n'

// 导入异步加载函数（Store 内部也会使用）
// 尽管 Store 内部已导入，保持这里导入以便知道依赖关系
// import { loadLocaleMessages } from '@/plugins/i18n' 

// 只需要获取当前语言的响应式引用，以便组件能自动响应变化
const { locale } = useI18n() 
const i18nStore = useI18nStore() // 初始化 Store

// 语言配置映射（保持不变）
const languageOptions = {
  en: { title: 'English', icon: 'i-flag-us' },
  zh: { title: '中文', icon: 'i-flag-cn' },
}

// 使用 Store 中的可用语言列表
const locales = i18nStore.availableLocales.map(lang => ({
  value: lang,
  title: languageOptions[lang]?.title || lang.toUpperCase(),
  icon: languageOptions[lang]?.icon || 'i-flag',
}))

/**
 * 切换语言的核心方法
 * @param {string} newLocale - 目标语言（如 'en'）
 */
const switchLanguage = newLocale => {
  // 关键：直接调用 Pinia Store 的 Action 来处理切换逻辑
  i18nStore.setLocale(newLocale)
}

console.log("Locales", i18nStore.availableLocales)
</script>

<template>
  <VMenu
    offset-y
    close-on-content-click 
  >
    <template #activator="{ props }">
      <VBtn
        v-bind="props"
        icon
        variant="text"
        size="small"
      >
        <span class="font-weight-medium text-body-1">{{ i18nStore.currentLocale.toUpperCase() }}</span>

        <VIcon 
          icon="ri-arrow-down-s-line" 
          size="18"
        />
      </VBtn>
    </template>

    <VList density="compact">
      <VListItem
        v-for="lang in locales"
        :key="lang.value"
        :disabled="i18nStore.currentLocale === lang.value"
        @click="switchLanguage(lang.value)"
      >
        <template #prepend>
          <VIcon
            :icon="lang.icon" 
            class="me-2"
          />
        </template>
        
        <VListItemTitle>{{ lang.title }}</VListItemTitle>
      </VListItem>
    </VList>
  </VMenu>
</template>
