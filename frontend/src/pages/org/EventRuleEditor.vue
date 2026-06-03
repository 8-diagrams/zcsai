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

// ----- 元数据 (字段/op/动作类型/情绪/stage 枚举, 都带中英文 label) ------------
// 每项形如 { value, label_zh, label_en, hint? }; v-select 用 itemTitle/itemValue 渲染
const meta = ref({
  fields: [], ops: [], emotions: [], action_types: [],
  stages_global: [], fire_policies: [], phases: [],
  stage_like_fields: [], emotion_like_fields: [], boolean_like_fields: [],
})

// 工具: 给 v-select 把 [{value, label_zh}] 包成 {title, value}; 也兼容老的字符串数组
const toItems = (arr) => (arr || []).map(x =>
  typeof x === 'string'
    ? { title: x, value: x }
    : { title: `${x.label_zh}  ·  ${x.value}`, value: x.value, hint: x.hint })

// stage 类下拉用 activity 自己的 stages_config, 拿不到再回退全局 6 个 stage
const stageOptions = computed(() => {
  const local = currentActivityStages.value
  if (local && local.length) return local
  return toItems(meta.value.stages_global)
})

const currentActivityStages = ref([])    // [{title, value}] (取自 activity.stages_config)

// 选中字段对应的提示, 显示在字段下拉下方
const currentFieldHint = computed(() => {
  if (!selectedNode.value || selectedNode.value.data.kind !== 'condition') return ''
  const f = (meta.value.fields || []).find(x => x.value === selectedNode.value.data.field)
  return f && f.hint ? f.hint : ''
})

// 加载某个 activity 的 stages_config 作为 stage 类下拉源 (优先级高于 stages_global)
async function loadStagesForActivity(actId) {
  if (!actId) { currentActivityStages.value = []; return }
  try {
    const all = await api.get(`/api/orgs/${orgId.value}/activities`)
    const act = all.find(a => a.id === actId)
    const cfg = act && act.stages_config
    if (cfg && typeof cfg === 'object') {
      currentActivityStages.value = Object.keys(cfg).map(k => {
        const v = cfg[k]
        const name = (v && typeof v === 'object' && v.name) ? v.name : k
        return { title: `${name}  ·  ${k}`, value: k }
      })
    } else {
      currentActivityStages.value = []
    }
  } catch {
    currentActivityStages.value = []
  }
}
// watch(activity_id) 在 ruleForm 声明之后再注册, 见下方 ruleForm 后面

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

// activity_id 切换 → 重新拉 stages_config 当 stage 类下拉源
watch(() => ruleForm.value.activity_id, (v) => { loadStagesForActivity(v) })

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
const GATE_ID    = 'gate_and'  // 固定 ID 的 AND 汇聚节点

// 重新计算所有边: trigger → c1 → c2 → ... → cN → AND → 各 action
// 改任何节点 (新增/删除/反序列化) 后都调用此函数, 保证图始终反映 all 语义
function relayoutEdges() {
  const conds   = nodes.value.filter(n => n.data.kind === 'condition')
  const actions = nodes.value.filter(n => n.data.kind === 'action')
  const newEdges = []

  // condition 串联链 (AND): 第一条 trigger→c1 不带 AND 标签 (前面没东西可 AND)
  let prev = TRIGGER_ID
  conds.forEach((c, i) => {
    const e = {
      id: `e_${prev}_${c.id}`, source: prev, target: c.id,
      style: { stroke: '#666' },
      markerEnd: MarkerType.ArrowClosed,
    }
    if (i > 0) {
      e.label = 'AND'
      e.labelBgPadding = [4, 2]
      e.labelStyle = { fontSize: 10, fill: '#555' }
    }
    newEdges.push(e)
    prev = c.id
  })

  // gate 节点: 没有 condition 时 trigger 直连 actions; 有 condition 时 chain 末端 → gate
  const gateAlive = actions.length > 0
  if (gateAlive) {
    // 确保 gate 节点在 nodes 中存在
    if (!nodes.value.find(n => n.id === GATE_ID)) {
      nodes.value.push({
        id: GATE_ID, type: 'default',
        position: { x: 540, y: 200 },
        data: { kind: 'gate', label: 'AND\n全部满足才执行' },
        deletable: false,
        selectable: false,
        style: {
          background: '#FFE082', border: '2px solid #F9A825',
          borderRadius: '50%', width: 80, height: 80,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 600, whiteSpace: 'pre-line',
        },
      })
    }
    newEdges.push({
      id: `e_${prev}_${GATE_ID}`, source: prev, target: GATE_ID,
      style: { stroke: '#F9A825', strokeWidth: 2 },
      markerEnd: MarkerType.ArrowClosed,
    })
    // gate → 每个 action
    actions.forEach((a) => {
      newEdges.push({
        id: `e_${GATE_ID}_${a.id}`, source: GATE_ID, target: a.id,
        style: { stroke: '#43A047', strokeWidth: 2 },
        markerEnd: MarkerType.ArrowClosed,
      })
    })
  } else {
    // 没动作就移除 gate 节点
    nodes.value = nodes.value.filter(n => n.id !== GATE_ID)
  }

  edges.value = newEdges
}

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
    id, position: { x: 300, y: 80 + idx * 110 },
    data: { kind: 'condition', label: '条件',
      field: 'new_emotion', op: 'in', value: ['anger'] },
  })
  relayoutEdges()
}

