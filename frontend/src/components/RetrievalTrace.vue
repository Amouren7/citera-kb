<script setup lang="ts">
/**
 * 检索轨迹 + 命中片段（记忆点 2，契约 §7.2.4）：
 * 默认折叠，展开后逐个片段显示 rank / 通道 / 相关度 / 全文片段。
 */
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { Citation } from '@/api'
import { formatScore, truncate } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    citations: Citation[]
    elapsedMs?: number | null
    mode?: string
    /** 流式过程中默认展开，让用户马上看到依据 */
    defaultExpanded?: boolean
  }>(),
  { elapsedMs: null, mode: '', defaultExpanded: false },
)

const expanded = ref(props.defaultExpanded)

watch(
  () => props.defaultExpanded,
  (value) => {
    if (value) expanded.value = true
  },
)

const expandedSnippets = ref<Set<number>>(new Set())

function toggleSnippet(chunkId: number): void {
  const next = new Set(expandedSnippets.value)
  if (next.has(chunkId)) next.delete(chunkId)
  else next.add(chunkId)
  expandedSnippets.value = next
}

const channelCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const citation of props.citations) {
    counts.set(citation.retrieval, (counts.get(citation.retrieval) ?? 0) + 1)
  }
  return [...counts.entries()].map(([channel, count]) => ({ channel, count }))
})

/** 三条通道命中量的竖条：纯 CSS，不走图表库。 */
const maxChannelCount = computed(() => Math.max(1, ...channelCounts.value.map((item) => item.count)))
</script>

<template>
  <section class="trace" aria-label="检索轨迹">
    <button class="trace__head" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span class="micro">检索轨迹</span>
      <span class="trace__stat num">命中 {{ citations.length }} 块</span>
      <span v-if="elapsedMs !== null" class="trace__stat num">{{ elapsedMs }} ms</span>
      <span v-if="mode" class="trace__stat">{{ mode }}</span>

      <span class="trace__bars" aria-hidden="true">
        <span
          v-for="item in channelCounts"
          :key="item.channel"
          class="trace__bar"
          :style="{ height: `${6 + (item.count / maxChannelCount) * 14}px` }"
          :title="`${item.channel} 命中 ${item.count}`"
        />
      </span>

      <span class="grow" />
      <span class="trace__toggle">{{ expanded ? '收起片段' : '展开片段' }}</span>
    </button>

    <ul v-if="expanded" class="frags">
      <li v-for="citation in citations" :key="citation.chunk_id" class="frag">
        <div class="frag__head">
          <span class="frag__rank num">#{{ citation.rank }}</span>
          <span class="frag__title truncate">{{ citation.document_title }}</span>
          <span class="badge">{{ citation.retrieval }}</span>
          <span class="frag__meta num">{{ citation.heading ?? '无章节' }} · 块 {{ citation.ord }}</span>
          <span class="frag__score num">{{ formatScore(citation.score) }}</span>
        </div>
        <p class="frag__snippet" :class="{ 'is-clamped': !expandedSnippets.has(citation.chunk_id) }">
          {{ citation.snippet }}
        </p>
        <div class="frag__foot">
          <button class="btn btn--sm btn--quiet" type="button" @click="toggleSnippet(citation.chunk_id)">
            {{ expandedSnippets.has(citation.chunk_id) ? '收起片段' : '展开全文片段' }}
          </button>
          <RouterLink
            class="frag__link"
            :to="{ name: 'document-detail', params: { id: citation.document_id }, query: { chunk: String(citation.ord) } }"
          >
            打开原文 →
          </RouterLink>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.trace {
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.trace__head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.trace__head:hover {
  background: var(--c-sunken);
}

.trace__stat {
  font-size: var(--fs-12);
  color: var(--c-ink-2);
}

.trace__bars {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 20px;
}

.trace__bar {
  width: 4px;
  min-height: 6px;
  background: var(--c-accent);
}

.trace__toggle {
  font-size: var(--fs-12);
  color: var(--c-accent);
  white-space: nowrap;
}

.frags {
  border-top: 1px solid var(--c-line);
}

.frag {
  padding: var(--sp-3) var(--sp-3) var(--sp-2);
}

.frag + .frag {
  border-top: 1px solid var(--c-line);
}

.frag__head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.frag__rank {
  min-width: 26px;
  font-size: var(--fs-11);
  color: var(--c-accent);
}

.frag__title {
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  max-width: 46%;
}

.frag__meta {
  font-size: var(--fs-11);
  color: var(--c-ink-3);
}

.frag__score {
  margin-left: auto;
  font-size: var(--fs-11);
  color: var(--c-ink-2);
}

.frag__snippet {
  margin: var(--sp-2) 0 0;
  padding-left: var(--sp-3);
  border-left: 2px solid var(--c-line-2);
  color: var(--c-ink-2);
  font-size: var(--fs-13);
  line-height: 1.7;
}

.frag__snippet.is-clamped {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.frag__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}

.frag__link {
  font-size: var(--fs-12);
  white-space: nowrap;
}

@media (max-width: 768px) {
  .trace__head {
    flex-wrap: wrap;
    gap: var(--sp-2);
  }

  .frag__title {
    max-width: 100%;
  }
}
</style>
