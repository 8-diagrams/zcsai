<script setup>
import VerticalNavSectionTitle from '@/@layouts/components/VerticalNavSectionTitle.vue'
import VerticalNavLink from '@layouts/components/VerticalNavLink.vue'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
</script>

<template>
  <!-- 通用 -->
  <VerticalNavLink
    :item="{
      title: '工作台',
      icon: 'ri-home-smile-line',
      to: '/dashboard',
    }"
  />

  <!-- 平台管理员 -->
  <template v-if="auth.isPlatformAdmin">
    <VerticalNavSectionTitle :item="{ heading: '平台管理' }" />
    <VerticalNavLink
      :item="{
        title: '代理商',
        icon: 'ri-shake-hands-line',
        to: '/admin/referrers',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '公司/租户',
        icon: 'ri-building-line',
        to: '/admin/organizations',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '用户账号',
        icon: 'ri-user-settings-line',
        to: '/admin/users',
      }"
    />
  </template>

  <!-- 公司管理员 -->
  <template v-if="auth.isOrgAdmin || auth.isPlatformAdmin">
    <VerticalNavSectionTitle :item="{ heading: '公司管理' }" />
    <VerticalNavLink
      :item="{
        title: '组管理',
        icon: 'ri-team-line',
        to: '/org/groups',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '坐席',
        icon: 'ri-customer-service-2-line',
        to: '/org/employees',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '活动剧本',
        icon: 'ri-flag-line',
        to: '/org/activities',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '知识库',
        icon: 'ri-book-open-line',
        to: '/org/kbs',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '素材库',
        icon: 'ri-image-2-line',
        to: '/org/materials',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '会话总览',
        icon: 'ri-chat-3-line',
        to: '/org/sessions',
      }"
    />
    <VerticalNavLink
      v-if="auth.isOrgAdmin"
      :item="{
        title: '本公司账号',
        icon: 'ri-user-settings-line',
        to: '/admin/users',
      }"
    />
  </template>

  <!-- 组管理员 -->
  <template v-if="auth.isGroupAdmin">
    <VerticalNavSectionTitle :item="{ heading: '本组管理' }" />
    <VerticalNavLink
      :item="{
        title: '组首页',
        icon: 'ri-dashboard-3-line',
        to: '/group',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '组内坐席',
        icon: 'ri-customer-service-2-line',
        to: '/group/employees',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '组内活动',
        icon: 'ri-flag-line',
        to: '/group/activities',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '组内知识库',
        icon: 'ri-book-open-line',
        to: '/org/kbs',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '组内素材库',
        icon: 'ri-image-2-line',
        to: '/org/materials',
      }"
    />
    <VerticalNavLink
      :item="{
        title: '实时会话',
        icon: 'ri-chat-poll-line',
        to: '/group/sessions',
      }"
    />
  </template>

  <!-- 坐席 -->
  <template v-if="auth.isAgent">
    <VerticalNavSectionTitle :item="{ heading: '我的工作台' }" />
    <VerticalNavLink
      :item="{
        title: '我的会话',
        icon: 'ri-chat-1-line',
        to: '/me/sessions',
      }"
    />
  </template>

  <!-- 公共底部 -->
  <VerticalNavSectionTitle :item="{ heading: '账户' }" />
  <VerticalNavLink
    :item="{
      title: '账户设置',
      icon: 'ri-settings-3-line',
      to: '/account-settings',
    }"
  />
</template>
