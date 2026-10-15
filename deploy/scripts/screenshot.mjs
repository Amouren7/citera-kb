/**
 * Citera · 真实环境截图脚本（给 README 用）
 *
 * 产出（默认写到 docs/screenshots/）：
 *   01-chat.png            问答页：回答 + 引用角标 + 命中片段
 *   02-documents.png       文档库（种子文档列表）
 *   03-evaluation.png      评测对比（三种模式指标）
 *   04-document-detail.png 文档详情（切块预览）
 *   00-login.png           登录页（顺带）
 *
 * 为什么用 Playwright 而不是服务端截图：问答页要真登录、真发一次 SSE 提问，
 * 才能截到"引用角标"这个项目最想展示的东西。
 *
 * 用法：
 *   1) 先把应用跑起来：docker compose -f deploy/docker-compose.yml up -d --build
 *   2) 装一次 Playwright（放在仓库外，避免污染前端依赖）：
 *        mkdir /tmp/pw && cd /tmp/pw && npm i playwright && npx playwright install chromium
 *      Windows:  mkdir D:\temp\pw ; cd D:\temp\pw ; npm i playwright ; npx playwright install chromium
 *   3) 运行（用 PLAYWRIGHT_HOME 指向步骤 2 的目录）：
 *        PLAYWRIGHT_HOME=/tmp/pw node deploy/scripts/screenshot.mjs --base-url http://localhost:8000
 *      Windows:  $env:PLAYWRIGHT_HOME='D:\temp\pw'; node deploy\scripts\screenshot.mjs
 *
 * 说明：前端选择器可能随 UI 调整而变化，脚本对关键控件做了多路兜底，
 * 抓不到时会打印告警并继续截剩下的图，不会整体失败。
 */

import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const args = new Map()
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, '')
  args.set(key, process.argv[i + 1])
}

const BASE_URL = (args.get('base-url') || 'http://localhost:8000').replace(/\/$/, '')
const OUT_DIR = path.resolve(args.get('out') || 'docs/screenshots')
const EMAIL = args.get('email') || 'demo@citera.dev'
const PASSWORD = args.get('password') || 'demo1234'
const QUESTION = args.get('question') || '整机保修期是多久？'
const VIEWPORT = { width: 1440, height: 900 }
const log = (msg) => console.log(`[screenshot] ${msg}`)
const warn = (msg) => console.warn(`[screenshot] ⚠️ ${msg}`)

/** 依次尝试多种方式加载 playwright（仓库外安装很常见） */
async function loadPlaywright() {
  const home = process.env.PLAYWRIGHT_HOME || args.get('playwright-home')
  const candidates = [
    'playwright',
    process.env.PLAYWRIGHT_MODULE,
    home ? pathToFileURL(path.join(home, 'node_modules', 'playwright', 'index.mjs')).href : null,
    home ? pathToFileURL(path.join(home, 'node_modules', 'playwright-core', 'index.mjs')).href : null,
  ].filter(Boolean)

  for (const candidate of candidates) {
    try {
      return await import(candidate)
    } catch {
      /* 试下一个 */
    }
  }
  throw new Error(
    '找不到 playwright。请先安装，并用 PLAYWRIGHT_HOME 指向安装目录：\n' +
      '  mkdir D:\\temp\\pw ; cd D:\\temp\\pw ; npm i playwright ; npx playwright install chromium\n' +
      '  $env:PLAYWRIGHT_HOME=\'D:\\temp\\pw\' ; node deploy\\scripts\\screenshot.mjs',
  )
}

/** 多点兜底点击：任一命中即可 */
async function clickAny(page, selectors, label) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first()
    try {
      if ((await locator.count()) > 0 && (await locator.isVisible())) {
        await locator.click({ timeout: 4000 })
        return true
      }
    } catch {
      /* 试下一个 */
    }
  }
  warn(`点不到「${label}」（试过：${selectors.join(' | ')}）`)
  return false
}

/** 多点兜底填值 */
async function fillAny(page, selectors, value, label) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first()
    try {
      if ((await locator.count()) > 0) {
        await locator.fill(value, { timeout: 4000 })
        return true
      }
    } catch {
      /* 试下一个 */
    }
  }
  warn(`填不了「${label}」（试过：${selectors.join(' | ')}）`)
  return false
}

async function shot(page, name) {
  const file = path.join(OUT_DIR, name)
  await page.screenshot({ path: file, fullPage: false })
  log(`已保存 ${path.relative(process.cwd(), file)}`)
  return file
}

