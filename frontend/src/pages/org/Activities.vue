<script setup>
import { useRouter } from 'vue-router'
import CrudTable from '@/components/CrudTable.vue'
import { api, ApiError } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])
const groupOptions = ref([])
const ready = ref(false)
const tableRef = ref(null)

const loadGroups = async () => {
  if (!orgId.value) return
  const gs = await api.get(`/api/orgs/${orgId.value}/groups`)
  groupOptions.value = gs.map(g => ({ title: g.name, value: g.id }))
}

onMounted(async () => {
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
  }
  if (orgId.value) {
    await loadGroups()
    ready.value = true
  }
})

watch(orgId, async () => {
  await loadGroups()
  ready.value = true
})

const headers = computed(() => [
  { title: 'ID', key: 'id' },
  { title: t('activities.name'), key: 'name' },
  { title: t('common.group'), key: 'group_id' },
  { title: t('activities.stagesCount'), key: 'stages_count' },
  { title: t('common.createdAt'), key: 'created_at' },
  { title: t('activities.copyToGroup'), key: 'copy_to_group', sortable: false, width: 96 },
])

const formFields = computed(() => [
  { key: 'name', label: t('activities.name'), required: true },
  { key: 'group_id', label: t('activities.execGroup'), type: 'select', options: groupOptions.value, required: true },
  { key: 'welcome_message', label: t('activities.welcomeMessage'), type: 'textarea', rows: 2 },
  { key: 'closing_message', label: t('activities.closingMessage'), type: 'textarea', rows: 2 },
  { key: 'global_guideline', label: t('activities.globalGuideline'), type: 'textarea', rows: 3 },
  { key: 'stages_json', label: t('activities.stagesConfig'), type: 'textarea', rows: 8 },
])

const detailDialog = ref(false)
const currentActivity = ref(null)
const activityDetail = ref(null)
const detailLoading = ref(false)
const kbMounts = ref([])
const allKbs = ref([])
const mountForm = ref({ kb_id: null, priority: 0, mount_guideline: '' })
const mountErr = ref('')
const shareDialog = ref(false)
const shareActivity = ref(null)
const shareForm = ref({ target_group_id: null, name: '' })
const shareErr = ref('')
const shareResult = ref(null)
const sharing = ref(false)

const groupName = (groupId) => groupOptions.value.find(g => g.value === groupId)?.title || groupId || t('common.none')

const formatJson = value => JSON.stringify(value || {}, null, 2)

const stageSortNumber = key => {
  const match = String(key || '').match(/^stage_(\d+)/)
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER
}

const sortStageEntries = entries => [...entries].sort(([a], [b]) => {
  const diff = stageSortNumber(a) - stageSortNumber(b)
  return diff || String(a).localeCompare(String(b))
})

const sortStageConfig = config => Object.fromEntries(sortStageEntries(Object.entries(config || {})))

const stageEntries = computed(() => {
  const stages = activityDetail.value?.activity?.stages_config || {}
  return sortStageEntries(Object.entries(stages)).map(([key, value]) => ({
    key,
    title: typeof value === 'object' && value ? (value.name || value.title || key) : key,
    body: typeof value === 'object' && value ? formatJson(value) : String(value || ''),
  }))
})

