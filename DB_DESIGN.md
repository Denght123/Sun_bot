# 数据库设计文档 DB_DESIGN

## 1. 文档目的
本文定义基金理财热点消息机器人 MVP 的数据库设计，覆盖核心实体、字段建议、索引建议、状态流转以及数据保留策略。

数据库默认采用 PostgreSQL，Redis 作为缓存与短期状态辅助存储。

---

## 2. 设计目标
- 支撑多源数据抓取与标准化存储
- 支撑事件去重、聚类、分类
- 支撑日报生成结果存档
- 支撑发送任务、重试、失败追踪
- 支撑发信端在线状态与心跳管理
- 为后续多人广播预留扩展空间

---

## 3. 存储分层

### 3.1 PostgreSQL
用于持久化：
- 原始抓取数据
- 聚类事件
- 日报内容
- 发送任务
- 发信端状态
- 错误与审计记录

### 3.2 Redis
用于短期状态与缓存：
- 去重缓存
- 热点临时排行缓存
- 发信端最近在线状态缓存
- 任务轮询优化缓存

---

## 4. 表设计总览
建议核心表如下：
1. `raw_items`
2. `event_clusters`
3. `event_sources`
4. `daily_reports`
5. `report_sections`
6. `dispatch_tasks`
7. `dispatch_attempts`
8. `senders`
9. `sender_heartbeats`
10. `system_events`

---

## 5. 详细表设计

## 5.1 raw_items
存储抓取后的标准化原始内容。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| source_platform | varchar(50) | not null | 来源平台，如 weibo / zhihu / cls |
| source_type | varchar(20) | not null | social / finance |
| external_id | varchar(128) | null | 源站原始 ID |
| title | text | not null | 标题 |
| summary | text | null | 摘要 |
| url | text | null | 原始链接 |
| fallback_url | text | null | 落地页或搜索页 |
| published_at | timestamptz | null | 源内容发布时间 |
| collected_at | timestamptz | not null | 抓取时间 |
| content_hash | varchar(64) | not null | 去重哈希 |
| raw_payload | jsonb | null | 原始抓取结果 |
| language | varchar(10) | null | 语言 |
| is_finance_related | boolean | not null default false | 是否财经相关 |
| finance_score | numeric(5,2) | null | 财经相关性评分 |
| process_status | varchar(20) | not null default 'pending' | pending / processed / filtered |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `idx_raw_items_source_platform_collected_at`
- `idx_raw_items_content_hash`
- `idx_raw_items_is_finance_related`
- `idx_raw_items_published_at`

---

## 5.2 event_clusters
存储聚类后的事件主记录。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| event_key | varchar(128) | unique | 聚类唯一键 |
| title | text | not null | 聚类后的主标题 |
| category | varchar(30) | not null | overview / sector / policy / international / risk / hot_topic |
| sub_category | varchar(50) | null | 细分类，如 ai / 医药 / 地产 |
| importance_score | numeric(6,2) | not null default 0 | 综合重要度 |
| heat_score | numeric(6,2) | not null default 0 | 热度分 |
| source_count | int | not null default 0 | 合并来源数 |
| first_seen_at | timestamptz | null | 首次出现时间 |
| last_seen_at | timestamptz | null | 最后出现时间 |
| cluster_date | date | not null | 所属业务日期 |
| status | varchar(20) | not null default 'active' | active / dropped |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `uk_event_clusters_event_key`
- `idx_event_clusters_cluster_date_category`
- `idx_event_clusters_importance_score`
- `idx_event_clusters_last_seen_at`

---

## 5.3 event_sources
建立聚类事件与原始抓取内容的映射关系。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| cluster_id | bigint | FK -> event_clusters.id | 聚类事件 ID |
| raw_item_id | bigint | FK -> raw_items.id | 原始内容 ID |
| source_weight | numeric(5,2) | null | 来源权重 |
| created_at | timestamptz | not null | 创建时间 |

### 索引建议
- `idx_event_sources_cluster_id`
- `idx_event_sources_raw_item_id`
- `(cluster_id, raw_item_id)` 唯一索引

