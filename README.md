# LIMS 设备数据对接服务

这是一个基于 FastAPI、SQLite 和 JSON 的 LIMS/SCADA 对接原型，用于验证工单下发、检测客户端通知、实验结果上传和结果回推的完整链路。

## 功能概览

- 接收 LIMS 工单，并按 `order_no` 幂等保存。
- 按实验人员查询 SCADA 待处理工单。
- 支持分批上传实验结果，并按工单、样品和检测项目 UPSERT。
- 将完成的实验结果回推到配置的 LIMS 地址。
- 按对方接口文档提供 `/startTest` 和 `/stopTest`。
- 保存检测会话的盲样号、开始时间、结束时间、状态和可选样品关联。
- 使用可替换的录屏/截图适配器；默认 Mock 适配器不创建真实媒体文件。
- 自动生成 Swagger 和 OpenAPI 文档。

## 业务流程

```text
LIMS 下发工单
    -> 本服务保存工单和样品
    -> SCADA 获取工单
    -> 检测客户端调用 /startTest
    -> 采集适配器开始录制并保存开始时间
    -> SCADA 上传实验结果
    -> 检测客户端调用 /stopTest
    -> 采集适配器结束录制、截图并保存结束时间
    -> 本服务将结果回推 LIMS
```

## 项目结构

```text
.
├── app/
│   ├── api/routes/          # HTTP 路由
│   ├── core/                # 配置和时间工具
│   ├── db/                  # SQLite 连接和建表
│   ├── integrations/        # LIMS、录屏和截图适配器
│   ├── repositories/        # 数据持久化
│   ├── schemas/             # Pydantic 请求响应模型
│   └── services/            # 工单和检测会话业务逻辑
├── tests/                   # 接口和业务回归测试
├── main.py                  # 兼容启动入口
├── requirements.txt         # 运行依赖
└── requirements-dev.txt     # 测试依赖
```

## 快速启动

要求 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --reload
```

启动后访问：

- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/health>

首次启动会在 `LIMS_DB_PATH` 指定的位置创建 SQLite 数据库，默认是项目根目录下的 `lims_demo.db`。

## 接口一览

| 调用方 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 系统 | GET | `/health` | 健康检查 |
| LIMS | POST | `/api/work-orders` | 下发工单 |
| SCADA | GET | `/api/scada/work-orders?experimenter_id=EMP001` | 获取待处理工单 |
| SCADA | POST | `/api/scada/results` | 上传或更新实验结果 |
| 检测客户端 | POST | `/startTest` | 开始检测通知 |
| 检测客户端 | POST | `/stopTest` | 结束检测通知 |
| 联调 | GET | `/api/work-orders/{order_no}/results` | 查询实验结果 |
| 本服务 | POST | `/api/work-orders/{order_no}/push-to-lims` | 回推 LIMS |
| 本地 Mock | POST | `/mock/lims/results` | 模拟 LIMS 接收结果 |

## 检测客户端接口

请求头使用 `Content-Type: application/json`，请求体为：

```json
{
  "blindSampleNo": "92fbbc8e88c949158fade880b8d69b27"
}
```

开始检测：

```text
POST /startTest
```

结束检测：

```text
POST /stopTest
```

成功响应：

```json
{
  "code": "0010",
  "response": null,
  "message": "成功"
}
```

业务失败仍返回 HTTP 200，响应中的 `code` 为 `500`。缺少字段、字段为空或增加未定义字段时，返回 HTTP 422。

同一盲样号重复开始不会重复创建活动会话；重复结束也按幂等成功处理。盲样号可以不属于现有工单，若能匹配 `samples.sample_no` 则会自动建立关联。

## 工单和结果示例

下发工单：

```json
{
  "order_no": "WO20260917001",
  "experimenter_id": "EMP001",
  "project_name": "钢材成分检测",
  "samples": [
    {"sample_no": "S001", "sample_name": "钢材样品1"}
  ],
  "test_items": ["Fe", "C", "Mn"]
}
```

上传结果：

```json
{
  "order_no": "WO20260917001",
  "results": [
    {"sample_no": "S001", "test_item": "Fe", "value": 96.2, "unit": "%"},
    {"sample_no": "S001", "test_item": "C", "value": 0.42, "unit": "%"}
  ],
  "finished": true
}
```

回推结果：

```text
POST /api/work-orders/WO20260917001/push-to-lims
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LIMS_DB_PATH` | `lims_demo.db` | SQLite 数据库路径 |
| `LIMS_RESULT_URL` | `http://127.0.0.1:8000/mock/lims/results` | LIMS 结果接收地址 |
| `CAPTURE_BACKEND` | `mock` | 录屏/截图适配器，当前支持 `mock` |

## 测试

```powershell
python -m pytest
python -m compileall app main.py
python -m pip check
```

## 文档

- [主要接口和功能](./主要接口和功能.md)
- [启动与使用手册](./启动与使用手册.md)
- [项目架构分析](./项目架构分析.md)

## 原型边界

当前实现用于接口联调，默认不会调用 Windows 录屏程序，也不会生成真实视频或截图。正式部署前应接入经过确认的采集程序，补充鉴权、HTTPS、结构化日志、失败重试、数据库备份和监控；并发量增大后再评估迁移 PostgreSQL 和 Outbox 任务模式。
