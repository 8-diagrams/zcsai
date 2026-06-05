<script setup>
/**
 * 通用 CRUD 列表 + 抽屉表单。
 * Props:
 *   title          - 页面标题
 *   headers        - VDataTable headers (含一个 key='actions' 自动渲染编辑/删除)
 *   fetchFn        - () => Promise<rows[]>
 *   createFn       - (body) => Promise   传 null 则隐藏新建按钮
 *   updateFn       - (id, body) => Promise   传 null 则不显示编辑
 *   deleteFn       - (id) => Promise   传 null 则不显示删除
 *   formFields     - [{ key, label, type, options?, required?, hint? }]
 *   defaultForm    - 新建时的初始表单
 *   itemKey        - 行主键字段名,默认 id
 *   readonly       - 全只读模式 (会话查看类)
 */
const props = defineProps({
  title: { type: String, default: '' },
  headers: { type: Array, required: true },
  fetchFn: { type: Function, required: true },
  createFn: { type: Function, default: null },
  updateFn: { type: Function, default: null },
  deleteFn: { type: Function, default: null },
  formFields: { type: Array, default: () => [] },
  defaultForm: { type: Object, default: () => ({}) },
  itemKey: { type: String, default: 'id' },
  readonly: { type: Boolean, default: false },
  search: { type: Boolean, default: true },
})

import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const emit = defineEmits(['row-click'])

const rows = ref([])
const loading = ref(false)
const drawer = ref(false)
const editing = ref(null) // null = 新建,object = 编辑
const form = ref({ ...props.defaultForm })
const errorMsg = ref('')
const submitting = ref(false)
const keyword = ref('')

const filteredRows = computed(() => {
  if (!keyword.value) return rows.value
  const k = keyword.value.toLowerCase()
  return rows.value.filter(r =>
    JSON.stringify(r).toLowerCase().includes(k),
  )
})

const finalHeaders = computed(() => {
  if (props.readonly) return props.headers
  if (!props.updateFn && !props.deleteFn) return props.headers
  if (props.headers.some(h => h.key === 'actions')) return props.headers
  return [...props.headers, { title: t('crud.actions'), key: 'actions', sortable: false, width: 160 }]
})

