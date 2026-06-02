<script setup>
/**
 * 事件规则节点画布编辑器
 * -----------------------------------------------------------------------
 * 节点拓扑(线性链):  Trigger → [N 个 Condition] → [N 个 Action]
 * 序列化:  conditions 节点扁平为 {all:[...]}, actions 节点扁平为有序数组
 * (any 分组留作后期扩展; MVP 默认全部走 all 与门)
 */
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import { api } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const orgId = ref(auth.orgId)
const orgOptions = ref([])

const ruleId = computed(() => route.params.id || null)

// ----- 元数据 (字段/op/动作类型/情绪枚举) ------------------------------
const meta = ref({
  fields: [], ops: [], emotions: [], action_types: [],
  fire_policies: ['once_per_session'], phases: ['pre_llm', 'post_llm'],
})

// ----- 表单层 (规则的非画布属性) ---------------------------------------
const ruleForm = ref({
  name: '',
  activity_id: null,
  phase: 'post_llm',
  priority: 0,
  fire_policy: 'once_per_session',
  short_circuit: false,
  is_active: true,
})

const activities = ref([])

const reloadActivities = async () => {
  if (!orgId.value) { activities.value = []; return }
  const acts = await api.get(`/api/orgs/${orgId.value}/activities`)
  activities.value = [
    { title: '★ 该公司所有活动通用 (留空)', value: null },
    ...acts.map(a => ({ title: a.name, value: a.id })),
  ]
}

watch(orgId, async () => {
  await reloadActivities()
})

// ----- 节点画布 --------------------------------------------------------
const nodes = ref([])
const edges = ref([])

const newId = () => `n_${Math.random().toString(36).slice(2, 9)}`

const TRIGGER_ID = 'trigger'

const initEmptyCanvas = () => {
  nodes.value = [
    { id: TRIGGER_ID, type: 'input', position: { x: 80, y: 200 },
      data: { kind: 'trigger', label: 'Trigger' },
      deletable: false },
  ]
  edges.value = []
}

const addCondition = () => {
  const id = newId()
  const idx = nodes.value.filter(n => n.data.kind === 'condition').length
  nodes.value.push({
    id, position: { x: 320, y: 80 + idx * 110 },
    data: { kind: 'condition', label: '条件',
      field: 'new_emotion', op: 'in', value: ['anger'] },
  })
  // 与 trigger 连边
  edges.value.push({ id: `e_${TRIGGER_ID}_${id}`, source: TRIGGER_ID, target: id,
    markerEnd: MarkerType.ArrowClosed })
}

const addAction = () => {
  const id = newId()
  const idx = nodes.value.filter(n => n.data.kind === 'action').length
  nodes.value.push({
    id, position: { x: 640, y: 80 + idx * 110 },
    data: { kind: 'action', label: '动作', type: 'send_text', payload: { content: '' } },
  })
  // 自动从最后一个条件(或 trigger)连过来
  const lastCond = [...nodes.value].reverse().find(n => n.data.kind === 'condition')
  const src = lastCond ? lastCond.id : TRIGGER_ID
  edges.value.push({ id: `e_${src}_${id}`, source: src, target: id,
    markerEnd: MarkerType.ArrowClosed })
}

// ----- 选中节点 + 右侧抽屉 ---------------------------------------------
const selectedId = ref(null)
const selectedNode = computed(() =>
  nodes.value.find(n => n.id === selectedId.value) || null)

const onNodeClick = (e) => { selectedId.value = e.node.id }

const removeSelected = () => {
  if (!selectedId.value || selectedId.value === TRIGGER_ID) return
  const id = selectedId.value
  nodes.value = nodes.value.filter(n => n.id !== id)
  edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
  selectedId.value = null
}

// ----- 序列化: 节点 → 后端 conditions/actions JSON ----------------------
function serialize() {
  const conds = nodes.value
    .filter(n => n.data.kind === 'condition')
    .map(n => ({ field: n.data.field, op: n.data.op, value: n.data.value }))
  const acts = nodes.value
    .filter(n => n.data.kind === 'action')
    .map(n => ({ type: n.data.type, ...(n.data.payload || {}) }))
  return {
    conditions: { all: conds },
    actions: acts,
  }
}

