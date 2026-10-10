# 标衡 · 标书相似性核查

前后端分离的 DOCX/PDF 标书查重系统。目录沿用 DigitalTwin 的 `server/services` 与 `web/app` 分层：FastAPI 提供分析 API，Vue 3 + TypeScript + Tailwind CSS 提供操作台。

## Windows 桌面版（Python + Electron）

桌面版复用全部现有检测功能和界面：DOCX/PDF 混合检测、招标文件排除、扫描 PDF 中文/英文 OCR、图片证据、后台进度、历史记录、CSV/JSON 导出。支持 Windows 10/11 x64。

打包产物包含 Electron、Python 3.12 解释器、Python 依赖和 Tesseract OCR 运行库、简体中文/英文模型。使用者**不需要安装 Python、Node.js、Tesseract 或 Docker**，也不需要连接后台服务器。检测在本机运行。

- `BiaoHeng-0.1.0-windows-x64-portable.exe`：单文件便携版，下载后双击即可运行。首次启动会解压随包运行库到临时目录，可能稍慢；无需安装或管理员权限。
- `BiaoHeng-0.1.0-windows-x64-setup.exe`：安装版，可以选择安装目录和创建快捷方式，同样自带运行环境。

两种版本使用相同的 `%APPDATA%\BiaoHeng\jobs` 数据目录，历史报告存于其中的 `history.sqlite3`。程序升级、便携版临时文件清理或卸载不会主动删除历史。备份时先退出应用，再复制整个 `jobs` 目录。日志位于 `%APPDATA%\BiaoHeng\logs\backend.log`。关闭窗口会结束 API、worker 和 OCR 子进程；未完成任务在下次启动重新处理，已完成结果继续保留。

### GitHub 自动生成 EXE

整个项目根目录（`server`、`web`、`desktop`、`.github`）必须处于**同一个 GitHub 仓库**。[Windows 工作流](.github/workflows/windows-exe.yml) 在推送 `main`/`master`、推送 `v*` 标签、Pull Request 或手动触发时运行。

1. 打开仓库 **Actions → Windows desktop EXE**，选择成功的运行；需要手动构建时点击 **Run workflow**。
2. 下载 **Artifacts → BiaoHeng-windows-x64-运行编号**，解压产物 ZIP。
3. 双击其中的 `*-portable.exe`；需要常规安装时运行 `*-setup.exe`。`SHA256SUMS.txt` 提供产物校验值。

构建在 Windows x64 runner 上完成，依赖使用 `uv.lock`/`pnpm-lock.yaml` 固定。OCR 引擎、语言模型及测试字体固定版本和 SHA256；测试字体只用于生成扫描夹具。流水线依次运行 Python 和 Electron 进程管理测试、构建 Vue、冻结 Python、打包 EXE，并**实际启动打包目录里的应用和最终 portable.exe**。启动验证将 PATH 限制为 Windows 系统目录，清除外部 Python/OCR 环境配置，在中文及空格目录下验证 Vue 页面、DOCX/招标文件/图片、文字 PDF、真实中文扫描 PDF OCR、重启后的历史报告及退出后的进程清理。验证失败时不上传可交付 EXE；诊断报告和日志单独保留。

更改版本时修改 `desktop/package.json` 的 `version`。默认生成未签名程序；Windows 可能显示 SmartScreen 提示，正式分发时可配置自己的代码签名证书。目前不自动上传 GitHub Release，构建产物保存在 Actions Artifacts 中。

### 桌面开发和本机打包

开发/构建机器需要 Python 3.12、uv 0.11.28、Node.js 24.18 和 pnpm 11.24；这些只用于开发和构建，不是终端用户依赖。

```bash
uv sync --project server/services/checker --frozen --group packaging
pnpm --dir web/app install --frozen-lockfile
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop dev
```

`dev` 构建 Vue，并由 Electron 自动启动源码 API 和 worker。开发模式的 PDF OCR 可以使用系统 Tesseract，或通过 `TESSERACT_CMD` 与 `TESSDATA_PREFIX` 指定引擎及中文/英文模型；Windows 打包模式始终使用随包 OCR。

在 **Windows x64** 构建机上运行以下 PowerShell 命令（`prepare-ocr.ps1` 需要完整 7-Zip 的 `7z.exe` 在 PATH 中）：

```powershell
./desktop/scripts/prepare-ocr.ps1
pnpm --dir desktop package:win
```

输出位于 `desktop/release/`。Python 使用 PyInstaller `onedir` 连解释器一起冻结，再把整个运行目录装入 Electron `extraResources`，最后封装成便携版单 EXE 或安装包。不能在 macOS/Linux 上用本机 Python 冻结产物冒充 Windows 后端；Windows 构建必须在 Windows 完成。`package:win:prepared` 供流水线在完成前端和 Python 构建后调用。

实现文件包括 `desktop/electron/`（窗口、运行进程与打包验证）、`desktop/python/checker.spec`（Python 冻结）、`checker.desktop`（桌面 API/worker 启动器）。浏览器窗口使用沙箱和上下文隔离，API 只监听随机 `127.0.0.1` 端口，拒绝外站 Origin/Host；既有 Docker 和 Web 部署保持可用。

