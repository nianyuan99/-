<template>
  <div class="home-page">
    <!-- 欢迎横幅 -->
    <div class="banner">
      <h1 class="banner-title">AI 大模型评测平台</h1>
      <p class="banner-subtitle">FastAPI + Vue 全栈项目初始化模板</p>
    </div>

    <div class="content-wrapper">
      <!-- 欢迎卡片 -->
      <a-card class="welcome-card" :bordered="false">
        <template #title>
          <span>👋 欢迎使用</span>
        </template>
        <p>欢迎来到 AI 大模型评测平台，前后端项目骨架搭建完成！</p>
      </a-card>

      <!-- 模板特性 -->
      <h2 class="features-title">模板特性</h2>
      <a-row :gutter="16" class="features-row">
        <a-col :span="8">
          <a-card class="feature-card" :bordered="false">
            <template #title>
              <span>👤 用户模块</span>
            </template>
            <p>完整的用户注册、登录、权限管理功能</p>
          </a-card>
        </a-col>
        <a-col :span="8">
          <a-card class="feature-card" :bordered="false">
            <template #title>
              <span>📄 接口文档</span>
            </template>
            <p>FastAPI 自动生成 Swagger 接口文档</p>
          </a-card>
        </a-col>
        <a-col :span="8">
          <a-card class="feature-card" :bordered="false">
            <template #title>
              <span>💾 数据持久化</span>
            </template>
            <p>SQLAlchemy + MySQL + Redis 数据存储</p>
          </a-card>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script setup lang="ts">
// 主页
</script>

<style scoped>
.home-page {
  padding-bottom: 24px;
}

.banner {
  text-align: center;
  padding: 56px 16px 40px;
}

.banner-title {
  font-size: 40px;
  font-weight: bold;
  color: #1677ff;
  margin: 0 0 12px;
}

.banner-subtitle {
  font-size: 16px;
  color: #888;
  margin: 0;
}

.content-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 16px;
}

.welcome-card {
  margin-bottom: 32px;
}

.features-title {
  text-align: center;
  font-size: 24px;
  margin: 0 0 24px;
}

.feature-card p {
  color: #666;
  margin: 0;
}
</style>
