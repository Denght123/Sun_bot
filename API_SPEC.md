# API 规格文档 API_SPEC

## 1. 文档目的
本文定义基金理财热点消息机器人 MVP 的云端 API 规范，主要覆盖以下通信场景：
- Windows 发信端向云端上报心跳
- Windows 发信端拉取待发送任务
- Windows 发信端回传发送结果
- 管理员手动触发日报生成与补跑
- 管理端查询日报与任务状态

本文以当前技术设计为准，默认部署在阿里云 ECS，云端服务由 FastAPI 提供。

---

## 2. 设计范围

### 2.1 API使用方
- **Windows 发信端 Sender Agent**
- **管理员/运维人员**
- **后续可扩展的内部后台服务**

### 2.2 非范围
- 微信用户直接调用的外部开放 API
- 面向第三方开发者的开放平台 API
- 多租户鉴权体系

---

## 3. 通用约定

### 3.1 基础信息
- Base URL：`https://<your-domain-or-ip>`
- API 前缀：`/api`
- 数据格式：`application/json`
- 字符编码：`UTF-8`
- 时间格式：ISO 8601，服务端统一以 `Asia/Shanghai` 为业务时区

### 3.2 响应结构
成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

失败响应：

```json
{
  "code": 1001,
  "message": "sender not found",
  "data": null
}
```

### 3.3 状态码约定
| HTTP状态码 | 含义 |
|---|---|
| 200 | 请求成功 |
| 400 | 参数错误 |
| 401 | 未认证或签名错误 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 状态冲突 |
| 429 | 请求过于频繁 |
| 500 | 服务内部异常 |

### 3.4 认证建议
MVP 推荐使用以下其中一种：
- 发信端使用固定 `sender_token`
- 管理端使用 `admin_token`
- Header 建议：`Authorization: Bearer <token>`

后续若扩展，可切换为更规范的 API Key / JWT 机制。

---

## 4. 发信端接口

## 4.1 发信端心跳上报
用于发信端周期性上报在线状态、微信登录状态、版本信息。

- **Method**：`POST`
- **Path**：`/api/sender/heartbeat`

### 请求头
```http
Authorization: Bearer <sender_token>
Content-Type: application/json
```

### 请求体
```json
{
  "sender_id": "sender-win-001",
  "status": "online",
  "wechat_login_status": "logged_in",
  "client_version": "0.1.0",
  "host_name": "WIN-SENDER-01",
  "ip": "192.168.1.10",
  "timestamp": "2026-03-07T07:55:00+08:00"
}
```

### 字段说明
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| sender_id | string | 是 | 发信端唯一标识 |
| status | string | 是 | online / offline / degraded |
| wechat_login_status | string | 是 | logged_in / logged_out / unknown |
| client_version | string | 否 | 客户端版本 |
| host_name | string | 否 | 主机名 |
| ip | string | 否 | 本机 IP |
| timestamp | string | 是 | 心跳上报时间 |

### 成功响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "server_time": "2026-03-07T07:55:01+08:00",
    "next_heartbeat_in_seconds": 30
  }
}
```

---

## 4.2 拉取待发送任务
发信端轮询云端，拉取待发送的消息任务。

- **Method**：`GET`
- **Path**：`/api/sender/tasks/pending`

### Query 参数
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| sender_id | string | 是 | 发信端唯一标识 |
| limit | int | 否 | 默认 1，最大 10 |

### 请求示例
```http
GET /api/sender/tasks/pending?sender_id=sender-win-001&limit=1
Authorization: Bearer <sender_token>
```

### 成功响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "tasks": [
      {
        "task_id": "task_20260307_080000_001",
        "report_date": "2026-03-07",
        "task_type": "daily_report",
        "target_user": "my_wechat_id",
        "message_chunks": [
          "【基金理财热点早报】\n1. 今日总览...",
          "【板块观察】\n1. AI..."
        ],
        "max_retry": 3,
        "created_at": "2026-03-07T07:59:50+08:00"
      }
    ]
  }
}
```

### 无任务响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "tasks": []
  }
}
```

---

## 4.3 回传发送结果
发信端在任务执行后回传发送状态。

- **Method**：`POST`
- **Path**：`/api/sender/tasks/{task_id}/result`

### 路径参数
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| task_id | string | 是 | 发送任务 ID |

### 请求体
```json
{
  "sender_id": "sender-win-001",
  "success": true,
  "status": "sent",
  "error_message": "",
  "retryable": false,
  "sent_at": "2026-03-07T08:00:12+08:00",
  "detail": {
    "chunk_count": 2,
    "wechat_account": "my_wechat_id"
  }
}
```

### 字段说明
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| sender_id | string | 是 | 发信端 ID |
| success | bool | 是 | 是否发送成功 |
| status | string | 是 | sent / failed / partial |
| error_message | string | 否 | 错误信息 |
| retryable | bool | 否 | 是否建议服务端重试 |
| sent_at | string | 是 | 发送完成时间 |
| detail | object | 否 | 扩展诊断信息 |

### 成功响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_status": "sent"
  }
}
```

---

## 4.4 上报发信端主动异常
用于发信端在检测到微信掉线、自动化异常时主动上报。

