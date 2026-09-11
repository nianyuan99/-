<template>
  <div class="scene-manage-page">
    <a-card title="场景管理" :bordered="false">
      <template #extra>
        <a-space>
          <a-button type="primary" @click="handleCreateScene">
            <template #icon><PlusOutlined /></template>
            创建场景
          </a-button>
        </a-space>
      </template>

      <!-- 筛选区域 -->
      <div class="filter-section">
        <a-form layout="inline" :model="filterForm" class="filter-form">
          <a-form-item label="场景名称">
            <a-input
              v-model:value="filterForm.name"
              placeholder="按名称搜索"
              allow-clear
              style="width: 180px"
              @press-enter="handleSearch"
            />
          </a-form-item>
          <a-form-item label="分类">
            <a-select
              v-model:value="filterForm.category"
              placeholder="选择分类"
              allow-clear
              style="width: 150px"
            >
              <a-select-option v-for="cat in categories" :key="cat" :value="cat">
                {{ cat }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="类型">
            <a-select
              v-model:value="filterForm.isPreset"
              placeholder="选择类型"
              allow-clear
              style="width: 150px"
            >
              <a-select-option :value="true">预设场景</a-select-option>
              <a-select-option :value="false">自定义场景</a-select-option>
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
      </div>

      <!-- 场景列表 -->
      <a-table
        :columns="columns"
        :data-source="scenes"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'isPreset'">
            <a-tag :color="record.isPreset ? 'blue' : 'green'">
              {{ record.isPreset ? '预设' : '自定义' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'category'">
            <a-tag v-if="record.category">{{ record.category }}</a-tag>
            <span v-else style="color: #999">未分类</span>
          </template>
          <template v-else-if="column.key === 'description'">
            <a-typography-text
              v-if="record.description"
              :content="record.description"
              :ellipsis="{ tooltip: record.description }"
              style="max-width: 320px"
            />
            <span v-else style="color: #999">-</span>
          </template>
          <template v-else-if="column.key === 'createTime'">
            {{ dayjs(record.createTime).format('YYYY-MM-DD HH:mm:ss') }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="handleManagePrompts(record)">
                管理提示词
              </a-button>
              <a-button
                v-if="!record.isPreset"
                type="link"
                size="small"
                @click="handleEditScene(record)"
              >
                编辑
              </a-button>
              <a-popconfirm
                v-if="!record.isPreset"
                title="确定要删除这个场景吗？"
                @confirm="handleDeleteScene(record.id)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 创建/编辑场景模态框 -->
    <a-modal
      v-model:open="sceneModalVisible"
      :title="editingScene ? '编辑场景' : '创建场景'"
      :confirm-loading="savingScene"
      @ok="handleSaveScene"
      @cancel="handleCancelScene"
    >
      <a-form ref="sceneFormRef" :model="sceneForm" :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
        <a-form-item label="场景名称" name="name" :rules="[{ required: true, message: '请输入场景名称' }]">
          <a-input v-model:value="sceneForm.name" placeholder="请输入场景名称" />
        </a-form-item>
        <a-form-item label="场景描述" name="description">
          <a-textarea
            v-model:value="sceneForm.description"
            placeholder="请输入场景描述（可选）"
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="分类" name="category">
          <a-select
            v-model:value="sceneForm.category"
            placeholder="选择分类（可选）"
            allow-clear
            style="width: 100%"
          >
            <a-select-option v-for="cat in categories" :key="cat" :value="cat">
              {{ cat }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 提示词管理模态框 -->
    <a-modal
      v-model:open="promptModalVisible"
      :title="currentScene ? `管理提示词 - ${currentScene.name}` : '管理提示词'"
      width="90%"
      :footer="null"
      @cancel="handleClosePromptModal"
    >
      <div v-if="currentScene" class="prompt-management">
        <div class="prompt-actions">
          <a-space>
            <a-button v-if="!currentScene?.isPreset" type="primary" @click="handleAddPrompt">
              <template #icon><PlusOutlined /></template>
              添加提示词
            </a-button>
            <a-upload
              v-if="!currentScene?.isPreset"
              :before-upload="handleBeforeUpload"
              :show-upload-list="false"
              accept=".csv,.json"
            >
              <a-button :loading="importing">
                <template #icon><UploadOutlined /></template>
                批量导入
              </a-button>
            </a-upload>
            <a-button @click="handleExportPrompts">
              <template #icon><DownloadOutlined /></template>
              导出提示词
            </a-button>
          </a-space>
        </div>

        <a-table
          :columns="promptColumns"
          :data-source="prompts"
          :loading="loadingPrompts"
          row-key="id"
          style="margin-top: 16px"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'content'">
              <a-typography-paragraph
                :content="record.content"
                :ellipsis="{ rows: 2, expandable: true }"
                style="max-width: 400px"
              />
            </template>
            <template v-else-if="column.key === 'difficulty'">
              <a-tag v-if="record.difficulty" :color="difficultyColor(record.difficulty)">
                {{ difficultyLabel(record.difficulty) }}
              </a-tag>
              <span v-else style="color: #999">-</span>
            </template>
            <template v-else-if="column.key === 'tags'">
              <template v-if="record.tags && record.tags.length">
                <a-tag v-for="tag in record.tags" :key="tag">{{ tag }}</a-tag>
              </template>
              <span v-else style="color: #999">-</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a-button
                  v-if="!currentScene?.isPreset"
                  type="link"
                  size="small"
                  @click="handleEditPrompt(record)"
                >
                  编辑
                </a-button>
                <a-popconfirm
                  v-if="!currentScene?.isPreset"
                  title="确定要删除这个提示词吗？"
                  @confirm="handleDeletePrompt(record.id)"
                >
                  <a-button type="link" size="small" danger>删除</a-button>
                </a-popconfirm>
                <span v-if="currentScene?.isPreset" style="color: #999; font-size: 12px">
                  内置场景不可编辑
                </span>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>
    </a-modal>

    <!-- 添加/编辑提示词模态框 -->
    <a-modal
      v-model:open="promptFormModalVisible"
      :title="editingPrompt ? '编辑提示词' : '添加提示词'"
      :confirm-loading="savingPrompt"
      width="800px"
      @ok="handleSavePrompt"
      @cancel="handleCancelPrompt"
    >
      <a-form
        ref="promptFormRef"
        :model="promptForm"
        :label-col="{ span: 4 }"
        :wrapper-col="{ span: 20 }"
      >
        <a-form-item label="标题" name="title" :rules="[{ required: true, message: '请输入提示词标题' }]">
          <a-input v-model:value="promptForm.title" placeholder="请输入提示词标题" />
        </a-form-item>
        <a-form-item label="内容" name="content" :rules="[{ required: true, message: '请输入提示词内容' }]">
          <a-textarea v-model:value="promptForm.content" placeholder="请输入提示词内容" :rows="6" />
        </a-form-item>
        <a-form-item label="难度" name="difficulty">
          <a-select v-model:value="promptForm.difficulty" placeholder="选择难度（可选）" allow-clear>
            <a-select-option value="easy">简单</a-select-option>
            <a-select-option value="medium">中等</a-select-option>
            <a-select-option value="hard">困难</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标签" name="tags">
          <a-select
            v-model:value="promptForm.tags"
            mode="tags"
            placeholder="输入标签后回车（可选）"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="期望输出" name="expectedOutput">
          <a-textarea
            v-model:value="promptForm.expectedOutput"
            placeholder="请输入期望输出（可选，便于后续做自动评分）"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import {
  DownloadOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import {
  addScenePrompt,
  createScene,
  deleteScene,
  deleteScenePrompt,
  listSceneByPage,
  listSceneCategories,
  listScenePrompts,
  updateScene,
  updateScenePrompt,
  type ScenePromptVO,
  type SceneVO,
} from '@/api/scene.ts'

/** 场景列表表格列 */
const columns = [
  { title: '场景名称', dataIndex: 'name' },
  { title: '分类', key: 'category', width: 120 },
  { title: '类型', key: 'isPreset', width: 100 },
  { title: '描述', key: 'description' },
  { title: '提示词数', dataIndex: 'promptCount', width: 100 },
  { title: '创建时间', key: 'createTime', width: 180 },
  { title: '操作', key: 'action', width: 240 },
]

/** 提示词表格列 */
const promptColumns = [
  { title: '序号', dataIndex: 'promptIndex', width: 70 },
  { title: '标题', dataIndex: 'title', width: 200 },
  { title: '内容', key: 'content' },
  { title: '难度', key: 'difficulty', width: 90 },
  { title: '标签', key: 'tags', width: 180 },
  { title: '操作', key: 'action', width: 180 },
]

// ============ 场景列表 ============

const scenes = ref<SceneVO[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const total = ref(0)

const filterForm = reactive<{
  name?: string
  category?: string
  isPreset?: boolean
  current: number
  pageSize: number
}>({
  name: '',
  category: undefined,
  isPreset: undefined,
  current: 1,
  pageSize: 10,
})

const pagination = computed(() => ({
  current: filterForm.current,
  pageSize: filterForm.pageSize,
  total: total.value,
  showSizeChanger: true,
  showTotal: (value: number) => `共 ${value} 条`,
}))

const fetchScenes = async () => {
  loading.value = true
  try {
    const res = await listSceneByPage({
      name: filterForm.name || undefined,
      category: filterForm.category,
      isPreset: filterForm.isPreset,
      current: filterForm.current,
      pageSize: filterForm.pageSize,
    })
    if (res.data.code === 0 && res.data.data) {
      scenes.value = res.data.data.records ?? []
      total.value = res.data.data.total ?? 0
    } else {
      message.error('获取场景列表失败，' + res.data.message)
    }
  } finally {
    loading.value = false
  }
}

const fetchCategories = async () => {
  const res = await listSceneCategories()
  if (res.data.code === 0) {
    categories.value = res.data.data ?? []
  }
}

const handleTableChange = (page: { current: number; pageSize: number }) => {
  filterForm.current = page.current
  filterForm.pageSize = page.pageSize
  fetchScenes()
}

const handleSearch = () => {
  filterForm.current = 1
  fetchScenes()
}

const handleReset = () => {
  filterForm.name = ''
  filterForm.category = undefined
  filterForm.isPreset = undefined
  filterForm.current = 1
  handleSearch()
}

// ============ 场景增删改 ============

const sceneModalVisible = ref(false)
const savingScene = ref(false)
const editingScene = ref<SceneVO | null>(null)
const sceneFormRef = ref()
const sceneForm = reactive<{ name: string; description?: string; category?: string }>({
  name: '',
  description: '',
  category: undefined,
})

const handleCreateScene = () => {
  editingScene.value = null
  sceneForm.name = ''
  sceneForm.description = ''
  sceneForm.category = undefined
  sceneModalVisible.value = true
}

const handleEditScene = (record: SceneVO) => {
  editingScene.value = record
  sceneForm.name = record.name
  sceneForm.description = record.description
  sceneForm.category = record.category
  sceneModalVisible.value = true
}

const handleSaveScene = async () => {
  try {
    await sceneFormRef.value?.validate()
  } catch {
    return
  }

  savingScene.value = true
  try {
    const res = editingScene.value
      ? await updateScene({
          id: editingScene.value.id,
          name: sceneForm.name,
          description: sceneForm.description,
          category: sceneForm.category,
        })
      : await createScene({
          name: sceneForm.name,
          description: sceneForm.description,
          category: sceneForm.category,
        })

    if (res.data.code === 0) {
      message.success(editingScene.value ? '更新成功' : '创建成功')
      sceneModalVisible.value = false
      await Promise.all([fetchScenes(), fetchCategories()])
    } else {
      message.error((editingScene.value ? '更新失败，' : '创建失败，') + res.data.message)
    }
  } finally {
    savingScene.value = false
  }
}

const handleCancelScene = () => {
  sceneModalVisible.value = false
}

const handleDeleteScene = async (id: string) => {
  const res = await deleteScene(id)
  if (res.data.code === 0) {
    message.success('删除成功')
    fetchScenes()
  } else {
    message.error('删除失败，' + res.data.message)
  }
}

// ============ 提示词管理 ============

const promptModalVisible = ref(false)
const currentScene = ref<SceneVO | null>(null)
const prompts = ref<ScenePromptVO[]>([])
const loadingPrompts = ref(false)
const importing = ref(false)

const handleManagePrompts = async (record: SceneVO) => {
  currentScene.value = record
  promptModalVisible.value = true
  await fetchPrompts()
}

const fetchPrompts = async () => {
  if (!currentScene.value) {
    return
  }
  loadingPrompts.value = true
  try {
    const res = await listScenePrompts(currentScene.value.id)
    if (res.data.code === 0) {
      prompts.value = res.data.data ?? []
    } else {
      message.error('获取提示词失败，' + res.data.message)
    }
  } finally {
    loadingPrompts.value = false
  }
}

const handleClosePromptModal = () => {
  promptModalVisible.value = false
  currentScene.value = null
  prompts.value = []
  // 提示词数量变了，列表里的 promptCount 需要刷新
  fetchScenes()
}

const difficultyLabel = (difficulty: string) =>
  ({ easy: '简单', medium: '中等', hard: '困难' })[difficulty] ?? difficulty

const difficultyColor = (difficulty: string) =>
  ({ easy: 'green', medium: 'orange', hard: 'red' })[difficulty] ?? 'default'

/**
 * 导出提示词为 CSV
 *
 * 纯前端生成 Blob 下载，不额外增加后端接口；
 * CSV 用 UTF-8 BOM 开头，Excel 打开才不会中文乱码。
 */
const handleExportPrompts = () => {
  if (!prompts.value.length) {
    message.warning('当前场景没有提示词可导出')
    return
  }
  const header = ['序号', '标题', '内容', '难度', '标签', '期望输出']
  const escapeCsv = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
  const lines = [header.join(',')]
  prompts.value.forEach((prompt) => {
    lines.push(
      [
        prompt.promptIndex,
        prompt.title,
        prompt.content,
        prompt.difficulty ?? '',
        (prompt.tags ?? []).join('|'),
        prompt.expectedOutput ?? '',
      ]
        .map(escapeCsv)
        .join(','),
    )
  })

  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${currentScene.value?.name ?? '场景'}-提示词.csv`
  link.click()
  URL.revokeObjectURL(url)
  message.success(`已导出 ${prompts.value.length} 条提示词`)
}

/** 解析 CSV 文本为提示词数组（支持带引号与逗号的字段） */
const parseCsv = (text: string): Array<Record<string, string>> => {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i += 1
        } else {
          inQuotes = false
        }
      } else {
        field += char
      }
    } else if (char === '"') {
      inQuotes = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (char !== '\r') {
      field += char
    }
  }
  if (field || row.length) {
    row.push(field)
    rows.push(row)
  }

  const [header, ...body] = rows.filter((item) => item.some((cell) => cell.trim() !== ''))
  if (!header) {
    return []
  }
  return body.map((cells) => {
    const record: Record<string, string> = {}
    header.forEach((key, index) => {
      record[key.trim()] = (cells[index] ?? '').trim()
    })
    return record
  })
}

/** 把导入记录归一化成提示词字段（兼容中英文表头） */
const normalizeImported = (record: Record<string, unknown>) => {
  const pick = (...keys: string[]) => {
    for (const key of keys) {
      const value = record[key]
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        return String(value).trim()
      }
    }
    return ''
  }
  const tagsRaw = pick('标签', 'tags')
  return {
    title: pick('标题', 'title'),
    content: pick('内容', 'content', 'prompt'),
    difficulty: pick('难度', 'difficulty').toLowerCase() || undefined,
    tags: tagsRaw
      ? tagsRaw
          .split(/[|,;]/)
          .map((tag) => tag.trim())
          .filter(Boolean)
      : undefined,
    expectedOutput: pick('期望输出', 'expectedOutput', 'expected_output') || undefined,
  }
}

/**
 * 批量导入提示词
 *
 * 上传组件里 return false 只是阻止 antd 自动发请求，文件仍由这里读出来逐条调用新增接口。
 */
const handleBeforeUpload = async (file: File) => {
  if (!currentScene.value) {
    return false
  }
  importing.value = true
  try {
    const text = await file.text()
    let rows: Array<Record<string, unknown>> = []
    if (file.name.toLowerCase().endsWith('.json')) {
      const parsed = JSON.parse(text)
      rows = Array.isArray(parsed) ? parsed : [parsed]
    } else {
      rows = parseCsv(text)
    }

    let successCount = 0
    const failedTitles: string[] = []
    for (const row of rows) {
      const item = normalizeImported(row)
      if (!item.title || !item.content) {
        failedTitles.push(item.title || '(缺少标题或内容)')
        continue
      }
      const res = await addScenePrompt({
        sceneId: currentScene.value.id,
        title: item.title,
        content: item.content,
        difficulty: item.difficulty,
        tags: item.tags,
        expectedOutput: item.expectedOutput,
      })
      if (res.data.code === 0) {
        successCount += 1
      } else {
        failedTitles.push(`${item.title}（${res.data.message}）`)
      }
    }

    if (successCount > 0) {
      message.success(`成功导入 ${successCount} 条提示词`)
    }
    if (failedTitles.length) {
      message.warning(`有 ${failedTitles.length} 条未导入：${failedTitles.slice(0, 3).join('、')}`)
    }
    await fetchPrompts()
  } catch (error) {
    message.error('导入失败，请检查文件格式（支持 CSV / JSON）')
    console.error(error)
  } finally {
    importing.value = false
  }
  return false
}

// ============ 提示词增删改 ============

const promptFormModalVisible = ref(false)
const savingPrompt = ref(false)
const editingPrompt = ref<ScenePromptVO | null>(null)
const promptFormRef = ref()
const promptForm = reactive<{
  title: string
  content: string
  difficulty?: string
  tags?: string[]
  expectedOutput?: string
}>({
  title: '',
  content: '',
  difficulty: undefined,
  tags: [],
  expectedOutput: '',
})

const handleAddPrompt = () => {
  editingPrompt.value = null
  promptForm.title = ''
  promptForm.content = ''
  promptForm.difficulty = undefined
  promptForm.tags = []
  promptForm.expectedOutput = ''
  promptFormModalVisible.value = true
}

const handleEditPrompt = (record: ScenePromptVO) => {
  editingPrompt.value = record
  promptForm.title = record.title
  promptForm.content = record.content
  promptForm.difficulty = record.difficulty
  promptForm.tags = record.tags ?? []
  promptForm.expectedOutput = record.expectedOutput
  promptFormModalVisible.value = true
}

const handleSavePrompt = async () => {
  try {
    await promptFormRef.value?.validate()
  } catch {
    return
  }
  if (!currentScene.value) {
    return
  }

  savingPrompt.value = true
  try {
    const res = editingPrompt.value
      ? await updateScenePrompt({
          id: editingPrompt.value.id,
          title: promptForm.title,
          content: promptForm.content,
          difficulty: promptForm.difficulty,
          tags: promptForm.tags,
          expectedOutput: promptForm.expectedOutput,
        })
      : await addScenePrompt({
          sceneId: currentScene.value.id,
          title: promptForm.title,
          content: promptForm.content,
          difficulty: promptForm.difficulty,
          tags: promptForm.tags,
          expectedOutput: promptForm.expectedOutput,
        })

    if (res.data.code === 0) {
      message.success(editingPrompt.value ? '更新成功' : '添加成功')
      promptFormModalVisible.value = false
      await fetchPrompts()
    } else {
      message.error((editingPrompt.value ? '更新失败，' : '添加失败，') + res.data.message)
    }
  } finally {
    savingPrompt.value = false
  }
}

const handleCancelPrompt = () => {
  promptFormModalVisible.value = false
}

const handleDeletePrompt = async (id: string) => {
  const res = await deleteScenePrompt(id)
  if (res.data.code === 0) {
    message.success('删除成功')
    await fetchPrompts()
  } else {
    message.error('删除失败，' + res.data.message)
  }
}

onMounted(() => {
  fetchScenes()
  fetchCategories()
})
</script>

<style scoped>
.scene-manage-page {
  padding: 24px;
}

.filter-section {
  margin-bottom: 16px;
}

.filter-form {
  row-gap: 8px;
}

.prompt-management {
  min-height: 320px;
}
</style>
