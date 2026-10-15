/**
 * vue-tsc 兼容启动器。
 *
 * 背景（已实测）：契约 §2 钉死 TypeScript 7.0.2，而 TS 7 是原生移植版（tsgo），
 * 其 package.json 的 exports 不再包含 `./lib/tsc`，也没有 JS 编译器 API。
 * vue-tsc 3.x 通过 `require.resolve('typescript/lib/tsc')` 定位编译器，因此必然启动失败：
 *   Error [ERR_PACKAGE_PATH_NOT_EXPORTED]: Package subpath './lib/tsc' is not defined ...
 * pnpm 的 overrides 也无法替换 peerDependency（typescript 是 vue-tsc 的 peer）。
 *
 * 做法：为**这一个检查器进程**把 `typescript` 解析重定向到 devDependency 里的
 * `typescript-legacy`（npm:typescript@5.9.3，完整 JS 编译器 API）。
 *  - 项目编译器仍是 7.0.2（`npm run typecheck:ts` 用 tsc 7 独立跑一遍 .ts 检查）
 *  - `npm run typecheck:vue` 只用于补充 .vue / SFC 模板里的类型检查
 * 这是工具链适配，不改动任何业务代码，也不改变契约 §2 的依赖版本。
 */

const path = require('node:path')
const Module = require('node:module')

const legacyRoot = path.dirname(require.resolve('typescript-legacy/package.json'))

const originalResolve = Module._resolveFilename
Module._resolveFilename = function resolveFilename(request, parent, isMain, options) {
  if (request === 'typescript') {
    return path.join(legacyRoot, 'lib', 'typescript.js')
  }
  if (typeof request === 'string' && request.startsWith('typescript/')) {
    // 形如 typescript/lib/tsc → <legacyRoot>/lib/tsc（sub 已含 lib 前缀）
    return path.join(legacyRoot, request.slice('typescript/'.length))
  }
  return originalResolve.call(this, request, parent, isMain, options)
}

require('vue-tsc/bin/vue-tsc.js')
