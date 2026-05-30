// src/stores/i18nStore.js

import { defineStore } from 'pinia'

// 🚀 导入 i18n 实例和异步加载函数
import { i18n, loadLocaleMessages, SUPPORTED_LOCALES } from '@/plugins/i18n'

// 获取当前的语言环境作为初始状态
const initialLocale = i18n.global.locale.value 

export const useI18nStore = defineStore('i18n', {
  /**
   * State 存储当前的语言环境。
   * 初始值从 i18n 实例中获取（i18n 实例已从 localStorage 中读取默认值）。
   */
  state: () => ({
    currentLocale: initialLocale,

    // 也可以存储所有支持的语言列表，方便 UI 使用
    availableLocales: SUPPORTED_LOCALES,
  }),

  /**
   * Getters 通常不用于此场景，但可以用于计算友好显示的语言名称等。
   */
  getters: {
    // 示例：获取当前语言的大写版本
    localeUpper: state => state.currentLocale.toUpperCase(),
  },

  /**
   * Actions 包含业务逻辑：切换语言，并处理异步加载和持久化。
   */
  actions: {
    /**
     * 异步切换应用语言
     * @param {string} newLocale - 目标语言（如 'en' 或 'zh'）
     */
    async setLocale(newLocale) {
      if (this.currentLocale === newLocale) {
        return // 语言相同，不执行任何操作
      }
      
      try {
        // 1. 调用异步加载函数。
        //    loadLocaleMessages 内部会完成：
        //    a. 检查语言包是否已加载。
        //    b. 动态加载语言包（如果需要）。
        //    c. 更新 i18n.global.locale.value。
        //    d. 更新 localStorage。
        await loadLocaleMessages(newLocale)

        // 2. 更新 Pinia Store 的状态
        this.currentLocale = newLocale
        
        console.log(`Language successfully switched to: ${newLocale}`)

      } catch (error) {
        console.error('Failed to switch or load locale:', error)
      }
    },
  },
})
