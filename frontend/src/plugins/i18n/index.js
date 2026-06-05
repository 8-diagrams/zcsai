import { createI18n } from 'vue-i18n'

// ----------------------------------------------------
// 1. 配置和初始化
// ----------------------------------------------------

// 定义项目支持的所有语言列表
const SUPPORTED_LOCALES = ['en', 'zh']
const messages = {} // 初始语言包为空，等待异步加载

// 默认语言判断逻辑
const getDefaultLocale = () => {
  // 尝试从本地存储读取
  const storedLocale = localStorage.getItem('user-locale')
  if (storedLocale && SUPPORTED_LOCALES.includes(storedLocale)) return storedLocale

  // 尝试使用浏览器语言
  const browserLang = navigator.language.split('-')[0]
  if (SUPPORTED_LOCALES.includes(browserLang)) return browserLang

  // 默认回退到 'en'
  return 'en' 
}

// 核心 I18n 实例创建
const i18n = createI18n({
  // Vue 3 Composition API 模式
  legacy: false, 

  // 允许在组件中直接使用 $t, $i18n
  globalInjection: true, 
  
  locale: getDefaultLocale(),
  messages, 
  fallbackLocale: 'en',
})

// ----------------------------------------------------
// 2. 异步加载函数
// ----------------------------------------------------

// 记录已加载的语言，防止重复加载
let loadedLanguages = []

/**
 * 异步加载指定语言的语言包，并在加载完成后切换语言
 * @param {string} locale - 目标语言（如 'en', 'zh'）
 */
// 🚀 修正：移除这里的 export 关键字
async function loadLocaleMessages(locale) {
  if (!SUPPORTED_LOCALES.includes(locale)) {
    console.error(`Locale ${locale} is not supported.`)
    
    return
  }
  
  if (loadedLanguages.includes(locale)) {
    // 语言已加载，直接切换
    i18n.global.locale.value = locale
    localStorage.setItem('user-locale', locale)
    
    return 
  }

  try {
    // 使用 Vite/Webpack 的动态导入语法加载对应的 JSON 文件
    const module = await import(`./locales/${locale}.json`)

    // 设置语言包到 I18n 实例
    i18n.global.setLocaleMessage(locale, module.default)
    loadedLanguages.push(locale)

    // 切换语言
    i18n.global.locale.value = locale
    localStorage.setItem('user-locale', locale)
    
  } catch (error) {
    console.error(`Failed to load locale messages for ${locale}:`, error)

    // 切换失败，回退到 fallbackLocale
    i18n.global.locale.value = i18n.global.fallbackLocale
  }
}

// ----------------------------------------------------
// 3. 初始化加载默认语言
// ----------------------------------------------------

// 应用启动时立即加载默认语言包，确保有内容可显示
loadLocaleMessages(i18n.global.locale.value)

// ----------------------------------------------------
// 4. 插件导出（包含默认导出和所有命名导出）
// ----------------------------------------------------

/**
 * 默认导出：作为一个函数，满足 registerPlugins 的调用期望。
 * @param {object} app - Vue 应用实例
 */
export default app => {
  app.use(i18n)
}

// 🚀 修正：集中命名导出，供 Pinia Store 或其他模块使用
export { i18n, loadLocaleMessages, SUPPORTED_LOCALES }

