# 技术设计文档 TECH_DESIGN

## 1. 文档目的

本文用于统一当前仓库的技术口径，避免后续分支继续沿着“Windows sender-agent + 本地微信自动化是默认主链路”的旧叙述推进。

本分支只做两类事情：

- 统一架构文档与运行说明
- 扩展环境变量配置契约

本分支**不**实现企业微信实际发送逻辑，也**不**改动现有 dispatch / scheduler / sender-agent 运行行为。

---

## 2. 当前状态与目标架构

### 2.1 当前代码现状
当前仓库仍保留以下 sender-oriented 能力：

- sender heartbeat / pending task polling / result callback API
- sender online / degraded / `waiting_sender` 相关状态语义
- Windows sender-agent 运行代码
- 本地微信自动化兼容链路

这些能力在当前代码中依然有效，因此本次文档切换不能把 sender-agent 写成“已废弃”或“已移除”。

### 2.2 当前默认部署形态
默认部署已经是 **backend-only**，仓库中的 [docker-compose.yml](docker-compose.yml) 与 [Dockerfile](Dockerfile) 只覆盖：

- `api-service`
- `scheduler-service`
- `postgres`
- `redis`

也就是说，默认部署层面并不要求与仓库一起常驻一台 Windows 发信机。

### 2.3 目标发送口径
本分支需要把默认架构口径统一为：

- **主发送方向：backend -> WeCom app messaging**
- **legacy fallback：backend -> dispatch task -> sender-agent -> local WeChat automation**

说明：这里的“主发送方向”是本分支要确立的**架构方向与 env 契约**，不是说企业微信发送已经在本分支落地完成。

### 2.4 与其他设计文档的关系
本分支不深改 [API_SPEC.md](API_SPEC.md)、[DB_DESIGN.md](DB_DESIGN.md)、[PRD(基金理财热点消息机器人).md](PRD(基金理财热点消息机器人).md)。

因此需要接受一个事实：

- 这些文档仍更多反映当前 sender-oriented 实现现实
- 本文负责明确新的默认部署口径与未来主发送方向

---

## 3. 总体设计原则

1. **默认部署后端优先**
   - 默认运行节点以 ECS 上的后端服务为主
   - Docker 默认编排不依赖 Windows 机器常驻

2. **主发送方向切换为企业微信应用消息**
   - 后端直接调用企业微信应用消息接口，适合作为统一广播主路径
   - 收件对象、发送凭据、回调参数等通过后端 env 契约管理

3. **保留 sender-agent 作为 legacy fallback**
   - 当前 sender-agent 代码、API 与状态模型继续保留
   - 用于 fallback / rollback / 特殊场景或兼容已有自动化链路

4. **文档真实反映代码边界**
   - 不能把未来方向写成“已经实现”
   - 不能把当前 sender-oriented 运行逻辑伪装成“已经 transport-agnostic”

5. **规则优先，LLM 兜底增强**
   - 先规则去重、聚类、筛选，再调用大模型摘要
   - 模型失败时允许降级为规则模板版日报

6. **统一日报，不做个性化生成**
   - 所有接收端默认接收同一份日报文本
   - 降低复杂度与运维成本

---

## 4. 系统架构

### 4.1 部署拓扑

```text
                   ┌──────────────────────────┐
                   │      阿里云 ECS          │
                   │──────────────────────────│
                   │ FastAPI API Service      │
                   │ APScheduler              │
                   │ Collector / Parser       │
                   │ Rule Engine              │
                   │ LLM Summarizer           │
                   │ Report Generator         │
                   │ Dispatch Service         │
                   │ PostgreSQL / Redis       │
                   └───────────┬──────────────┘
                               │
                     Primary   │   Legacy fallback
                     path      │
              ┌────────────────▼───────────────┐
              │ WeCom app messaging            │
              │ (follow-up implementation)     │
              └────────────────┬───────────────┘
                               │ optional fallback
                   ┌───────────▼──────────────┐
                   │ Windows 发信端           │
                   │──────────────────────────│
                   │ Sender Agent             │
                   │ WeChat Automation        │
                   │ Login State Monitor      │
                   └──────────────────────────┘
```

