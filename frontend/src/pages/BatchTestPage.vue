<template>
  <div class="batch-test-page">
    <!-- 创建批量测试任务 -->
    <a-card title="创建批量测试任务" :bordered="false">
      <a-form :model="form" :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
        <a-form-item label="任务名称" name="name">
          <a-input v-model:value="form.name" placeholder="请输入任务名称（可选）" />
        </a-form-item>
        <a-form-item label="选择场景" name="sceneId">
          <a-select
            v-model:value="form.sceneId"
            placeholder="请选择测试场景"
            :loading="loadingScenes"
            @change="handleSceneChange"
          >
            <a-select-option v-for="scene in scenes" :key="scene.id" :value="scene.id">
              {{ scene.name }}
              <span v-if="scene.promptCount" style="color: #999">
                （{{ scene.promptCount }} 条提示词）
              </span>
            </a-select-option>
          </a-select>
          <div v-if="currentScene" class="scene-hint">
            <a-typography-text type="secondary">
              {{ currentScene.description || '暂无场景描述' }} · 预计调用
              {{ (form.models.length || 0) * (currentScene.promptCount || 0) }} 次
            </a-typography-text>
          </div>
        </a-form-item>
        <a-form-item label="选择模型" name="models">
          <!--
            模型下拉的两个关键属性
            optionFilterProp="value"：按模型 ID 过滤（如 nemotron-3-ultra、deepseek/deepseek-chat），
              用户通常记得的是模型 ID；用默认的 label（"NVIDIA: Nemotron 3 Ultra (free)"）过滤时，
              输入 ID 会一条都搜不到，直接显示 "No data"。
            optionLabelProp="label"：选中后标签只显示模型名称，
              否则会把下拉里的「名称 + ID」整块内容塞进标签，撑得很长。
          -->
          <a-select
            v-model:value="form.models"
            mode="multiple"
            placeholder="请选择要测试的模型（可多选）"
            :loading="loadingModels"
            :max-tag-count="6"
            option-filter-prop="value"
            option-label-prop="label"
            show-search
          >
            <a-select-option
              v-for="model in modelOptions"
              :key="model.value"
              :value="model.value"
              :label="model.label"
            >
              <div class="model-option">
                <span>{{ model.label }}</span>
                <span class="model-option-id">{{ model.value }}</span>
              </div>
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-divider>高级参数配置（可选）</a-divider>
        <a-form-item label="Temperature" name="temperature">
          <a-input-number
            v-model:value="form.temperature"
            :min="0"
            :max="2"
            :step="0.1"
            placeholder="0.7"
          />
        </a-form-item>
        <a-form-item label="最大 Token" name="maxTokens">
          <a-input-number
            v-model:value="form.maxTokens"
            :min="128"
            :max="8192"
            :step="128"
            placeholder="2000"
          />
        </a-form-item>
        <a-form-item label="启用 AI 评分" name="enableAiScoring">
          <a-checkbox v-model:checked="form.enableAiScoring">
            让多个 AI 评委给每条回答交叉打分（会增加耗时与费用）
          </a-checkbox>
        </a-form-item>
        <a-form-item :wrapper-col="{ offset: 6, span: 18 }">
          <a-button type="primary" :loading="creating" @click="handleCreate">
            创建测试任务
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 任务进度监控 -->
    <a-card v-if="currentTask" title="任务进度" :bordered="false" style="margin-top: 16px">
      <template #extra>
        <a-space>
          <a-tag :color="statusColor(currentTask.status)">
            {{ statusLabel(currentTask.status) }}
          </a-tag>
          <a-button
            v-if="currentTask.status === 'running' || currentTask.status === 'pending'"
            danger
            size="small"
            :loading="cancelling"
            @click="handleCancelTask"
          >
            取消任务
          </a-button>
        </a-space>
      </template>

      <a-progress
        :percent="progressPercentage"
        :status="currentTask.status === 'failed' ? 'exception' : 'active'"
      />

      <a-row :gutter="16" style="margin-top: 16px">
        <a-col :span="8">
          <a-statistic
            title="已完成 / 总数"
            :value="`${currentTask.completedSubtasks} / ${currentTask.totalSubtasks}`"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic title="连接状态" :value="wsConnected ? '已连接' : '未连接'" />
        </a-col>
        <a-col :span="8">
          <a-statistic title="任务状态" :value="statusLabel(currentTask.status)" />
        </a-col>
      </a-row>

      <div v-if="progressInfo.currentModel" style="margin-top: 16px">
        <a-typography-text type="secondary">
          当前测试: {{ progressInfo.currentModel }} - {{ progressInfo.currentPrompt || '—' }}
          <span v-if="progressInfo.success === false" style="color: #ff4d4f">
            （该子任务失败：{{ progressInfo.errorMessage || '未知原因' }}）
          </span>
        </a-typography-text>
      </div>

      <div style="margin-top: 16px">
        <a-button style="margin-left: 8px" @click="handleViewDetail"> 查看详情 </a-button>
        <a-button
          v-if="currentTask && currentTask.status === 'completed'"
          type="primary"
          style="margin-left: 8px"
          @click="handleViewReport"
        >
          查看报告
        </a-button>
        <a-button style="margin-left: 8px" @click="handleBackToList"> 返回列表 </a-button>
      </div>
    </a-card>

    <!-- 测试结果 -->
    <a-card v-if="showReport && currentTask" title="测试结果" :bordered="false" style="margin-top: 16px">
      <template #extra>
        <a-space>
          <a-select
            v-model:value="filterModel"
            placeholder="按模型筛选"
            allow-clear
            style="width: 220px"
            @change="fetchResults"
          >
            <a-select-option v-for="model in currentTask.models" :key="model" :value="model">
              {{ model }}
            </a-select-option>
          </a-select>
          <a-button :loading="loadingResults" @click="fetchResults">刷新</a-button>
        </a-space>
      </template>

      <a-table
        :columns="resultColumns"
        :data-source="results"
        :loading="loadingResults"
        row-key="id"
        :pagination="{ pageSize: 10, showSizeChanger: true }"
        :scroll="{ x: 1500 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'modelName'">
            <a-tag color="blue">{{ record.modelName }}</a-tag>
          </template>
          <template v-else-if="column.key === 'outputText'">
            <a-typography-paragraph
              :content="record.outputText"
              :ellipsis="{ rows: 2, expandable: true, symbol: '展开' }"
              style="max-width: 360px; margin-bottom: 0"
            />
          </template>
          <template v-else-if="column.key === 'metrics'">
            <div class="metrics-cell">
              <div>耗时：{{ record.responseTimeMs ?? '-' }} ms</div>
              <div>
                Token：{{ record.inputTokens ?? 0 }} / {{ record.outputTokens ?? 0 }}
              </div>
              <div>成本：${{ formatCost(record.cost) }}</div>
            </div>
          </template>
          <template v-else-if="column.key === 'reasoning'">
            <a-typography-paragraph
              v-if="record.reasoning"
              :content="record.reasoning"
              :ellipsis="{ rows: 2, expandable: true, symbol: '展开' }"
              style="max-width: 240px; margin-bottom: 0"
            />
            <span v-else style="color: #999">-</span>
          </template>
          <template v-else-if="column.key === 'userRating'">
            <a-rate
              :value="record.userRating || 0"
              :count="5"
              @change="(value: number) => handleRate(record, value)"
            />
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" size="small" @click="handleShowDetail(record)">查看全部</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 我的任务列表 -->
    <a-card title="我的测试任务" :bordered="false" style="margin-top: 16px">
      <template #extra>
        <a-button :loading="loadingTasks" @click="fetchTasks">刷新</a-button>
      </template>
      <a-table
        :columns="taskColumns"
        :data-source="tasks"
        :loading="loadingTasks"
        row-key="id"
        :pagination="taskPagination"
        @change="handleTaskTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'progress'">
            {{ record.completedSubtasks }} / {{ record.totalSubtasks }}
          </template>
          <template v-else-if="column.key === 'models'">
            <a-tag v-for="model in record.models" :key="model" style="margin-bottom: 4px">
              {{ model }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'createTime'">
            {{ dayjs(record.createTime).format('YYYY-MM-DD HH:mm:ss') }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="handleOpenTask(record)">
                查看进度
              </a-button>
              <a-popconfirm title="确定要删除这个任务吗？" @confirm="handleDeleteTask(record.id)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 结果详情 -->
    <a-modal
      v-model:open="detailVisible"
      title="测试结果详情"
      width="800px"
      :footer="null"
      @cancel="detailVisible = false"
    >
      <template v-if="detailRecord">
        <a-descriptions :column="2" bordered size="small">
          <a-descriptions-item label="模型">{{ detailRecord.modelName }}</a-descriptions-item>
          <a-descriptions-item label="提示词">{{ detailRecord.promptTitle || '-' }}</a-descriptions-item>
          <a-descriptions-item label="响应时间">
            {{ detailRecord.responseTimeMs ?? '-' }} ms
          </a-descriptions-item>
          <a-descriptions-item label="Token">
            {{ detailRecord.inputTokens ?? 0 }} / {{ detailRecord.outputTokens ?? 0 }}
          </a-descriptions-item>
          <a-descriptions-item label="成本">${{ formatCost(detailRecord.cost) }}</a-descriptions-item>
          <a-descriptions-item label="时间">
            {{ dayjs(detailRecord.createTime).format('YYYY-MM-DD HH:mm:ss') }}
          </a-descriptions-item>
        </a-descriptions>

        <a-divider orientation="left">输入提示词</a-divider>
        <pre class="detail-block">{{ detailRecord.inputPrompt }}</pre>

        <a-divider orientation="left">输出内容</a-divider>
        <pre class="detail-block">{{ detailRecord.outputText }}</pre>

        <template v-if="detailRecord.reasoning">
          <a-divider orientation="left">思考过程</a-divider>
          <pre class="detail-block reason-block">{{ detailRecord.reasoning }}</pre>
        </template>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { listModels, type ModelVO } from '@/api/model.ts'
import { listAvailableScenes, type SceneVO } from '@/api/scene.ts'
import {
  cancelBatchTestTask,
  createBatchTestTask,
  deleteBatchTestTask,
  getBatchTestTask,
  listBatchTestResult,
  listBatchTestTaskByPage,
  updateBatchTestResultRating,
  type TaskProgressMessage,
  type TaskStatus,
  type TestResultVO,
  type TestTaskVO,
} from '@/api/batchTest.ts'
import { WebSocketClient } from '@/utils/websocketClient.ts'

/**
 * 结果表格列
 *
 * 提示词列用 promptTitle + promptIndex，后端已经把场景提示词的标题 join 回来，
 * 这样同一任务下不同模型的回答可以按提示词横向对比。
 */
const resultColumns = [
  { title: '#', dataIndex: 'promptIndex', width: 60 },
  { title: '提示词', dataIndex: 'promptTitle', width: 160 },
  { title: '模型', key: 'modelName', width: 200 },
  { title: '输出内容', key: 'outputText' },
  { title: '思考过程', key: 'reasoning' },
  { title: '指标', key: 'metrics', width: 200 },
  { title: '我的评分', key: 'userRating', width: 160 },
  { title: '操作', key: 'action', width: 100 },
]

const taskColumns = [
  { title: '任务名称', dataIndex: 'name' },
  { title: '场景', dataIndex: 'sceneName', width: 160 },
  { title: '模型', key: 'models', width: 260 },
  { title: '进度', key: 'progress', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '创建时间', key: 'createTime', width: 180 },
  { title: '操作', key: 'action', width: 170 },
]

// ============ 创建任务表单 ============

const scenes = ref<SceneVO[]>([])
const models = ref<ModelVO[]>([])
const loadingScenes = ref(false)
const loadingModels = ref(false)
const creating = ref(false)

const router = useRouter()

const form = reactive<{
  name?: string
  sceneId?: string
  models: string[]
  temperature?: number
  maxTokens?: number
  enableAiScoring?: boolean
}>({
  name: '',
  sceneId: undefined,
  models: [],
  temperature: 0.7,
  maxTokens: 2000,
  enableAiScoring: false,
})

const modelOptions = computed(() =>
  models.value.map((model) => ({
    value: model.id,
    label: `${model.name}${model.isChina ? '（国内）' : ''}`,
  })),
)

const currentScene = computed(() => scenes.value.find((scene) => scene.id === form.sceneId))

const fetchScenes = async () => {
  loadingScenes.value = true
  try {
    const res = await listAvailableScenes()
    if (res.data.code === 0) {
      scenes.value = res.data.data ?? []
    } else {
      message.error('获取场景列表失败，' + res.data.message)
    }
  } finally {
    loadingScenes.value = false
  }
}

const fetchModels = async () => {
  loadingModels.value = true
  try {
    const res = await listModels()
    if (res.data.code === 0) {
      models.value = res.data.data ?? []
    } else {
      message.error('获取模型列表失败，' + res.data.message)
    }
  } finally {
    loadingModels.value = false
  }
}

const handleSceneChange = () => {
  // 换场景后清空上一次的进度展示，避免误读成新任务的进度
  if (!currentTask.value) {
    progressInfo.value = { currentModel: '', currentPrompt: '' }
  }
}

// ============ 任务进度（WebSocket） ============

const currentTask = ref<TestTaskVO | null>(null)
const progressPercentage = ref(0)
const progressInfo = ref<{ currentModel?: string; currentPrompt?: string; success?: boolean; errorMessage?: string }>(
  { currentModel: '', currentPrompt: '' },
)
const wsConnected = ref(false)
const cancelling = ref(false)

let wsClient: WebSocketClient | null = null
let pollTimer: number | null = null

const subscribeTask = (taskId: string) => {
  // 每个任务单独建一条连接，切换任务时先把旧连接断开，避免订阅串台
  wsClient?.disconnect()
  wsConnected.value = false

  wsClient = new WebSocketClient(undefined, {
    onConnect: () => {
      wsConnected.value = true
      wsClient?.subscribe(`/topic/task/${taskId}`)
    },
    onDisconnect: () => {
      wsConnected.value = false
    },
    onError: (error) => {
      console.warn('WebSocket 错误:', error)
    },
    onMessage: (_topic, body) => {
      const message = body as TaskProgressMessage
      if (!message || message.taskId !== taskId) {
        return
      }
      applyProgress(message)
    },
  })
  wsClient.connect()

  // 兜底轮询：WebSocket 建连失败或不支持时，进度仍然能往前走
  startPolling(taskId)
}

/**
 * 应用一条进度消息
 *
 * 后端在任务开始时也会推一条 pending 消息，这里统一更新任务快照，
 * 保证「进度条 / 已完成数 / 当前测试对象」三者始终来自同一份数据。
 */
const applyProgress = (message: TaskProgressMessage) => {
  if (!currentTask.value || currentTask.value.id !== message.taskId) {
    return
  }
  currentTask.value = {
    ...currentTask.value,
    status: message.status ?? currentTask.value.status,
    totalSubtasks: message.totalSubtasks ?? currentTask.value.totalSubtasks,
    completedSubtasks: message.completedSubtasks ?? currentTask.value.completedSubtasks,
  }
  progressPercentage.value = message.percentage ?? 0
  progressInfo.value = {
    currentModel: message.currentModel ?? message.modelName,
    currentPrompt: message.currentPrompt ?? message.promptTitle,
    success: message.success,
    errorMessage: message.errorMessage,
  }

  if (message.status === 'completed' || message.status === 'failed' || message.status === 'cancelled') {
    stopPolling()
    fetchResults()
    fetchTasks()
  }
}

const startPolling = (taskId: string) => {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    const res = await getBatchTestTask(taskId)
    if (res.data.code !== 0 || !res.data.data) {
      return
    }
    const task = res.data.data
    if (!currentTask.value || currentTask.value.id !== task.id) {
      return
    }
    currentTask.value = task
    progressPercentage.value =
      task.totalSubtasks > 0 ? Math.floor((task.completedSubtasks / task.totalSubtasks) * 100) : 0
    if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') {
      stopPolling()
      fetchResults()
      fetchTasks()
    }
  }, 5000)
}