---

## 5.4 daily_reports
存储日报主记录。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| report_date | date | unique | 日报日期 |
| generation_status | varchar(30) | not null | pending / processing / success / failed / fallback_success |
| fallback_used | boolean | not null default false | 是否使用降级模板 |
| data_window_start | timestamptz | not null | 数据窗口开始 |
| data_window_end | timestamptz | not null | 数据窗口结束 |
| total_word_count | int | null | 总字数 |
| total_message_chunks | int | null | 拆分消息数 |
| full_text | text | null | 完整日报文本 |
| link_bundle | jsonb | null | 链接集合 |
| generated_at | timestamptz | null | 生成完成时间 |
| last_error | text | null | 最后错误 |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `uk_daily_reports_report_date`
- `idx_daily_reports_generation_status`

---

## 5.5 report_sections
存储日报模块级内容，便于关键词查询。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| report_id | bigint | FK -> daily_reports.id | 日报 ID |
| section_key | varchar(30) | not null | overview / sector / policy / international / hot_topics / risk / help |
| title | varchar(100) | not null | 模块标题 |
| content | text | not null | 模块正文 |
| message_chunks | jsonb | null | 预拆分消息数组 |
| sort_order | int | not null default 0 | 展示顺序 |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `idx_report_sections_report_id`
- `(report_id, section_key)` 唯一索引

---

## 5.6 dispatch_tasks
存储发送任务主记录。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| task_id | varchar(64) | unique | 业务任务号 |
| report_id | bigint | FK -> daily_reports.id | 关联日报 |
| sender_id | varchar(64) | null | 指定发信端 |
| target_user | varchar(128) | not null | 目标微信用户 |
| task_type | varchar(30) | not null | daily_report / keyword_reply / manual_resend |
| payload | jsonb | not null | 待发送内容 |
| status | varchar(30) | not null | pending / dispatched / sending / sent / failed / waiting_sender / cancelled |
| retry_count | int | not null default 0 | 已重试次数 |
| max_retry | int | not null default 3 | 最大重试次数 |
| scheduled_at | timestamptz | not null | 计划发送时间 |
| dispatched_at | timestamptz | null | 下发时间 |
| sent_at | timestamptz | null | 实际完成时间 |
| last_error | text | null | 最后错误 |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `uk_dispatch_tasks_task_id`
- `idx_dispatch_tasks_status_scheduled_at`
- `idx_dispatch_tasks_sender_id`
- `idx_dispatch_tasks_report_id`

---

## 5.7 dispatch_attempts
记录每次发送尝试，便于排障与审计。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| task_id | bigint | FK -> dispatch_tasks.id | 主任务 ID |
| attempt_no | int | not null | 第几次尝试 |
| sender_id | varchar(64) | null | 执行发信端 |
| status | varchar(20) | not null | success / failed |
| error_code | varchar(50) | null | 错误码 |
| error_message | text | null | 错误描述 |
| retryable | boolean | not null default true | 是否可重试 |
| started_at | timestamptz | null | 尝试开始时间 |
| finished_at | timestamptz | null | 尝试结束时间 |
| created_at | timestamptz | not null | 创建时间 |

### 索引建议
- `idx_dispatch_attempts_task_id`
- `(task_id, attempt_no)` 唯一索引

---

## 5.8 senders
存储发信端注册信息。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| sender_id | varchar(64) | unique | 发信端唯一 ID |
| sender_name | varchar(100) | null | 发信端名称 |
| status | varchar(20) | not null | online / offline / degraded |
| wechat_login_status | varchar(20) | not null | logged_in / logged_out / unknown |
| host_name | varchar(100) | null | 主机名 |
| current_ip | varchar(64) | null | 当前 IP |
| client_version | varchar(50) | null | 版本号 |
| last_heartbeat_at | timestamptz | null | 最后心跳时间 |
| token_hash | varchar(128) | null | token 摘要 |
| created_at | timestamptz | not null | 创建时间 |
| updated_at | timestamptz | not null | 更新时间 |