- **Method**：`POST`
- **Path**：`/api/sender/events`

### 请求体
```json
{
  "sender_id": "sender-win-001",
  "event_type": "wechat_logged_out",
  "level": "warning",
  "message": "wechat session lost",
  "occurred_at": "2026-03-07T07:40:00+08:00"
}
```

### event_type 建议值
- `wechat_logged_out`
- `wechat_window_not_found`
- `sender_process_error`
- `network_unavailable`

---

## 5. 日报与管理端接口

## 5.1 手动触发日报生成
用于管理员手动补跑日报或测试流程。

- **Method**：`POST`
- **Path**：`/api/admin/report/run`

### 请求体
```json
{
  "report_date": "2026-03-07",
  "mode": "manual",
  "force_regenerate": false,
  "skip_send": false
}
```

### 字段说明
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| report_date | string | 是 | 目标日报日期 |
| mode | string | 否 | manual / retry |
| force_regenerate | bool | 否 | 是否强制重新生成 |
| skip_send | bool | 否 | 是否只生成不发送 |

### 成功响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "job_id": "job_report_run_20260307_001",
    "status": "queued"
  }
}
```

---

## 5.2 查询日报详情
用于查看某天日报内容及生成状态。

- **Method**：`GET`
- **Path**：`/api/admin/reports/{report_date}`

### 响应示例
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "report_date": "2026-03-07",
    "generation_status": "success",
    "fallback_used": false,
    "full_text": "【基金理财热点早报】...",
    "created_at": "2026-03-07T07:54:33+08:00"
  }
}
```

---

## 5.3 查询发送任务详情
用于查看任务执行状态、重试情况、失败原因。

- **Method**：`GET`
- **Path**：`/api/admin/tasks/{task_id}`

### 响应示例
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "task_20260307_080000_001",
    "status": "sent",
    "retry_count": 0,
    "last_error": "",
    "sender_id": "sender-win-001",
    "scheduled_at": "2026-03-07T08:00:00+08:00",
    "sent_at": "2026-03-07T08:00:12+08:00"
  }
}
```

---

## 5.4 查询发信端状态
用于运维检查发信端是否在线。

- **Method**：`GET`
- **Path**：`/api/admin/senders/{sender_id}/status`

### 响应示例
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "sender_id": "sender-win-001",
    "status": "online",
    "wechat_login_status": "logged_in",
    "last_heartbeat_at": "2026-03-07T07:59:40+08:00",
    "is_healthy": true
  }
}
```

---

## 5.5 获取关键词菜单内容
用于发信端根据用户输入拉取菜单或模块内容。

- **Method**：`GET`
- **Path**：`/api/content/menu`

### Query 参数
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| keyword | string | 是 | 功能 / 早报 / 板块 / 政策 / 国际 / 热搜 / 风险 / 帮助 |
| report_date | string | 否 | 默认当天 |

### 成功响应
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "keyword": "板块",
    "title": "Top10热门财经板块",
    "content": "1. AI\n2. 医药...",
    "message_chunks": [
      "【板块】\n1. AI..."
    ]
  }
}
```

---

## 6. 状态机定义

## 6.1 日报生成状态 generation_status
| 状态 | 说明 |
|---|---|
| pending | 待生成 |
| processing | 生成中 |
| success | 生成成功 |
| failed | 生成失败 |
| fallback_success | 降级生成成功 |

## 6.2 发送任务状态 dispatch_task.status
| 状态 | 说明 |
|---|---|
| pending | 已创建待下发 |
| dispatched | 已下发给发信端 |
| sending | 发信端执行中 |
| sent | 发送成功 |
| failed | 发送失败 |
| waiting_sender | 发信端不在线 |
| cancelled | 已取消 |

## 6.3 发信端状态 sender.status
| 状态 | 说明 |
|---|---|
| online | 正常在线 |
| offline | 离线 |
| degraded | 在线但状态异常 |

---

## 7. 错误码建议
| code | 含义 |
|---|---|
| 0 | 成功 |
| 1001 | sender 不存在 |
| 1002 | sender token 无效 |
| 1003 | 参数校验失败 |
| 1004 | 任务不存在 |
| 1005 | 当前无待发送任务 |
| 1006 | 任务状态冲突 |
| 1007 | 报表不存在 |
| 1008 | 发信端状态异常 |
| 2001 | 内部服务异常 |
| 2002 | 数据库异常 |
| 2003 | 调度执行失败 |
| 2004 | LLM 调用失败 |

---

## 8. 安全建议
- 发信端与管理端分离 token
- 管理端接口建议限制来源 IP
- 日志中避免打印完整 token、API Key、敏感配置
- 后续对外网开放时，建议启用 HTTPS
- 对管理接口增加简单审计日志

---

## 9. MVP落地建议
第一阶段至少实现以下 API：
1. `POST /api/sender/heartbeat`
2. `GET /api/sender/tasks/pending`
3. `POST /api/sender/tasks/{task_id}/result`
4. `POST /api/admin/report/run`
5. `GET /api/admin/reports/{report_date}`
6. `GET /api/content/menu`

这些接口足以支撑 MVP 的“日报生成 + 微信发送 + 关键词交互”主链路。
