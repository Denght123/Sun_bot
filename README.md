# 基金理财热点消息机器人

一个后端优先的财经热点日报机器人项目。

系统负责抓取多平台财经相关热点，经过规则筛选与大模型摘要后生成统一日报；发送链路的默认架构口径统一为：

- **主发送方向：后端直连企业微信应用消息接口**
- **legacy fallback：Windows sender-agent + 本地微信自动化**

> 当前状态说明：本分支只完成**文档与配置契约切换**，不包含企业微信实际发送实现。仓库当前仍保留 sender-agent 相关 API、心跳 / polling / 结果回传能力，以及本地微信自动化兼容链路，用于 fallback / 回滚 / 特殊场景。

## 项目定位

这个项目聚焦于三件事：

- 统一收集财经热点
- 输出结构化、可读的日报
- 通过稳定的后端调度完成每日分发

当前版本仍是 **MVP / 单用户优先验证阶段**，重点验证内容质量、调度稳定性、发送链路与异常恢复能力。

## 默认部署形态

默认部署已经是 **backend-only**：

- `api-service`
- `scheduler-service`
- `postgres`
- `redis`
- 企业微信应用消息所需凭据

仓库中的 [docker-compose.yml](docker-compose.yml) 与 [Dockerfile](Dockerfile) 已经体现这一点：默认部署不再要求随仓库一起常驻一台 Windows 发信机。

## 当前能力范围

### 已有后端能力
- 多源财经热点抓取
- 规则筛选、去重、聚类与摘要生成
- 结构化日报生成
- 每日定时调度与手动补跑入口
- dispatch task、发送状态与重试状态管理
- sender-agent 兼容 API（heartbeat / pending tasks / result callback）

### 当前发送口径
- **默认 / 目标主路径**：backend -> WeCom app messaging
- **当前兼容路径**：backend -> dispatch task -> sender-agent -> local WeChat automation

说明：本仓库当前已经具备 sender-agent fallback 所需的运行代码与配置；企业微信主路径在本分支中只完成架构口径与环境变量契约，具体发送实现仍依赖后续分支接入。

## 日报内容结构

每日早报默认输出完整精简版，包含以下模块：

1. 今日总览（3-5 条）
2. 热门财经板块（Top10，行业赛道口径）
3. 国内政策与监管动态（Top10）
4. 国际事件与海外市场影响（Top10）
5. 风险提示（2-3 条）
6. 原文链接集合
7. 固定免责声明

### 内容风格
- 先事实，后影响
- 中性克制，不提供投资建议
- 同一时刻接收统一文本

## 系统工作流程

默认设计下，系统每天按以下节奏运行：

1. 前一日 18:00 至当日 07:30 收集数据
2. 07:30 - 07:45 进行去重、聚类、规则筛选
3. 07:45 - 07:55 调用大模型生成摘要
4. 08:00 生成统一日报并触发发送
5. 默认由后端走企业微信应用消息发送
6. 如需 fallback，则由 dispatch task 下发给 Windows sender-agent，再通过本地微信自动化发送

如果发送失败：
- 自动重试最多 3 次
- 仍失败则触发异常告警
- `waiting_sender` 只用于 legacy sender-agent fallback 语义，不再代表默认主链路前提

## 为什么这样设计

采用这种口径切换的原因是：

- 默认部署已经是后端服务优先，文档应与实际部署形态一致
- 企业微信应用消息更适合作为统一广播和后端直连的主发送方向
- Windows sender-agent / 本地微信自动化仍可保留为兼容、回滚和特殊场景兜底
- 这样既不会丢掉当前已有的 sender-agent 能力，也能为后续主链路演进提供更稳定的配置契约

## legacy fallback 何时使用

以下场景可以启用 Windows sender-agent：

- 需要沿用当前本地微信自动化能力
- 需要演练 fallback / rollback
- 需要验证 sender heartbeat、pending-task polling、result callback 相关链路

对应运行说明见 [src/sender_agent/WINDOWS_RUN_GUIDE.md](src/sender_agent/WINDOWS_RUN_GUIDE.md)。

## 本分支不做的事

本分支**不**包含以下实现：

- 企业微信 access token 获取与刷新
- 企业微信应用消息实际发送 service
- dispatch 主流程 provider-aware 改造
- scheduler / dispatch 与企业微信发送打通
- 企业微信回调联调

这些能力仍需后续分支继续完成。

## 免责声明

本项目仅用于信息整理与消息推送，不构成任何投资建议。投资决策请独立判断。