### 索引建议
- `uk_senders_sender_id`
- `idx_senders_status`
- `idx_senders_last_heartbeat_at`

---

## 5.9 sender_heartbeats
存储发信端心跳明细，用于监控与历史排查。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| sender_id | bigint | FK -> senders.id | 发信端主键 |
| status | varchar(20) | not null | online / offline / degraded |
| wechat_login_status | varchar(20) | not null | logged_in / logged_out / unknown |
| payload | jsonb | null | 心跳原始内容 |
| reported_at | timestamptz | not null | 上报时间 |
| created_at | timestamptz | not null | 创建时间 |

### 索引建议
- `idx_sender_heartbeats_sender_id_reported_at`

---

## 5.10 system_events
存储系统异常、告警、关键事件。

### 字段设计
| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigserial | PK | 主键 |
| event_type | varchar(50) | not null | report_failed / sender_offline / llm_failed / crawl_failed |
| level | varchar(20) | not null | info / warning / error |
| object_type | varchar(50) | null | report / task / sender / collector |
| object_id | varchar(64) | null | 关联对象标识 |
| message | text | not null | 事件说明 |
| detail | jsonb | null | 扩展详情 |
| occurred_at | timestamptz | not null | 发生时间 |
| created_at | timestamptz | not null | 创建时间 |

### 索引建议
- `idx_system_events_event_type`
- `idx_system_events_level_occurred_at`
- `idx_system_events_object_type_object_id`

---

## 6. 状态流转设计

## 6.1 daily_reports.generation_status
- `pending`：待生成
- `processing`：生成中
- `success`：生成成功
- `failed`：生成失败
- `fallback_success`：降级生成成功

### 推荐流转
`pending -> processing -> success`
`pending -> processing -> failed`
`pending -> processing -> fallback_success`

## 6.2 dispatch_tasks.status
- `pending`：待发送
- `dispatched`：已下发
- `sending`：发送中
- `sent`：成功
- `failed`：失败
- `waiting_sender`：等待发信端上线
- `cancelled`：取消

### 推荐流转
`pending -> dispatched -> sending -> sent`
`pending -> waiting_sender -> dispatched -> sending -> sent`
`pending -> dispatched -> sending -> failed`

## 6.3 senders.status
- `online`
- `offline`
- `degraded`

判定建议：
- 最近 60 秒内有心跳：`online`
- 最近 60-180 秒无心跳：`degraded`
- 超过 180 秒无心跳：`offline`

---

## 7. Redis设计建议

### 7.1 建议Key
- `sender:last_heartbeat:{sender_id}`
- `sender:status:{sender_id}`
- `dispatch:pending:{sender_id}`
- `report:latest`
- `dedup:content_hash:{hash}`

### 7.2 用途
- 提高发信端轮询效率
- 避免重复抓取内容重复入库
- 快速读取最新日报内容

---

## 8. 数据保留策略
- `raw_items`：建议保留 30-90 天
- `event_clusters`：建议保留 90-180 天
- `daily_reports`：建议长期保留
- `dispatch_attempts`：建议保留 180 天
- `sender_heartbeats`：建议保留 30 天
- `system_events`：建议保留 180 天

MVP 可以先全部保留，后续再加归档清理任务。

---

## 9. 约束与规范建议
- 所有时间字段统一使用 `timestamptz`
- 所有业务状态字段统一使用小写枚举值
- 大文本优先使用 `text`
- 结构化扩展字段优先使用 `jsonb`
- 所有表统一保留 `created_at`、`updated_at`

---

## 10. MVP最小建表范围
如果先追求最小可运行版本，优先建以下表：
1. `raw_items`
2. `event_clusters`
3. `daily_reports`
4. `report_sections`
5. `dispatch_tasks`
6. `senders`
7. `sender_heartbeats`

这 7 张表足以支撑主链路跑通；`event_sources`、`dispatch_attempts`、`system_events` 可在第二阶段补齐。
