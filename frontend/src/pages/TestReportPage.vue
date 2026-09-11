<template>
  <div class="task-report-page">
    <a-card title="测试报告" :bordered="false">
      <template #extra>
        <a-button type="primary" :loading="exportingPDF" @click="handleExportPDF">
          <template #icon>
            <DownloadOutlined />
          </template>
          导出PDF
        </a-button>
      </template>

      <a-spin :spinning="loadingReport">
        <a-descriptions :column="2" bordered style="margin-bottom: 24px">
          <a-descriptions-item label="任务ID">{{ report?.taskId || taskId || '-' }}</a-descriptions-item>
          <a-descriptions-item label="任务名称">{{ report?.taskName || task?.name || '未命名' }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="getStatusColor(task?.status || '')">
              {{ getStatusText(task?.status || '') }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="完成时间">{{ task?.completedAt || '-' }}</a-descriptions-item>
        </a-descriptions>

        <!-- 统计摘要 -->
        <a-row :gutter="16" style="margin-bottom: 24px">
          <a-col :span="8">
            <a-statistic
              title="总成本"
              :value="report?.summary?.totalCost || 0"
              prefix="$"
              :precision="6"
            />
          </a-col>
          <a-col :span="8">
            <a-statistic
              title="平均响应时间"
              :value="report?.summary?.avgResponseTimeMs || 0"
              suffix="ms"
              :precision="2"
            />
          </a-col>
          <a-col :span="8">
            <a-statistic title="总Token消耗" :value="report?.summary?.totalTokens || 0" />
          </a-col>
        </a-row>
        <a-row :gutter="16" style="margin-bottom: 24px">
          <a-col :span="8">
            <a-statistic title="测试结果总数" :value="report?.summary?.totalResults || 0" />
          </a-col>
          <a-col :span="8">
            <a-statistic title="参与模型数量" :value="report?.summary?.modelCount || 0" />
          </a-col>
        </a-row>

        <!-- 雷达图 -->
        <a-card title="多维度能力对比（雷达图）" :bordered="false" style="margin-bottom: 24px">
          <div ref="radarChartRef" style="width: 100%; height: 400px"></div>
        </a-card>

        <!-- 柱状图 -->
        <a-card title="性能指标对比（柱状图）" :bordered="false" style="margin-bottom: 24px">
          <a-radio-group v-model:value="barChartType" style="margin-bottom: 16px">
            <a-radio-button value="responseTime">响应时间</a-radio-button>
            <a-radio-button value="tokens">Token消耗</a-radio-button>
            <a-radio-button value="cost">成本</a-radio-button>
          </a-radio-group>
          <div ref="barChartRef" style="width: 100%; height: 400px"></div>
        </a-card>

        <!-- 模型统计表格 -->
        <a-card title="模型统计" :bordered="false" style="margin-bottom: 24px">
          <div ref="modelStatsRef">
            <a-table
              :columns="modelStatColumns"
              :data-source="report?.modelStatistics || []"
              row-key="modelName"
              :pagination="false"
              size="small"
              :scroll="{ x: 1200 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'modelName'">
                  <a-tag color="blue">{{ record.modelName }}</a-tag>
                </template>
                <template v-else-if="column.key === 'avgResponseTime'">
                  {{ record.avgResponseTimeMs != null ? `${record.avgResponseTimeMs.toFixed(1)} ms` : '-' }}
                </template>
                <template v-else-if="column.key === 'avgTokens'">
                  {{ formatNumber(record.avgInputTokens) }} / {{ formatNumber(record.avgOutputTokens) }}
                </template>
                <template v-else-if="column.key === 'totalCost'">
                  ${{ formatCost(record.totalCost) }}
                </template>
                <template v-else-if="column.key === 'avgCost'">
                  ${{ formatCost(record.avgCost) }}
                </template>
                <template v-else-if="column.key === 'avgUserRating'">
                  {{ record.avgUserRating != null ? record.avgUserRating.toFixed(2) : '-' }}
                </template>
                <template v-else-if="column.key === 'avgAiScore'">
                  {{ record.avgAiScore != null ? record.avgAiScore.toFixed(2) : '-' }}
                </template>
              </template>
            </a-table>
          </div>
        </a-card>

        <!-- 详细测试结果 -->
        <a-card title="详细测试结果" :bordered="false">
          <a-table
            :columns="resultColumns"
            :data-source="report?.testResults || []"
            row-key="id"
            size="small"
            :pagination="{ pageSize: 10, showSizeChanger: true }"
            :scroll="{ x: 1100 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'modelName'">
                <a-tag color="blue">{{ record.modelName }}</a-tag>
              </template>
              <template v-else-if="column.key === 'outputText'">
                <a-typography-paragraph
                  :content="record.outputText"
                  :ellipsis="{ rows: 2, expandable: true, symbol: '展开' }"
                  style="max-width: 320px; margin-bottom: 0"
                />
              </template>
              <template v-else-if="column.key === 'metrics'">
                <div class="metrics-cell">
                  <div>耗时：{{ record.responseTimeMs ?? '-' }} ms</div>
                  <div>Token：{{ record.inputTokens ?? 0 }} / {{ record.outputTokens ?? 0 }}</div>
                  <div>成本：${{ formatCost(record.cost) }}</div>
                </div>
              </template>
              <template v-else-if="column.key === 'userRating'">
                <a-rate :value="record.userRating || 0" disabled :count="5" />
              </template>
              <template v-else-if="column.key === 'aiScore'">
                <template v-if="record.aiScore">
                  <div class="ai-score-cell">
                    <div>
                      总分：<a-tag color="purple">{{ formatNumber(rowAiTotal(record), 2) }}</a-tag>
                    </div>
                    <div>
                      一致性：
                      <a-tooltip :title="consistencyTip(record.aiScore.consistency)">
                        {{ formatNumber(record.aiScore.consistency, 2) }}
                      </a-tooltip>
                    </div>
                    <div>评委数：{{ record.aiScore.judges?.length ?? 0 }}</div>
                  </div>
                </template>
                <span v-else style="color: #999">-</span>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" size="small" @click="handleShowDetail(record)">查看详情</a-button>
              </template>
            </template>
          </a-table>
        </a-card>
      </a-spin>
    </a-card>

    <!-- 结果详情（含 AI 评分明细） -->
    <a-modal
      v-model:open="detailVisible"
      title="测试结果详情"
      width="860px"
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
          <a-descriptions-item label="用户评分">
            <a-rate :value="detailRecord.userRating || 0" disabled :count="5" />
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

        <template v-if="detailRecord.aiScore">
          <a-divider orientation="left">AI 评分（多评委交叉验证）</a-divider>
          <a-row :gutter="16" style="margin-bottom: 12px">
            <a-col :span="6">
              <a-statistic title="总分(0-100)" :value="rowAiTotal(detailRecord) || 0" :precision="2" />
            </a-col>
            <a-col :span="6">
              <a-statistic
                title="平均评级(1-10)"
                :value="detailRecord.aiScore.averageRating || 0"
                :precision="2"
              />
            </a-col>
            <a-col :span="6">
              <a-statistic
                title="一致性(标准差)"
                :value="detailRecord.aiScore.consistency || 0"
                :precision="2"
              />
            </a-col>
            <a-col :span="6">
              <a-statistic title="评委数量" :value="detailRecord.aiScore.judges?.length || 0" />
            </a-col>
          </a-row>
          <a-table
            :columns="judgeColumns"
            :data-source="detailRecord.aiScore.judges || []"
            row-key="model"
            size="small"
            :pagination="false"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'scores'">
                <a-space wrap>
                  <a-tag v-for="(value, key) in record.scores" :key="key">{{ key }}: {{ value }}</a-tag>
                </a-space>
              </template>
            </template>
          </a-table>
        </template>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownloadOutlined } from '@ant-design/icons-vue'
import * as echarts from 'echarts'
import { jsPDF } from 'jspdf'
import html2canvas from 'html2canvas'
import { generateReport, type ReportVO } from '@/api/report.ts'
import { getBatchTestTask, type TestResultVO, type TestTaskVO } from '@/api/batchTest.ts'

/**
 * 测试报告页
 *
 * 数据全部由后端算好（摘要 / 模型统计 / 雷达图 / 柱状图），前端只负责渲染。
 * 图表用 ECharts，PDF 导出用 jsPDF + html2canvas（jsPDF 对中文支持不好，
 * 所以先把文本和图表渲染成图片，再贴进 PDF，这样中文不会乱码）。
 */

const route = useRoute()
const taskId = route.query.taskId as string | undefined

const report = ref<ReportVO | null>(null)
const task = ref<TestTaskVO | null>(null)
const loadingReport = ref(false)
const exportingPDF = ref(false)

const radarChartRef = ref<HTMLDivElement | null>(null)
const barChartRef = ref<HTMLDivElement | null>(null)
const modelStatsRef = ref<HTMLDivElement | null>(null)

let radarChartInstance: echarts.ECharts | null = null
let barChartInstance: echarts.ECharts | null = null

// ============ 图表 ============

const barChartType = ref<'responseTime' | 'tokens' | 'cost'>('responseTime')

/** 柱状图三个系列在后端返回的 series 数组里的下标：平均响应时间 / 总Token消耗 / 总成本 */
const BAR_SERIES_INDEX: Record<string, number> = {
  responseTime: 0,
  tokens: 1,
  cost: 2,
}

const initRadarChart = () => {
  if (!radarChartRef.value || !report.value?.radarChart) return

  radarChartInstance?.dispose()
  radarChartInstance = echarts.init(radarChartRef.value)

  const option = {
    tooltip: {},
    legend: {
      data: report.value.radarChart.series.map((s) => s.modelName),
    },
    radar: {
      // 后端已经把数据标准化到 0-100，这里固定 max，避免不同报告的图表比例不一致
      indicator: report.value.radarChart.dimensions.map((dim) => ({
        name: dim,
        max: 100,
      })),
    },
    series: [
      {
        type: 'radar',
        data: report.value.radarChart.series.map((s) => ({
          name: s.modelName,
          value: s.values,
        })),
      },
    ],
  }

  radarChartInstance.setOption(option)
}

const initBarChart = () => {
  if (!barChartRef.value || !report.value?.barChart) return

  barChartInstance?.dispose()
  barChartInstance = echarts.init(barChartRef.value)

  const data = report.value.barChart
  const index = BAR_SERIES_INDEX[barChartType.value] ?? 0
  const series = data.series[index]

  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 30, top: 40, bottom: 80 },
    xAxis: {
      type: 'category',
      data: data.categories,
      axisLabel: { interval: 0, rotate: 20, width: 140, overflow: 'truncate' },
    },
    yAxis: { type: 'value', name: series?.unit ?? '' },
    series: series
      ? [
          {
            name: series.name,
            type: 'bar',
            data: series.data,
            barMaxWidth: 60,
            label: {
              show: true,
              position: 'top',
              formatter: (p: any) => formatSeriesValue(p.value, series.unit),
            },
          },
        ]
      : [],
  }

  barChartInstance.setOption(option)
}