const stopPolling = () => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

const handleCreate = async () => {
  if (!form.sceneId) {
    message.warning('请选择测试场景')
    return
  }
  if (!form.models.length) {
    message.warning('请至少选择一个模型')
    return
  }

  creating.value = true
  try {
    const res = await createBatchTestTask({
      name: form.name,
      sceneId: form.sceneId,
      models: form.models,
      temperature: form.temperature,
      maxTokens: form.maxTokens,
      enableAiScoring: form.enableAiScoring,
    })
    if (res.data.code !== 0 || !res.data.data) {
      message.error('创建任务失败，' + res.data.message)
      return
    }

    const taskId = res.data.data
    message.success('任务创建成功，正在执行测试')
    showReport.value = false
    results.value = []
    progressPercentage.value = 0
    progressInfo.value = { currentModel: '', currentPrompt: '' }

    const detail = await getBatchTestTask(taskId)
    if (detail.data.code === 0 && detail.data.data) {
      currentTask.value = detail.data.data
    } else {
      // 详情拿不到时先放一个占位任务，保证进度卡片可见，随后由推送/轮询补齐
      currentTask.value = {
        id: taskId,
        name: form.name,
        sceneId: form.sceneId,
        models: [...form.models],
        status: 'pending',
        totalSubtasks: (currentScene.value?.promptCount ?? 0) * form.models.length,
        completedSubtasks: 0,
        createTime: dayjs().toISOString(),
        updateTime: dayjs().toISOString(),
      }
    }
    subscribeTask(taskId)
    fetchTasks()
  } finally {
    creating.value = false
  }
}