// ----- 反序列化: 已有规则 JSON → 节点 -----------------------------------
function deserialize(rule) {
  initEmptyCanvas()
  const all = (rule.conditions && rule.conditions.all) || []
  all.forEach((c, i) => {
    const id = newId()
    nodes.value.push({
      id, position: { x: 320, y: 80 + i * 110 },
      data: { kind: 'condition', label: '条件',
        field: c.field, op: c.op, value: c.value },
    })
    edges.value.push({ id: `e_${TRIGGER_ID}_${id}`, source: TRIGGER_ID, target: id,
      markerEnd: MarkerType.ArrowClosed })
  })
  const condIds = nodes.value.filter(n => n.data.kind === 'condition').map(n => n.id)
  const lastSrc = condIds.length ? condIds[condIds.length - 1] : TRIGGER_ID
  ;(rule.actions || []).forEach((a, i) => {
    const id = newId()
    const { type, ...rest } = a
    nodes.value.push({
      id, position: { x: 640, y: 80 + i * 110 },
      data: { kind: 'action', label: '动作', type, payload: rest },
    })
    edges.value.push({ id: `e_${lastSrc}_${id}`, source: lastSrc, target: id,
      markerEnd: MarkerType.ArrowClosed })
  })
}

// ----- 加载/保存/干跑 ---------------------------------------------------
const dryRunDialog = ref(false)
const dryRunCtx = ref('{\n  "new_emotion": "anger",\n  "stage_turn_count": 5\n}')
const dryRunResult = ref(null)

const errMsg = ref('')

const onSave = async () => {
  errMsg.value = ''
  const body = { ...ruleForm.value, ...serialize() }
  try {
    if (ruleId.value) {
      await api.patch(`/api/orgs/${orgId.value}/event-rules/${ruleId.value}`, body)
    } else {
      const created = await api.post(`/api/orgs/${orgId.value}/event-rules`, body)
      router.replace(`/org/event-rules/edit/${created.id}`)
    }
    router.push('/org/event-rules')
  } catch (e) {
    errMsg.value = e.detail || e.message
  }
}

const onDryRun = async () => {
  errMsg.value = ''
  let ctxObj
  try { ctxObj = JSON.parse(dryRunCtx.value) }
  catch { errMsg.value = '上下文 JSON 不合法'; return }
  try {
    const r = await api.post(`/api/orgs/${orgId.value}/event-rules/dry-run`, {
      conditions: serialize().conditions,
      simulated_ctx: ctxObj,
    })
    dryRunResult.value = r
  } catch (e) {
    errMsg.value = e.detail || e.message
  }
}

onMounted(async () => {
  // platform_admin 没绑定固定 org, 需要先选 org 才能列 activity
  if (auth.isPlatformAdmin) {
    const orgs = await api.get('/api/organizations')
    orgOptions.value = orgs.map(o => ({ title: o.name, value: o.id }))
    if (!orgId.value && orgs[0]) orgId.value = orgs[0].id
  }

  // 元数据 + 当前 org 的 activity 列表
  const [md] = await Promise.all([
    api.get('/api/event-rules/metadata'),
    reloadActivities(),
  ])
  meta.value = md

  if (ruleId.value) {
    const list = await api.get(`/api/orgs/${orgId.value}/event-rules`)
    const r = list.find(x => x.id === ruleId.value)
    if (r) {
      Object.assign(ruleForm.value, {
        name: r.name, activity_id: r.activity_id, phase: r.phase,
        priority: r.priority, fire_policy: r.fire_policy,
        short_circuit: r.short_circuit, is_active: r.is_active,
      })
      deserialize(r)
    } else {
      initEmptyCanvas()
    }
  } else {
    initEmptyCanvas()
  }
})

