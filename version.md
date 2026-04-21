# RolePlayCard 版本日志

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
