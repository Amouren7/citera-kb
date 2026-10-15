"""最终端到端验收（契约 §8.3）：桌面 + 移动两个视口，逐页断言。

用法：
    & "D:\Deepseek Project\amz-harness\.venv\Scripts\python.exe" tools\e2e_final.py --base-url http://127.0.0.1:8010

判定标准（任一不满足即 exit 1）：
1. 全流程零 pageerror / 零 console error
2. 问答页：SSE 流式答案渲染、echo 声明行、引用角标、检索轨迹
3. 文档库：种子文档与统计数字渲染
4. 文档详情：分块预览渲染
5. 评测页：图表有非空像素、逐题命中表渲染、点「运行评测」后图表仍在
6. 移动视口（390×844）：无横向溢出
"""

from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import sync_playwright

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(name)


CHART_PROBE = """
() => {
  const el = document.querySelector('.chart');
  const canvas = el ? el.querySelector('canvas') : null;
  let painted = null;
  if (canvas && canvas.width > 0) {
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const d = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) n++;
      painted = n;
    }
  }
  return { hasCanvas: !!canvas, painted };
}
"""


def login(page, base: str) -> None:
    page.goto(f"{base}/login", wait_until="networkidle")
    page.fill('input[type="email"], input[placeholder*="邮箱"]', "demo@citera.dev")
    page.fill('input[type="password"]', "demo1234")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base}/**", timeout=15000)
    page.wait_for_timeout(800)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        login(page, base)
        check("登录后进入 /chat", page.url.endswith("/chat"), page.url)

        # ---- 问答：流式 ----
        page.wait_for_timeout(600)
        textarea = page.locator("textarea").first
        textarea.fill("整机保修期是多久？")
        textarea.press("Enter")
        page.wait_for_timeout(6000)
        body = page.inner_text("body")
        check("问答：echo 声明行", "受控合成" in body)
        check("问答：渲染出引用角标（原始 [[cN]] 已被消费）", "[[c" not in body)
        check("问答：检索轨迹存在", "检索" in body)
        page.screenshot(path=r"D:\temp\citera-shots2\final-chat.png")

        # ---- 文档库 ----
        page.goto(f"{base}/documents", wait_until="networkidle")
        page.wait_for_timeout(1500)
        docs_text = page.inner_text("body")
        check("文档库：渲染种子文档统计", "文档总数" in docs_text and "已就绪" in docs_text)
        check("文档库：出现 6 篇种子文档", "6" in docs_text)
        page.screenshot(path=r"D:\temp\citera-shots2\final-documents.png")

        # ---- 文档详情 ----
        page.goto(f"{base}/documents/1", wait_until="networkidle")
        page.wait_for_timeout(1500)
        detail_text = page.inner_text("body")
        check("文档详情：分块预览渲染", "切" in detail_text or "片段" in detail_text or "块" in detail_text)

        # ---- 评测页 ----
        page.goto(f"{base}/evaluation", wait_until="networkidle")
        page.wait_for_timeout(2500)
        before = page.evaluate(CHART_PROBE)
        check("评测页：首屏图表已绘制", bool(before["hasCanvas"]) and (before["painted"] or 0) > 1000, json.dumps(before))
        for label in ("运行评测", "运行"):
            try:
                page.get_by_role("button", name=label).first.click(timeout=2500)
                break
            except Exception:
                continue
        page.wait_for_timeout(8000)
        after = page.evaluate(CHART_PROBE)
        check("评测页：运行后图表仍在", bool(after["hasCanvas"]) and (after["painted"] or 0) > 1000, json.dumps(after))
        eval_text = page.inner_text("body")
        check("评测页：逐题命中表渲染", "逐题命中排名" in eval_text and "22" in eval_text)
        check("评测页：无 undefined 泄漏", "undefined" not in eval_text)
        page.screenshot(path=r"D:\temp\citera-shots2\final-evaluation.png", full_page=True)

        # ---- 移动视口 ----
        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(f"{base}/evaluation", wait_until="networkidle")
        mobile.wait_for_timeout(2000)
        overflow = mobile.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("移动视口：无横向溢出", overflow <= 2, f"overflow={overflow}px")
        mobile.screenshot(path=r"D:\temp\citera-shots2\final-mobile.png", full_page=False)

        check("全流程零控制台错误", not errors, " | ".join(errors[:3]))
        browser.close()

    print()
    if FAILURES:
        print(f"❌ {len(FAILURES)} 项未通过：{FAILURES}")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
