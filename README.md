# RolePlayCard

> 根据短篇小说自动生成可游玩角色卡（多角色 + 世界书 + 时间线）。

[Demo地址](https://roleplay.chihaya-anon.uk/)

## 项目定位

RolePlayCard 是一个面向 TavernAI / SillyTavern 工作流的角色卡工具。  
你可以直接粘贴短篇小说全文，系统会自动提取角色、地点、首屏信息、剧情时间线，并生成可导出的角色卡 PNG。

## 亮点功能

| 模块 | 能力 |
| --- | --- |
| 短篇小说一键生成 | 全文解析 -> 先产出剧情骨架，再逐角色生成 |
| 时间线系统 | 独立编辑、支持父子树结构、图形化展示 |
| 玩家扮演角色 | 可指定一个角色导出时映射为 `{{user}}`，保留背景设定 |
| 世界书条目 | 关键词/蓝灯触发、顺序/概率/插入位置/深度参数 |
| 文本增强 | 自定义或内置前置提示词（`jailbreak-prompts/*.txt`） |
| 导入导出 | 导入 PNG/JSON，导出 Tavern 兼容 PNG（含元数据） |

## 核心流程

```mermaid
flowchart LR
  A["短篇小说全文"] --> B["阶段1: 抽取 outline / 地点 / 时间线"]
  B --> C["阶段2: 按角色逐个生成角色卡字段"]
  C --> D["手动编辑: 角色 / 世界书 / 时间线图"]
  D --> E["导出: TavernAI PNG + chara 元数据"]
```

## 技术栈

- 前端: Vue 3 + Vite + TypeScript
- 后端: Python + Flask
- 测试: pytest

## 目录结构

```text
RolePlayCard/
├─ vue-renderer/          # 前端
├─ python-service/        # Flask API 与业务逻辑
├─ shared/                # 前后端共享类型
├─ jailbreak-prompts/     # 内置前置提示词（按 模型名.txt 匹配）
└─ version.md             # 版本日志
```

## 快速开始

### 1) 安装依赖

```bash
npm install
python -m pip install -r python-service/requirements.txt
```

### 2) 启动开发环境

```bash
npm run dev
```

默认会同时启动：

- Web 前端（Vite）
- Python API（`127.0.0.1:8765`）

### 3) 常用命令

```bash
npm run typecheck
npm run test
```

### 4) 使用 PM2 托管

PM2 会先构建前端，再用同一个 Python 服务托管前端页面和 API。

```bash
npm install -g pm2
python -m pip install -r python-service/requirements.txt
npm run pm2:start
```

默认访问：

- 页面: `http://127.0.0.1:8765`
- 健康检查: `http://127.0.0.1:8765/api/health`

常用管理命令：

```bash
npm run pm2:logs
npm run pm2:restart
npm run pm2:stop
npm run pm2:delete
```

如需修改监听地址、端口或数据目录，可在启动前设置环境变量：

PowerShell:

```powershell
$env:RPC_HOST="0.0.0.0"; $env:RPC_PORT="8765"; $env:RPC_APP_DATA=".role-play-card-data"; npm run pm2:start
```

Bash:

```bash
RPC_HOST=0.0.0.0 RPC_PORT=8765 RPC_APP_DATA=.role-play-card-data npm run pm2:start
```

## 使用说明（推荐）

1. 打开编辑器顶部的“短篇小说一键生成”。
2. 粘贴小说全文或上传 `.txt`。
3. 点击“根据短篇小说生成角色卡”。
4. 在角色列表中可指定一个“玩家扮演”角色。
5. 在时间线中检查主线与分叉结构（图与列表会同步）。
6. 导出 TavernAI PNG。

## 文本 Provider 提示

- 文本调用支持拼接：`前置提示词 + 正常提示词`。
- 若开启内置模式，会按模型名匹配 `jailbreak-prompts/<model>.txt`。
- 未命中时回退到自定义前置提示词。

## 版本

当前发布节奏与变更详见：

- [version.md](./version.md)

## 引用

破限提示词来自：  
- Levoglucose 发布在https://discord.com/channels/1134557553011998840/1482001001702756423
