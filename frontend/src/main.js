import { createApp } from 'vue'
import App from '@/App.vue'
import { registerPlugins } from '@core/utils/plugins'

// Styles
import '@core/scss/template/index.scss'
import '@layouts/styles/index.scss'

// edit loader color - haha 
localStorage.setItem('materio-initial-loader-color', '#2467E4')
localStorage.setItem('materio-initial-loader-bg', '#FFFFFF')

// Create vue app
const app = createApp(App)


// Register plugins
registerPlugins(app)

// Mount vue app
app.mount('#app')
