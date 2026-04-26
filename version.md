# RolePlayCard 版本日志

## 1.1.1（2026-04-27）

### Web 多用户隔离修复（公网部署重点）
- 草稿接口改为按 `X-Client-Id` 隔离：`/api/drafts`、`/api/drafts/<id>`、`/api/drafts/clear` 只操作当前客户端空间。
- 后端新增 `X-Client-Id` 校验（缺失或非法直接拒绝），避免匿名共享数据目录导致“全员可见草稿”。
- 草稿存储从单目录改为“按 client_id 哈希分桶”，并新增测试覆盖“用户 A/B 相互不可见、清空仅影响当前用户”。

### 设置持久化改造（避免用户配置交叉）
- 前端设置改为浏览器 `localStorage` 主存储（并兼容迁移旧 Cookie）。
- 前端不再依赖服务端全局 settings 落盘；后端 settings 接口改为无状态返回，防止公网多用户配置互相覆盖。
- AI 请求继续使用前端携带的 `settings`，用户配置保持浏览器级隔离。

### 生成质量与稳定性补强
- 调整提示词：首屏信息、地点设定、时间线节点改为“详细且自包含”，避免依赖原文才能理解。
- 分段/整文 AI 调用超时统一遵循 UI `timeoutMs` 设置，不再受前端固定 60s 限制。

### 测试与构建
- `python -m pytest python-service/tests` 通过（38 tests）。
- `npm run test -w vue-renderer` 通过（4 tests）。
- `npm run typecheck -w vue-renderer` 与 `npm run build -w vue-renderer` 通过。

## 1.1.0（2026-04-26）

### 长篇分段增量（默认手动）上线
- 新增 `POST /api/ai/story-segments/preview` 与 `POST /api/ai/card-from-story-segment`，支持“分段预览 -> 当前段生成 -> 下一段增量更新”流程。
- 分段策略支持章节优先 + 20000 字硬切 fallback，并可在 UI 中直接编辑章节识别正则。
- 章节识别默认规则补齐 `幕` 等常见格式；支持修正误写内联 flag（如 `(?:imx)`）。

### 增量合并策略升级（避免重复、支持更新）
- 角色、地点、首屏、时间线由“只追加”改为“增量 upsert”：
  - 已存在条目支持更新字段与关键词并集。
  - 名称别名去重能力增强（如“中文名(英文名)”与简称归并）。
- 时间线节点支持跨段去重、ID 防冲突重写与根节点桥接判断，减少分段后断裂与重复。

### 首屏与结构化生成稳定性提升
- 分段模式引入更短、更稳的结构化提示词，降低模型 JSON 截断概率。
- 结构化 JSON 解析器增强：支持 `json\\n{{...}}` 前缀与混杂文本中的首个完整 JSON 提取。
- 增加结构化生成重试机制；分段模式下角色生成默认走种子信息，减少失败率与耗时。
- 当 outline 未返回可用 openings 时，自动生成首屏 fallback，避免“首屏空白”。

### 时间线系统（商业化编辑体验增强）
- 时间线时间轴统一到单一基准：`T0=当前主线时刻`，并统一 `timePoint` 格式为 `T±<offset> | 时间描述`。
- 新增 `POST /api/ai/timeline/organize`：
  - 由 LLM 生成“时间线整理提案（重排+重写+校时）”。
  - 前端支持“采用提案 / 保留当前时间线”，不会强制覆盖。
- 时间线编辑支持拖拽重排父子从属：
  - 可将节点拖到其他节点下挂载为子节点。
  - 可拖到根节点投放区设为根。
  - 通过父节点下拉修改从属时，会携带整棵子树一起移动。
- 节点字段加入长度约束与自动压缩，明显提升时间线可读性。

### 类型、接口与测试
- `TimelineInfo` 新增 `timeBaseline`、`timeFormat` 字段；共享类型增加时间线整理请求/响应结构。
- 后端测试覆盖扩展至时间轴统一、时间断层断根、自动整理提案等场景。
- 当前测试与构建结果：
  - `python -m pytest python-service/tests` 通过（33 tests）
  - `npm run build` 通过

## 1.0.1（2026-04-24）

### 短篇小说入口强化
- 编辑器顶部新增“短篇小说一键生成”主入口卡片，突出“根据短篇小说生成可游玩角色卡”定位。
- 一键生成输入框、`txt` 上传与触发按钮统一上移到最上方。
- 侧边栏标题与状态文案统一为“短篇小说”语义。

### 时间线可视化与结构约束
- 时间线新增图形化展示（节点+连线），支持点击图上节点联动编辑。
- 时间线图缩小并优化间距，提升多节点时可读性。
- 时间线列表显式标注父子结构（根节点/子节点及父节点名称）。
- 剧情节点生成规则升级：
  - 时间最前节点固定为根节点
  - 时间向后默认链式推进（后一个是前一个子节点）
  - 同一时间点并行节点自动形成分叉。

### 玩家扮演角色
- 角色新增“玩家扮演”单选开关（同一时间仅一个）。
- 导出时将该角色映射为 `{{user}}`，并保留外貌、性格、背景等设定内容。
- 导出主角色优先选择非玩家角色，避免把玩家角色当作 NPC 主体。

### 测试与校验
- 后端测试扩展到时间线分叉与玩家角色导出映射。
- `python -m pytest python-service/tests` 与 `npm run typecheck` 均通过。

