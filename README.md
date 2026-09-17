# LIMS / SCADA 设备数据对接服务

这是一个用于接口联调和方案展示的 LIMS / SCADA 中转服务。项目接收 LIMS 工单，向 SCADA 提供待处理工单，接收实验结果，接收检测客户端的开始/结束通知，并将完成结果回推到 LIMS。

项目同时提供一个由 FastAPI 直接托管的网页联调控制台，启动服务后访问 <http://127.0.0.1:8000/> 即可进行可视化演示。

## 功能概览

- LIMS 工单接收与按 `order_no` 幂等保存
- SCADA 工单查询和实验结果 UPSERT
- 检测客户端 `/startTest`、`/stopTest` 设备通知
- SQLite 记录检测会话、时间、状态和样品关联
- 结果查询与 LIMS 回推，默认支持本地 Mock LIMS
- 可替换的录屏/截图 `CaptureAdapter`，默认 Mock 不创建媒体文件
- 原生 HTML/CSS/JavaScript 联调控制台，无前端构建步骤
- Swagger 和 OpenAPI 自动接口说明

## 快速启动

需要 Python 3.10 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --reload
```

启动后：

- 网页控制台：<http://127.0.0.1:8000/>
- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/health>

## 接口清单

| 方法 | 路径 | 调用方 | 作用 |
| --- | --- | --- | --- |
| GET | `/health` | 系统 | 健康检查 |
| POST | `/api/work-orders` | LIMS | 下发工单 |
| GET | `/api/scada/work-orders?experimenter_id=EMP001` | SCADA | 查询待处理工单 |
| POST | `/api/scada/results` | SCADA | 上传或更新实验结果 |
| POST | `/startTest` | 检测客户端 | 通知开始检测 |
| POST | `/stopTest` | 检测客户端 | 通知结束检测 |
| GET | `/api/work-orders/{order_no}/results` | 联调页面 | 查询工单结果 |
| POST | `/api/work-orders/{order_no}/push-to-lims` | 联调页面/服务 | 回推 LIMS |
| POST | `/mock/lims/results` | 本地 Mock | 模拟 LIMS 接收回推结果 |

## 网页联调演示

打开根路径后，按照页面中的“工单 → 检测 → 结果 → 回推”流程操作：

1. 在“接收 LIMS 工单”中创建工单。
2. 查询 SCADA 工单，确认工单已经保存。
3. 使用盲样号调用“开始检测”和“结束检测”。页面会显示会话状态，服务端 SQLite 会记录 UTC 时间。
4. 上传实验结果，查询结果详情。
5. 点击“回推 LIMS”，默认发送到本地 Mock 地址，并在响应面板查看 JSON。

页面的服务状态、最近响应和操作日志只用于本地联调辅助。接口返回 `code = "500"` 时，页面会按业务失败标记，即使 HTTP 状态仍为 200。录屏和截图显示为 Mock 模式，不代表已经生成真实视频或图片。

## 检测客户端请求示例

```json
{
  "blindSampleNo": "92fbbc8e88c949158fade880b8d69b27"
}
```

成功和业务失败均使用 HTTP 200：

```json
{
  "code": "0010",
  "response": null,
  "message": "成功"
}
```

```json
{
  "code": "500",
  "response": null,
  "message": "未找到正在进行的检测"
}
```

缺少字段、空字段或额外字段属于请求格式错误，由 FastAPI 返回 HTTP 422。

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LIMS_DB_PATH` | 项目根目录 `lims_demo.db` | SQLite 数据库路径 |
| `LIMS_RESULT_URL` | `http://127.0.0.1:8000/mock/lims/results` | LIMS 结果接收地址 |
| `CAPTURE_BACKEND` | `mock` | 当前可用的采集适配器 |

生产联调前，应根据对方确认的地址和协议配置正式 LIMS，不要把本地 Mock 地址作为生产目标。

## 测试与检查

```powershell
pytest
python -m compileall app main.py
python -m pip check
node --check frontend/app.js
```

## 项目文档

- [启动与使用手册](./启动与使用手册.md)
- [项目架构分析](./项目架构分析.md)
- [主要接口和功能](./主要接口和功能.md)

## 原型边界与生产化建议

当前实现用于接口联调和展示，默认没有鉴权、HTTPS、真实录屏程序、消息队列和自动重试。正式部署前应补充 API 鉴权、HTTPS、脱敏日志、数据库备份、LIMS 回推记录与失败重试。并发量增加后，建议迁移到 PostgreSQL，并使用 Outbox 或任务队列保证回推可靠性。
