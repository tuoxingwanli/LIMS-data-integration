# LIMS 数据对接 Demo

一个基于 **FastAPI + SQLite + JSON** 的 LIMS / SCADA 数据对接原型，用于快速验证“工单下发、实验执行、结果回传”的完整业务闭环。

## 功能概览

```text
第三方 LIMS 下发工单
        ↓
本系统保存 work_orders / samples
        ↓
SCADA 按实验人员 ID 获取工单
        ↓
SCADA 上传检测结果
        ↓
本系统保存 test_results
        ↓
本系统回推结果至第三方 LIMS
```

- 工单按 `order_no` 幂等接收，避免重复下发造成重复数据。
- 一个工单可包含多个样品和多个检测项目。
- SCADA 可分批上传结果；同一“工单 + 样品 + 检测项目”重复上传时自动更新。
- 结果成功回推 LIMS 后，工单状态更新为 `pushed`。
- 内置 Mock LIMS，单机即可完成全流程联调。
- 提供自动生成的 Swagger 接口页面。

## 技术栈

| 类型 | 选型 |
| --- | --- |
| Web 框架 | FastAPI |
| 数据库 | SQLite |
| HTTP 客户端 | httpx |
| 接口格式 | JSON / REST |

项目刻意不引入 ORM、Redis、消息队列、Docker、微服务或复杂权限，便于第一阶段快速确认接口协议。

## 快速启动

要求：Python 3.10 或以上。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

启动成功后访问：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

首次启动会自动生成本地数据库 `lims_demo.db`。

## 核心接口

| 调用方 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| LIMS | `POST` | `/api/work-orders` | 下发工单 |
| SCADA | `GET` | `/api/scada/work-orders?experimenter_id=EMP001` | 获取待处理工单 |
| SCADA | `POST` | `/api/scada/results` | 上传或更新检测结果 |
| 联调 | `GET` | `/api/work-orders/{order_no}/results` | 查询工单结果 |
| 本系统 | `POST` | `/api/work-orders/{order_no}/push-to-lims` | 回推结果至 LIMS |

## 最小联调示例

### 1. LIMS 下发工单

```json
{
  "order_no": "WO20260910001",
  "experimenter_id": "EMP001",
  "project_name": "钢材成分检测",
  "samples": [
    {"sample_no": "S001", "sample_name": "钢材样品1"},
    {"sample_no": "S002", "sample_name": "钢材样品2"}
  ],
  "test_items": ["Fe", "C", "Mn"]
}
```

调用：`POST /api/work-orders`

### 2. SCADA 上传结果

```json
{
  "order_no": "WO20260910001",
  "results": [
    {"sample_no": "S001", "test_item": "Fe", "value": 96.2, "unit": "%"},
    {"sample_no": "S001", "test_item": "C", "value": 0.42, "unit": "%"}
  ],
  "finished": true
}
```

调用：`POST /api/scada/results`

### 3. 回推 LIMS

```text
POST /api/work-orders/WO20260910001/push-to-lims
```

默认会回推到本地 Mock 接口；服务终端将打印其收到的 JSON。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `LIMS_DB_PATH` | `lims_demo.db` | SQLite 数据库文件位置 |
| `LIMS_RESULT_URL` | `http://127.0.0.1:8000/mock/lims/results` | 第三方 LIMS 结果接收地址 |

正式联调前请将 `LIMS_RESULT_URL` 改为对方正式接口，并补充双方确认的鉴权、字段映射、超时与重试协议。

## 文档

- [项目架构分析](./项目架构分析.md)
- [启动与使用手册](./启动与使用手册.md)

## 生产化前建议

该项目是单机原型。正式使用前建议增加 API 鉴权、HTTPS、调用审计、失败重试、数据库备份和监控；当并发量或数据规模增长后，再迁移到 PostgreSQL 并拆分业务模块。