### 4.2 架构职责划分

| 节点 | 角色 | 当前状态 |
|---|---|---|
| 阿里云 ECS | 数据抓取、清洗、聚类、LLM 摘要、日报生成、任务调度、状态管理 | 已存在 |
| WeCom app messaging | 默认主发送方向 | 本分支只建立架构口径与 env 契约，实际发送实现留待后续 |
| Windows 发信端 | legacy fallback，负责本地微信自动化发送 | 已存在运行代码 |
| PostgreSQL | 原始数据、日报结果、dispatch task、sender 状态 | 已存在 |
| Redis | 缓存、短期状态、调度辅助 | 已存在 |

---

## 5. 核心模块设计

### 5.1 Collector 抓取模块
职责：
- 按平台抓取热点榜单与财经媒体内容
- 统一抽取标题、摘要、链接、来源、时间、标签、抓取时间
- 对源站失败、结构变化、超时进行容错记录

输出：标准化原始内容列表。

### 5.2 Rule Engine 规则处理模块
职责：
- 去重：按标题相似度、链接、关键词进行去重
- 初筛：过滤非财经热点
- 聚类：把同一事件的多个来源合并
- 打标签：行业赛道、政策、国际、风险等
- 排序：按热度、来源权重、时效综合排序

输出：高价值候选事件列表。

### 5.3 LLM Summarizer 摘要模块
职责：
- 接收规则筛选后的候选事件
- 输出“事实 + 影响”的统一摘要
- 保持中性、克制，不输出投资建议
- 控制整体输出长度

降级策略：
- 模型超时 / 调用失败时，使用规则模板生成简版日报

### 5.4 Report Generator 日报生成模块
职责：
- 生成完整精简版日报
- 生成关键词查询子模块内容
- 自动拼接免责声明
- 生成链接集合
- 控制文本总长度与拆分段落数

### 5.5 Scheduler 调度模块
职责：
- 每日定时触发抓取、分析、摘要、发送流程
- 管理失败重试
- 支持手动补跑

推荐时间链路：
- T-1 18:00 ~ T 07:30：数据采集窗口
- 07:30 ~ 07:45：规则处理
- 07:45 ~ 07:55：LLM 摘要
- 08:00：创建并触发发送

### 5.6 Dispatch Service 任务编排模块
职责：
- 统一创建 dispatch task 与任务状态
- 管理发送重试与失败状态
- 在 legacy fallback 场景下继续服务 sender-agent polling / callback

说明：当前代码中的 dispatch 仍然是 sender-oriented；本分支不改其运行逻辑，只调整文档语义与未来 provider 合同。

### 5.7 WeCom Delivery（后续分支实现）
职责将包括：
- access token 获取与刷新
- 企业微信应用消息发送
- 主发送结果回写
- 如启用则处理回调验签与状态联动

本分支仅定义其配置契约，不新增运行代码。

### 5.8 Sender Agent legacy fallback 模块
职责：
- 轮询云端待发送任务
- 调起本地微信自动化执行推送
- 回传发送成功 / 失败 / 错误信息
- 定期上报心跳与登录状态

定位说明：
- 它仍是当前代码中真实可运行的兼容路径
- 但不再是默认部署的前提，也不再是文档中的默认主链路

---

## 6. 端到端业务流程

### 6.1 默认每日自动流程（目标主路径）
1. Scheduler 在阿里云 ECS 上按北京时间运行。
2. Collector 按预设时间窗口收集多源内容。
3. Rule Engine 完成去重、聚类、财经相关性过滤、标签归类。
4. LLM Summarizer 生成统一日报摘要。
5. Report Generator 产出完整日报及关键词详情内容。
6. Dispatch Service 创建发送任务与状态记录。
7. 后端通过 WeCom app messaging 发送日报。
8. 发送结果写回后端状态。
9. 若失败，则按后续分支定义的主路径重试 / 告警逻辑处理。

说明：第 7-9 步是本分支要确立的默认方向，具体实现仍需后续分支完成。

### 6.2 legacy fallback 自动流程
当系统显式配置为 fallback 模式，或进行回滚 / 演练时：

