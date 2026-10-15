<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AppShell from '@/components/AppShell.vue'

const route = useRoute()
const bare = computed(() => route.meta.layout === 'bare')
</script>

<template>
  <AppShell v-if="!bare">
    <RouterView />
  </AppShell>
  <RouterView v-else />
</template>
