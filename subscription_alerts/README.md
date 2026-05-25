# Subscription Alerts

> ElectrifySZU 的邮件订阅与预警模块。负责用户的邮箱注册、验证激活、低电量预警以及退订全流程。

## 概要

此模块实现了「先提交 → 邮箱验证 → 激活生效 → 每日巡检 → 阈值报警」的完整闭环。详细的端到端流程请参阅仓库根目录的 [`SUBSCRIPTION_FLOW.md`](../SUBSCRIPTION_FLOW.md)。

## 文件职责

| 文件 | 作用 |
|------|------|
| `store.py` | 订阅模型 (`Subscription`) 及 CSV 持久化。包含增删改查、活跃判定、合并逻辑等 |
| `verification.py` | 待审订阅创建、验证链接拼接、验证邮件发送、token 校验与激活 |
| `alerts.py` | 定时巡检后台线程 (`AlertWorker`) 和单次扫描入口 (`AlertRunner.run_once`) |
| `email_service.py` | SMTP 连接管理与邮件投递 (`EmailService.send`) |
| `email_templates.py` | 各类邮件主题和内容模板（验证、预警、日报） |
| `unsubscribe.py` | 退订处理（通过 token 禁用订阅） |
| `subscriptions.py` | 聚合导出，方便一次性导入常用符号 |
| `test_delivery.py` | 独立运行的测试脚本，可脱离校园网验证发信链路 |

## 关键概念

- **Pending 状态**：刚提交的订阅 `enabled=false, verified=false`，等待用户点击验证邮件
- **Active 状态**：验证通过后 `enabled=true, verified=true`，纳入每日巡检
- **Daily cap**：每条订阅一天最多收到一封预警邮件（通过 `last_alert_date` 控制）

## 集成方式

在 `server.py` 中被以下路由调用：

- `POST /api/subscriptions` → `verification.create_pending_subscription()`
- `GET /api/subscriptions/verify?token=` → `verification.verify_subscription()`
- `GET /api/unsubscribe?token=` → `unsubscribe.unsubscribe_subscription()`
- `POST /api/alerts/check` → `alerts.AlertRunner.run_once()`

启动时还会拉起后台线程 `alerts.start_alert_worker()`，每天在 `ALERT_CHECK_TIME` 执行一轮巡检。

## 测试发信

在校外或不具备校园网条件的环境下，可以用自带的测试脚本走通发信链路：

```bash
python -m test_delivery --email you@example.com [--alert|--report]
```

这会创建一个临时订阅、跳过校园网查询环节，直接向指定邮箱发送邮件以验证 SMTP 配置是否正确。

## 注意

- 同 `building_power_ranking`，本目录下的大部分 `.py` 已是薄包装，实际实现在 `electrifyszu/subscription/`。此处保留以保证旧导入路径不中断。
- `test_delivery.py` 是本目录独有的实用脚本。
