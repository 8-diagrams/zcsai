<script setup>
import { useTheme } from 'vuetify'

// 轻量图表: type='donut' (会话状态) 或 'bar' (情绪分布)
// data: [{ label, value }, ...]
const props = defineProps({
  type: { type: String, default: 'donut' }, // donut | bar
  data: { type: Array, default: () => [] },
  height: { type: Number, default: 240 },
})

const vuetifyTheme = useTheme()
const themeColors = computed(() => vuetifyTheme.current.value.colors)

const palette = computed(() => {
  const c = themeColors.value
  return [c.primary, c.success, c.warning, c.info, c.error, c.secondary]
})

const labels = computed(() => props.data.map(d => d.label))
const values = computed(() => props.data.map(d => Number(d.value) || 0))
const isEmpty = computed(() => values.value.every(v => v === 0))

const series = computed(() =>
  props.type === 'bar'
    ? [{ data: values.value }]
    : values.value,
)

const chartOptions = computed(() => {
  const base = {
    chart: { toolbar: { show: false }, parentHeightOffset: 0 },
    colors: palette.value,
    legend: { show: props.type === 'donut', position: 'bottom', labels: { colors: themeColors.value['on-surface'] } },
    dataLabels: { enabled: false },
    tooltip: { enabled: true },
  }
  if (props.type === 'bar') {
    return {
      ...base,
      plotOptions: { bar: { columnWidth: '45%', borderRadius: 4, distributed: true } },
      xaxis: {
        categories: labels.value,
        labels: { style: { colors: themeColors.value['on-surface'] } },
      },
      yaxis: { labels: { style: { colors: themeColors.value['on-surface'] } } },
      grid: { borderColor: themeColors.value['track-bg'] },
    }
  }
  return { ...base, labels: labels.value, stroke: { width: 0 } }
})
</script>

<template>
  <div>
    <div v-if="isEmpty" class="text-center text-medium-emphasis py-8">
      {{ $t('dashboard.noData') }}
    </div>
    <VueApexCharts
      v-else
      :type="type"
      :options="chartOptions"
      :series="series"
      :height="height"
    />
  </div>
</template>