const handleResize = () => {
  radarChartInstance?.resize()
  barChartInstance?.resize()
}

// 切换指标时重画柱状图（先 dispose 再 init，避免旧系列残留）
watch(barChartType, () => {
  initBarChart()
})

onMounted(async () => {
  if (!taskId) {
    message.error('缺少任务 ID')
    return
  }

  loadingReport.value = true
  try {
    const res = await generateReport({ taskId })
    if (res.data.code === 0 && res.data.data) {
      report.value = res.data.data
      // 用 nextTick 确保 DOM 更新完毕后再渲染图表，不然 ECharts 找不到容器元素
      nextTick(() => {
        initRadarChart()
        initBarChart()
      })
      window.addEventListener('resize', handleResize)
    } else {
      message.error('加载报告失败，' + res.data.message)
    }

    // 任务状态、完成时间来自任务详情接口（报告接口只返回统计数据）
    const detail = await getBatchTestTask(taskId)
    if (detail.data.code === 0 && detail.data.data) {
      task.value = detail.data.data
    }
  } catch (error) {
    message.error('加载报告失败')
  } finally {
    loadingReport.value = false
  }
})

onUnmounted(() => {
  radarChartInstance?.dispose()
  barChartInstance?.dispose()
  window.removeEventListener('resize', handleResize)
})