const addAction = () => {
  const id = newId()
  const idx = nodes.value.filter(n => n.data.kind === 'action').length
  nodes.value.push({
    id, position: { x: 780, y: 80 + idx * 110 },
    data: { kind: 'action', label: '动作', type: 'send_text', payload: { content: '' } },
  })
  relayoutEdges()
}

// ----- 选中节点 + 右侧抽屉 ---------------------------------------------
const selectedId = ref(null)
const drawerOpen = ref(false)
const selectedNode = computed(() =>
  nodes.value.find(n => n.id === selectedId.value) || null)

const onNodeClick = (e) => {
  selectedId.value = e.node.id
  drawerOpen.value = true
}

const removeSelected = () => {
  if (!selectedId.value || selectedId.value === TRIGGER_ID || selectedId.value === GATE_ID) return
  const id = selectedId.value
  nodes.value = nodes.value.filter(n => n.id !== id)
  selectedId.value = null
  drawerOpen.value = false
  relayoutEdges()
}

// ----- 序列化: 节点 → 后端 conditions/actions JSON ----------------------
// 防线: 即便 UI 上 op/value 形状对不上 (例如老规则历史脏数据),
// 也按 op 强行归一,保证写到后端的 conditions 一定合法。
function coerceValueForOp(op, v) {
  if (['in', 'not_in'].includes(op)) {
    if (Array.isArray(v)) return v
    if (v === undefined || v === null || v === '') return []
    if (typeof v === 'string') return v.split(',').map(t => t.trim()).filter(Boolean)
    return [v]
  }
  if (['eq', 'neq'].includes(op)) {
    if (Array.isArray(v)) return v.length ? v[0] : ''
    return v
  }
  if (['gte', 'gt', 'lte', 'lt'].includes(op)) {
    const n = Number(Array.isArray(v) ? v[0] : v)
    return Number.isFinite(n) ? n : 0
  }
  return v
}

function serialize() {
  const conds = nodes.value
    .filter(n => n.data.kind === 'condition')
    .map(n => ({
      field: n.data.field,
      op: n.data.op,
      value: coerceValueForOp(n.data.op, n.data.value),
    }))
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
      id, position: { x: 300, y: 80 + i * 110 },
      data: { kind: 'condition', label: '条件',
        field: c.field, op: c.op, value: c.value },
    })
  })
  ;(rule.actions || []).forEach((a, i) => {
    const id = newId()
    const { type, ...rest } = a
    nodes.value.push({
      id, position: { x: 780, y: 80 + i * 110 },
      data: { kind: 'action', label: '动作', type, payload: rest },
    })
  })
  relayoutEdges()
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

const onEscClose = (e) => {
  if (e.key === 'Escape' && drawerOpen.value) drawerOpen.value = false
}
onBeforeUnmount(() => window.removeEventListener('keydown', onEscClose))

