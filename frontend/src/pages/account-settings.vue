<script setup>
import { api } from '@/utils/api'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const isCurrentVisible = ref(false)
const isNewVisible = ref(false)
const isConfirmVisible = ref(false)

const submitting = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

const submit = async () => {
  errorMsg.value = ''
  successMsg.value = ''
  if (!currentPassword.value || !newPassword.value) {
    errorMsg.value = t('changePassword.fillAll')
    return
  }
  if (newPassword.value.length < 8) {
    errorMsg.value = t('changePassword.tooShort')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMsg.value = t('changePassword.mismatch')
    return
  }
  submitting.value = true
  try {
    await api.post('/api/auth/change-password', {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    successMsg.value = t('changePassword.success')
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (e) {
    errorMsg.value = e.detail || e.message
  } finally { submitting.value = false }
}

const reset = () => {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  errorMsg.value = ''
  successMsg.value = ''
}
</script>

<template>
  <VRow>
    <VCol cols="12" md="8" lg="6">
      <VCard :title="t('changePassword.title')">
        <VForm @submit.prevent="submit">
          <VCardText>
            <VAlert v-if="errorMsg" type="error" density="compact" class="mb-4">{{ errorMsg }}</VAlert>
            <VAlert v-if="successMsg" type="success" density="compact" class="mb-4">{{ successMsg }}</VAlert>

            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="currentPassword"
                  :type="isCurrentVisible ? 'text' : 'password'"
                  :append-inner-icon="isCurrentVisible ? 'ri-eye-off-line' : 'ri-eye-line'"
                  :label="t('changePassword.current')"
                  autocomplete="current-password"
                  placeholder="············"
                  @click:append-inner="isCurrentVisible = !isCurrentVisible"
                />
              </VCol>
              <VCol cols="12">
                <VTextField
                  v-model="newPassword"
                  :type="isNewVisible ? 'text' : 'password'"
                  :append-inner-icon="isNewVisible ? 'ri-eye-off-line' : 'ri-eye-line'"
                  :label="t('changePassword.new')"
                  autocomplete="new-password"
                  placeholder="············"
                  @click:append-inner="isNewVisible = !isNewVisible"
                />
              </VCol>
              <VCol cols="12">
                <VTextField
                  v-model="confirmPassword"
                  :type="isConfirmVisible ? 'text' : 'password'"
                  :append-inner-icon="isConfirmVisible ? 'ri-eye-off-line' : 'ri-eye-line'"
                  :label="t('changePassword.confirm')"
                  autocomplete="new-password"
                  placeholder="············"
                  @click:append-inner="isConfirmVisible = !isConfirmVisible"
                />
              </VCol>
            </VRow>

            <p class="text-caption text-medium-emphasis mt-3 mb-0">
              {{ t('changePassword.requirement') }}
            </p>
          </VCardText>

          <VCardText class="d-flex flex-wrap gap-4">
            <VBtn type="submit" :loading="submitting">{{ t('general.save') }}</VBtn>
            <VBtn type="button" color="secondary" variant="outlined" @click="reset">
              {{ t('changePassword.reset') }}
            </VBtn>
          </VCardText>
        </VForm>
      </VCard>
    </VCol>
  </VRow>
</template>