参考：[PyInstaller 打包模式](https://pyinstaller.org/en/stable/operating-mode.html)、[Electron 安全配置](https://www.electronjs.org/docs/latest/tutorial/security/)、[electron-builder NSIS/portable](https://www.electron.build/v26/docs/nsis/)、[Tesseract 5.5.3](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3)、[tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast)。

## 服务器一键部署（Docker Compose）

服务器需要 Docker Engine 与 Docker Compose 插件，部署时只需把本项目目录放到服务器，进入项目根目录运行：

```bash
docker compose up -d --build --wait
```

默认通过 `http://服务器IP:8088/` 访问。Compose 会构建 Vue 静态资源和 Python API 镜像，并在 API 镜像中安装 Tesseract 简体中文、英文 OCR。API、独立分析 worker 和 Nginx 共用一个 Compose 项目；外部只开放 8088。后台任务使用 `checker-jobs` 卷：上传完成后即返回任务编号，页面刷新不会中断分析。上传原件在任务结束后删除；检测记录与压缩后的完整报告存入卷内 SQLite 数据库，不再按 72 小时清理。升级时会把现有卷中的旧报告导入数据库。

需要换端口或仅允许服务器本机反向代理访问时：

```bash
cp .env.example .env
# 编辑 .env 中的 HTTP_PORT 与 BIND_ADDRESS
docker compose up -d --build --wait
```

常用运维命令：

```bash
docker compose ps
docker compose logs -f --tail=100
docker compose up -d --build --wait  # 更新代码后重新构建并启动
docker compose down
```

系统目前没有内置登录与 TLS，历史记录是本服务器共用列表。正式对外使用时请在服务器现有的 HTTPS 与访问控制之后部署，并将 `.env` 的 `BIND_ADDRESS` 设为 `127.0.0.1`，由代理转发到本机 8088 端口。Nginx 已将同源 `/api/` 代理到 API 容器，反向代理应保留请求路径与上传请求体。不要用 `docker compose down -v`，否则会清除 SQLite 历史数据库和正在排队的任务；请定期备份 `checker-jobs` 卷。

## 本地开发启动

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Node.js 20.19+、pnpm。

终端一（后端）：

```bash
cd server/services/checker
uv sync
uv run uvicorn checker.api:app --reload --host 127.0.0.1 --port 8000
```

终端二（独立 worker）：

```bash
cd server/services/checker
uv run python -m checker.worker
```

终端三（前端）：

```bash
cd web/app
pnpm install
pnpm dev
```

打开 `http://127.0.0.1:5173/new`。Vite 将 `/api` 转发至本地 8000 端口。本地处理扫描 PDF 时需另行安装 Tesseract 和 `chi_sim`、`eng` 语言包；可选中文本 PDF 不依赖 OCR。生产环境需将同源 `/api/v1/checker/` 反向代理至后端，并部署 `web/app/dist`。页面路由分别为 `/new`（新建检测）、`/jobs/<任务编号>`（进度与详细报告）、`/history`（历史记录）。

## 判定口径

- 一次输入 2–12 份 `.docx` / `.pdf`，可以混合上传，自动生成全部两两组合。上传不设固定的 20 MB 单文件或 80 MB 总量限制；大文件需确保服务器有足够临时磁盘空间。PDF 和 OCR 不再设置固定页数上限，分析时间会随内容增加。
- PDF 直接用 `pdfplumber` 提取文字、`pypdf` 提取图片并保留页码，统一进入内部文档块模型，不经过 PDF→DOCX 的有损中转。扫描页使用 PDFium 渲染与 Tesseract OCR；前端可选自动识别、全部强制识别或关闭 OCR。结果列出 PDF 页数、OCR 页数和解析提示。
- 读取正文、表格、页眉和页脚文字。先做 Unicode 标准化、大小写与标点归一，再按句和长段窗口匹配。相似度阈值、最短相同字符数、短片段过滤可调整。
- 每一对提供 A/B 双向覆盖率，综合文本分数为两者的调和平均值。可展开各自的原文片段、段落位置和高亮相同字符。
- 比对工作台可按文件名搜索、筛选和排序文件对；「全文对照」展示两份文件的全部已提取文字，按匹配目录跳转到双方对应段落，并可仅看命中段落。手机上可切换 A/B 文档。
- 「相似片段」提供并排证据卡片，可定位回全文；「图片证据」单独查看完全一致和疑似相似图片。支持按匹配类型筛选、搜索文字，以及导出 CSV 摘要和完整 JSON 报告。
- 图片分为 SHA-256 字节一致、解码后像素一致、感知相似三类。前两类计入“完全一致图片”；感知哈希、颜色与纹理只提供疑似线索。图片不计入文本分数。
- 三份以上可排除全部标书共同出现的完全相同片段，减少统一模板影响；修改参数需重新分析。
- 可额外上传 1 份招标文件作为排除依据，它不进入投标文件两两组合。与招标文件连续相同达到设置长度（默认 16 字符）的文字、字节或像素一致的图片，从投标文件的覆盖率分母和重复证据中排除。全文对照用浅紫色标出排除位置，并展示各文件的排除字符、图片数量。
- `POST /api/v1/checker/jobs` 接收文件并返回 202 与任务编号；`GET /api/v1/checker/jobs/{id}` 查询进度，`GET /api/v1/checker/jobs/{id}/result` 读取完成结果，`GET /api/v1/checker/history` 按游标分页查询历史。任务详情有独立 URL，刷新后自动恢复进度；worker 在服务重启后会重新处理未完成任务。上传原件在成功或失败后清理，结果在 SQLite 中持续保留。

## 验证

```bash
cd server/services/checker && uv run pytest -q
cd web/app && pnpm build
```

## 当前边界

全文对照展示提取后的文字和位置，不还原 Word/PDF 的原始排版。PDF 多栏、复杂表格和低清晰度扫描件可能影响阅读顺序或 OCR 准确度；DOCX 形状、文本框、批注以及修订模式中未接受的文字可能未被提取。相似度是辅助筛查指标，不能单独认定抄袭；行业通用模板、法规条款和授权复用内容需要人工复核。文本匹配不截断，前端每次显示 100 条并可继续加载；图片证据列表展示前 100 组，完全一致图片总数按全部结果统计。
