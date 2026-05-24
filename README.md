# 麦笔 / Maibi

麦笔是一款面向 Windows 10/11 桌面的中文语音输入工具。首版采用系统托盘应用、浮窗预览和轻量签名服务，不注册为 Windows 系统 IME。

当前仓库处于项目骨架阶段，产品边界和技术计划见 `docs/PLAN.md`，PR 流程见 `docs/PR_GUIDELINES.md`，项目进度见 `docs/STATUS.md`，Agent 协作规则见 `agents.md`。

当前主线已经具备：

- 本地签名服务生成腾讯云实时 ASR 签名 URL
- 客户端 bootstrap 获取 `websocket_url`
- demo 壳接入真实 `sounddevice + websockets` 路径的基础版本

当前仍未收口的问题主要是真正的实时流式发送模型和输入法级交互细节，详情见 `docs/STATUS.md`。

## 目录结构

- `client/`：Windows 桌面客户端，后续负责托盘、浮窗、录音、快捷键、配置和文本上屏。
- `server/`：签名服务和后端 API，后续负责生成短期 ASR 会话参数。
- `core/`：客户端与服务端共享的核心类型、接口和工具。
- `tests/`：自动化测试。
- `docs/`：产品、设计、部署和验收文档。

## 文档入口

- `docs/README.md`：文档索引。
- `docs/PLAN.md`：产品与技术计划。
- `docs/PR_GUIDELINES.md`：PR 提交规范。
- `docs/STATUS.md`：项目进度。
- `agents.md`：Agent 工作指南。

## 开发环境

- Python 3.11+
- Windows 10/11 用于客户端验收

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 常用命令

运行测试：

```powershell
pytest
```

后续客户端和服务端启动命令会在对应模块完成后补充。

启动签名服务：

```powershell
uvicorn server.app:app --reload
```

安装客户端音频依赖：

```powershell
python -m pip install -e ".[client]"
```

启动可体验客户端壳：

```powershell
python -m client.demo_app
```

腾讯云本地配置：

- 示例文件：`server/config.example.json`
- 本地真实配置：`server/config.local.json`
- `server/config.local.json` 已被 `.gitignore` 忽略，不应提交到仓库

## 开发流程

- 文档小修、错别字和说明性规范更新可以直接提交到 `main`。
- 功能代码、依赖、接口、配置和可运行行为变更必须通过 Pull Request。
- 每个 PR 只做一件事，并在合并后保持主分支可运行。
- 多 Agent 并行开发时，主 Agent / 主线程负责最终构建、测试和运行验证。

