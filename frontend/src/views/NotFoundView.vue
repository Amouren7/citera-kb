<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="nf">
    <span class="micro">404</span>
    <h1 class="nf__title">这个地址没有对应的页面</h1>
    <p class="nf__hint">
      可能是链接被改过，或者文档 / 会话已经被删除。可以从下面两个入口继续。
    </p>
    <div class="row row--gap">
      <RouterLink class="btn btn--primary btn--lg" to="/chat">回到问答</RouterLink>
      <RouterLink class="btn btn--lg" to="/documents">查看文档库</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.nf {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-4);
  min-height: 100dvh;
  justify-content: center;
  padding: var(--sp-9) var(--sp-8);
  max-width: 720px;
  margin: 0 auto;
}

.nf__title {
  font-size: var(--fs-34);
  letter-spacing: -0.02em;
}

.nf__hint {
  color: var(--c-ink-2);
  max-width: 46ch;
}

a.btn {
  border-bottom: 1px solid var(--c-line-2);
}

a.btn--primary {
  color: var(--c-accent-ink);
}
</style>
