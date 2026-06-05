<script setup>
import avatar1 from '@images/avatars/avatar-1.png'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const roleLabel = computed(() =>
  auth.role ? t(`roles.${auth.role}`) : t('user.notLoggedIn'),
)

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <VBadge
    dot
    location="bottom right"
    offset-x="3"
    offset-y="3"
    color="success"
    bordered
  >
    <VAvatar
      class="cursor-pointer"
      color="primary"
      variant="tonal"
    >
      <VImg :src="avatar1" />

      <VMenu
        activator="parent"
        width="240"
        location="bottom end"
        offset="14px"
      >
        <VList>
          <VListItem>
            <template #prepend>
              <VListItemAction start>
                <VBadge
                  dot
                  location="bottom right"
                  offset-x="3"
                  offset-y="3"
                  color="success"
                >
                  <VAvatar color="primary" variant="tonal">
                    <VImg :src="avatar1" />
                  </VAvatar>
                </VBadge>
              </VListItemAction>
            </template>

            <VListItemTitle class="font-weight-semibold">
              {{ auth.displayName || t('user.notLoggedIn') }}
            </VListItemTitle>
            <VListItemSubtitle>{{ roleLabel }}</VListItemSubtitle>
          </VListItem>
          <VDivider class="my-2" />

          <VListItem to="/account-settings" link>
            <template #prepend>
              <VIcon class="me-2" icon="ri-user-line" size="22" />
            </template>
            <VListItemTitle>{{ t('nav.accountSettings') }}</VListItemTitle>
          </VListItem>

          <VDivider class="my-2" />

          <VListItem @click="handleLogout">
            <template #prepend>
              <VIcon class="me-2" icon="ri-logout-box-r-line" size="22" />
            </template>
            <VListItemTitle>{{ t('general.Logout') }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
    </VAvatar>
  </VBadge>
</template>