const handleCancelTask = async () => {
  if (!currentTask.value) {
    return
  }
  cancelling.value = true
  try {
    const res = await cancelBatchTestTask(currentTask.value.id)
    if (res.data.code === 0) {
      message.success('任务已取消')
      const detail = await getBatchTestTask(currentTask.value.id)
      if (detail.data.code === 0 && detail.data.data) {
        currentTask.value = detail.data.data
      }
      stopPolling()
    } else {
      message.error('取消失败，' + res.data.message)
    }
  } finally {
    cancelling.value = false
  }
}

/** 在当前页展开测试结果列表（详情） */
const handleViewDetail = () => {
  showReport.value = true
  fetchResults()
}

/** 跳转到独立的测试报告页：雷达图 / 柱状图 / 模型统计 / PDF 导出 */
const handleViewReport = () => {
  if (!currentTask.value) {
    return
  }
  router.push({ path: '/test/report', query: { taskId: currentTask.value.id } })
}

const handleBackToList = () => {
  showReport.value = false
  currentTask.value = null
  progressPercentage.value = 0
  progressInfo.value = { currentModel: '', currentPrompt: '' }
  wsClient?.disconnect()
  wsClient = null
  wsConnected.value = false
  stopPolling()
  fetchTasks()
}

const handleOpenTask = async (record: TestTaskVO) => {
  showReport.value = false
  results.value = []
  const detail = await getBatchTestTask(record.id)
  if (detail.data.code !== 0 || !detail.data.data) {
    message.error('获取任务详情失败，' + detail.data.message)
    return
  }
  currentTask.value = detail.data.data
  progressPercentage.value =
    record.totalSubtasks > 0 ? Math.floor((record.completedSubtasks / record.totalSubtasks) * 100) : 0
  progressInfo.value = { currentModel: '', currentPrompt: '' }

  if (record.status === 'running' || record.status === 'pending') {
    subscribeTask(record.id)
  } else {
    showReport.value = true
    fetchResults()
  }
}

