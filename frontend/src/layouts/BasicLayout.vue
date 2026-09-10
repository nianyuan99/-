<template>
  <a-layout class="basic-layout">
    <!-- 顶部导航栏（全屏页面自带左侧栏，不显示全局导航） -->
    <GlobalHeader v-if="!route.meta.fullscreen" />
    <!-- 主要内容区域 -->
    <a-layout-content class="main-content">
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import GlobalHeader from '@/components/GlobalHeader.vue'

const route = useRoute()
</script>

<style scoped>
.basic-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.main-content {
  flex: 1;
  width: 100%;
  padding: 0;
  margin: 0;
}
</style>
