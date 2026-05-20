# 宿舍不断电

> ElectrifySZU 的宿舍电费查询模块。

本目录保留查询校园电费系统所需的 Python 代码、配置模板和楼栋数据。它面向命令行、本地 API 代理和部署在校园内网的服务器使用；公开的 GitHub Pages 页面只展示静态仪表盘，不直接运行这里的 Python 代码。

## 工作原理

两个参数定位一个房间：

| 参数 | 含义 | 从哪里来 |
|------|------|---------|
| `roomId` | 数据库唯一ID | 网页登录后可得 |
| `roomName` | 房间号(展示用) | 你自己知道 |

两者必须精确匹配。`roomId=7322` + `roomName=713` 有效，但同一栋楼其他房间的 `roomId` 完全不同且不可推算。

## roomId 发现流程

```
浏览器打开 http://192.168.84.3:9090/cgcSims/
  → 选楼栋 → 输房间号 → 点查询
  → 页面跳到 selectList.do → 选日期 → 再点查询
  → 此时复制地址栏完整 URL
  → python -m src.discover "粘贴URL"
```

楼栋列表见 `data/buildings.txt`

## 项目结构

```
room-power-monitor/
├── .env                # 房间配置
├── .env.example        # 模板
├── src/
│   ├── config.py       # .env 读取
│   ├── api.py          # selectList.do 客户端
│   ├── cli.py          # status / usage / json
│   └── discover.py     # roomId 提取工具
└── data/
    └── buildings.txt   # 楼栋列表
```

## 使用

```bash
# 配置（.env）
DORM_ROOM_ID=7322
DORM_ROOM_NAME=713
DORM_CLIENT=192.168.84.87

# 命令行
python -m src.cli status         # 当前状态
python -m src.cli status 714     # 换房间
python -m src.cli json           # JSON 输出
```

在仓库根目录运行 `uv run electrifyszu` 可以启动网页服务和 API 代理。完整查询要求运行环境能够访问深圳大学电费系统。
