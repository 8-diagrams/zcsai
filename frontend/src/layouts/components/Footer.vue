<script setup>
import LocaleSwitcher from '@/layouts/components/LocaleSwitcher.vue'
</script>

<template>
  <div class="h-100 d-flex align-center justify-md-space-between justify-center">
    <!-- 👉 Footer: left content -->
    <span class="d-flex align-center">
      &copy;
      {{ new Date().getFullYear() }}
      Power 
      By Teemflux
    </span>
    <!-- 👉 Footer: right content -->
    <span class="d-md-flex gap-x-4 text-primary d-none align-center">
      <a
        href="/"
        target="noopener noreferrer"
      >License</a>
      
      <a
        href="/"
        target="noopener noreferrer"
      >Documentation</a>
      <a
        href="/"
        target="noopener noreferrer"
      >Support</a>
      <span class="me-4"> 
        <LocaleSwitcher class="me-4" />
      </span>
    </span>
    
  </div>
  
</template>
