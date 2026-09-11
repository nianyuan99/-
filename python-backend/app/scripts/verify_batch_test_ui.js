/**
 * 批量测试页 + 场景管理页 浏览器端验证脚本（Playwright）
 *
 * 为什么需要浏览器验证：前端的进度推送走的是 sockjs-client + @stomp/stompjs，
 * 协议细节（SockJS 握手路径、'a' 帧类型前缀、STOMP MESSAGE 帧）只有在真实浏览器里
 * 才能确认与 Python 手写的协议实现对得上。
 *
 * 流程：注册并登录 → 创建场景（UI）→ 批量测试页创建任务（UI）→
 *       观察 WebSocket 帧与进度条 → 查看报告 → 统计页 / 模型管理页 → 截图
 *
 * 前置条件：
 *   1. 后端已在 127.0.0.1:9090 运行
 *   2. 前端 dev server 已在 localhost:5173 运行
 *   3. 在安装了 playwright + chromium 的环境下用 node 直接执行本脚本
 *
 * 用法：
 *   SHOT_DIR=<截图输出目录> node app/scripts/verify_batch_test_ui.js
 *
 * 注意：脚本会真实调用模型（默认 2 个免费模型 × 2 条提示词 = 4 次调用），
 * 请使用免费模型，避免消耗额度。
 */

const { chromium } = require('playwright')
const fs = require('fs')

const FRONTEND = 'http://localhost:5173'
const BACKEND = 'http://localhost:9090'
const SHOT_DIR = process.env.SHOT_DIR || '.'

const account = `uitest_${Math.floor(Math.random() * 900000 + 100000)}`
const password = '12345678'