onMounted(async () => {
  // Esc 关闭抽屉 (因为 scrim=false, 没遮罩可点)
  window.addEventListener('keydown', onEscClose)

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

/**
 * 切换 op 时把 value 形状归一化:
 *   in / not_in  → 数组
 *   eq / neq     → 标量(若当前是数组, 取第一项)
 *   gte/gt/lte/lt → 数字
 *   其它          → 维持
 * 修一个 bug: 之前从 in([anger]) 切到 eq, value 仍是 ['anger'] 列表,
 * 序列化成 {"op":"eq","value":["anger"]} 在后端永不命中。
 */
function normalizeValueForOp(node, newOp) {
  if (!node || !node.data) return
  const v = node.data.value
  if (['in', 'not_in'].includes(newOp)) {
    if (!Array.isArray(v)) {
      node.data.value = (v === undefined || v === null || v === '') ? [] : [v]
    }
  } else if (['eq', 'neq'].includes(newOp)) {
    if (Array.isArray(v)) {
      node.data.value = v.length ? v[0] : ''
    }
  } else if (['gte', 'gt', 'lte', 'lt'].includes(newOp)) {
    const n = Number(Array.isArray(v) ? v[0] : v)
    node.data.value = Number.isFinite(n) ? n : 0
  }
}

// 用 sig 记忆"当前 drawer 里那个节点的 (id, op, field)";
// 只有 id 不变, 仅仅 op/field 在 UI 上被用户切了, 才做归一化/清空。
// 不区分这两种场景就会出 bug: 比如打开节点 (从 null → node) 会触发 field/op 的 watch,
// 把刚反序列化进来的合法 value 清成 ''。
const lastSig = ref({ id: null, op: null, field: null })

watch(selectedNode, (node) => {
  // 切节点 (或关闭 drawer): 只更新 sig, 不动任何 value
  lastSig.value = node
    ? { id: node.id, op: node.data.op, field: node.data.field }
    : { id: null, op: null, field: null }
}, { immediate: true })

watch(() => selectedNode.value && selectedNode.value.data.op, (newOp) => {
  const node = selectedNode.value
  if (!node || !newOp) return
  // 同一节点内 op 才发生变化 → 归一 value
  if (lastSig.value.id === node.id && lastSig.value.op !== newOp) {
    normalizeValueForOp(node, newOp)
  }
  lastSig.value = { ...lastSig.value, id: node.id, op: newOp }
})

watch(() => selectedNode.value && selectedNode.value.data.field, (newField) => {
  const node = selectedNode.value
  if (!node || !newField) return
  // 同一节点内 field 才被用户切 → 按当前 op 给一个空值
  if (lastSig.value.id === node.id && lastSig.value.field !== newField) {
    const op = node.data.op
    if (['gte', 'gt', 'lte', 'lt'].includes(op)) node.data.value = 0
    else if (['in', 'not_in'].includes(op))     node.data.value = []
    else                                         node.data.value = ''
  }
  lastSig.value = { ...lastSig.value, id: node.id, field: newField }
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
            <VSelect v-model="ruleForm.phase" :items="toItems(meta.phases)"
                     item-title="title" item-value="value"
                     label="阶段" density="compact" />
          </VCol>
          <VCol cols="6" md="1">
            <VTextField v-model.number="ruleForm.priority" label="优先级" type="number" density="compact" />
          </VCol>
          <VCol cols="6" md="2">
            <VSelect v-model="ruleForm.fire_policy" :items="toItems(meta.fire_policies)"
                     item-title="title" item-value="value"
                     label="触发频率" density="compact" />
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

      <div class="vue-flow-host">
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" @node-click="onNodeClick" fit-view-on-init>
          <Background pattern-color="#bbb" :gap="16" />
          <Controls />
        </VueFlow>
      </div>
    </VCard>

    <!-- 选中节点的属性侧抽屉 -->
    <VNavigationDrawer
      v-model="drawerOpen"
      location="right"
      temporary
      width="380"
      :scrim="false"
    >
      <div v-if="selectedNode" class="pa-4 drawer-body">
        <div class="d-flex align-center mb-2">
          <h3 class="text-h6 me-auto">{{ selectedNode.data.label }}</h3>
          <VBtn icon="ri-close-line" size="small" variant="text" @click="drawerOpen = false" />
        </div>
        <div class="text-caption text-medium-emphasis mb-3">{{ selectedNode.id }}</div>

        <!-- Condition -->
        <template v-if="selectedNode.data.kind === 'condition'">
          <div class="field-label">字段</div>
          <VSelect v-model="selectedNode.data.field" :items="toItems(meta.fields)"
                   item-title="title" item-value="value"
                   variant="outlined" density="compact" hide-details class="mb-3" />
          <div v-if="currentFieldHint" class="text-caption text-medium-emphasis mb-3">
            {{ currentFieldHint }}
          </div>

          <div class="field-label">操作符</div>
          <VSelect v-model="selectedNode.data.op" :items="toItems(meta.ops)"
                   item-title="title" item-value="value"
                   variant="outlined" density="compact" hide-details class="mb-3" />

          <!-- 情绪类字段 -->
          <template v-if="meta.emotion_like_fields.includes(selectedNode.data.field)">
            <div class="field-label">值</div>
            <VSelect
              v-if="['in','not_in'].includes(selectedNode.data.op)"
              v-model="selectedNode.data.value"
              :items="toItems(meta.emotions)"
              item-title="title" item-value="value"
              multiple chips
              variant="outlined" density="compact" hide-details
            />
            <VSelect
              v-else
              v-model="selectedNode.data.value"
              :items="toItems(meta.emotions)"
              item-title="title" item-value="value"
              variant="outlined" density="compact" hide-details
            />
          </template>

          <!-- Stage 类字段: new_stage / prev_stage / stage_flipped_to -->
          <template v-else-if="meta.stage_like_fields.includes(selectedNode.data.field)">
            <div class="field-label">值 (SOP 阶段)</div>
            <VSelect
              v-if="['in','not_in'].includes(selectedNode.data.op)"
              v-model="selectedNode.data.value"
              :items="stageOptions"
              item-title="title" item-value="value"
              multiple chips
              variant="outlined" density="compact" hide-details
            />
            <VSelect
              v-else
              v-model="selectedNode.data.value"
              :items="stageOptions"
              item-title="title" item-value="value"
              variant="outlined" density="compact" hide-details
            />
          </template>

          <!-- Boolean 类字段: stage_flipped / emotion_degraded -->
          <template v-else-if="meta.boolean_like_fields.includes(selectedNode.data.field)">
            <div class="field-label">值 (布尔)</div>
            <VSelect
              v-model="selectedNode.data.value"
              :items="[{title:'是 (true)', value:true},{title:'否 (false)', value:false}]"
              item-title="title" item-value="value"
              variant="outlined" density="compact" hide-details
            />
          </template>

          <!-- 数值类 / 字符串类: 自由输入 -->
          <template v-else>
            <div class="field-label">
              值
              <span v-if="['in','not_in'].includes(selectedNode.data.op)">(多个用逗号分隔)</span>
              <span v-else-if="['gte','gt','lte','lt'].includes(selectedNode.data.op)">(数字)</span>
            </div>
            <VTextField
              v-model="valueAsString"
              variant="outlined" density="compact" hide-details
            />
          </template>
        </template>

        <!-- Action -->
        <template v-if="selectedNode.data.kind === 'action'">
          <div class="field-label">动作类型</div>
          <VSelect v-model="selectedNode.data.type" :items="toItems(meta.action_types)"
                   item-title="title" item-value="value"
                   variant="outlined" density="compact" hide-details class="mb-3" />

          <div v-for="f in (actionFieldsByType[selectedNode.data.type] || [])" :key="f.key" class="mb-3">
            <div class="field-label">{{ f.label }}</div>
            <VTextarea v-if="f.type === 'textarea'"
              v-model="selectedNode.data.payload[f.key]" rows="3" auto-grow
              variant="outlined" density="compact" hide-details />
            <VTextField v-else
              v-model="selectedNode.data.payload[f.key]"
              :type="f.type === 'number' ? 'number' : 'text'"
              variant="outlined" density="compact" hide-details />
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

<style scoped>
/* Vue Flow 必须有 position:relative 才能正确定位节点 (它内部用 transform);
   再开 overflow:hidden 防止画布溢出影响外层文字布局; */
.vue-flow-host {
  position: relative;
  height: 560px;
  overflow: hidden;
  border-top: 1px solid #eee;
}

/* Vuetify 全局 line-height/letter-spacing 会让 Vue Flow 节点内的小字"挤"在一起。
   在节点容器里恢复默认。 */
.vue-flow-host :deep(.vue-flow__node) {
  line-height: 1.4;
  letter-spacing: normal;
  font-family: inherit;
}
.vue-flow-host :deep(.vue-flow__node-default),
.vue-flow-host :deep(.vue-flow__node-input),
.vue-flow-host :deep(.vue-flow__node-output) {
  padding: 8px 12px;
  font-size: 13px;
}

/* drawer 内字段排版: 用顶部小标签 + outlined 输入框替代 floating label,
   一来视觉干净, 二来 compact density 下垂直空间足够。 */
.drawer-body .field-label {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 4px;
}
</style>