// ============ 结果 ============

const results = ref<TestResultVO[]>([])
const loadingResults = ref(false)
const showReport = ref(false)
const filterModel = ref<string | undefined>(undefined)
const detailVisible = ref(false)
const detailRecord = ref<TestResultVO | null>(null)

const fetchResults = async () => {
  if (!currentTask.value) {
    return
  }
  loadingResults.value = true
  try {
    const res = await listBatchTestResult(currentTask.value.id, filterModel.value)
    if (res.data.code === 0) {
      results.value = res.data.data ?? []
    } else {
      message.error('获取测试结果失败，' + res.data.message)
    }
  } finally {
    loadingResults.value = false
  }
}

const handleRate = async (record: TestResultVO, value: number) => {
  const res = await updateBatchTestResultRating(record.id, value)
  if (res.data.code === 0) {
    record.userRating = value
    message.success('评分已保存')
  } else {
    message.error('评分失败，' + res.data.message)
  }
}

const handleShowDetail = (record: TestResultVO) => {
  detailRecord.value = record
  detailVisible.value = true
}

// ============ 任务列表 ============

const tasks = ref<TestTaskVO[]>([])
const loadingTasks = ref(false)
const taskQuery = reactive<{ current: number; pageSize: number }>({ current: 1, pageSize: 5 })
const taskTotal = ref(0)

