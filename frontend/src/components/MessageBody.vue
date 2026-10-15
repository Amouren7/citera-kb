<script setup lang="ts">
/**
 * 回答正文：Markdown 过 DOMPurify（契约 §7.2.6），`[[cN]]` 渲染成可点角标（§7.2.5）。
 * 角标来自 v-html，所以用事件委托处理点击/键盘，弹层交给 CitationPopover。
 */
import { computed, ref } from 'vue'
import type { Citation } from '@/api'
import { renderMarkdown } from '@/utils/markdown'
import CitationPopover from './CitationPopover.vue'

const props = withDefaults(
  defineProps<{
    content: string
    citations?: Citation[]
    streaming?: boolean
  }>(),
  { citations: () => [], streaming: false },
)

const html = computed(() => renderMarkdown(props.content, props.citations))

const openIndex = ref<number | null>(null)
const anchor = ref<DOMRect | null>(null)
let activeElement: HTMLElement | null = null

const openCitation = computed(() => {
  if (openIndex.value === null) return null
  return props.citations[openIndex.value - 1] ?? null
})

function clearActive(): void {
  if (activeElement) {
    activeElement.removeAttribute('aria-expanded')
    activeElement = null
  }
}

function close(): void {
  clearActive()
  openIndex.value = null
  anchor.value = null
}

function activate(element: HTMLElement): void {
  const index = Number(element.dataset.cite)
  if (!Number.isFinite(index)) return
  if (openIndex.value === index) {
    close()
    return
  }
  clearActive()
  activeElement = element
  element.setAttribute('aria-expanded', 'true')
  anchor.value = element.getBoundingClientRect()
  openIndex.value = index
}

function onClick(event: MouseEvent): void {
  const target = (event.target as HTMLElement | null)?.closest('[data-cite]')
  if (target instanceof HTMLElement) activate(target)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const target = (event.target as HTMLElement | null)?.closest?.('[data-cite]')
  if (target instanceof HTMLElement) {
    event.preventDefault()
    activate(target)
  }
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 已过 DOMPurify，见 src/utils/markdown.ts -->
  <div class="mbody" @click="onClick" @keydown="onKeydown">
    <div class="md" v-html="html" />
    <span v-if="streaming" class="md-cursor" aria-hidden="true" />
    <CitationPopover
      v-if="openIndex !== null"
      :citation="openCitation"
      :index="openIndex"
      :anchor="anchor"
      @close="close"
    />
  </div>
</template>

<style scoped>
.mbody {
  position: relative;
}
</style>
