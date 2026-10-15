<script setup lang="ts">
/**
 * 问答主界面（契约 §7.2 全量）：
 * 会话列表 + 消息流 + 流式（fetch/ReadableStream）+ 停止生成 + 命中片段卡片 + [[cN]] 角标。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentsApi, errorMessage, type DocumentItem, type RetrievalMode } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import MessageBody from '@/components/MessageBody.vue'
import RetrievalTrace from '@/components/RetrievalTrace.vue'
import { useIsCompact } from '@/composables/useMediaQuery'
import { useChatStore } from '@/stores/chat'
import { formatRelative, truncate } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const isCompact = useIsCompact()

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const composer = ref<HTMLTextAreaElement | null>(null)
const drawerOpen = ref(false)

const scopeDocuments = ref<DocumentItem[]>([])
const suggestions = [
  '整机保修期是多久？需要提供什么凭证？',
  '七天无理由退货的商品需要保持什么状态？',
  '普通工单的首次响应时限是多少小时？',
]

const modeOptions: Array<{ value: RetrievalMode; label: string }> = [
  { value: 'hybrid', label: '混合检索 RRF' },
  { value: 'vector', label: '向量检索' },
  { value: 'keyword', label: '关键词检索' },
]

const activeTitle = computed(() => chat.activeConversation?.title ?? '新会话')
const readyDocuments = computed(() => scopeDocuments.value.filter((doc) => doc.status === 'ready'))
const canSend = computed(() => draft.value.trim().length > 0 && !chat.streaming)
const showEmptyConversation = computed(
  () => chat.messages.length === 0 && !chat.streaming && chat.messagesStatus !== 'loading',
)

function scrollToBottom(): void {
  void nextTick(() => {
    const element = scroller.value
    if (element) element.scrollTop = element.scrollHeight
  })
}

function onComposerKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  void submit()
}

async function submit(): Promise<void> {
  const content = draft.value.trim()
  if (!content || chat.streaming) return
  draft.value = ''
  await chat.send(content)
  const id = chat.activeId
  if (id && Number(route.params.conversationId) !== id) {
    void router.replace({ name: 'chat', params: { conversationId: String(id) } })
  }
  scrollToBottom()
}

function useSuggestion(text: string): void {
  draft.value = text
  composer.value?.focus()
}

async function newConversation(): Promise<void> {
  chat.startNewConversation()
  drawerOpen.value = false
  void router.replace({ name: 'chat' })
  draft.value = ''
  await nextTick()
  composer.value?.focus()
}

async function selectConversation(id: number): Promise<void> {
  drawerOpen.value = false
  if (chat.activeId === id) return
  await router.push({ name: 'chat', params: { conversationId: String(id) } })
}

async function renameConversation(id: number, current: string): Promise<void> {
  try {
    const result = await ElMessageBox.prompt('新的会话标题', '重命名会话', {
      inputValue: current,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (value) => (value && value.trim().length > 0 ? true : '标题不能为空'),
    })
    const ok = await chat.renameConversation(id, result.value.trim())
    if (ok) ElMessage.success('标题已更新')
  } catch {
    /* 用户取消 */
  }
}

async function removeConversation(id: number, title: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`删除会话《${truncate(title, 20)}》？聊天记录将不再显示。`, '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  const ok = await chat.removeConversation(id)
  if (ok) {
    ElMessage.success('已删除')
    if (chat.activeId === null) void router.replace({ name: 'chat' })
  }
}

async function loadScope(): Promise<void> {
  try {
    const page = await documentsApi.list({ page: 1, page_size: 100, sort: '-created_at' })
    scopeDocuments.value = page.items
  } catch {
    scopeDocuments.value = []
  }
}

watch(
  () => route.params.conversationId,
  async (value) => {
    const id = Number(value)
    if (!Number.isFinite(id) || id <= 0) {
      if (chat.activeId !== null && route.name === 'chat' && !route.params.conversationId) return
      chat.startNewConversation()
      return
    }
    if (chat.activeId === id && chat.messages.length > 0) return
    await chat.openConversation(id)
    scrollToBottom()
  },
)

watch(() => chat.messages.length, scrollToBottom)
watch(() => chat.streamText, scrollToBottom)
watch(
  () => chat.messagesStatus,
  (value) => {
    if (value === 'ready') scrollToBottom()
  },
)

onMounted(async () => {
  await Promise.all([chat.fetchConversations(), loadScope()])
  const id = Number(route.params.conversationId)
  if (Number.isFinite(id) && id > 0) {
    await chat.openConversation(id)
  }
  const docScope = Number(route.query.doc)
  if (Number.isFinite(docScope) && docScope > 0) {
    chat.setOptions({ documentIds: [docScope] })
  }
  scrollToBottom()
})
</script>