## 1.0.0（2026-04-24）

### 一键生成与剧情结构
- 一键生成改为两阶段流程：
  - 先基于全文生成 `outline + openings + locations + plot progression`
  - 再按角色逐个调用生成角色信息。
- 角色生成强制参考全文，不再截断文本。
- 新增“剧情推进”结构化节点能力，支持从故事中提取可执行的主线推进节点。

### 时间线系统（独立编辑）
- 新增独立“时间线（剧情推进）”编辑单元，不再与普通世界书条目混编。
- 时间线支持节点增删改、父子树结构、节点顺序调整。
- 历史草稿中世界书“剧情推进”条目会自动迁移到时间线。
- 导出 TavernAI PNG 时，自动将时间线回写为世界书“剧情推进”条目嵌入导出数据。

### 提示词与模型控制
- 文本 Provider 设置新增“前置破限提示词”输入框。
- 每次文本调用支持自动拼接：`前置破限提示词 + 正常提示词`。
- 新增 `jailbreak-prompts/` 内置破限词目录，支持按“模型名.txt”自动匹配；未命中可回退到自定义文本。
- “角色信息输入（用于一键生成）”支持上传 `.txt` 文件。

### 提示词模板强化
- 强化角色生成提示词的结构约束：
  - `appearance` 使用分段+要点的格式硬约束
  - `triggerKeywords` 约束为角色称呼类关键词，减少泛词。
- 移除生成链路中的 trim 截断行为，避免示例风格和上下文被压缩。

### 稳定性与容错
- Provider 请求增强重试与错误摘要，覆盖 408/429/5xx/Cloudflare 524 等超时场景。
- 一键生成在剧情结构缺失时自动 fallback 构建可用剧情推进节点。

### 测试与类型检查
- 新增/更新后端测试覆盖：
  - 一键生成多角色流程
  - 剧情推进 fallback
  - 时间线与世界书迁移/导出回写
  - 前置破限词拼接与内置匹配。
- 前端 `vue-tsc` 类型检查通过。

## 0.0.2（2026-04-21）

### 架构调整
- 移除 Electron 桌面壳，项目改为纯 Web 形态（Vue + Flask API）。
- 前端通过 HTTP 调用后端，不再依赖 preload/IPC bridge。
- 开发脚本改为并行启动：
  - `npm run dev:web`（Vite）
  - `npm run dev:api`（Flask）

### 数据与功能升级
- 「姓名栏」升级为「角色卡」结构，支持一个卡内多个角色。
- 世界书改为条目化结构（entries），支持手动增删条目。
- 角色条目与世界书条目均支持蓝灯/绿灯触发模式：
  - 蓝灯：常驻触发（always）
  - 绿灯：关键词触发（keyword）
- 新增高级参数：
  - 触发顺序（insertion order）
  - 触发概率（probability）
  - 插入位置（position）
  - 深度（depth）

### 导入导出
- 导入：
  - 支持上传 PNG/JSON 角色卡文件导入。
  - 支持从卡内元数据恢复草稿与世界书条目。
- 导出：
  - 后端生成 Tavern 兼容 PNG 并回传 base64，前端直接下载。
  - 导出时写入 `chara` 与 `roleplaycard` 元数据。

### 设置持久化
- 设置改为浏览器 Cookie 存储（不再使用本地桌面配置文件）。
- Provider 配置在前端读取/保存，调用接口时随请求发送。

### API（Web）
- `GET /api/health`
- `GET /api/settings`
- `POST /api/settings`
- `POST /api/settings/test`
- `GET /api/drafts`
- `GET /api/drafts/<draft_id>`
- `POST /api/drafts`
- `POST /api/ai/field`
- `POST /api/ai/image-prompt`
- `POST /api/ai/image`
- `POST /api/files/upload-image`
- `GET /api/files/image`
- `POST /api/card/import-file`
- `POST /api/card/export-download`

## 0.0.2 修复补丁（2026-04-21）

### 导入兼容性修复
- 修复部分角色卡无法读取世界书条目的问题。
- 导入解析增强，支持：
  - `chara` / `ccv3` / `roleplaycard` 元数据来源
  - `chara_card_v2` 与 `chara_card_v3`
  - `character_book.entries` 为 `list` 或 `dict`
  - 多种字段别名（keys/key/keywords，content/text/value/entry）

### 图片预览修复
- 修复预览错误 URL（错误使用 `file:///api/...`）导致 broken image。
- 改为 HTTP 预览（`/api/files/image?path=...`）。
- 导入后强制刷新预览参数，避免缓存导致不更新。
- 导入时清空 `generatedImagePath`，避免覆盖 `originalImagePath`。

### 前端稳定性修复
- 修复 `structuredClone` 克隆 Vue 响应式对象触发 `DataCloneError`。
- 统一改为 plain object 深拷贝后再发送请求（JSON 序列化路径）。

### 测试
- Python 测试覆盖扩展至：
  - 保存/读取草稿
  - 导出元数据校验
  - v2/v3 卡导入
  - `ccv3` 回退导入

## 0.0.1（2026-04-21）

- 首个可用版本：Electron + Vue + Python。
- 支持角色卡编辑、AI 字段生成、AI 图像生成、Tavern PNG 导出。
