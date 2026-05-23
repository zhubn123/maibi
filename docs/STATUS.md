# 项目进度

最后更新：2026-05-23

## 当前阶段

项目处于首版基础建设阶段。已完成产品计划、协作规范、Python 项目骨架和 `core` 共享接口；正在推进 `server` 最小 FastAPI 签名服务。

## 已完成

- PR #1：[Add project planning docs](https://github.com/zhubn123/maibi/pull/1)
  - 状态：已合并
  - 内容：新增项目计划、PR 规范、Agent 工作指南和 `.gitignore`
- 直接提交：[Add collaboration workflow guidelines](https://github.com/zhubn123/maibi/commit/ff4faa38edcc78ca002664ceaa5bcf1f5af83756)
  - 状态：已进入 `main`
  - 内容：补充多 Agent 协作规范和小改动免 PR 规则
- PR #2：[Add project skeleton](https://github.com/zhubn123/maibi/pull/2)
  - 状态：已合并
  - 内容：新增 `README.md`、`pyproject.toml`、`client/`、`core/`、`server/`、`tests/`、`docs/`
- PR #3：[Add core contracts](https://github.com/zhubn123/maibi/pull/3)
  - 状态：已合并
  - 内容：新增 ASR Provider/Session/Event、配置、热词、用量限制和文本提交接口

## 进行中

- PR #4：Add server minimal API
  - 状态：Draft
  - 内容：新增 `GET /healthz` 和 `POST /v1/asr/session` 最小 FastAPI 服务

## 下一步

1. 合并 PR #4。
2. PR #5：实现 Mock ASR WebSocket 集成测试。
3. PR #6：实现 `client/` 托盘和浮窗基础 UI。
4. 在 PR #5 到 PR #6 之后，再并行推进麦克风采集、腾讯云 ASR Provider 和文本上屏能力。

## 执行规则

- 功能代码、接口、依赖、配置和运行行为变更走 PR。
- 文档小修、状态更新、错别字和说明性规范更新可以直接提交到 `main`。
- 多 Agent 并行时，子 Agent 不默认运行全量编译、全量测试、服务或打包命令；最终验证由主 Agent / 主线程统一判断。

## 文档位置

- `README.md`：仓库入口和开发入口。
- `agents.md`：Agent 工作指南，保留在根目录便于工具自动发现。
- `docs/README.md`：文档索引。
- `docs/PLAN.md`：产品与技术计划。
- `docs/PR_GUIDELINES.md`：PR 提交规范。
- `docs/STATUS.md`：项目进度。