<template>
  <div class="chat" :class="{ 'is-compact': isCompact }">
    <!-- 会话列表（窄屏走抽屉） -->
    <aside v-if="!isCompact" class="convs">
      <header class="convs__head">
        <span class="micro">会话</span>
        <button class="btn btn--sm" type="button" @click="newConversation()">新建</button>
      </header>

      <div v-if="chat.conversationsStatus === 'loading'" class="convs__body">
        <span v-for="index in 5" :key="index" class="skel skel-line" style="width: 100%" />
      </div>

      <ErrorState
        v-else-if="chat.conversationsStatus === 'error'"
        :error="chat.listError"
        title="会话列表加载失败"
        @retry="chat.fetchConversations()"
      />

      <EmptyState
        v-else-if="chat.conversations.length === 0"
        title="还没有会话"
        hint="新建一个会话，或直接在右侧提问会自动创建。"
        action-label="新建会话"
        @action="newConversation()"
      />

      <ul v-else class="convlist">
        <li
          v-for="conversation in chat.sortedConversations"
          :key="conversation.id"
          class="convitem"
          :class="{ 'is-active': chat.activeId === conversation.id }"
        >
          <button class="convitem__main" type="button" @click="selectConversation(conversation.id)">
            <span class="convitem__title truncate">{{ conversation.title }}</span>
            <span class="convitem__meta num">
              {{ conversation.message_count ?? 0 }} 条 ·
              {{ formatRelative(conversation.last_message_at ?? conversation.updated_at) }}
            </span>
          </button>
          <div class="convitem__actions">
            <button class="iconbtn" type="button" title="重命名" @click="renameConversation(conversation.id, conversation.title)">
              改名
            </button>
            <button class="iconbtn iconbtn--danger" type="button" title="删除" @click="removeConversation(conversation.id, conversation.title)">
              删除
            </button>
          </div>
        </li>
      </ul>
    </aside>

    <!-- 消息流 -->
    <section class="stream">
      <header class="stream__head">
        <div class="row row--gap">
          <button v-if="isCompact" class="btn btn--sm" type="button" @click="drawerOpen = true">会话</button>
          <div class="stack">
            <span class="micro">当前会话</span>
            <strong class="stream__title truncate">{{ activeTitle }}</strong>
          </div>
        </div>
        <div class="row row--gap stream__options">
          <label class="field field--inline">
            <span class="micro">检索</span>
            <select
              class="select select--sm"
              :value="chat.options.retrievalMode"
              @change="chat.setOptions({ retrievalMode: ($event.target as HTMLSelectElement).value as RetrievalMode })"
            >
              <option v-for="option in modeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="field field--inline">
            <span class="micro">top_k</span>
            <input
              class="input input--sm"
              type="number"
              min="1"
              max="10"
              :value="chat.options.topK"
              @change="chat.setOptions({ topK: Math.min(10, Math.max(1, Number(($event.target as HTMLInputElement).value) || 5)) })"
            />
          </label>
          <label class="field field--inline stream__scope">
            <span class="micro">范围</span>
            <el-select
              :model-value="chat.options.documentIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="全部文档"
              size="small"
              :disabled="readyDocuments.length === 0"
              @update:model-value="(value: number[]) => chat.setOptions({ documentIds: value })"
            >
              <el-option v-for="doc in readyDocuments" :key="doc.id" :label="doc.title" :value="doc.id" />
            </el-select>
          </label>
        </div>
      </header>

      <div ref="scroller" class="messages">
        <div v-if="chat.messagesStatus === 'loading'" class="stack stack--gap">
          <span class="skel" style="width: 55%; height: 64px" />
          <span class="skel" style="width: 100%; height: 140px" />
        </div>

        <ErrorState
          v-else-if="chat.messagesStatus === 'error'"
          :error="chat.detailError"
          title="会话加载失败"
          @retry="chat.activeId && chat.openConversation(chat.activeId)"
        />

        <EmptyState
          v-else-if="showEmptyConversation"
          title="问一个文档里能查到答案的问题"
          hint="回答会逐句标注来源，点角标就能看到命中的文档、章节与块序号。也可以先缩小检索范围，只用某几份文档。"
        >
        </EmptyState>

        <template v-else>
          <article v-for="message in chat.messages" :key="message.id" class="msg" :class="`msg--${message.role}`">
            <div class="msg__head">
              <span class="msg__role micro">{{ message.role === 'user' ? '提问' : '回答' }}</span>
              <span v-if="message.latency_ms" class="msg__meta num">{{ message.latency_ms }} ms</span>
              <span class="msg__meta num">{{ formatRelative(message.created_at) }}</span>
            </div>

            <RetrievalTrace
              v-if="message.role === 'assistant' && message.citations.length > 0"
              :citations="message.citations"
              :mode="message.citations[0]?.retrieval"
              class="msg__trace"
            />

            <MessageBody :content="message.content" :citations="message.citations" />
          </article>

          <!-- 流式中的回答 -->
          <article v-if="chat.streaming || chat.streamText" class="msg msg--assistant">
            <div class="msg__head">
              <span class="msg__role micro">回答</span>
              <span v-if="chat.streaming" class="msg__meta"><i class="dot dot--pulse" /> 生成中</span>
              <span v-if="chat.streamMeta" class="msg__meta num">
                {{ chat.streamMeta.retrieval_mode }} · top_k {{ chat.streamMeta.top_k }}
              </span>
            </div>

            <RetrievalTrace
              v-if="chat.streamCitations.length > 0"
              :citations="chat.streamCitations"
              :elapsed-ms="chat.streamElapsedMs"
              :mode="chat.streamMeta?.retrieval_mode"
              :default-expanded="true"
              class="msg__trace"
            />

            <div v-if="chat.streamText" class="msg__pending">
              <MessageBody :content="chat.streamText" :citations="chat.streamCitations" streaming />
            </div>
            <div v-else-if="chat.streaming" class="stack stack--gap">
              <span class="skel skel-line" style="width: 80%" />
              <span class="skel skel-line" style="width: 62%" />
              <span class="skel skel-line" style="width: 44%" />
            </div>
          </article>
        </template>

        <div v-if="chat.streamError" class="errbox" role="alert">
          <div class="stack stack--gap grow">
            <span class="errbox__code">{{ chat.streamError.code }}</span>
            <strong>生成中断</strong>
            <span>{{ chat.streamError.message }}</span>
          </div>
        </div>

        <ErrorState
          v-if="chat.sendError"
          :error="chat.sendError"
          title="提问失败"
          @retry="submit()"
        />
      </div>

      <!-- 输入区 -->
      <footer class="composer">
        <div class="composer__box">
          <textarea
            ref="composer"
            v-model="draft"
            class="composer__input"
            rows="2"
            placeholder="Enter 发送，Shift+Enter 换行"
            :disabled="chat.streaming"
            @keydown="onComposerKeydown"
          />
          <div class="composer__actions">
            <span class="micro composer__count num">{{ draft.length }} 字</span>
            <button
              v-if="chat.streaming"
              class="btn btn--danger"
              type="button"
              @click="chat.stop()"
            >
              停止生成
            </button>
            <button v-else class="btn btn--primary" type="button" :disabled="!canSend" @click="submit()">
              发送
            </button>
          </div>
        </div>
        <div v-if="showEmptyConversation" class="composer__suggestions">
          <span class="micro">可以这样问</span>
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            class="suggestionbtn"
            type="button"
            @click="useSuggestion(suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </footer>
    </section>

    <!-- 窄屏会话抽屉 -->
    <el-drawer v-model="drawerOpen" title="会话" direction="ltr" size="82%">
      <div class="stack stack--gap">
        <button class="btn btn--primary btn--block" type="button" @click="newConversation()">新建会话</button>
        <ul class="convlist">
          <li
            v-for="conversation in chat.sortedConversations"
            :key="conversation.id"
            class="convitem"
            :class="{ 'is-active': chat.activeId === conversation.id }"
          >
            <button class="convitem__main" type="button" @click="selectConversation(conversation.id)">
              <span class="convitem__title truncate">{{ conversation.title }}</span>
              <span class="convitem__meta num">
                {{ conversation.message_count ?? 0 }} 条 · {{ formatRelative(conversation.last_message_at ?? conversation.updated_at) }}
              </span>
            </button>
            <div class="convitem__actions">
              <button class="iconbtn" type="button" @click="renameConversation(conversation.id, conversation.title)">改名</button>
              <button class="iconbtn iconbtn--danger" type="button" @click="removeConversation(conversation.id, conversation.title)">
                删除
              </button>
            </div>
          </li>
        </ul>
        <p v-if="chat.conversations.length === 0" class="dim">还没有会话。</p>
      </div>
    </el-drawer>

    <p v-if="false" class="sr-only">{{ errorMessage(null) }}</p>
  </div>