1. Scheduler 与日报生成链路保持不变。
2. Dispatch Service 创建 dispatch task。
3. 若存在健康 sender，则任务进入 `pending` 并由 sender-agent 轮询获取。
4. Windows sender-agent 调起本地微信自动化发送。
5. sender-agent 回传结果，后端更新任务状态。
6. 若 sender 离线，则任务进入 `waiting_sender`。

### 6.3 用户交互流程说明
关键词交互、菜单查询与模块返回能力仍可继续沿用当前 sender-oriented 兼容链路；是否迁移到企业微信交互方式，留待后续实现分支决定。

---

## 7. 当前数据与接口边界

### 7.1 数据层边界
当前 schema 仍保留 sender-related 数据概念，例如：

- `dispatch_tasks`
- `senders`
- `sender_heartbeats`

这说明当前运行现实仍然支持 sender fallback；本分支不对数据模型做 transport-agnostic 重构。

### 7.2 API 边界
当前运行中的 sender-related API 仍然有效，包括：

- `/api/sender/heartbeat`
- `/api/sender/tasks/pending`
- `/api/sender/tasks/{task_id}/result`
- `/api/sender/events`

这些接口在本分支中应被理解为：
- 当前兼容路径接口
- fallback / rollback 支撑能力
- 不是默认主发送方向的长期唯一形态

### 7.3 主路径接口状态
企业微信主路径在本分支中只有 env 契约，没有新增 API / service 运行实现。

---

## 8. 配置与部署设计

### 8.1 默认部署
推荐的默认部署要素：

- `api-service`
- `scheduler-service`
- `postgres`
- `redis`
- 企业微信发送所需凭据

这与当前 [docker-compose.yml](docker-compose.yml) 和 [Dockerfile](Dockerfile) 保持一致。

### 8.2 环境变量分组
后端配置建议分为四组：

1. 基础应用配置
2. 调度 / dispatch 核心配置
3. 企业微信主路径配置
4. legacy sender-agent fallback 配置

### 8.3 企业微信主路径配置
本分支会建立但不消费以下配置契约：

- `DISPATCH_PROVIDER`
- `DISPATCH_EXECUTION_MODE`
- `WECOM_*`

这些变量在本分支中的意义是：
- 明确未来主发送方向
- 稳定 env key 契约
- 为后续发送 service 接入做准备

它们**不**意味着本分支已经具备企业微信发送能力。

### 8.4 legacy sender-agent fallback 配置
以下配置仍需保留：

- `DISPATCH_DEFAULT_TARGET_USER`
- `SENDER_ONLINE_THRESHOLD_SECONDS`
- `SENDER_DEGRADED_THRESHOLD_SECONDS`
- `SENDER_NEXT_HEARTBEAT_SECONDS`
- `SENDER_API_BASE_URL`
- `SENDER_ID`
- 所有 `SENDER_*`
- 所有 `WECHAT_*`

原因：
- 当前 dispatch / sender status 逻辑仍依赖这些字段
- [src/sender_agent/config.py](src/sender_agent/config.py) 仍将 `SENDER_API_BASE_URL`、`SENDER_TOKEN`、`SENDER_ID` 视为必需配置

### 8.5 时区与时间配置
- ECS 使用北京时间
- 所有任务调度、日志展示、日报日期统一基于 `Asia/Shanghai`
- legacy sender-agent fallback 场景也继续使用北京时间，避免发送时间偏差

---

## 9. 重试、告警与降级策略

### 9.1 抓取失败
- 单个平台失败不阻断全局流程
- 记录错误日志
- 平台异常在日报中不单独暴露给用户

### 9.2 LLM 失败
- 自动降级为规则模板版日报
- 标记 `fallback_used = true`
- 仍允许日报继续发送

### 9.3 主发送路径失败（后续实现）
默认主路径切换到企业微信后，后续分支需要把以下能力纳入统一状态流：

- WeCom 发送失败重试
- 主路径失败告警
- 发送结果回写
- 如有必要，切换到 legacy fallback

本分支只定义该方向，不实现具体逻辑。