// ============ 表格列 ============

const modelStatColumns = [
  { title: '模型', key: 'modelName', width: 220 },
  { title: '测试次数', dataIndex: 'testCount', width: 90 },
  { title: '平均响应时间', key: 'avgResponseTime', width: 130 },
  { title: '平均Token(入/出)', key: 'avgTokens', width: 170 },
  { title: '总Token', dataIndex: 'totalTokens', width: 110 },
  { title: '总成本', key: 'totalCost', width: 130 },
  { title: '平均成本', key: 'avgCost', width: 130 },
  { title: '用户评分', key: 'avgUserRating', width: 100 },
  // AI总分是 0-100 口径（各评委 totalScore 的平均），与雷达图「准确性」同源
  { title: 'AI总分', key: 'avgAiScore', width: 100 },
]

const resultColumns = [
  // 注意：报告里的 testResults 只来自 test_result 表（没有 join 场景提示词），
  // 所以这里不展示 promptTitle / promptIndex，避免出现两列常驻空白
  { title: '模型', key: 'modelName', width: 200 },
  { title: '输出内容', key: 'outputText' },
  { title: '指标', key: 'metrics', width: 200 },
  { title: '用户评分', key: 'userRating', width: 160 },
  { title: 'AI评分', key: 'aiScore', width: 170 },
  { title: '操作', key: 'action', width: 100 },
]

