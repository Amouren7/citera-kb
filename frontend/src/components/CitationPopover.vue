<script setup lang="ts">
/**
 * 引用来源卡（记忆点 1，DESIGN §6）：回答里的角标点开后必须能看清
 * 文档 / 章节 / 块序号 / 片段 / 相关度，并能跳回原文。
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { Citation } from '@/api'
import { formatScore } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    citation: Citation | null
    index: number
    anchor: DOMRect | null
    /** 登录页的演示角标不提供跳转（跳过去也会被守卫拦回登录页） */
    showLink?: boolean
  }>(),
  { showLink: true },
)

const emit = defineEmits<{ close: [] }>()

const card = ref<HTMLElement | null>(null)
const position = ref<{ top: number; left: number }>({ top: -9999, left: -9999 })

const metaLine = computed(() => {
  const citation = props.citation
  if (!citation) return ''
  const parts = [
    citation.heading ?? '无章节',
    `第 ${citation.ord} 块`,
    `score ${formatScore(citation.score)}`,
    citation.retrieval,
    `rank ${citation.rank}`,
  ]
  return parts.join(' · ')
})

function place(): void {
  const anchor = props.anchor
  const element = card.value
  if (!anchor || !element) return
  const margin = 8
  const rect = element.getBoundingClientRect()
  const width = rect.width || 380
  const height = rect.height || 240
  const maxLeft = Math.max(margin, window.innerWidth - width - margin)
  const left = Math.min(Math.max(margin, anchor.left), maxLeft)
  let top = anchor.bottom + 6
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, anchor.top - height - 6)
  }
  position.value = { top, left }
  element.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`
}

function onPointerDown(event: PointerEvent): void {
  const element = card.value
  if (element && !element.contains(event.target as Node)) emit('close')
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

function onViewportChange(): void {
  emit('close')
}

onMounted(async () => {
  await nextTick()
  place()
  requestAnimationFrame(() => {
    place()
    // 绑定放到下一帧，避免打开它的那一次点击立刻把自己关掉
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeydown)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
  })
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
})
</script>

<template>
  <Teleport to="body">
    <div ref="card" class="citecard" role="dialog" aria-label="引用详情">
      <div class="citecard__head">
        <span class="citecard__badge num">c{{ index }}</span>
        <span class="micro">引用来源</span>
        <button class="citecard__close" type="button" aria-label="关闭" @click="emit('close')">×</button>
      </div>

      <div v-if="citation" class="citecard__body">
        <strong class="citecard__title">{{ citation.document_title }}</strong>
        <span class="citecard__meta num">{{ metaLine }}</span>
        <p class="citecard__snippet">{{ citation.snippet }}</p>
        <div class="citecard__foot">
          <span class="micro">相关度 {{ formatScore(citation.score) }}</span>
          <RouterLink
            v-if="showLink"
            class="citecard__link"
            :to="{ name: 'document-detail', params: { id: citation.document_id }, query: { chunk: String(citation.ord) } }"
          >
            打开原文 →
          </RouterLink>
        </div>
      </div>

      <div v-else class="citecard__body">
        <strong class="citecard__title">该引用不在本条回答的引用列表中</strong>
        <p class="citecard__snippet">
          正文里出现了 <code>[[c{{ index }}]]</code>，但本条消息的 citations 只有更少的条目。这通常意味着生成被中断或数据不一致。
        </p>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.citecard {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 3000;
  width: 380px;
  max-width: calc(100vw - 16px);
  border: 1px solid var(--c-line-2);
  background: var(--c-surface);
  box-shadow: var(--shadow-pop);
  will-change: transform;
}

.citecard__head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--c-line);
  background: var(--c-sunken);
}

.citecard__badge {
  display: inline-grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  background: var(--c-accent);
  color: var(--c-accent-ink);
  font-size: var(--fs-11);
}

.citecard__close {
  margin-left: auto;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--c-ink-2);
  font-size: var(--fs-16);
  line-height: 1;
  cursor: pointer;
}

.citecard__close:hover {
  border-color: var(--c-line-2);
  color: var(--c-ink);
}

.citecard__body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
}

.citecard__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semi);
}

.citecard__meta {
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  letter-spacing: 0.03em;
  color: var(--c-ink-3);
}

.citecard__snippet {
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  border-left: 2px solid var(--c-accent-line);
  background: var(--c-sunken);
  color: var(--c-ink-2);
  font-size: var(--fs-13);
  line-height: 1.7;
}

.citecard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

.citecard__link {
  font-size: var(--fs-13);
  border-bottom: none;
}
</style>