### 9.4 legacy sender fallback 失败
- sender 心跳异常、未登录或窗口不可用时，可进入 `waiting_sender`
- `waiting_sender` 仅表示 fallback 发信端暂不可用
- 它不再是默认主链路不可用时的唯一解释

### 9.5 告警建议
优先关注：
- 日报未按时生成
- 主路径发送失败
- fallback sender 长时间离线
- LLM 连续调用失败
- 重试次数触顶

---

## 10. 启动与运行说明

### 10.1 后端服务启动
默认通过 Docker Compose 启动：

- API
- Scheduler
- PostgreSQL
- Redis

服务器重启后依赖 `unless-stopped` 自动恢复。

### 10.2 Windows sender-agent 启动
只有在以下场景才需要：

- fallback 演练
- 回滚到本地微信自动化
- 兼容当前 sender-oriented API / task flow

此时才需要：
- 保持 WeChat Desktop 登录态
- 启动 sender-agent
- 周期性 heartbeat / polling / result callback

对应说明见 [src/sender_agent/WINDOWS_RUN_GUIDE.md](src/sender_agent/WINDOWS_RUN_GUIDE.md)。

---

## 11. 安全与合规边界

- 仅抓取公开可访问内容，注意平台反爬与合规限制
- 严格保留免责声明，不输出买卖建议
- API Key、数据库密码、企业微信凭据、sender-agent 配置均通过环境变量管理
- 阿里云安全组只开放必要端口
- 如需公网接口，建议增加 HTTPS 与鉴权

---

## 12. 日志、监控与运维建议

### 12.1 日志分类
- `collector.log`：抓取日志
- `scheduler.log`：调度日志
- `llm.log`：模型调用日志
- `dispatch.log`：任务下发与发送结果日志
- `sender.log`：legacy sender-agent 执行日志

### 12.2 关键监控指标
- 当日抓取成功的平台数
- 候选事件数量
- LLM 调用成功率
- 当日日报生成状态
- 默认主路径发送成功率
- fallback sender 最近心跳时间
- 重试次数与失败原因

### 12.3 告警建议
- 08:00 前日报未生成完成
- 主路径发送失败
- fallback sender 离线超过阈值
- 推送重试 3 次失败
- LLM 连续调用失败

---

## 13. MVP 实施优先级（更新后口径）

### Phase 1：后端主链路清晰化
- 保持阿里云 ECS 上的 FastAPI + APScheduler 基础服务
- 打通 1-2 个数据源抓取
- 生成固定模板日报
- 完成 WeCom 主路径所需配置契约

### Phase 2：主发送实现补齐
- 新增企业微信发送 service
- 接入 access token 获取 / 刷新
- 打通 dispatch -> WeCom 主发送路径
- 把主路径结果纳入重试与状态管理

### Phase 3：内容质量提升
- 扩展多平台抓取
- 增强去重、聚类、分类能力
- 引入 LLM 摘要
- 优化文本结构与链接质量

### Phase 4：legacy fallback 与运维增强
- 保持 sender-agent fallback 可用
- 演练 rollback / fallback
- 补充监控、告警、补跑与排障说明

---

## 14. 验收映射

本文对应的验收重点不再是“sender-agent 作为默认主链路”，而是：

- 默认部署说明与 Docker 编排一致
- 文档明确 backend-only 是当前默认部署
- 文档明确 WeCom app messaging 是默认主发送方向
- 文档明确 sender-agent 是 legacy fallback
- `.env.example` 与 [src/app/core/config.py](src/app/core/config.py) 的配置契约保持一致
- 当前 sender-oriented 代码事实没有被文档错误掩盖

---

## 15. 结论

当前仓库最合适的统一口径应为：

- 阿里云 ECS 常驻运行核心后端服务
- 企业微信应用消息是默认主发送方向
- Windows sender-agent / 本地微信自动化是 legacy fallback
- FastAPI + APScheduler 继续作为后端骨架
- PostgreSQL + Redis 提供存储与状态支持

这样既能让文档与现有部署形态一致，也能保留当前 sender-agent 兼容链路，为后续企业微信主路径实现留出清晰边界。