</template>

<style scoped>
.chat {
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
  gap: var(--sp-5);
  height: calc(100dvh - var(--topbar-h) - var(--sp-5) * 2);
  min-height: 520px;
}

.chat.is-compact {
  grid-template-columns: minmax(0, 1fr);
}

/* ----------------------------- 会话列表 ----------------------------- */
.convs {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.convs__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--c-line);
  min-height: 44px;
}

.convs__body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-3);
}

.convlist {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-height: 0;
}

.convitem {
  display: flex;
  align-items: stretch;
  gap: var(--sp-1);
  border-bottom: 1px solid var(--c-line);
  border-left: 2px solid transparent;
}

.convitem.is-active {
  border-left-color: var(--c-accent);
  background: var(--c-accent-wash);
}

.convitem__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
  padding: var(--sp-2) var(--sp-3);
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.convitem__main:hover {
  background: var(--c-sunken);
}

.convitem.is-active .convitem__main:hover {
  background: transparent;
}

.convitem__title {
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
}

.convitem__meta {
  font-size: var(--fs-11);
  color: var(--c-ink-3);
}

.convitem__actions {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding-right: var(--sp-2);
  opacity: 0;
  transition: opacity var(--dur-1) var(--ease);
}

.convitem:hover .convitem__actions,
.convitem:focus-within .convitem__actions {
  opacity: 1;
}