const reload = async () => {
  loading.value = true
  try {
    rows.value = await props.fetchFn()
  } catch (e) {
    errorMsg.value = e.detail || e.message || t('crud.loadFailed')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  form.value = JSON.parse(JSON.stringify(props.defaultForm))
  errorMsg.value = ''
  drawer.value = true
}

const openEdit = (row) => {
  editing.value = row
  // 仅取表单字段对应的值,避免把整行展开污染
  const init = {}
  props.formFields.forEach(f => {
    init[f.key] = row[f.key] ?? props.defaultForm[f.key] ?? null
  })
  form.value = init
  errorMsg.value = ''
  drawer.value = true
}

const submit = async () => {
  errorMsg.value = ''
  submitting.value = true
  try {
    if (editing.value) {
      await props.updateFn(editing.value[props.itemKey], form.value)
    } else {
      await props.createFn(form.value)
    }
    drawer.value = false
    await reload()
  } catch (e) {
    errorMsg.value = e.detail || e.message || t('crud.saveFailed')
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row) => {
  if (!confirm(t('crud.confirmDelete', { name: row.name || row.email || row[props.itemKey] }))) return
  try {
    await props.deleteFn(row[props.itemKey])
    await reload()
  } catch (e) {
    alert(e.detail || e.message || t('crud.deleteFailed'))
  }
}

defineExpose({ reload })

onMounted(reload)
</script>

<template>
  <VCard>
    <VCardItem>
      <VCardTitle>
        {{ title }}
        <VChip class="ms-2" size="small" variant="tonal">{{ rows.length }}</VChip>
      </VCardTitle>
      <template #append>
        <div class="d-flex align-center" style="gap: 8px;">
          <VTextField
            v-if="search"
            v-model="keyword"
            density="compact"
            hide-details
            :placeholder="t('crud.searchPlaceholder')"
            prepend-inner-icon="ri-search-line"
            style="max-width: 240px;"
          />
          <VBtn
            v-if="createFn && !readonly"
            color="primary"
            prepend-icon="ri-add-line"
            @click="openCreate"
          >
            {{ t('crud.create') }}
          </VBtn>
          <VBtn
            icon="ri-refresh-line"
            variant="text"
            @click="reload"
          />
        </div>
      </template>
    </VCardItem>

    <VAlert
      v-if="errorMsg && !drawer"
      type="error"
      density="compact"
      class="mx-4 mb-2"
    >
      {{ errorMsg }}
    </VAlert>

    <VDataTable
      :headers="finalHeaders"
      :items="filteredRows"
      :item-value="itemKey"
      :loading="loading"
      density="comfortable"
      @click:row="(_, { item }) => emit('row-click', item)"
    >
      <template v-for="h in headers" :key="h.key" #[`item.${h.key}`]="{ item }">
        <slot :name="`cell.${h.key}`" :item="item">
          <template v-if="h.formatter">{{ h.formatter(item[h.key], item) }}</template>
          <template v-else>{{ item[h.key] }}</template>
        </slot>
      </template>

      <template #item.actions="{ item }">
        <VBtn
          v-if="updateFn"
          icon="ri-edit-line"
          size="small"
          variant="text"
          @click.stop="openEdit(item)"
        />
        <VBtn
          v-if="deleteFn"
          icon="ri-delete-bin-line"
          size="small"
          variant="text"
          color="error"
          @click.stop="handleDelete(item)"
        />
      </template>
    </VDataTable>
  </VCard>

  <!-- 抽屉式表单 -->
  <VNavigationDrawer
    v-model="drawer"
    location="right"
    temporary
    width="480"
  >
    <VCard flat class="h-100 d-flex flex-column">
      <VCardItem>
        <VCardTitle>{{ editing ? t('crud.edit') : t('crud.create') }}{{ title }}</VCardTitle>
        <template #append>
          <VBtn icon="ri-close-line" variant="text" @click="drawer = false" />
        </template>
      </VCardItem>

      <VCardText class="flex-grow-1" style="overflow-y: auto;">
        <VForm @submit.prevent="submit">
          <VRow>
            <VCol
              v-for="f in formFields"
              :key="f.key"
              cols="12"
            >
              <slot :name="`field.${f.key}`" :field="f" :form="form">
                <VSelect
                  v-if="f.type === 'select'"
                  v-model="form[f.key]"
                  :items="f.options || []"
                  :label="f.label"
                  :hint="f.hint"
                  :persistent-hint="!!f.hint"
                  :required="f.required"
                  :disabled="editing && f.disableOnEdit"
                  clearable
                />
                <VSwitch
                  v-else-if="f.type === 'switch'"
                  v-model="form[f.key]"
                  :label="f.label"
                  color="primary"
                  inset
                />
                <VTextarea
                  v-else-if="f.type === 'textarea'"
                  v-model="form[f.key]"
                  :label="f.label"
                  :hint="f.hint"
                  :persistent-hint="!!f.hint"
                  :rows="f.rows || 4"
                  auto-grow
                />
                <VTextField
                  v-else
                  v-model="form[f.key]"
                  :label="f.label"
                  :type="f.type || 'text'"
                  :hint="f.hint"
                  :persistent-hint="!!f.hint"
                  :required="f.required"
                  :disabled="editing && f.disableOnEdit"
                />
              </slot>
            </VCol>
          </VRow>
          <VAlert
            v-if="errorMsg"
            type="error"
            density="compact"
            class="mt-3"
          >
            {{ errorMsg }}
          </VAlert>
        </VForm>
      </VCardText>

      <VDivider />
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="text" @click="drawer = false">{{ t('general.cancel') }}</VBtn>
        <VBtn
          color="primary"
          :loading="submitting"
          @click="submit"
        >
          {{ t('general.save') }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VNavigationDrawer>
</template>