const results = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '[PASS]' : '[FAIL]'} ${name}${detail ? ' -> ' + detail : ''}`)
  results.push({ name, ok, detail })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1560, height: 1000 } })
  const page = await context.newPage()

  // 记录控制台与 WebSocket 帧，用于确认 STOMP 链路真的通了
  // 注意：Vite 的 devtools / HMR 也会开 WebSocket，必须按 URL 过滤出连后端 /ws 的那条
  const consoleErrors = []
  const wsFrames = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
    if (msg.type() === 'warning' && msg.text().includes('ant-design-vue')) {
      consoleErrors.push('vue-warning: ' + msg.text())
    }
  })
  page.on('pageerror', (err) => consoleErrors.push('pageerror: ' + err.message))
  // 抓所有 console（含 debug）用于定位订阅问题，同时单独收集 error 级别
  const allLogs = []
  page.on('console', (msg) => allLogs.push(`[${msg.type()}] ${msg.text()}`))
  page.on('websocket', (ws) => {
    const isBackend = ws.url().includes(':9090/ws')
    const entry = { url: ws.url(), isBackend, frames: [] }
    wsFrames.push(entry)
    ws.on('framesent', (f) => entry.frames.push({ dir: 'sent', payload: String(f.payload) }))
    ws.on('framereceived', (f) => entry.frames.push({ dir: 'recv', payload: String(f.payload) }))
  })

  // ---------- 1. 注册 + 登录（走真实 UI 与接口） ----------
  // 先打开前端页面：在页面上下文里 fetch 才是同源请求，避免跨域预检问题
  await page.goto(`${FRONTEND}/user/register`)
  await page.waitForTimeout(1500)

  const registerBody = await page.evaluate(
    async ([base, acc, pwd]) => {
      const res = await fetch(`${base}/api/user/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ userAccount: acc, userPassword: pwd, checkPassword: pwd }),
      })
      return res.json()
    },
    [BACKEND, account, password],
  )
  check('注册测试账号', registerBody.code === 0, JSON.stringify(registerBody).slice(0, 120))

  await page.goto(`${FRONTEND}/user/login`)
  await page.waitForSelector('input[placeholder*="请输入账号"]', { timeout: 15000 })
  await page.fill('input[placeholder*="请输入账号"]', account)
  await page.fill('input[placeholder*="请输入密码"]', password)
  await page.click('button[type="submit"]')
  await page.waitForTimeout(3000)

  // 用接口确认登录态（比看页面文案可靠）
  const loginState = await page.evaluate(async (base) => {
    const res = await fetch(`${base}/api/user/get/login`, { credentials: 'include' })
    return res.json()
  }, BACKEND)
  check(
    '通过登录页登录成功',
    loginState.code === 0 && loginState.data?.userAccount === account,
    JSON.stringify(loginState).slice(0, 140),
  )

  // ---------- 2. 场景管理页：创建场景 + 添加提示词 ----------
  await page.goto(`${FRONTEND}/scene-manage`)
  await page.waitForSelector('text=场景管理', { timeout: 15000 })
  await page.waitForTimeout(1500)

  const sceneName = `UI验证场景-${Date.now() % 100000}`
  await page.click('button:has-text("创建场景")')
  await page.waitForSelector('.ant-modal-content input', { timeout: 10000 })
  await page.fill('.ant-modal-content input', sceneName)
  await page.fill('.ant-modal-content textarea', '浏览器端验证用场景')
  await page.click('.ant-modal-footer button.ant-btn-primary')
  await page.waitForTimeout(2000)
  const sceneRows = await page.locator('table tbody tr').count()
  check('创建场景后列表有数据', sceneRows > 0, `${sceneRows} 行`)
  await page.screenshot({ path: `${SHOT_DIR}/browser-scene-manage.png`, fullPage: true })

  // 打开提示词管理弹窗并添加 2 条提示词
  const row = page.locator('table tbody tr', { hasText: sceneName })
  await row.locator('button:has-text("管理提示词")').click()
  await page.waitForTimeout(1500)

  for (const [title, content] of [
    ['UI自我介绍', '请用一句话介绍你自己，不要超过 30 个字。'],
    ['UI简单算术', '3 加 5 等于几？只回答数字。'],
  ]) {
    await page.click('button:has-text("添加提示词")')
    await page.waitForTimeout(800)
    const modal = page.locator('.ant-modal-content').last()
    await modal.locator('input').first().fill(title)
    await modal.locator('textarea').first().fill(content)
    await modal.locator('.ant-modal-footer button.ant-btn-primary').click()
    await page.waitForTimeout(1200)
  }
  const promptRows = await page.locator('.ant-modal-content table tbody tr').count()
  check('添加提示词成功', promptRows >= 2, `${promptRows} 行`)
  await page.screenshot({ path: `${SHOT_DIR}/browser-scene-prompts.png`, fullPage: true })

  // ---------- 3. 批量测试页：创建任务并观察 WebSocket 进度 ----------
  await page.goto(`${FRONTEND}/batch-test`)
  await page.waitForSelector('text=创建批量测试任务', { timeout: 15000 })
  await page.waitForTimeout(2000)

  // 填任务名称
  await page.fill('input[placeholder*="任务名称"]', 'UI 验证任务')

  // 选择场景（antd Select：点 .ant-select-selector 打开下拉，再点可见选项）
  // 注意：直接点 .ant-select 有可能被隐藏的内部 input 吃掉点击，
  // 所以统一点 .ant-select-selector；选项必须加 :visible，否则会命中历史隐藏下拉
  await page.locator('.ant-select-selector').first().click()
  await page.waitForTimeout(1000)
  await page
    .locator('.ant-select-item-option:visible', { hasText: sceneName })
    .first()
    .click()
  await page.waitForTimeout(500)

  // 选择两个免费模型（支持搜索的多选下拉：输入模型 ID → 回车选中）
  const modelSelector = page.locator('.ant-select-selector').nth(1)
  for (const keyword of ['nemotron-3-ultra', 'nex-n2.5-mini']) {
    await modelSelector.click()
    await page.waitForTimeout(800)
    await page.keyboard.type(keyword, { delay: 30 })
    await page.waitForTimeout(2000)
    const optionCount = await page.locator('.ant-select-item-option:visible').count()
    if (optionCount === 0) {
      console.log(`[WARN] 关键词 ${keyword} 没有可见下拉选项`)
      break
    }
    await page.keyboard.press('Enter')
    await page.waitForTimeout(800)
  }
  await page.keyboard.press('Escape')
  await page.waitForTimeout(800)

  // 确认已选中的模型标签数量，避免「模型为空」导致创建接口直接报参数错误
  const selectedTags = await page.locator('.ant-select-selection-item').count()
  check('已选中场景与模型标签', selectedTags >= 3, `${selectedTags} 个标签`)

  await page.click('button:has-text("创建测试任务")')
  await page.waitForSelector('text=任务进度', { timeout: 20000 })
  check('创建任务后出现进度卡片', true)

  // 等几秒让 WebSocket 完成连接与订阅，便于观察帧
  await page.waitForTimeout(6000)

  // 等待任务结束（最多 4 分钟；免费模型较慢，2 个模型 × 2 条提示词）
  // 进度判定不只看 a-progress 文本：任务结束时进度卡片会被状态标签替换，
  // 因此同时接受「进度 100%」与「已完成/失败/已取消」两种终态信号
  let finished = false
  let lastProgressText = ''
  for (let i = 0; i < 120; i += 1) {
    await page.waitForTimeout(2000)
    lastProgressText = await page
      .locator('.ant-progress-text')
      .first()
      .innerText()
      .catch(() => '')
    if (lastProgressText.includes('100')) {
      finished = true
      break
    }
    const pageText = await page.locator('.batch-test-page').innerText()
    if (pageText.includes('查看报告')) {
      finished = true
      lastProgressText = '查看报告按钮已出现'
      break
    }
  }

  const backendSockets = wsFrames.filter((f) => f.isBackend)
  const backendFrames = backendSockets.flatMap((f) => f.frames)
  const stompConnect = backendFrames.some((f) => f.dir === 'sent' && f.payload.includes('CONNECT'))
  const stompSubscribe = backendFrames.some((f) => f.dir === 'sent' && f.payload.includes('SUBSCRIBE'))
  const stompMessage = backendFrames.some((f) => f.dir === 'recv' && f.payload.includes('MESSAGE'))

  check('浏览器建立了到后端 /ws 的 WebSocket 连接', backendSockets.length > 0, `${backendSockets.length} 条`)
  check('发出了 STOMP CONNECT 帧', stompConnect)
  check('发出了 STOMP SUBSCRIBE 帧（订阅任务主题）', stompSubscribe)
  check('收到 STOMP MESSAGE 进度帧', stompMessage, `${backendFrames.length} 个帧`)
  check('任务在页面上跑到 100%', finished, `最后进度=${lastProgressText}`)
  await page.screenshot({ path: `${SHOT_DIR}/browser-batch-progress.png`, fullPage: true })

  // ---------- 4. 查看报告 ----------
  await page.click('button:has-text("查看报告")')
  await page.waitForTimeout(2500)
  const resultRows = await page.locator('table tbody tr').count()
  check('报告表格有结果行', resultRows > 0, `${resultRows} 行`)
  await page.screenshot({ path: `${SHOT_DIR}/browser-batch-report.png`, fullPage: true })

  // ---------- 5. 数据统计页 ----------
  await page.goto(`${FRONTEND}/statistics`)
  await page.waitForTimeout(2500)
  const statText = await page.locator('.statistics-page').innerText()
  check('统计页渲染核心指标', statText.includes('测试任务') && statText.includes('累计 Token'))
  await page.screenshot({ path: `${SHOT_DIR}/browser-statistics.png`, fullPage: true })

  // ---------- 6. 模型管理页 ----------
  await page.goto(`${FRONTEND}/model-manage`)
  await page.waitForTimeout(2500)
  const modelRows = await page.locator('table tbody tr').count()
  check('模型管理页有模型数据', modelRows > 0, `${modelRows} 行`)
  await page.screenshot({ path: `${SHOT_DIR}/browser-model-manage.png`, fullPage: true })

  check('页面无 console 错误', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))

  fs.writeFileSync(
    `${SHOT_DIR}/browser-check-result.json`,
    JSON.stringify({ account, results, wsFrames, consoleLogs: allLogs.slice(-60) }, null, 2),
  )

  await browser.close()

  const failed = results.filter((r) => !r.ok)
  console.log(`\n通过 ${results.length - failed.length}/${results.length}`)
  return failed.length === 0 ? 0 : 1
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error('脚本异常:', err)
    process.exit(1)
  })
