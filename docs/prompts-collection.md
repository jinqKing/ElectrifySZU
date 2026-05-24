# 近期 Prompt 精选分享

> 整理自 Codex 会话记录（2026-05-20 ~ 2026-05-22）
> 项目：**ElectrifySZU** — 深大电费查询仪表盘

---

## 目录

1. [多 Agent 并行开发与安全重构](#1-多-agent-并行开发与安全重构)
2. [功能迭代与 UI 优化](#2-功能迭代与-ui-优化)
3. [分支与 Worktree 管理](#3-分支与-worktree-管理)
4. [静态页面与子模块](#4-静态页面与子模块)
5. [测试与 CI](#5-测试与-ci)
6. [版本管理](#6-版本管理)

---

## 1. 多 Agent 并行开发与安全重构

这类 Prompt 展示了如何将大型任务拆解为多 Agent 并行作业，是 Codex 在多人协作环境下的最佳实践。

### 1.1 🔐 安全边界 + 告警一致性 + CI 三方并行

> **一句话：** 把一个大任务拆成 Worker A/B/C 三个并行 Agent，指定各自的文件范围，互不干扰。

```
请对整个项目做一次全面的优化建议，从几个方面来说。
work-intro 正在改先不管。

---

你能给这个项目整体做什么优化建议，从几个角度说。但不要修改任何文件。

---

请考虑 server.py 安全边界、subscription_alerts 与 likes/alert 的一致性、
AlertRunner 的四元组、client/campus、SubscriptionStore CSV 原子写、
likes.json 原子写、token 存储/过期边界。
要求输出：
1) 一个安全+CI的优化计划（最小的改动）
2) 测试建议
3) 任何会影响现有行为的文件改动的风险
不要修改 web/work-intro.html。
```

**Agent 分工执行：**

```
现在开始实施计划。跟之前一样，一个 agent 完成工作后要 commit。
每完成一部分就 commit。

现在分3个 Worker：
- Worker A：负责 server.py 安全边界。禁止修改 web/work-intro.*，不要 revert 用户改动。
  写入范围：server.py + tests/test_server_security.py
- Worker B：负责存储/alert 一致性。禁止修改 web/work-intro.*，不要 revert 用户改动。
  写入范围：subscription_alerts/store.py, subscription_alerts/alerts.py + tests
- Worker C：负责 CI。禁止修改 web/work-intro.*，不要 revert 用户改动。
  写入范围：.github/workflows/ci.yml

请给出计划之后一次性实施。
```

**安全边界的具体指令：**

```
Worker A，强化 server.py 安全边界。
这是代码仓库 D:\ElectrifySZU，你不是唯一在改代码的人。
写入范围只限于 server.py 和必要的 tests/test_server_security.py。

目标实现计划中的 server.py 安全边界：
- /api/alerts/check 改为 POST + X-Admin-Token/ALERT_ADMIN_TOKEN
- POST 同源校验
- 请求体大小/JSON content-type 限制
- like ID 的 seenIds 校验
- access log query 注入
- _request_base_url 配合 PUBLIC_BASE_URL 限制合法 host

之前先确认当前状态。
```

### 1.2 📦 订阅/邮件路径 + 数据层加固

```
Worker A，完善订阅/邮件路径测试，顺路加固 subscription_alerts/store.py 的字段校验。
你不是唯一在改代码的人，不要修改 room-power-monitor/src/api.py，不要修改 web/ 任何文件。

写入范围限于：
subscription_alerts/store.py
subscription_alerts/verification.py
subscription_alerts/email_service.py
subscription_alerts/email_templates.py
以及对应的 test 文件。

目标：
1) 为 build_verification_url/create_pending_subscription/send_xxx 写单元测试
2) 字段校验：邮箱格式、token 格式、过期时间合理性
3) 使用 pytest fixture 管理测试数据
4) 不 mock 外部依赖的地方用 tmp_path

完成后提交 commit，汇报改了什么。
```

### 1.3 🏠 room-power-monitor 解析层加固

```
Worker B，负责稳固 room-power-monitor 解析层。
你不是唯一在改代码的人，不要修改 subscription_alerts/ 和 web/。

写入范围限于 room-power-monitor/src/api.py 及必要的 tests/。

目标：
1) 减少对 Excel 单元格硬编码位置依赖，改用表头匹配 usage/recharge
2) 缺关键列时抛出明确错误，不返回默认数据
3) 保证 public return shape 一致
4) 全面测试至少覆盖三个校区

完成后提交 commit，汇报改了什么和测试结果。
```

### 1.4 🧩 app.js 拆分为模块

```
Worker C，负责拆分 web/app.js 为独立小模块。
你不是唯一在改代码的人，不要修改 subscription_alerts/ 和 room-power-monitor/。

写入范围限于 web/index.html、web/app.js 以及新建的：
web/app-api.js, web/app-like.js, web/app-subscription.js, web/app-chart.js

注意不要整体重构，只做必要的拆分。
目标：
1) 将 api/like/subscription/chart 的可独立测试的线性逻辑从 app.js 拆出去
2) 页面其余部分保持为全局变量和函数
3) 模块内聚、正交设计
4) 拆分后保证功能和视觉不变，保留初始化顺序。

不要提交 commit，汇报改了什么文件以及是否需要回归测试。
```

---

## 2. 功能迭代与 UI 优化

### 2.1 🃏 赞助二维码弹窗

```
pic/qrcode 图片已放好，和 GitHub 拼图放一起。
再加一个对话框，点击显示"打赏一下"的二维码和"感谢支持"文字。
```

### 2.2 🌐 首页文案更新与邮箱自动补全

```
我改动了 index 一些文案，但似乎需要 i18n 对应地方才会更新显示。

现统一为：
"输入深大学号和邮箱，自动查询开始使用"
"查询即实付，让使用更透明"
"自动补全 @email.szu.edu.cn，支持自定义邮箱域名。"
改为：
"自动补全 @email.szu.edu.cn，支持自定义邮箱域名。"

看看怎么优化合适。
```

### 2.3 📊 余额与用电趋势图表优化

```
改动一下 目前电量的折线图 纵坐标的刻度范围，因为数据比较接近 目前纵坐标肉眼看不出来波动，
能不能让纵坐标高度去掉一个固定偏移量，让波动更明显。
```

### 2.4 ⏳ 查询余额加载动效

```
改进一下，每次点击查询时的加载动效。
我发现第一次点击查询能正常显示，第二次就没效果了，有时还会报错误信息。
应该每次点击查询按钮时都触发动画效果。
```

### 2.5 🚫 阻止误刷新提示

```
请将本次对话中的所有改动，恢复为原始状态。
```

### 2.6 🔗 主页与弹窗幻灯片链接

```
参考飞书页面做一个矩阵团队介绍的幻灯片：
https://my.feishu.cn/wiki/EuOXwd1Efi0uLCktmx7cIocynBb

一个 HTML 幻灯片展示团队介绍，可以嵌入弹窗或页面中。
```

### 2.7 📧 邮箱验证系统

```
我不确定你说的文件路径，帮我确认一下对应的 worktree 地址。

我的理解是：用户订阅之后没有进一步操作。
原理一致：只显示"已预登记"。当余额低于阈值时，系统每天都会发一封预警邮件。
这里的变化在哪里？

能不能把验证系统做得更完善一些，同时找比较好的实践性参考。
或者直接作为全局 serve 不用在 worktree 搞，先放一放。
```

---

## 3. 分支与 Worktree 管理

### 3.1 🔄 检查未合并 Worktree

```
帮我查一下当前有哪些 worktree 分支还没有合并。

能不能逐个进入 worktree 查看改了什么，然后给出合并建议？
```

### 3.2 🔍 检查 Master 未提交改动

```
检查一下当前的 master 分支有什么未提交的改动，以及应该怎么处理。

哦对，二维码图片问题也是个改动项，还有 changelog 更新。
```

### 3.3 🧪 新 Branch 测试邮箱验证系统

```
我不确定你说的文件路径，帮我确认一下对应的 worktree 地址。
```

### 3.4 📋 记录 Worktree 端口规则

```
记录到项目说明里：
在 worktree 环境时，每次展示页面需要使用不冲突的端口 `uv run server.py`。
```

### 3.5 🚀 审查并合并 PR

```
项目收到了一个 PR，帮忙看看怎么合并比较合理，准备好后执行。

已经收到 PR，你来看怎么合并。

合并方式有什么建议？直接 cherry-pick 应该不会冲突，还是直接合并 master？
```

---

## 4. 静态页面与子模块

### 4.1 📄 新增静态查询子模块 (lite-web)

```
请查看 room-power-monitor/ 写一个前端查询模块，直接在目录的 index.html 中
使用 JS 实现同样的查询功能，不需要后端/Python 等工具。

就是把 Python 的查询逻辑重写为 JS 即可。

写一个完整实现计划：
在仓库根目录新建一个轻量静态模块 lite-web/，与现有站点视觉一致，
在不启动 server.py 时也可直接通过文件路径访问。
```

### 4.2 🎨 美化 work-intro 页面

```
简单美化一下 work-intro.html，先看一下内容。

可以加点页脚信息，看看有什么信息可以提供给大家。

静态页面直接改文件就可以了，不需要启动服务。

---

横屏提示太大了，从侧边显示也可以。
```

---

## 5. 测试与 CI

### 5.1 🧪 订阅邮件测试 + 字段校验加固

```
补齐订阅邮件模块的单元测试，同时加固字段校验。
```

### 5.2 🤖 添加 Python CI Workflow

```
Worker C，添加 CI。
在 .github/workflows/ci.yml 中添加 Python CI workflow：
- trigger: pull_request, push master, workflow_dispatch
- permissions: contents read
- concurrency group
- ubuntu-latest + setup uv with cache
- Python 3.11, uv sync --extra dev --locked
- env 使用保密值
- uv run pytest -q
```

---

## 6. 版本管理

### 6.1 🏷️ 更新版本到 2.7 → 2.71

```
帮我看看 version 版本号怎么改，
现在用到的版本号写在哪里，改成 2.7。

哦已经改为 2.71 相当于小版本更新了，在 changelog 也记录一下。
```

### 6.2 📖 添加版本读取脚本

```
写一个 JS 脚本从 `<span class="version-label">Version 2.71</span>` 读取版本显示。

版本写在 pyproject.toml 里。
```

---

## 总结

这几天的 Prompt 主要体现了几个有意思的模式：

| 模式 | 说明 |
|------|------|
| **多 Agent 分工** | 将大任务拆成 Worker A/B/C，各自限定文件范围，并行执行后汇总 |
| **范围约束** | 用 "不要修改 xxx" 明确禁止修改区域，避免冲突 |
| **逐步推进** | 先问整体建议 → 确认计划 → 分步执行 → 每步 commit |
| **worktree 管理** | 频繁使用 worktree 进行并行开发，验证后合并回 master |
| **安全与测试意识** | 每次功能迭代都会伴随安全边界加固和测试补充 |

---

*整理于 2026-05-24*
