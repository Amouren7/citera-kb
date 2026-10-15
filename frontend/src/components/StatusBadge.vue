<script setup lang="ts">
/** 文档状态徽标：直角 + mono + 语义圆点（DESIGN §3/§8）。 */
import { computed } from 'vue'
import { documentStatusMeta } from '@/utils/format'

const props = defineProps<{ status: string; withDot?: boolean }>()

const meta = computed(() => documentStatusMeta(props.status))
const classes = computed(() => {
  const tone = meta.value.tone
  return tone === 'neutral' ? 'badge' : `badge badge--${tone}`
})
</script>

<template>
  <span :class="classes" :title="`状态：${meta.label}`">
    <i v-if="withDot !== false" class="dot" :class="{ 'dot--pulse': status === 'processing' || status === 'pending' }" />
    {{ meta.label }}
  </span>
</template>