const taskPagination = computed(() => ({
  current: taskQuery.current,
  pageSize: taskQuery.pageSize,
  total: taskTotal.value,
  showSizeChanger: true,
  showTotal: (value: number) => `共 ${value} 条`,
}))

const fetchTasks = async () => {
  loadingTasks.value = true
  try {
    const res = await listBatchTestTaskByPage({
      current: taskQuery.current,
      pageSize: taskQuery.pageSize,
    })
    if (res.data.code === 0 && res.data.data) {
      tasks.value = res.data.data.records ?? []
      taskTotal.value = res.data.data.total ?? 0
    } else {
      message.error('获取任务列表失败，' + res.data.message)
    }
  } finally {
    loadingTasks.value = false
  }
}

const handleTaskTableChange = (page: { current: number; pageSize: number }) => {
  taskQuery.current = page.current
  taskQuery.pageSize = page.pageSize
  fetchTasks()
}

const handleDeleteTask = async (id: string) => {
  const res = await deleteBatchTestTask(id)
  if (res.data.code === 0) {
    message.success('删除成功')
    if (currentTask.value?.id === id) {
      handleBackToList()
    } else {
      fetchTasks()
    }
  } else {
    message.error('删除失败，' + res.data.message)
  }
}

// ============ 展示辅助 ============

const statusLabel = (status: TaskStatus) =>
  ({
    pending: '等待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  })[status] ?? status

const statusColor = (status: TaskStatus) =>
  ({
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
    cancelled: 'warning',
  })[status] ?? 'default'

const formatCost = (cost?: number) => (cost === undefined || cost === null ? '-' : cost.toFixed(6))

onMounted(() => {
  fetchScenes()
  fetchModels()
  fetchTasks()
})

onUnmounted(() => {
  wsClient?.disconnect()
  stopPolling()
})
</script>

<style scoped>
.batch-test-page {
  padding: 24px;
}

.scene-hint {
  margin-top: 4px;
}

.model-option {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.model-option-id {
  color: #8c8c8c;
  font-size: 12px;
}

.metrics-cell {
  font-size: 12px;
  color: #595959;
  line-height: 1.6;
}

.detail-block {
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.reason-block {
  background: #fffbe6;
  border-color: #ffe58f;
}
</style>