// ----- Action 类型字段表 (按 type 显示不同输入) -------------------------
const actionFieldsByType = {
  send_text: [{ key: 'content', label: '文本', type: 'textarea' }],
  send_link: [{ key: 'url', label: 'URL' }, { key: 'label', label: '按钮文案' }],
  send_image: [{ key: 'url', label: '图片 URL' }, { key: 'caption', label: '图说' }],
  send_video: [{ key: 'url', label: '视频 URL' }, { key: 'caption', label: '说明' }],
  send_payment_link: [
    { key: 'url', label: '支付链接' },
    { key: 'amount', label: '金额', type: 'number' },
    { key: 'currency', label: '币种' },
  ],
  send_material: [{ key: 'material_id', label: '素材 ID(暂未启用)' }],
  transfer_to_human: [
    { key: 'target_employee_id', label: '指定员工 ID(可空 = 同组广播)' },
    { key: 'target_group_id', label: '指定组 ID(可空 = 沿用 session.group)' },
    { key: 'reason', label: '原因' },
  ],
  system_notify: [
    { key: 'level', label: '级别(info/warning/urgent)' },
    { key: 'title', label: '标题' },
    { key: 'body', label: '内容', type: 'textarea' },
    { key: 'target_employee_id', label: '收件员工(可空)' },
  ],
  webhook: [
    { key: 'url', label: 'Webhook URL' },
    { key: 'method', label: 'HTTP Method (GET/POST/PUT)' },
  ],
  override_reply: [{ key: 'content', label: '覆盖文本', type: 'textarea' }],
  block_llm: [],
  set_tag: [{ key: 'tag', label: '标签(暂未启用)' }],
}

const valueAsString = computed({
  get: () => {
    if (!selectedNode.value) return ''
    const v = selectedNode.value.data.value
    return Array.isArray(v) ? v.join(',') : (v ?? '')
  },
  set: (s) => {
    if (!selectedNode.value) return
    const op = selectedNode.value.data.op
    if (['in', 'not_in'].includes(op)) {
      selectedNode.value.data.value = String(s).split(',').map(t => t.trim()).filter(Boolean)
    } else if (['gte', 'gt', 'lte', 'lt'].includes(op)) {
      const n = Number(s); selectedNode.value.data.value = Number.isFinite(n) ? n : 0
    } else if (['eq', 'neq'].includes(op) && (s === 'true' || s === 'false')) {
      selectedNode.value.data.value = s === 'true'
    } else {
      selectedNode.value.data.value = s
    }
  },
})
</script>

