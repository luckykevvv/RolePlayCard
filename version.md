# RolePlayCard 0.0.1 版本日志

发布日期：2026-04-21

## 一、框架与技术栈

### 1) 桌面端与前端
- Electron `^35.1.4`（桌面应用容器）
- Vue `^3.5.13`（界面框架）
- Vite `^6.2.3`（前端构建与开发服务器）
- TypeScript `^5.8.2`（类型系统）

### 2) 后端服务
- Python（本地服务运行时）
- Flask `3.1.0`（HTTP API）
- Pillow `11.1.0`（图像处理与 PNG 元数据写入）

### 3) 开发与工程工具
- concurrently `^9.1.2`（并行启动多进程）
- wait-on `^8.0.3`（等待端口/构建产物就绪）
- cross-env `^7.0.3`（跨平台环境变量）
- pytest `8.3.5`（Python 测试）

## 二、功能清单

### 1) 角色卡编辑器（Vue + Electron）
- 角色描述字段编辑：
  - `profile.name` / `profile.age` / `profile.gender`
  - `profile.appearance` / `profile.personality` / `profile.speakingStyle` / `profile.background`
- 首屏信息字段编辑：
  - `opening.greeting` / `opening.scenario` / `opening.exampleDialogue` / `opening.firstMessage`
- 世界书编辑：`worldBook`
- 插图信息编辑：
  - `illustration.stylePrompt` / `illustration.promptSnapshot` / `illustration.negativePrompt`

### 2) 草稿管理
- 新建草稿（自动生成 `id`、时间戳）
- 草稿列表展示（按更新时间排序）
- 打开草稿
- 保存草稿
- 另存为草稿（生成新 `id`）
- 自动保存（字段变更后延迟触发）

### 3) AI 文本能力
- 字段级 AI 生成（`generate`）
- 字段级 AI 改写（`rewrite`）
- 自动拼接上下文（角色设定 + 首屏信息 + 世界书摘要）
- 输出清洗（移除多余标记，返回可直接粘贴内容）

### 4) AI 图像能力
- 本地图片上传并预览
- 自动生成绘图提示词（Prompt + Negative Prompt）
- 文生图生成角色插图
- 生成图写入本地缓存目录并回填到草稿

### 5) Provider 配置与连通性
- 文本 Provider：`mock` / `openai_compatible`
- 图像 Provider：`mock` / `openai_compatible`
- 可配置项：
  - `baseUrl` / `apiKey` / `model` / `timeoutMs` / `temperature`
- 配置连通性测试（文本与图像分别校验）

### 6) TavernAI 角色卡导出
- 导出前校验：
  - 必填角色名
  - 必填首条消息
  - 必选导出图片
- 自动将输入图像转换为 PNG
- 向 PNG 写入 Tavern 兼容元数据：
  - `chara`（Base64 JSON）
  - `roleplaycard`（完整草稿 JSON）
- 导出目标路径由系统保存对话框选择

### 7) 本地数据存储
- `settings.json`：应用配置
- `drafts/*.json`：角色草稿
- `cache/images/*`：生成图缓存
- `logs/*`：日志目录占位

### 8) IPC 与后端 API
- Electron IPC：
  - `app.info`
  - `settings.get` / `settings.set` / `settings.test`
  - `draft.list` / `draft.load` / `draft.save` / `draft.saveAs`
  - `ai.generateField` / `ai.generateImagePrompt` / `ai.generateImage`
  - `card.export`
  - `files.pickImage` / `files.pickExportPath`
- Flask API：
  - `GET /health`
  - `GET /settings`
  - `POST /settings`
  - `POST /settings/test`
  - `GET /drafts`
  - `GET /drafts/<draft_id>`
  - `POST /drafts`
  - `POST /ai/field`
  - `POST /ai/image-prompt`
  - `POST /ai/image`
  - `POST /card/export`

### 9) 测试覆盖（当前）
- 草稿保存与读取测试
- 导出 PNG 元数据写入与可读性测试

## 三、0.0.1 目标总结
- 完成“本地桌面编辑 + AI 辅助生成 + TavernAI PNG 导出”的首个可用闭环版本。
