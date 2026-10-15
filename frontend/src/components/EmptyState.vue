<script setup lang="ts">
/** 空状态：构图完整 + 明确的下一步动作（DESIGN §8）。 */
withDefaults(
  defineProps<{
    title: string
    hint?: string
    actionLabel?: string
    secondaryLabel?: string
  }>(),
  { hint: '', actionLabel: '', secondaryLabel: '' },
)

defineEmits<{ action: []; secondary: [] }>()
</script>

<template>
  <div class="empty">
    <span class="micro">空</span>
    <h2 class="empty__title">{{ title }}</h2>
    <p v-if="hint" class="empty__hint">{{ hint }}</p>
    <div v-if="actionLabel || secondaryLabel" class="empty__actions">
      <button v-if="actionLabel" class="btn btn--primary" type="button" @click="$emit('action')">
        {{ actionLabel }}
      </button>
      <button v-if="secondaryLabel" class="btn" type="button" @click="$emit('secondary')">
        {{ secondaryLabel }}
      </button>
    </div>
  </div>
</template>
