# CLAUDE_STARTER_PROMPTS

下面是给 7 个 Claude Code 会话直接使用的启动提示词模板。你可以把对应段落直接复制到不同窗口里。

使用方式：
1. 每个 Claude 先阅读 `TempNews.md`
2. 再阅读自己职责相关文档
3. 切到对应分支开始工作
4. 只在自己的模块边界内开发
5. 完成后提交到自己的 feature 分支，并准备提 PR 到 `integration`

> 当前架构口径提醒：默认发送方向已经切换为“后端直连企业微信应用消息”；Windows sender-agent / 本地微信自动化只作为 legacy fallback。注意：这不代表企业微信发送实现已经完成，后续分支仍需落地对应 service 与状态流转。

---

## Claude 1：后端基础骨架
请在分支 `feature/claude-01-backend-scaffold` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `TECH_DESIGN.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 搭建 FastAPI 项目基础结构
- 增加配置管理（环境变量）
- 初始化日志组件
- 建立 PostgreSQL / Redis 基础连接
- 准备 Dockerfile / docker-compose 基础骨架

你的边界：
- 不负责抓取器实现
- 不负责数据库详细建模
- 不负责具体发送逻辑
- 不新增产品需求

你的目标：
- 让后端项目具备最小可启动能力
- 为其他模块提供稳定的基础工程骨架

完成后请输出：
- 修改了哪些文件
- 如何启动
- 还缺什么依赖其他分支配合

---

## Claude 2：数据库与模型层
请在分支 `feature/claude-02-db-models` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `DB_DESIGN.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 建立 MVP 所需核心表
- 设计 ORM Model / Migration
- 定义状态枚举
- 封装基础 repository / DAO

优先处理：
- `raw_items`
- `event_clusters`
- `daily_reports`
- `report_sections`
- `dispatch_tasks`
- `senders`
- `sender_heartbeats`

你的边界：
- 不负责抓取器实现
- 不负责发信端实现
- 不擅自改变产品字段含义

你的目标：
- 提供可迁移、可扩展的 MVP 数据层基础

完成后请输出：
- 建了哪些表/模型
- 关键状态字段如何设计
- 如何初始化数据库

---

## Claude 3：抓取与规则引擎
请在分支 `feature/claude-03-collectors-rule-engine` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `TECH_DESIGN.md`
- `DB_DESIGN.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 接入首批关键数据源
- 做原始数据标准化
- 实现基础去重
- 实现财经相关性过滤
- 实现基础分类与简单聚类

首批建议数据源：
- 财联社
- 微博热搜 或 百度热搜

你的边界：
- 不负责 LLM 摘要
- 不负责发送实现
- 不引入泛娱乐热搜到正文

你的目标：
- 产出可供日报生成模块消费的候选事件数据

完成后请输出：
- 支持了哪些数据源
- 标准化结构是什么
- 去重/过滤/分类规则如何实现

---

## Claude 4：日报生成与 LLM
请在分支 `feature/claude-04-report-llm` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `PRD(基金理财热点消息机器人).md`
- `TECH_DESIGN.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 先实现规则模板版日报生成
- 再接入 LLM 摘要能力
- 生成完整精简版日报
- 生成模块详情内容
- 控制总字数与消息拆分数

必须遵守：
- 先事实，后影响
- 中性克制
- 不输出投资建议
- 总长度约 1200-1800 字
- 总推送不超过 6 条消息

你的边界：
- 不负责抓取器实现
- 不负责发送实现
- 不重新定义产品模块结构

你的目标：
- 让系统可以稳定输出可读的日报内容，并支持 LLM 失败时降级

完成后请输出：
- 日报结构如何生成
- LLM 与模板生成的关系
- 降级逻辑是什么

---

## Claude 5：调度与任务下发
请在分支 `feature/claude-05-scheduler-dispatch` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `TECH_DESIGN.md`
- `API_SPEC.md`
- `DB_DESIGN.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 接入 APScheduler
- 配置北京时间时区
- 实现日报生成调度
- 实现 dispatch task 创建
- 为主发送路径预留 provider-aware 状态流转
- 提供手动补跑入口

你的边界：
- 不负责企业微信具体发送 service 实现
- 不负责具体微信自动化发送
- 不负责抓取器细节
- 不改动日报业务结构

你的目标：
- 打通“定时生成 -> 创建发送任务 -> 跟踪任务状态”的调度闭环
- 为后续 WeCom 主发送接入保留清晰边界

完成后请输出：
- 调度链路如何工作
- dispatch task 状态有哪些
- 如何为主路径 / fallback 路径划分状态语义
- 如何手动补跑

---

## Claude 6：Windows 发信端（legacy fallback）
请在分支 `feature/claude-06-windows-sender` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `TECH_DESIGN.md`
- `API_SPEC.md`
- `TASK_BREAKDOWN.md`
- `src/sender_agent/WINDOWS_RUN_GUIDE.md`

你的职责：
- 维护 Sender Agent 兼容路径
- 实现或修复心跳上报
- 实现或修复待发送任务轮询
- 维护本地微信自动化发送能力
- 实现或修复发送结果回传
- 补充 fallback / rollback 运行说明

必须遵守：
- 不要求用户提供微信账号密码
- 默认采用本机已登录微信会话
- 若微信掉线，设计为人工重新登录恢复
- 明确这是 legacy fallback / compatibility path，不把它当作默认主链路

你的边界：
- 不负责云端抓取逻辑
- 不负责数据库核心建模
- 不擅自把 sender-agent 改写成默认发送方案

你的目标：
- 让 Windows 发信端在需要 fallback 时能与云端通信，并执行真实发送动作

完成后请输出：
- 发信端运行方式
- 如何与云端交互
- 作为 fallback 时如何启用
- 微信发送失败时如何处理

---

## Claude 7：测试与运维支持
请在分支 `feature/claude-07-test-ops` 上工作。

开始前请阅读：
- `TempNews.md`
- `README.md`
- `TECH_DESIGN.md`
- `API_SPEC.md`
- `TASK_BREAKDOWN.md`

你的职责：
- 设计核心测试用例
- 覆盖主链路和异常链路
- 整理阿里云 ECS 部署检查项
- 梳理健康检查、日志与告警方案

优先关注：
- ECS 重启恢复
- 企业微信主路径配置校验
- fallback sender-agent 离线
- 微信掉线
- LLM 失败降级
- 推送失败重试 3 次

你的边界：
- 不重新定义产品功能
- 不直接改动其他模块核心业务逻辑，除非是为了测试可观测性所必需

你的目标：
- 为后续主链路联调、上线前验证和运维准备可执行的测试与检查方案
- 同时覆盖 legacy fallback 的演练与回滚检查项

完成后请输出：
- 测试清单
- 异常验证方案
- 部署检查项
- 告警建议

---

## 给所有 Claude 的统一提醒
- 你们都应基于当前 MVP 边界工作
- 所有改动优先提交到各自 `feature/...` 分支
- 不要直接改 `main`
- 完成后先提 PR 到 `integration`
- 若与其他模块存在接口依赖，请在结果里明确写出依赖项
- 敏感信息一律不要写入仓库
- 不要把“未来主发送方向”误写成“已经实现完成”