<template>
  <div>
    <VCard v-if="auth.isPlatformAdmin" class="mb-4">
      <VCardText class="d-flex align-center" style="gap:12px">
        <span class="text-body-2">公司:</span>
        <VSelect v-model="orgId" :items="orgOptions" density="compact" hide-details style="max-width: 360px" />
      </VCardText>
    </VCard>
    <VCard class="mb-4">
      <VCardText>
        <VRow dense>
          <VCol cols="12" md="4">
            <VTextField v-model="ruleForm.name" label="规则名称" density="compact" />
          </VCol>
          <VCol cols="12" md="3">
            <VSelect
              v-model="ruleForm.activity_id"
              :items="activities"
              label="适用活动 (可选某个 activity, 也可全公司通用)"
              density="compact"
              clearable
              :disabled="!activities.length"
            />
          </VCol>
          <VCol cols="6" md="2">
            <VSelect v-model="ruleForm.phase" :items="meta.phases" label="阶段" density="compact" />
          </VCol>
          <VCol cols="6" md="1">
            <VTextField v-model.number="ruleForm.priority" label="优先级" type="number" density="compact" />
          </VCol>
          <VCol cols="6" md="2">
            <VSelect v-model="ruleForm.fire_policy" :items="meta.fire_policies" label="触发频率" density="compact" />
          </VCol>
          <VCol cols="6" md="2">
            <VSwitch v-model="ruleForm.short_circuit" label="命中后短路" inset density="compact" hide-details />
          </VCol>
          <VCol cols="6" md="2">
            <VSwitch v-model="ruleForm.is_active" label="启用" inset density="compact" color="primary" hide-details />
          </VCol>
        </VRow>
        <VAlert v-if="errMsg" type="error" density="compact" class="mt-2">{{ errMsg }}</VAlert>
      </VCardText>
    </VCard>

    <VCard>
      <VCardText class="d-flex align-center" style="gap:12px">
        <VBtn size="small" prepend-icon="ri-add-line" variant="tonal" @click="addCondition">加条件</VBtn>
        <VBtn size="small" prepend-icon="ri-add-line" variant="tonal" color="primary" @click="addAction">加动作</VBtn>
        <VBtn v-if="selectedId && selectedId !== TRIGGER_ID" size="small" color="error" variant="text"
              prepend-icon="ri-delete-bin-line" @click="removeSelected">删除选中</VBtn>
        <VSpacer />
        <VBtn size="small" variant="text" prepend-icon="ri-test-tube-line" @click="dryRunDialog = true">干跑预览</VBtn>
        <VBtn size="small" color="primary" prepend-icon="ri-save-line" @click="onSave">保存</VBtn>
      </VCardText>

      <div style="height: 520px; border-top: 1px solid #eee">
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" @node-click="onNodeClick" fit-view-on-init>
          <Background pattern-color="#bbb" :gap="16" />
          <Controls />
        </VueFlow>
      </div>
    </VCard>

    <!-- 选中节点的属性侧抽屉 -->
    <VNavigationDrawer v-model="selectedId" location="right" temporary width="380" :model-value="!!selectedId" @update:model-value="v => !v && (selectedId = null)">
      <div v-if="selectedNode" class="pa-4">
        <h3 class="text-h6 mb-2">{{ selectedNode.data.label }}</h3>
        <small class="text-medium-emphasis">{{ selectedNode.id }}</small>

        <!-- Condition -->
        <template v-if="selectedNode.data.kind === 'condition'">
          <VSelect v-model="selectedNode.data.field" :items="meta.fields" label="字段" density="compact" class="mt-3" />
          <VSelect v-model="selectedNode.data.op" :items="meta.ops" label="操作符" density="compact" />
          <template v-if="selectedNode.data.field === 'new_emotion' || selectedNode.data.field === 'prev_emotion'">
            <VSelect
              v-if="['in','not_in'].includes(selectedNode.data.op)"
              v-model="selectedNode.data.value"
              :items="meta.emotions" label="值(多选)"
              multiple chips density="compact"
            />
            <VSelect
              v-else
              v-model="selectedNode.data.value"
              :items="meta.emotions" label="值"
              density="compact"
            />
          </template>
          <VTextField
            v-else
            v-model="valueAsString"
            label="值 (in/not_in 用逗号分隔; 数值类直接填; 布尔填 true/false)"
            density="compact"
          />
        </template>

        <!-- Action -->
        <template v-if="selectedNode.data.kind === 'action'">
          <VSelect v-model="selectedNode.data.type" :items="meta.action_types" label="动作类型" density="compact" class="mt-3" />
          <div v-for="f in (actionFieldsByType[selectedNode.data.type] || [])" :key="f.key" class="mt-2">
            <VTextarea v-if="f.type === 'textarea'"
              v-model="selectedNode.data.payload[f.key]" :label="f.label" rows="3" auto-grow density="compact" />
            <VTextField v-else
              v-model="selectedNode.data.payload[f.key]"
              :label="f.label"
              :type="f.type === 'number' ? 'number' : 'text'"
              density="compact" />
          </div>
        </template>
      </div>
    </VNavigationDrawer>

    <!-- 干跑对话框 -->
    <VDialog v-model="dryRunDialog" max-width="640">
      <VCard>
        <VCardItem><VCardTitle>干跑: 模拟一个 ctx 看会不会命中</VCardTitle></VCardItem>
        <VCardText>
          <VTextarea v-model="dryRunCtx" label="模拟上下文 (JSON)" rows="8" style="font-family:monospace" />
          <VAlert v-if="dryRunResult" :type="dryRunResult.matched ? 'success' : 'info'" class="mt-3" density="compact">
            {{ dryRunResult.matched ? '✅ 会命中' : '❌ 不会命中' }}
          </VAlert>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="dryRunDialog = false">关闭</VBtn>
          <VBtn color="primary" @click="onDryRun">运行</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>
