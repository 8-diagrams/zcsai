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
      title: $t('nav.dashboard'),
      icon: 'ri-home-smile-line',
      to: '/dashboard',
    }"
  />

  <!-- 平台管理员 -->
  <template v-if="auth.isPlatformAdmin">
    <VerticalNavSectionTitle :item="{ heading: $t('nav.section.platform') }" />
    <VerticalNavLink
      :item="{
        title: $t('nav.referrers'),
        icon: 'ri-shake-hands-line',
        to: '/admin/referrers',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.organizations'),
        icon: 'ri-building-line',
        to: '/admin/organizations',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.users'),
        icon: 'ri-user-settings-line',
        to: '/admin/users',
      }"
    />
  </template>

  <!-- 公司管理员 -->
  <template v-if="auth.isOrgAdmin || auth.isPlatformAdmin">
    <VerticalNavSectionTitle :item="{ heading: $t('nav.section.org') }" />
    <VerticalNavLink
      :item="{
        title: $t('nav.groups'),
        icon: 'ri-team-line',
        to: '/org/groups',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.employees'),
        icon: 'ri-customer-service-2-line',
        to: '/org/employees',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.activities'),
        icon: 'ri-flag-line',
        to: '/org/activities',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.kbs'),
        icon: 'ri-book-open-line',
        to: '/org/kbs',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.materials'),
        icon: 'ri-image-2-line',
        to: '/org/materials',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.sessions'),
        icon: 'ri-chat-3-line',
        to: '/org/sessions',
      }"
    />
    <VerticalNavLink
      v-if="auth.isOrgAdmin"
      :item="{
        title: $t('nav.orgUsers'),
        icon: 'ri-user-settings-line',
        to: '/admin/users',
      }"
    />
  </template>

  <!-- 组管理员 -->
  <template v-if="auth.isGroupAdmin">
    <VerticalNavSectionTitle :item="{ heading: $t('nav.section.group') }" />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupHome'),
        icon: 'ri-dashboard-3-line',
        to: '/group',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupEmployees'),
        icon: 'ri-customer-service-2-line',
        to: '/group/employees',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupAgentAccounts'),
        icon: 'ri-user-settings-line',
        to: '/admin/users',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupActivities'),
        icon: 'ri-flag-line',
        to: '/group/activities',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupKbs'),
        icon: 'ri-book-open-line',
        to: '/org/kbs',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupMaterials'),
        icon: 'ri-image-2-line',
        to: '/org/materials',
      }"
    />
    <VerticalNavLink
      :item="{
        title: $t('nav.groupSessions'),
        icon: 'ri-chat-poll-line',
        to: '/group/sessions',
      }"
    />
  </template>

  <!-- 坐席 -->
  <template v-if="auth.isAgent">
    <VerticalNavSectionTitle :item="{ heading: $t('nav.section.me') }" />
    <VerticalNavLink
      :item="{
        title: $t('nav.mySessions'),
        icon: 'ri-chat-1-line',
        to: '/me/sessions',
      }"
    />
  </template>

  <!-- 公共底部 -->
  <VerticalNavSectionTitle :item="{ heading: $t('nav.section.account') }" />
  <VerticalNavLink
    :item="{
      title: $t('nav.accountSettings'),
      icon: 'ri-settings-3-line',
      to: '/account-settings',
    }"
  />
</template>
