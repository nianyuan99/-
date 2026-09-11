<template>
  <div class="model-manage-page">
    <a-card title="模型管理" :bordered="false">
      <template #extra>
        <a-space>
          <a-button :loading="loading" @click="fetchData">刷新</a-button>
          <a-tooltip v-if="!isAdmin" title="同步模型列表需要管理员权限">
            <a-button disabled>从 OpenRouter 同步</a-button>
          </a-tooltip>
          <a-popconfirm
            v-else
            title="将从 OpenRouter 拉取最新模型列表并更新价格，确定继续吗？"
            @confirm="handleSync"
          >
            <a-button type="primary" :loading="syncing">
              <template #icon><SyncOutlined /></template>
              从 OpenRouter 同步
            </a-button>
          </a-popconfirm>
        </a-space>
      </template>

      <!-- 筛选区域 -->
      <a-form layout="inline" :model="filterForm" class="filter-form">
        <a-form-item label="关键词">
          <a-input
            v-model:value="filterForm.keyword"
            placeholder="模型 ID / 名称"
            allow-clear
            style="width: 220px"
            @press-enter="handleSearch"
          />
        </a-form-item>
        <a-form-item label="地区">
          <a-select
            v-model:value="filterForm.isChina"
            placeholder="全部"
            allow-clear
            style="width: 140px"
          >
            <a-select-option :value="1">国内模型</a-select-option>
            <a-select-option :value="0">海外模型</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="推荐">
          <a-select
            v-model:value="filterForm.recommended"
            placeholder="全部"
            allow-clear
            style="width: 140px"
          >
            <a-select-option :value="1">仅推荐</a-select-option>
            <a-select-option :value="0">非推荐</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-button type="primary" @click="handleSearch">
            <template #icon><SearchOutlined /></template>
            搜索
          </a-button>
          <a-button style="margin-left: 8px" @click="handleReset">
            <template #icon><ReloadOutlined /></template>
            重置
          </a-button>
        </a-form-item>
      </a-form>

      <a-alert
        style="margin-bottom: 16px"
        type="info"
        show-icon
        message="模型列表由定时任务每天凌晨 2 点自动从 OpenRouter 同步；价格单位为「每百万 tokens 的美元价格」，批量测试的成本就是按这里的价格计算的。"
      />

      <a-table
        :columns="columns"
        :data-source="pagedModels"
        :loading="loading"
        row-key="id"
        :pagination="pagination"
        :scroll="{ x: 1200 }"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="model-name">{{ record.name }}</div>
            <div class="model-id">{{ record.id }}</div>
          </template>
          <template v-else-if="column.key === 'provider'">
            <a-tag>{{ record.provider || '-' }}</a-tag>
            <a-tag v-if="record.isChina" color="red">国内</a-tag>
            <a-tag v-if="record.recommended" color="gold">推荐</a-tag>
          </template>
          <template v-else-if="column.key === 'pricing'">
            <div>输入：${{ formatPrice(record.inputPrice) }}</div>
            <div>输出：${{ formatPrice(record.outputPrice) }}</div>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  ReloadOutlined,
  SearchOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'
import { listModels, syncModels, type ModelVO } from '@/api/model.ts'
import { useLoginUserStore } from '@/stores/loginUser.ts'

const loginUserStore = useLoginUserStore()
const isAdmin = computed(() => loginUserStore.loginUser.userRole === 'admin')

/** 每页条数：模型表默认展示 10 条，和用户管理页保持一致 */
const PAGE_SIZE = 10

const columns = [
  { title: '模型', key: 'name' },
  { title: '提供商 / 标记', key: 'provider', width: 220 },
  { title: '上下文长度', dataIndex: 'contextLength', width: 130 },
  { title: '价格（每百万 tokens）', key: 'pricing', width: 220 },
]

const models = ref<ModelVO[]>([])
const loading = ref(false)
const syncing = ref(false)
const paginationCurrent = ref(1)

const filterForm = reactive<{ keyword?: string; isChina?: number; recommended?: number }>({
  keyword: '',
  isChina: undefined,
  recommended: undefined,
})

const fetchData = async () => {
  loading.value = true
  try {
    const res = await listModels()
    if (res.data.code === 0) {
      models.value = res.data.data ?? []
    } else {
      message.error('获取模型列表失败，' + res.data.message)
    }
  } finally {
    loading.value = false
  }
}

/**
 * 前端筛选
 *
 * 后端 /model/list 支持 keyword / isChina / recommended 参数，
 * 但这里已经一次性把全量模型（上限 500）拉回来了，直接在本地过滤，
 * 输入框敲字时不必反复请求接口。
 */
const filteredModels = computed(() =>
  models.value.filter((model) => {
    const keyword = (filterForm.keyword ?? '').trim().toLowerCase()
    if (keyword) {
      const hit =
        model.id.toLowerCase().includes(keyword) || (model.name ?? '').toLowerCase().includes(keyword)
      if (!hit) {
        return false
      }
    }
    if (filterForm.isChina !== undefined && model.isChina !== filterForm.isChina) {
      return false
    }
    if (filterForm.recommended !== undefined && model.recommended !== filterForm.recommended) {
      return false
    }
    return true
  }),
)

const handleSearch = () => {
  // 过滤逻辑写在 filteredModels 里，这里只需把当前页拉回第 1 页，
  // 保持与其它页面「搜索」按钮一致的操作手感
  paginationCurrent.value = 1
}

const handleReset = () => {
  filterForm.keyword = ''
  filterForm.isChina = undefined
  filterForm.recommended = undefined
  paginationCurrent.value = 1
}

const handleSync = async () => {
  syncing.value = true
  try {
    const res = await syncModels()
    if (res.data.code === 0) {
      message.success(`同步完成，共同步 ${res.data.data} 个模型`)
      await fetchData()
    } else {
      message.error('同步失败，' + res.data.message)
    }
  } finally {
    syncing.value = false
  }
}

const formatPrice = (price?: number) =>
  price === undefined || price === null ? '-' : price.toFixed(6)

/** 分页后的表格数据：过滤结果在前端切片，避免一次渲染 359 个模型 */
const pagedModels = computed(() => {
  const start = (paginationCurrent.value - 1) * PAGE_SIZE
  return filteredModels.value.slice(start, start + PAGE_SIZE)
})

const pagination = computed(() => ({
  current: paginationCurrent.value,
  pageSize: PAGE_SIZE,
  total: filteredModels.value.length,
  showSizeChanger: false,
  showTotal: (value: number) => `共 ${value} 条`,
}))

const handleTableChange = (page: { current: number }) => {
  paginationCurrent.value = page.current
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.model-manage-page {
  padding: 24px;
}

.filter-form {
  margin-bottom: 16px;
  row-gap: 8px;
}

.model-name {
  font-weight: 500;
}

.model-id {
  font-size: 12px;
  color: #8c8c8c;
}
</style>
