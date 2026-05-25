# Building Power Ranking

> ElectrifySZU 的整栋楼用电量排行模块。从采样房间的反向查询出发，计算一栋楼内哪些房间最耗电。

## 用途

单个宿舍查询只能看一间房的用电情况。这个模块通过在每层随机抽取少量房间（默认 3 间）、汇总 30 天的用量，生成一棟楼的「耗电量排行榜」，帮助识别异常高耗能房间。

隐私保护：输出的房间名经过掩码处理（只显示首字符）。

## 工作原理

```
楼层范围确定 → 抽样房间名单 → 逐房间查用电总量 → 排序打标 → 写入缓存
```

1. **楼层探测** — 通过 `floor_probe.py` 解析楼栋名称中的楼层区间（如 `5-19 层`），或在运行时实测探测
2. **抽样规划** — 每层从房间后缀 `01..20` 中随机选取 3 个，形成样本清单
3. **批量查询** — 逐个样本房间调用电费系统 API，拿到 30 天累计用量
4. **排序输出** — 按 `total_used_kwh` 降序排列，附加 rank 字段
5. **缓存落盘** — 将结果序列化为 JSON，存入 `data/ranking_cache.json`

## 两种运行模式

| 模式 | 是否需要校园网 | 数据来源 |
|------|--------------|---------|
| `--demo` | 否 | 伪随机生成的模拟数据 |
| 正常模式 | 是 | 真实的校园电费系统 |

## 使用

### 生成演示数据（离线）

```bash
cd building_power_ranking
python -m cache_builder --demo --all
```

### 基于真实数据构建排行

```bash
# 全部楼层、所有已知楼栋
python -m cache_builder --all

# 指定某校区的特定楼栋
python -m cache_builder --client 192.168.84.87 --building-id 7126 --building-name 风槐斋

# 缩小楼层范围
python -m cache_builder --all --min-floor 5 --max-floor 10 --client 192.168.84.87
```

### 楼层探测

```bash
# dry-run 只看推断结果，不发网络请求
python -m floor_probe --dry-run

# 实探并写入 building_floor_ranges.json
python -m floor_probe --client 192.168.84.87
```

## 项目结构

```
building_power_ranking/
├── cache_builder.py        # CLI 入口，编排整体流程
├── ranking.py              # build_ranking() 核心逻辑
├── cache.py                # 缓存读写 / 样例规划 / demo 数据生成
├── floor_probe.py          # 楼层范围探测 + 楼栋文件解析
├── data/
│   ├── ranking_cache.json      # 最新排行结果
│   ├── ranking_cache.example.json  # 示例文件
│   ├── sample_plan.json        # 本次采样的房间分布
│   ├── sample_plan.example.json
│   └── building_floor_ranges.json  # 已探测到的楼层范围
└── *.py (thin wrappers)    # 向后兼容的 re-export，委托给 electrifyszu.ranking.*
```

## 注意

- 本目录下大部分 `.py` 文件只是薄包装，实际实现位于 `electrifyszu/ranking/`。此处保留是为了向后兼容旧的导入路径。
- `cache_builder.py` (134 行) 是唯一在此处独有的较大型脚本，负责串联采样→查询→存盘的完整管线。
- 排行缓存在 `server.py` 冷启动时被预加载，避免首个请求延迟。
