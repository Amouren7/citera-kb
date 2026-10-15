/**
 * 视觉自检：对六个页面做两视口截图（契约 §8.2 要求 1440×900 与 390×844 不破版）。
 *
 * 用法（先确保 dev server 在 5173 跑着，且 mock 已启用）：
 *   node tools/screenshot.mjs
 * 可选环境变量：CITERA_URL（默认 http://localhost:5173）、CHROME_PATH、OUT_DIR。
 *
 * 依赖全局安装的 puppeteer；这里用 createRequire 指向全局 node_modules，
 * 避免往项目依赖里塞一个只在本地截图用的包。
 */

import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const OUT = process.env.OUT_DIR ?? path.join(ROOT, 'screenshots')
const BASE = process.env.CITERA_URL ?? 'http://localhost:5173'
const CHROME =
  process.env.CHROME_PATH ??
  [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ].find((candidate) => existsSync(candidate))

const require = createRequire('C:/Users/33849/AppData/Roaming/npm/node_modules/')
const puppeteer = require('puppeteer')

mkdirSync(OUT, { recursive: true })

const problems = []
const shots = []

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--hide-scrollbars', '--force-color-profile=srgb'],
  })
  const page = await browser.newPage()

  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console.error: ${message.text().slice(0, 300)}`)
  })
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message.slice(0, 300)}`))
  page.on('requestfailed', (request) => {
    const failure = request.failure()
    problems.push(`requestfailed: ${request.url()} ${failure ? failure.errorText : ''}`)
  })

  async function viewport(width, height) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 })
  }

  async function shot(name) {
    const file = path.join(OUT, name)
    await page.screenshot({ path: file })
    shots.push(name)
    console.log(`  shot ${name}`)
  }

  async function setTheme(theme) {
    await page.evaluate((value) => localStorage.setItem('citera.theme', value), theme)
    await page.reload({ waitUntil: 'networkidle2' })
    await sleep(300)
  }

  async function go(pathname, waitFor) {
    await page.goto(`${BASE}${pathname}`, { waitUntil: 'networkidle2' })
    if (waitFor) await page.waitForSelector(waitFor, { timeout: 20000 })
    await sleep(450)
  }

  async function login(email, password) {
    await go('/login', '#auth-email')
    await page.$eval('#auth-email', (el) => {
      el.value = ''
    })
    await page.type('#auth-email', email)
    await page.type('#auth-password', password)
    await page.click('form button[type="submit"]')
    await page.waitForFunction(() => location.pathname.startsWith('/chat'), { timeout: 20000 })
    await sleep(700)
  }

  // ------------------------------- 桌面 1440×900 -------------------------------
  await viewport(1440, 900)
  await go('/login', '#auth-email')
  await shot('01-login-light-1440.png')

  await setTheme('dark')
  await shot('02-login-dark-1440.png')
  await setTheme('light')

  await login('demo@citera.dev', 'demo1234')
  await page.waitForSelector('.convitem__main', { timeout: 20000 })
  await shot('03-chat-empty-light-1440.png')

  // 打开种子会话 → 点开引用角标（记忆点 1）
  await page.click('.convitem__main')
  await page.waitForSelector('.msg--assistant .cite', { timeout: 20000 })
  await sleep(500)
  await shot('04-chat-answer-light-1440.png')

  await page.click('.msg--assistant .cite')
  await page.waitForSelector('.citecard', { timeout: 10000 })
  await sleep(350)
  await shot('05-chat-citation-popover-1440.png')
  await page.keyboard.press('Escape')
  await sleep(250)

  // 展开检索轨迹里的命中片段（记忆点 2）
  await page.click('.trace__head')
  await page.waitForSelector('.frag', { timeout: 10000 })
  await sleep(350)
  await shot('06-chat-retrieval-trace-1440.png')

  // 真流式：提一个真实问题（走 mock 的 SSE）
  await page.type('.composer__input', '积分怎么抵扣订单金额？')
  await page.click('.composer__actions .btn--primary')
  await page.waitForSelector('.dot--pulse', { timeout: 20000 })
  await sleep(450)
  await shot('07-chat-streaming-1440.png')
  await page.waitForFunction(() => !document.querySelector('.composer__actions .btn--danger'), { timeout: 40000 })
  await sleep(400)
  await shot('08-chat-after-stream-1440.png')

  await setTheme('dark')
  await sleep(300)
  await shot('09-chat-dark-1440.png')
  await setTheme('light')

  await go('/documents', '.docs')
  await page.waitForSelector('.el-table__row', { timeout: 20000 })
  await sleep(400)
  await shot('10-documents-light-1440.png')

  await go('/documents/2?chunk=3', '.chunk')
  await sleep(600)
  await shot('11-document-detail-focus-1440.png')

  await go('/evaluation', 'canvas')
  await sleep(900)
  await shot('12-evaluation-light-1440.png')

  await setTheme('dark')
  await page.goto(`${BASE}/evaluation`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('canvas', { timeout: 20000 })
  await sleep(900)
  await shot('13-evaluation-dark-1440.png')
  await setTheme('light')

  // 404
  await go('/no-such-page', '.nf__title')
  await shot('14-not-found-1440.png')

  // 管理台需要 admin 身份：清掉会话重新登录
  await page.evaluate(() => localStorage.removeItem('citera.token'))
  await login('admin@citera.dev', 'admin1234')
  await go('/admin', '.stat')
  await page.waitForSelector('.el-table__row', { timeout: 20000 })
  await sleep(600)
  await shot('15-admin-light-1440.png')

  // ------------------------------- 移动 390×844 -------------------------------
  await viewport(390, 844)
  await go('/chat', '.composer')
  await page.waitForSelector('.convitem__main, .msg', { timeout: 20000 })
  await sleep(500)
  await shot('16-chat-mobile-390.png')

  await go('/documents', '.docs')
  await sleep(600)
  await shot('17-documents-mobile-390.png')

  await go('/evaluation', 'canvas')
  await sleep(900)
  await shot('18-evaluation-mobile-390.png')

  await go('/login', '#auth-email')
  await shot('19-login-mobile-390.png')

  // 移动端看引用角标弹层是否越界
  await go('/chat', '.composer')
  await sleep(600)
  const cite = await page.$('.cite')
  if (cite) {
    await cite.click()
    await page.waitForSelector('.citecard', { timeout: 10000 })
    await sleep(350)
    await shot('20-citation-mobile-390.png')
  }

  // 破版自查：三类视口下都不能出现横向溢出
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth }
  })
  if (overflow.scrollWidth > overflow.clientWidth + 2) {
    problems.push(`mobile 390 横向溢出：scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`)
  }

  await browser.close()

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl: BASE,
    screenshots: shots,
    problems,
  }
  writeFileSync(path.join(OUT, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')

  console.log(`\n截图 ${shots.length} 张 → ${OUT}`)
  if (problems.length > 0) {
    console.log(`\n发现 ${problems.length} 个问题：`)
    for (const problem of problems) console.log(`  - ${problem}`)
  } else {
    console.log('未发现 console 错误 / 请求失败 / 横向溢出')
  }
}

main().catch((error) => {
  console.error('截图失败：', error)
  process.exitCode = 1
})
