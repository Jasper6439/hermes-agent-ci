# ⚙️ Eleusinian Mysteries — 自定义规范

> 以下是我们对官方 Hermes Agent 开发指南的补充和覆盖。
> **冲突时以本节为准。** 官方文档见分割线下方。

## Output Language — English (Translation Hook)

**Always output in English.** The local translation hook (`scripts/local_translator.py`) converts English output to Chinese before delivery. This saves ~30-40% output tokens.

- Write all responses in English
- The gateway translates to Chinese automatically via qwen3.5:0.8b
- Exception: code blocks, URLs, technical identifiers stay as-is
- If translation hook fails, English is delivered as fallback
## Telegram 多话题群组配置

**必须**: `group_sessions_per_user: false`
否则同一用户的所有话题共享一个 session，导致上下文膨胀和 "no response" 错误。

## Tool Selection — `execute_code` > `terminal`

**多步操作用 `execute_code`**，只在单条简单命令时用 `terminal`。
- `execute_code`: 可导入 hermes_tools，一次执行多步逻辑，省 token
- `terminal`: 只用于单条命令（systemctl、docker、git 等）

## Code Search — `semblectl_search` First

**Always use `semblectl_search` for code/grep searches.** It compresses tokens ~98%.

- ❌ `terminal` grep/rg — raw output, no token compression
- ❌ `search_files` — bypasses RTK, raw rg output
- ✅ `semblectl_search` — token-compressed, registered in `file` toolset

Only fall back to `terminal` grep if `semblectl_search` fails or is unavailable.

### Memory Search — Same Order

**搜历史上下文时，必须按以下顺序：**
1. Topic Memory 自动注入（零成本，pre_llm_call 自动执行）
2. `semblectl_search`（首选手动搜索，~95% token 压缩）
3. `session_search`（最后 fallback，无压缩）

禁止跳过 semblectl_search 直接用 session_search。

grep/rg 已被拦截（代码索引 + 结构化匹配 + 低误报率），强制使用 semblectl_search。

---

### DO NOT hardcode coin lists, API endpoints, or config values

**铁律：代码中禁止出现硬编码的列表、常量、配置值。**

- 币种列表 / 交易对 → 必须从 API 动态获取（如 OKX instruments API）
- 配置值 → 必须从 config 文件或环境变量读取
- API 端点 → 必须从配置文件加载
- 硬编码的列表/常量是技术债，发现即修复，无例外
- Fallback 机制允许静态备份，但主路径必须是动态的
- 扫描范围不允许写死，必须按成交量 / 流动性 / 市场热度动态筛选

## 记忆召回工具链优先级（2026-06-18 新增）


---

> 完整的 Hermes 官方开发指南见 AGENTS_UPSTREAM.md

## 安全铁律

- **密码全部存 Vaultwarden**，引用格式 `"见Vaultwarden: <item-name>"`
- **`.env` 文件禁止用 `write_file` 工具**（会损坏内容）。写密钥到 `.env` 必须用 terminal `echo`/`printf`
- Vaultwarden 启动命令：`docker run -d --name vaultwarden -v ~/vaultwarden/data:/data -p 8222:80 -e ADMIN_TOKEN=<见Vaultwarden> --restart unless-stopped vaultwarden/server:latest`

## 文件组织规范

**目录结构（`/home/ubuntu/`）**:
- `hermes/` — 主系统源码、配置、插件、Dashboard
- `workspace/` — 项目代码，按 `projects/<name>/` 组织
- `scripts/` — 工具脚本（.py/.sh 统一归档）
- `media/` — 媒体文件存储
- `media-stack/` — qBit+Radarr+Sonarr+Jackett Docker栈
- `obsidian-vault/` — Obsidian vault
- `vaultwarden/` — 密码管理
- `honcho-qdrant/` — 记忆系统
- `qinglong/` — 青龙面板
- `camofox-browser/` — 反检测浏览器
- `obfuscator/` — 混淆工具
- `lib/` — 工具专用venv

**Workspace内部（`/workspace/`）**:
- `projects/` — 项目代码（每个项目一个目录）
- `scripts/`, `data/`, `docs/`, `cache/` — 辅助目录

**安装规范**:
- 可执行文件 → `/usr/local/bin/`（禁止放home根目录）
- systemd服务路径变更后必须 `daemon-reload && restart`
- 虚拟环境 → `~/lib/<tool-name>/` 或项目的 `.venv/`
- `~/workspace` → `/workspace`（软链接）

**禁止行为**:
- home根目录禁止放可执行文件、散落脚本、临时文件、泛化目录
- 创建新目录前先检查是否有功能相近的目录可复用
- 移动文件后必须验证相关服务正常运行
- 清理文件前先移到 `.hermes/archive/` 归档，确认无用后再删除
- 删除目录前先确认无systemd/docker依赖
