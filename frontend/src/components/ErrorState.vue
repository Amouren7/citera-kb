<script setup lang="ts">
/** 行内错误态：mono 错误码 + message + 重试（DESIGN §8：不用 toast 掩盖）。 */
import { computed } from 'vue'
import { toApiError } from '@/api'

const props = withDefaults(
  defineProps<{
    error: unknown
    title?: string
    retryable?: boolean
  }>(),
  { title: '请求失败', retryable: true },
)

defineEmits<{ retry: [] }>()

const detail = computed(() => {
  const api = toApiError(props.error)
  return { code: api.code, message: api.message, status: api.status, retry: api.isRetryable }
})
</script>

<template>
  <div class="errbox" role="alert">
    <div class="stack stack--gap grow">
      <span class="errbox__code">{{ detail.code }}<template v-if="detail.status"> · HTTP {{ detail.status }}</template></span>
      <strong>{{ title }}</strong>
      <span class="muted">{{ detail.message }}</span>
    </div>
    <button v-if="retryable && detail.retry" class="btn" type="button" @click="$emit('retry')">重试</button>
  </div>
</template>