.iconbtn {
  border: 0;
  background: transparent;
  color: var(--c-ink-3);
  font-size: var(--fs-11);
  cursor: pointer;
  padding: 1px 2px;
}

.iconbtn:hover {
  color: var(--c-accent);
}

.iconbtn--danger:hover {
  color: var(--c-err);
}

/* ------------------------------ 消息流 ------------------------------ */
.stream {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.stream__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid var(--c-line);
  min-height: 52px;
  flex-wrap: wrap;
}

.stream__title {
  font-size: var(--fs-14);
  max-width: 42ch;
}

.stream__options {
  flex-wrap: wrap;
}

.field--inline {
  flex-direction: row;
  align-items: center;
  gap: var(--sp-2);
}

.select--sm,
.input--sm {
  height: 28px;
  min-height: 28px;
  padding: 2px var(--sp-2);
  font-size: var(--fs-12);
}

.input--sm {
  width: 64px;
}

.stream__scope {
  min-width: 190px;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: var(--sp-4) var(--sp-4) var(--sp-5);
}

.msg {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 92ch;
}

.msg--user {
  align-self: flex-end;
  max-width: 76ch;
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--c-line);
  border-left: 2px solid var(--c-ink-3);
  background: var(--c-sunken);
}

.msg--assistant {
  align-self: flex-start;
  width: 100%;
}

.msg__head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.msg__role {
  color: var(--c-ink-3);
}

.msg--assistant .msg__role {
  color: var(--c-accent);
}

.msg__meta {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-11);
  color: var(--c-ink-3);
}

.msg__trace {
  margin-bottom: var(--sp-1);
}

.msg__pending {
  position: relative;
}

/* ------------------------------ 输入区 ------------------------------ */
.composer {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
  border-top: 1px solid var(--c-line);
  background: var(--c-surface);
}

.composer__box {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-3);
  padding: var(--sp-2);
  border: 1px solid var(--c-line-2);
  background: var(--c-surface);
  transition: border-color var(--dur-1) var(--ease), box-shadow var(--dur-1) var(--ease);
}

.composer__box:focus-within {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-wash);
}

.composer__input {
  flex: 1 1 auto;
  min-height: 46px;
  max-height: 180px;
  padding: var(--sp-2);
  border: 0;
  background: transparent;
  resize: vertical;
  font-size: var(--fs-14);
  line-height: 1.6;
}

.composer__input:focus {
  outline: none;
}

.composer__actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding-bottom: 2px;
}

.composer__count {
  white-space: nowrap;
}

.composer__suggestions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.suggestionbtn {
  padding: 3px var(--sp-2);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
  color: var(--c-ink-2);
  font-size: var(--fs-12);
  cursor: pointer;
  text-align: left;
}

.suggestionbtn:hover {
  border-color: var(--c-accent-line);
  color: var(--c-accent);
  background: var(--c-accent-wash);
}

/* ------------------------------ 响应式 ------------------------------ */
@media (max-width: 1024px) {
  .chat {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .stream__scope {
    min-width: 150px;
  }
}

@media (max-width: 768px) {
  .chat {
    height: auto;
    min-height: calc(100dvh - 220px);
  }

  .stream__head {
    align-items: flex-start;
  }

  .stream__options {
    width: 100%;
  }

  .stream__scope {
    flex: 1 1 100%;
  }

  .messages {
    padding: var(--sp-3);
  }

  .msg--user {
    max-width: 100%;
  }
}
</style>