const parseStagesJson = (value) => {
  if (!value) return {}
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

const stageEditorState = new WeakMap()

const stageConfigToRows = config => sortStageEntries(Object.entries(config || {})).map(([key, value]) => {
  const obj = value && typeof value === 'object' && !Array.isArray(value) ? value : { ai_guideline: String(value || '') }
  const { name, ai_guideline, next_possible_stages, ...extra } = obj
  return {
    uid: `${key}_${Math.random().toString(36).slice(2)}`,
    key,
    name: name || '',
    ai_guideline: ai_guideline || '',
    next_possible_stages: Array.isArray(next_possible_stages) ? next_possible_stages.join(', ') : '',
    extra,
  }
})

const getStageEditor = form => {
  const source = form.stages_json || ''
  const cached = stageEditorState.get(form)
  if (cached && cached.source === source) return cached
  const state = {
    source,
    rows: stageConfigToRows(parseStagesJson(source)),
  }
  stageEditorState.set(form, state)
  return state
}

const nextStageKey = rows => {
  const max = rows.reduce((acc, row) => Math.max(acc, stageSortNumber(row.key) === Number.MAX_SAFE_INTEGER ? 0 : stageSortNumber(row.key)), 0)
  return `stage_${max + 1}_new`
}

const splitNextStages = value => String(value || '')
  .split(/[,，\n]/)
  .map(item => item.trim())
  .filter(Boolean)

const syncStageEditor = form => {
  const state = getStageEditor(form)
  state.rows.sort((a, b) => {
    const diff = stageSortNumber(a.key) - stageSortNumber(b.key)
    return diff || String(a.key).localeCompare(String(b.key))
  })
  const config = {}
  for (const row of state.rows) {
    const key = String(row.key || '').trim()
    if (!key) continue
    const item = { ...(row.extra || {}) }
    if (row.name) item.name = row.name
    if (row.ai_guideline) item.ai_guideline = row.ai_guideline
    item.next_possible_stages = splitNextStages(row.next_possible_stages)
    config[key] = item
  }
  form.stages_json = JSON.stringify(sortStageConfig(config), null, 2)
  state.source = form.stages_json
}

const addStageRow = form => {
  const state = getStageEditor(form)
  state.rows.push({
    uid: `new_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    key: nextStageKey(state.rows),
    name: '',
    ai_guideline: '',
    next_possible_stages: '',
    extra: {},
  })
  syncStageEditor(form)
}

const removeStageRow = (form, row) => {
  const state = getStageEditor(form)
  state.rows = state.rows.filter(item => item.uid !== row.uid)
  stageEditorState.set(form, state)
  syncStageEditor(form)
}

const duplicateStageKeys = form => {
  const counts = new Map()
  for (const row of getStageEditor(form).rows) {
    const key = String(row.key || '').trim()
    if (!key) continue
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  return [...counts.entries()].filter(([, count]) => count > 1).map(([key]) => key)
}

const materialReasonLabel = (reason = '') => {
  const parts = reason.split(',').filter(Boolean)
  if (parts.includes('activity') && parts.includes('rule_action')) return t('activities.reasonActivityAndRule')
  if (parts.includes('rule_action')) return t('activities.reasonRuleAction')
  return t('activities.reasonActivity')
}

const reloadActivityDetail = async () => {
  if (!currentActivity.value) return
  detailLoading.value = true
  mountErr.value = ''
  try {
    const [detail, kbs] = await Promise.all([
      api.get(`/api/orgs/${orgId.value}/activities/${currentActivity.value.id}/detail`),
      api.get(`/api/orgs/${orgId.value}/kbs`),
    ])
    activityDetail.value = detail
    kbMounts.value = detail.kb_mounts || []
    allKbs.value = kbs
  } catch (e) {
    mountErr.value = e.detail || e.message
  } finally {
    detailLoading.value = false
  }
}

const openShare = (item) => {
  shareActivity.value = item
  const target = groupOptions.value.find(g => g.value !== item.group_id)
  shareForm.value = {
    target_group_id: target?.value || null,
    name: `${item.name} ${t('activities.copySuffix')}`,
  }
  shareErr.value = ''
  shareResult.value = null
  shareDialog.value = true
}

const submitShare = async () => {
  if (!shareActivity.value || !shareForm.value.target_group_id) {
    shareErr.value = t('activities.pleaseSelectTargetGroup')
    return
  }
  sharing.value = true
  shareErr.value = ''
  shareResult.value = null
  try {
    shareResult.value = await api.post(
      `/api/orgs/${orgId.value}/activities/${shareActivity.value.id}/share-copy`,
      {
        target_group_id: shareForm.value.target_group_id,
        name: shareForm.value.name || undefined,
      },
    )
    await tableRef.value?.reload?.()
  } catch (e) {
    shareErr.value = e.detail || e.message
  } finally {
    sharing.value = false
  }
}

const openDetail = async (item) => {
  currentActivity.value = item
  activityDetail.value = null
  mountErr.value = ''
  detailDialog.value = true
  await reloadActivityDetail()
}

const submitMount = async () => {
  if (!mountForm.value.kb_id) {
    mountErr.value = t('activities.pleaseSelectKb')
    return
  }
  try {
    await api.post('/api/kb/mount', {
      activity_id: currentActivity.value.id,
      kb_id: mountForm.value.kb_id,
      priority: Number(mountForm.value.priority) || 0,
      mount_guideline: mountForm.value.mount_guideline,
    })
    await reloadActivityDetail()
    mountForm.value = { kb_id: null, priority: 0, mount_guideline: '' }
  } catch (e) {
    mountErr.value = e.detail || e.message
  }
}

const unmount = async (kbId) => {
  if (!confirm(t('activities.confirmUnmount'))) return
  try {
    await api.delete(`/api/activities/${currentActivity.value.id}/kb-mounts/${kbId}`)
    await reloadActivityDetail()
  } catch (e) {
    mountErr.value = e.detail || e.message
  }
}

// 把后端返回的 stages_config (object) 在表单里显示成 JSON 文本
const beforeSave = (body) => {
  const out = { ...body }
  const stageRows = getStageEditor(body).rows
  if (stageRows.some(row => !String(row.key || '').trim())) throw new ApiError(0, t('activities.emptyStageKey'), null)
  const duplicates = duplicateStageKeys(body)
  if (duplicates.length) throw new ApiError(0, t('activities.duplicateStages', { stages: duplicates.join(', ') }), null)
  if (out.stages_json) {
    try { out.stages_config = sortStageConfig(JSON.parse(out.stages_json)) } catch { throw new ApiError(0, t('activities.invalidStagesJson'), null) }
  } else {
    out.stages_config = null
  }
  delete out.stages_json
  return out
}
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">{{ t('common.company') }}:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
        <VSpacer />
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          {{ t('activities.manageRules') }}
        </VBtn>
      </VCardText>
    </VCard>
    <VCard v-else class="mb-4">
      <VCardText class="d-flex align-center justify-end">
        <VBtn variant="tonal" prepend-icon="ri-flow-chart" @click="router.push('/org/event-rules')">
          {{ t('activities.manageRules') }}
        </VBtn>
      </VCardText>
    </VCard>

    <CrudTable
      ref="tableRef"
      v-if="ready"
      :key="orgId"
      :title="t('nav.activities')"
      :headers="headers"
      :form-fields="formFields"
      :default-form="{ name: '', group_id: null, welcome_message: '', closing_message: '', global_guideline: '', stages_json: '' }"
      :fetch-fn="async () => {
        const list = await api.get(`/api/orgs/${orgId}/activities`);
        return list.map(a => ({
          ...a,
          stages_config: a.stages_config ? sortStageConfig(a.stages_config) : null,
          stages_count: a.stages_config ? Object.keys(a.stages_config).length : 0,
          stages_json: a.stages_config ? JSON.stringify(sortStageConfig(a.stages_config), null, 2) : '',
        }));
      }"
      :create-fn="body => api.post(`/api/orgs/${orgId}/activities`, beforeSave(body))"
      :update-fn="(id, body) => api.patch(`/api/orgs/${orgId}/activities/${id}`, beforeSave(body))"
      :delete-fn="id => api.delete(`/api/orgs/${orgId}/activities/${id}`)"
      @row-click="openDetail"
    >
      <template #cell.copy_to_group="{ item }">
        <VBtn
          icon="ri-file-copy-line"
          size="small"
          variant="text"
          :disabled="groupOptions.length < 2"
          @click.stop="openShare(item)"
        />
      </template>
      <template #field.stages_json="{ form }">
        <div class="stage-editor">
          <div class="stage-editor-head">
            <div>
              <div class="text-subtitle-2">{{ t('activities.stageEditorTitle') }}</div>
              <div class="text-caption text-medium-emphasis">{{ t('activities.stageEditorHint') }}</div>
            </div>
            <VBtn size="small" color="primary" variant="tonal" prepend-icon="ri-add-line" @click="addStageRow(form)">
              {{ t('activities.addStage') }}
            </VBtn>
          </div>

          <VAlert
            v-if="duplicateStageKeys(form).length"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ t('activities.duplicateStages', { stages: duplicateStageKeys(form).join(', ') }) }}
          </VAlert>

          <div v-if="getStageEditor(form).rows.length" class="stage-editor-list">
            <div v-for="row in getStageEditor(form).rows" :key="row.uid" class="stage-editor-row">
              <div class="stage-row-top">
                <VTextField
                  v-model="row.key"
                  :label="t('activities.stageKey')"
                  density="compact"
                  hide-details
                  @update:model-value="syncStageEditor(form)"
                />
                <VTextField
                  v-model="row.name"
                  :label="t('activities.stageName')"
                  density="compact"
                  hide-details
                  @update:model-value="syncStageEditor(form)"
                />
                <VBtn
                  icon="ri-delete-bin-line"
                  size="small"
                  variant="text"
                  color="error"
                  @click="removeStageRow(form, row)"
                />
              </div>
              <VTextarea
                v-model="row.ai_guideline"
                :label="t('activities.stageAiGuideline')"
                rows="2"
                auto-grow
                hide-details
                @update:model-value="syncStageEditor(form)"
              />
              <VTextField
                v-model="row.next_possible_stages"
                :label="t('activities.nextPossibleStages')"
                :hint="t('activities.nextPossibleStagesHint')"
                persistent-hint
                density="compact"
                @update:model-value="syncStageEditor(form)"
              />
            </div>
          </div>
          <VAlert v-else type="info" variant="tonal" density="compact" class="mb-3">
            {{ t('activities.noStages') }}
          </VAlert>

          <VExpansionPanels variant="accordion">
            <VExpansionPanel>
              <VExpansionPanelTitle>{{ t('activities.jsonPreview') }}</VExpansionPanelTitle>
              <VExpansionPanelText>
                <pre class="stage-json-preview">{{ form.stages_json || '{}' }}</pre>
              </VExpansionPanelText>
            </VExpansionPanel>
          </VExpansionPanels>
        </div>
      </template>
    </CrudTable>

    <VDialog v-model="detailDialog" max-width="1120" scrollable>
      <VCard v-if="currentActivity">
        <VCardItem>
          <template #prepend>
            <VIcon icon="ri-route-line" />
          </template>
          <VCardTitle>{{ currentActivity.name }}</VCardTitle>
          <VCardSubtitle>
            {{ currentActivity.id }} · {{ groupName(activityDetail?.activity?.group_id || currentActivity.group_id) }}
          </VCardSubtitle>
        </VCardItem>
        <VCardText class="activity-detail">
          <VProgressLinear v-if="detailLoading" indeterminate class="mb-4" />
          <VAlert v-if="mountErr" type="error" density="compact" class="mb-4">{{ mountErr }}</VAlert>

          <template v-if="activityDetail">
            <div class="summary-grid mb-5">
              <div class="summary-tile">
                <span>{{ t('activities.summaryStages') }}</span>
                <strong>{{ activityDetail.summary.stages }}</strong>
              </div>
              <div class="summary-tile">
                <span>{{ t('activities.summaryMaterials') }}</span>
                <strong>{{ activityDetail.summary.materials }}</strong>
              </div>
              <div class="summary-tile">
                <span>{{ t('activities.summaryKbs') }}</span>
                <strong>{{ activityDetail.summary.kbs }}</strong>
              </div>
              <div class="summary-tile">
                <span>{{ t('activities.summaryRules') }}</span>
                <strong>{{ activityDetail.summary.activity_rules }} / {{ activityDetail.summary.global_rules }}</strong>
              </div>
            </div>

            <VRow dense>
              <VCol cols="12" md="7">
                <section class="detail-section">
                  <div class="section-title">
                    <VIcon icon="ri-compass-3-line" size="18" />
                    <span>{{ t('activities.runMethod') }}</span>
                  </div>
                  <div class="run-block">
                    <div>
                      <div class="text-caption text-medium-emphasis">{{ t('activities.welcomeMessage') }}</div>
                      <p>{{ activityDetail.activity.welcome_message || t('common.none') }}</p>
                    </div>
                    <div>
                      <div class="text-caption text-medium-emphasis">{{ t('activities.closingMessage') }}</div>
                      <p>{{ activityDetail.activity.closing_message || t('common.none') }}</p>
                    </div>
                    <div>
                      <div class="text-caption text-medium-emphasis">{{ t('activities.globalGuideline') }}</div>
                      <p>{{ activityDetail.activity.global_guideline || t('common.none') }}</p>
                    </div>
                  </div>
                </section>

                <section class="detail-section mt-4">
                  <div class="section-title">
                    <VIcon icon="ri-list-check-3" size="18" />
                    <span>{{ t('activities.stageFlow') }}</span>
                  </div>
                  <div v-if="stageEntries.length" class="stage-list">
                    <div v-for="stage in stageEntries" :key="stage.key" class="stage-row">
                      <VChip size="small" variant="tonal">{{ stage.key }}</VChip>
                      <div>
                        <strong>{{ stage.title }}</strong>
                        <pre>{{ stage.body }}</pre>
                      </div>
                    </div>
                  </div>
                  <VAlert v-else type="info" variant="tonal" density="compact">{{ t('activities.noStages') }}</VAlert>
                </section>
              </VCol>

              <VCol cols="12" md="5">
                <section class="detail-section">
                  <div class="section-title">
                    <VIcon icon="ri-image-line" size="18" />
                    <span>{{ t('activities.dependentMaterials') }}</span>
                  </div>
                  <div v-if="activityDetail.materials.length" class="dependency-list">
                    <div v-for="mat in activityDetail.materials" :key="mat.id" class="dependency-row">
                      <div class="dependency-main">
                        <strong>{{ mat.title }}</strong>
                        <span>{{ mat.kind }} · {{ materialReasonLabel(mat.dependency_reason) }}</span>
                      </div>
                      <VChip size="x-small" variant="tonal">{{ mat.id }}</VChip>
                    </div>
                  </div>
                  <VAlert v-else type="info" variant="tonal" density="compact">{{ t('activities.noMaterials') }}</VAlert>
                </section>

                <section class="detail-section mt-4">
                  <div class="section-title">
                    <VIcon icon="ri-book-open-line" size="18" />
                    <span>{{ t('activities.dependentKbs') }}</span>
                  </div>
                  <div v-if="kbMounts.length" class="dependency-list">
                    <div v-for="m in kbMounts" :key="m.kb_id" class="dependency-row align-start">
                      <div class="dependency-main">
                        <strong>{{ m.kb_name || m.kb_id }}</strong>
                        <span>{{ t('activities.priority') }} {{ m.priority }} · {{ m.raw_text_available ? t('activities.rawTextSaved') : t('activities.rawTextMissing') }}</span>
                        <small v-if="m.mount_guideline">{{ m.mount_guideline }}</small>
                      </div>
                      <VBtn icon="ri-delete-bin-line" size="small" variant="text" color="error" @click="unmount(m.kb_id)" />
                    </div>
                  </div>
                  <VAlert v-else type="info" variant="tonal" density="compact">{{ t('activities.noMounts') }}</VAlert>

                  <VDivider class="my-4" />
                  <div class="section-title compact">
                    <VIcon icon="ri-add-line" size="18" />
                    <span>{{ t('activities.mountNewKb') }}</span>
                  </div>
                  <VRow dense>
                    <VCol cols="12" md="7">
                      <VSelect
                        v-model="mountForm.kb_id"
                        :items="allKbs.map(k => ({ title: k.name, value: k.id }))"
                        :label="t('activities.selectKb')"
                        density="compact"
                        hide-details
                      />
                    </VCol>
                    <VCol cols="12" md="5">
                      <VTextField v-model.number="mountForm.priority" type="number" :label="t('activities.priority')" density="compact" hide-details />
                    </VCol>
                    <VCol cols="12">
                      <VTextarea v-model="mountForm.mount_guideline" :label="t('activities.mountGuidelineOptional')" rows="2" auto-grow hide-details />
                    </VCol>
                  </VRow>
                </section>

                <section class="detail-section mt-4">
                  <div class="section-title">
                    <VIcon icon="ri-flow-chart" size="18" />
                    <span>{{ t('activities.dependentRules') }}</span>
                  </div>
                  <div v-if="activityDetail.rules.length" class="dependency-list">
                    <div v-for="rule in activityDetail.rules" :key="rule.id" class="dependency-row align-start">
                      <div class="dependency-main">
                        <strong>{{ rule.name }}</strong>
                        <span>{{ rule.phase }} · {{ rule.fire_policy }} · {{ rule.scope === 'global' ? t('activities.globalRule') : t('activities.activityRule') }}</span>
                        <small>{{ t('activities.priority') }} {{ rule.priority }} · {{ rule.is_active ? t('rules.enabled') : t('activities.disabled') }}</small>
                      </div>
                      <VChip size="x-small" :color="rule.scope === 'global' ? 'secondary' : 'primary'" variant="tonal">
                        {{ rule.scope === 'global' ? t('common.all') : t('activities.activityScope') }}
                      </VChip>
                    </div>
                  </div>
                  <VAlert v-else type="info" variant="tonal" density="compact">{{ t('activities.noRules') }}</VAlert>
                </section>
              </VCol>
            </VRow>
          </template>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="detailDialog = false">{{ t('general.close') }}</VBtn>
          <VBtn color="primary" @click="submitMount">{{ t('activities.mount') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="shareDialog" max-width="520">
      <VCard v-if="shareActivity">
        <VCardItem>
          <VCardTitle>{{ t('activities.copyToGroupTitle') }}</VCardTitle>
        </VCardItem>
        <VCardText>
          <VTextField
            v-model="shareForm.name"
            :label="t('activities.copyName')"
            class="mb-3"
          />
          <VSelect
            v-model="shareForm.target_group_id"
            :items="groupOptions.filter(g => g.value !== shareActivity.group_id)"
            :label="t('activities.targetGroup')"
          />
          <VAlert v-if="shareErr" type="error" density="compact" class="mt-3">{{ shareErr }}</VAlert>
          <VAlert v-if="shareResult" type="success" density="compact" class="mt-3">
            {{ t('activities.copySuccess', {
              activity: shareResult.new_activity?.name || shareResult.new_activity?.id,
              materials: shareResult.copied_materials,
              kbs: shareResult.copied_kbs,
              rules: shareResult.copied_rules,
            }) }}
          </VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="shareDialog = false">{{ t('general.close') }}</VBtn>
          <VBtn color="primary" :loading="sharing" @click="submitShare">{{ t('activities.copy') }}</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.activity-detail {
  background: rgb(var(--v-theme-surface));
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.summary-tile {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 12px;
  min-height: 72px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.summary-tile span {
  color: rgba(var(--v-theme-on-surface), 0.64);
  font-size: 12px;
}

.summary-tile strong {
  font-size: 24px;
  line-height: 1.2;
}

.detail-section {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 14px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  margin-bottom: 12px;
}

.section-title.compact {
  margin-bottom: 8px;
}

.run-block {
  display: grid;
  gap: 12px;
}

.run-block p {
  margin: 4px 0 0;
  white-space: pre-wrap;
}

.stage-list,
.dependency-list {
  display: grid;
  gap: 10px;
}

.stage-row,
.dependency-row {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  padding: 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.035);
}

.stage-row {
  justify-content: flex-start;
  align-items: flex-start;
}

.stage-row pre {
  margin: 4px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
}

.dependency-main {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.dependency-main span,
.dependency-main small {
  color: rgba(var(--v-theme-on-surface), 0.64);
}

.dependency-main small {
  white-space: pre-wrap;
}

.stage-editor {
  display: grid;
  gap: 12px;
}

.stage-editor-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.stage-editor-list {
  display: grid;
  gap: 12px;
}

.stage-editor-row {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.stage-row-top {
  display: grid;
  grid-template-columns: minmax(120px, 0.85fr) minmax(140px, 1fr) 36px;
  gap: 8px;
  align-items: center;
}

.stage-json-preview {
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stage-editor-head,
  .stage-row-top {
    grid-template-columns: 1fr;
  }

  .stage-editor-head {
    display: grid;
  }
}
</style>