const judgeColumns = [
  { title: '评委模型', dataIndex: 'model', width: 220 },
  { title: '评级', dataIndex: 'rating', width: 80 },
  { title: '总分', dataIndex: 'totalScore', width: 80 },
  { title: '各维度得分', key: 'scores' },
  { title: '评语', dataIndex: 'comment', width: 200 },
]

const detailVisible = ref(false)
const detailRecord = ref<TestResultVO | null>(null)

const handleShowDetail = (record: TestResultVO) => {
  detailRecord.value = record
  detailVisible.value = true
}

// ============ 展示辅助 ============

const getStatusText = (status: string) =>
  ({
    pending: '等待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  })[status] ?? status

const getStatusColor = (status: string) =>
  ({
    pending: 'default',
    running: 'processing',
    completed: 'success',
    failed: 'error',
    cancelled: 'warning',
  })[status] ?? 'default'

const formatCost = (cost?: number) => {
  if (cost === undefined || cost === null) return '-'
  return cost.toFixed(6)
}

const formatNumber = (value?: number, precision?: number) => {
  if (value === undefined || value === null) return '-'
  if (precision !== undefined) return value.toFixed(precision)
  if (Math.abs(value) >= 1000) return Math.round(value).toLocaleString()
  if (Math.abs(value) >= 1) return value.toFixed(2)
  return value.toFixed(6)
}

/** 柱状图数据标签：毫秒 / Token 取整，USD 保留 6 位（后端成本精度就是 6 位） */
const formatSeriesValue = (value: number, unit?: string) => {
  if (value === undefined || value === null) return '0'
  if (unit === 'ms' || unit === 'tokens') return Math.round(value).toLocaleString()
  return value.toFixed(6)
}

/** 一致性说明：标准差越小说明评委意见越一致，评分越可靠 */
const consistencyTip = (consistency?: number) => {
  if (consistency === undefined || consistency === null) return '暂无一致性数据'
  return consistency < 1
    ? '评委评分高度一致，评分可靠'
    : consistency < 2
      ? '评委评分存在一定分歧'
      : '评委评分分歧较大，该回答存在争议'
}

/**
 * 该条结果的 AI 总分（0-100）
 *
 * 取各评委 `totalScore` 的平均值，与后端模型统计的 avgAiScore、雷达图的「准确性」
 * 保持同一口径（0-100）。aiScore 顶层的 averageRating 是 1-10 的综合评级，
 * 只作为「平均评级」单独展示，不再当作总分用。
 */
const rowAiTotal = (record: TestResultVO) => {
  const totals = (record.aiScore?.judges ?? [])
    .map((judge) => judge.totalScore)
    .filter((value): value is number => typeof value === 'number')
  if (!totals.length) return undefined
  return totals.reduce((sum, value) => sum + value, 0) / totals.length
}

// ============ PDF 导出 ============

const PDF_MARGIN = 20

let pdfDoc: jsPDF | null = null
let pdfPageWidth = 0
let pdfPageHeight = 0

/**
 * 把一段文本渲染到屏幕外的临时 DOM 元素上，再截成 canvas
 *
 * jsPDF 内置字体不支持中文，直接写文字会乱码；转成图片贴进 PDF 就正常了。
 */
const createTextCanvas = async (
  text: string,
  fontSize: number,
  maxWidth: number,
  bold = false,
): Promise<HTMLCanvasElement> => {
  const div = document.createElement('div')
  div.style.cssText = [
    'position: fixed',
    'left: -9999px',
    'top: 0',
    `width: ${maxWidth}px`,
    `font-size: ${fontSize}px`,
    `font-weight: ${bold ? 'bold' : 'normal'}`,
    'line-height: 1.6',
    'color: #000000',
    'background-color: #ffffff',
    'font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif',
    'white-space: pre-wrap',
    'word-break: break-word',
  ].join(';')
  div.textContent = text
  document.body.appendChild(div)
  try {
    return await html2canvas(div, { backgroundColor: '#ffffff', scale: 2 })
  } finally {
    document.body.removeChild(div)
  }
}

/**
 * 把 canvas 贴进 PDF，返回本次占用的高度
 *
 * 每次添加内容前都会检查剩余空间够不够，不够就自动新建一页；
 * 超过单页可用高度时按比例缩小，避免图片溢出页面。
 */
const addImageFromCanvas = (canvas: HTMLCanvasElement, yPos: number, maxHeight: number): number => {
  const doc = pdfDoc
  if (!doc) return 0

  const availWidth = pdfPageWidth - PDF_MARGIN * 2
  let imgWidth = availWidth
  let imgHeight = (canvas.height * availWidth) / canvas.width

  if (maxHeight > 0 && imgHeight > maxHeight) {
    imgHeight = maxHeight
    imgWidth = (canvas.width * maxHeight) / canvas.height
  }

  if (yPos + imgHeight > pdfPageHeight - PDF_MARGIN) {
    doc.addPage()
    yPos = PDF_MARGIN
  }

  doc.addImage(canvas.toDataURL('image/png'), 'PNG', PDF_MARGIN, yPos, imgWidth, imgHeight)
  return imgHeight + 6
}

const addTextToPdf = async (
  text: string,
  fontSize: number,
  yPos: number,
  bold = false,
): Promise<number> => {
  const canvas = await createTextCanvas(text, fontSize, pdfPageWidth - PDF_MARGIN * 2, bold)
  return addImageFromCanvas(canvas, yPos, pdfPageHeight - PDF_MARGIN * 2)
}

const handleExportPDF = async () => {
  if (!report.value) {
    message.warning('报告数据未加载完成')
    return
  }

  try {
    exportingPDF.value = true
    const hideMessage = message.loading('正在生成PDF，请稍候...', 0)

    const doc = new jsPDF('p', 'mm', 'a4')
    pdfDoc = doc
    pdfPageWidth = doc.internal.pageSize.getWidth()
    pdfPageHeight = doc.internal.pageSize.getHeight()
    let yPos = PDF_MARGIN

    // 1. 添加标题
    yPos += await addTextToPdf('AI大模型评测报告', 18, yPos, true)

    // 2. 任务信息
    yPos += await addTextToPdf(
      [
        `任务ID：${report.value.taskId}`,
        `任务名称：${report.value.taskName || task.value?.name || '未命名'}`,
        `状态：${getStatusText(task.value?.status || '')}`,
        `完成时间：${task.value?.completedAt || '-'}`,
      ].join('\n'),
      11,
      yPos,
    )

    // 3. 报告摘要
    const summary = report.value.summary
    yPos += await addTextToPdf(
      [
        '报告摘要',
        `测试结果总数：${summary.totalResults ?? 0}    参与模型数量：${summary.modelCount ?? 0}`,
        `总成本：$${summary.totalCost != null ? summary.totalCost.toFixed(6) : '-'}    ` +
          `平均响应时间：${summary.avgResponseTimeMs != null ? summary.avgResponseTimeMs.toFixed(2) : '-'} ms    ` +
          `总Token消耗：${summary.totalTokens ?? 0}`,
      ].join('\n'),
      11,
      yPos,
    )

    // 4. 添加雷达图
    if (radarChartRef.value && radarChartInstance) {
      const radarTitleHeight = await addTextToPdf('多维度能力对比（雷达图）', 12, yPos, true)
      yPos += radarTitleHeight
      const radarCanvas = await html2canvas(radarChartRef.value, {
        backgroundColor: '#ffffff',
        scale: 2,
      })
      yPos += addImageFromCanvas(radarCanvas, yPos, pdfPageHeight - yPos - 20)
    }

    // 5. 添加柱状图
    if (barChartRef.value && barChartInstance) {
      const barTitleHeight = await addTextToPdf('性能指标对比（柱状图）', 12, yPos, true)
      yPos += barTitleHeight
      const barCanvas = await html2canvas(barChartRef.value, {
        backgroundColor: '#ffffff',
        scale: 2,
      })
      yPos += addImageFromCanvas(barCanvas, yPos, pdfPageHeight - yPos - 20)
    }

    // 6. 添加模型统计表格
    if (modelStatsRef.value) {
      const tableTitleHeight = await addTextToPdf('模型统计', 12, yPos, true)
      yPos += tableTitleHeight
      const tableCanvas = await html2canvas(modelStatsRef.value, {
        backgroundColor: '#ffffff',
        scale: 2,
      })
      yPos += addImageFromCanvas(tableCanvas, yPos, 0)
    }

    hideMessage()
    doc.save(`测试报告_${report.value.taskName || report.value.taskId}.pdf`)
    message.success('PDF导出成功')
  } catch (error: any) {
    message.error('导出PDF失败: ' + (error.message || '未知错误'))
  } finally {
    pdfDoc = null
    exportingPDF.value = false
  }
}
</script>

<style scoped>
.task-report-page {
  padding: 24px;
}

.metrics-cell {
  font-size: 12px;
  color: #595959;
  line-height: 1.6;
}

.ai-score-cell {
  font-size: 12px;
  color: #595959;
  line-height: 1.8;
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