async function main() {
  const { chromium } = await loadPlaywright()
  await mkdir(OUT_DIR, { recursive: true })

  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] })
  const context = await browser.newContext({ viewport: VIEWPORT, locale: 'zh-CN', deviceScaleFactor: 1 })
  const page = await context.newPage()
  const saved = []

  try {
    // ---- 登录页 -----------------------------------------------------------
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() =>
      warn('/login 打不开，尝试首页'),
    )
    await page.waitForTimeout(1500)
    saved.push(await shot(page, '00-login.png'))

    // ---- 登录（用登录页自带的「演示账号 点一下自动填入」按钮，最稳）--------
    const filled = await clickAny(
      page,
      [`button:has-text("${EMAIL}")`, 'button:has-text("演示用户")', 'button:has-text("自动填入")'],
      '演示账号自动填入',
    )
    if (!filled) {
      await fillAny(page, ['input[type="email"]', 'input[placeholder*="邮箱"]'], EMAIL, '邮箱')
      await fillAny(page, ['input[type="password"]'], PASSWORD, '密码')
    }
    await page.waitForTimeout(600)

    // ⚠️ 登录页上「登录」同时是 tab 文案，必须点 submit 按钮，不能按文本点
    const submitted = await clickAny(
      page,
      ['button[type="submit"]', 'button.btn--primary:has-text("登录")', '.btn--primary:has-text("登录")'],
      '登录提交按钮',
    )
    if (!submitted) await page.keyboard.press('Enter')

    // 等真正离开 /login，而不是干等固定时长
    await page
      .waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 })
      .catch(() => warn(`登录后仍停在 ${page.url()}（后续截图可能只有登录页）`))
    await page.waitForTimeout(1500)
    if (!page.url().includes('/login')) log(`登录成功 → ${page.url()}`)

    // ---- 问答页：真发一个问题，等引用出来 ---------------------------------
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(1500)

    const typed = await fillAny(
      page,
      ['textarea', 'input[placeholder*="问"]', 'input[placeholder*="输入"]', '[contenteditable="true"]'],
      QUESTION,
      '提问输入框',
    )
    if (typed) {
      await page.keyboard.press('Enter')
      log(`已提问「${QUESTION}」，等待检索+合成（最多 20s）...`)
      // 优先等"引用角标/命中片段"出现；抓不到就退化为固定等待
      await page
        .locator('[class*="citation"], [class*="cite"], sup, [class*="retriev"], [class*="chunk"]')
        .first()
        .waitFor({ timeout: 20000 })
        .catch(() => warn('没等到引用元素，按固定时长等待后截图'))
      await page.waitForTimeout(2500)
    }
    saved.push(await shot(page, '01-chat.png'))

    // ---- 文档库 -----------------------------------------------------------
    await page.goto(`${BASE_URL}/documents`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(2500)
    saved.push(await shot(page, '02-documents.png'))

    // ---- 文档详情（点列表第一行）------------------------------------------
    const opened = await clickAny(
      page,
      [
        'button:has-text("查看块")',
        'a[href^="/documents/"]',
        'tbody tr:first-child',
        'table tbody tr',
      ],
      '文档「查看块」入口',
    )
    await page.waitForTimeout(2500)
    saved.push(await shot(page, opened ? '04-document-detail.png' : '04-document-detail.png'))

    // ---- 评测页：跑一次三种模式对比 ---------------------------------------
    await page.goto(`${BASE_URL}/evaluation`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(2000)
    const ran = await clickAny(
      page,
      ['button:has-text("运行评测")', 'button.btn--primary.btn--lg:has-text("运行")', 'button:has-text("运行")'],
      '运行评测按钮',
    )
    if (ran) {
      log('已触发评测，等待结果...')
      // 评测是同步接口，本地只需百毫秒级
      await page
        .locator('[class*="runrow"], [class*="history"], canvas')
        .first()
        .waitFor({ timeout: 25000 })
        .catch(() => warn('没等到评测结果元素，按固定时长等待'))
      await page.waitForTimeout(2000)

      // 「指标对比」柱状图只在勾选了可比 run 之后才渲染（store.metricRows 来自 selectedRunIds）：
      // 先点页面自带的「只选各模式最新一次」，若图表没出来就直接点历史运行行（= toggleRun 兜底）
      await clickAny(
        page,
        ['button:has-text("只选各模式最新一次")', 'button:has-text("各模式最新")'],
        '只选各模式最新一次',
      )
      await page.waitForTimeout(1800)

      const chartVisible = async () =>
        page
          .locator('div.chart canvas, canvas')
          .first()
          .isVisible()
          .catch(() => false)

      if (!(await chartVisible())) {
        const rows = page.locator('button[class*="runrow__main"]')
        const count = Math.min(await rows.count().catch(() => 0), 3)
        log(`兜底：直接勾选历史运行前 ${count} 行（每种模式一行）`)
        for (let i = 0; i < count; i += 1) {
          await rows.nth(i).click({ timeout: 4000 }).catch(() => {})
          await page.waitForTimeout(400)
        }
      }

      await page
        .locator('div.chart canvas, canvas')
        .first()
        .waitFor({ timeout: 15000 })
        .catch(() => warn('对比图表仍未渲染，截图将只含历史运行表'))
      await page.waitForTimeout(2000)
      log('已勾选各模式 run，对比图表应已渲染')
    }
    saved.push(await shot(page, '03-evaluation.png'))
  } finally {
    await browser.close()
  }

  await writeFile(
    path.join(OUT_DIR, 'index.json'),
    JSON.stringify({ baseUrl: BASE_URL, viewport: VIEWPORT, question: QUESTION, files: saved }, null, 2),
    'utf8',
  )
  log(`完成，共 ${saved.length} 张 → ${OUT_DIR}`)
  log('把需要的图贴进 README.md 的截图区（文件名已对应好）。')
}

main().catch((error) => {
  console.error(`[screenshot] 失败：${error.message}`)
  process.exit(1)
})
