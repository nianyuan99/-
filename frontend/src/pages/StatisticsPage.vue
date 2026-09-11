<template>
  <div class="statistics-page">
    <a-card title="数据统计概览" :bordered="false">
      <template #extra>
        <a-button :loading="loading" @click="fetchData">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </template>

      <a-spin :spinning="loading">
        <!-- 核心指标 -->
        <a-row :gutter="[16, 16]">
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic title="测试任务" :value="overview.taskCount">
                <template #suffix>个</template>
              </a-statistic>
              <div class="stat-sub">
                已完成 {{ overview.completedTaskCount }} · 进行中 {{ overview.runningTaskCount }}
              </div>
            </a-card>
          </a-col>
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic title="测试结果" :value="overview.resultCount">
                <template #suffix>条</template>
              </a-statistic>
              <div class="stat-sub">每个子任务一条结果</div>
            </a-card>
          </a-col>
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic title="参与测试的模型" :value="overview.modelCount">
                <template #suffix>个</template>
              </a-statistic>
              <div class="stat-sub">可用场景 {{ overview.sceneCount }} 个</div>
            </a-card>
          </a-col>
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic title="累计 Token" :value="overview.totalTokens" />
              <div class="stat-sub">输入 + 输出</div>
            </a-card>
          </a-col>
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic title="累计花费" :value="overview.totalCost" :precision="6" prefix="$" />
              <div class="stat-sub">按模型价格实时计算</div>
            </a-card>
          </a-col>
          <a-col :xs="24" :sm="12" :md="8" :lg="4">
            <a-card size="small" class="stat-card">
              <a-statistic
                title="平均响应时间"
                :value="overview.avgResponseTimeMs ?? 0"
                suffix="ms"
              />
              <div class="stat-sub">全部测试结果的平均值</div>
            </a-card>
          </a-col>
        </a-row>

        <!-- 模型维度统计 -->
        <a-divider orientation="left">模型测试统计</a-divider>
        <a-table
          :columns="modelStatColumns"
          :data-source="overview.modelStats"
          row-key="modelName"
          :pagination="false"
          :locale="{ emptyText: '还没有测试结果，先去批量测试页跑一个任务吧' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'model'">
              <div class="model-name">{{ record.modelLabel || record.modelName }}</div>
              <div class="model-id">{{ record.modelName }}</div>
            </template>
            <template v-else-if="column.key === 'avgResponseTimeMs'">
              {{ record.avgResponseTimeMs ?? '-' }} ms
            </template>
            <template v-else-if="column.key === 'totalCost'">
              ${{ formatCost(record.totalCost) }}
            </template>
          </template>
        </a-table>

        <!-- 用户-模型使用统计 -->
        <a-divider orientation="left">我的模型使用情况</a-divider>
        <a-table
          :columns="usageColumns"
          :data-source="overview.modelUsage"
          row-key="modelName"
          :pagination="false"
          :locale="{ emptyText: '还没有调用记录' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'model'">
              <div class="model-name">{{ record.modelLabel || record.modelName }}</div>
              <div class="model-id">{{ record.modelName }}</div>
            </template>
            <template v-else-if="column.key === 'totalCost'">
              ${{ formatCost(record.totalCost) }}
            </template>
          </template>
        </a-table>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { getStatisticsOverview, type StatisticsOverviewVO } from '@/api/batchTest.ts'

const modelStatColumns = [
  { title: '模型', key: 'model' },
  { title: '调用次数', dataIndex: 'callCount', width: 120 },
  { title: 'Token 消耗', dataIndex: 'totalTokens', width: 140 },
  { title: '成本', key: 'totalCost', width: 140 },
  { title: '平均响应时间', key: 'avgResponseTimeMs', width: 150 },
]

const usageColumns = [
  { title: '模型', key: 'model' },
  { title: '累计 Token', dataIndex: 'totalTokens', width: 160 },
  { title: '累计花费', key: 'totalCost', width: 160 },
]

const overview = ref<StatisticsOverviewVO>({
  taskCount: 0,
  completedTaskCount: 0,
  runningTaskCount: 0,
  resultCount: 0,
  modelCount: 0,
  sceneCount: 0,
  totalTokens: 0,
  totalCost: 0,
  modelUsage: [],
  modelStats: [],
})

const loading = ref(false)

const fetchData = async () => {
  loading.value = true
  try {
    const res = await getStatisticsOverview()
    if (res.data.code === 0 && res.data.data) {
      overview.value = res.data.data
    } else {
      message.error('获取统计数据失败，' + res.data.message)
    }
  } finally {
    loading.value = false
  }
}

const formatCost = (cost?: number) => (cost === undefined || cost === null ? '0.000000' : cost.toFixed(6))

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.statistics-page {
  padding: 24px;
}

.stat-card {
  height: 100%;
}

.stat-sub {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

.model-name {
  font-weight: 500;
}

.model-id {
  font-size: 12px;
  color: #8c8c8c;
}
</style>
