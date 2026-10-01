# 按需参考

## 当前报价与数据审计

### 选择数据源

所有端点相对于 `https://realapipricing.com`。数据量、榜单数量及活跃促销以本次响应为准。

| 端点 | 用途 |
|---|---|
| [`/data/points.json`](https://realapipricing.com/data/points.json) | 当前报价主入口；`points` 内联 `<board_key>__score` 等榜分，顶层 `generatedAt` 为数据日期，`mix` 为负载口径 |
| [`/data/site.json`](https://realapipricing.com/data/site.json) | `conventions`、`boards`、`configurations`、`mappings` 等元数据；查询内联榜分时使用上一端点 |
| [`/data/adopted.csv`](https://realapipricing.com/data/adopted.csv) | 导入表格工具查看全量数据 |
| [`/data/benchmark-configurations.json`](https://realapipricing.com/data/benchmark-configurations.json) | 模型、推理档与 harness 组合的原始榜分 |

在技能目录，可复用脚本的抓取与筛选函数列出某厂商全部订阅 point，而不触碰基线：

```bash
python3 - <<'PY'
import json
import sys
sys.path.insert(0, "scripts")
from fetch_and_diff import fetch_json, build_snapshot

data = fetch_json("/data/points.json")
rows, generated = build_snapshot(data, "subscription", "OpenAI", None)
print(json.dumps({"generatedAt": generated, "count": len(rows), "rows": rows},
                 ensure_ascii=False, indent=2))
PY
```

按请求替换筛选参数；榜分、来源等未进入快照的字段从原始 `data["points"]` 按 ID 提取。输出覆盖所有匹配 point，注明数据日期、币种、置信度及缺失字段，即完成当前报价查询。

### 价格口径

| 字段 | 解读 |
|---|---|
| `price_usd` | 美元价格；结合 `billing` 判定计费周期 |
| `real_usd_per_mtok` | 真实混合单价，美元/百万 token |
| `local_price`、`currency` | 本币价格与币种；币种为空时从来源核实，仅凭数值无法推断币种 |
| `list_price`、`list_blended_usd_per_mtok` | 官方按量价及按负载折算的混合单价，与订阅实测单价分开比较 |
| `unmetered` | 对应模型在订阅内是否不占额度，不代表套餐免费 |
| `source`、`confidence` | 社区数据来源与置信度；具体价格结论需要对应来源支持 |

`conventions.usdPerCny` 名称容易误导：项目采用 **CNY per USD**，即 `1 USD = 值 CNY`。核对响应口径后，本币价格除以该值换算美元；汇率与 `standardTokenMix` 使用响应中的值。

`--with-conventions` 获取 `site.json` 的 `conventions`；现有 Markdown 只显示其中的汇率，不展示全部促销元数据，也不将口径写入基线。额外抓取失败仅警告，主报告仍继续，`--commit` 仍可能更新基线。因此涉及汇率或口径的结论，必须另确认该请求成功。

### 证据链与历史比较

从[上游仓库](https://github.com/FeiZhuLulu/real-api-pricing)的 `data/research/` 查对应 round 证据，按 point ID、模型、采样日期关联；当前文件不存在时查看仓库历史。

比较榜分时对齐 board、模型、推理档及 harness；比较价格时同时核对汇率、负载与来源。榜分变化可以是测量或配置修订，并不自动证明模型升级。

现有监控状态不保存榜分、汇率或原始证据。需要这些字段的历史变化时，读取请求日期对应的上游提交或已有原始快照；找不到则说明无法作历史比较。审计完成条件是每个价格或能力结论都有对应来源、日期和可比口径，缺失证据已显式标记。

## 定时监控

仅在用户要求配置时创建任务。保留模型自动调用能力，使调度任务能加载本技能；调度器的调用语法以当前环境提供的工具为准。

任务内容必须固定：
- 频率：未指定时每天一次。
- 命令：脚本绝对路径、该任务专用的基线绝对路径、固定筛选参数，按主流程预演后提交。
- 输出：中文变化报告；只有各变化类别与到期扫描均为空且本次运行成功时静默，初始化、失败或数据异常均报告。现有脚本没有告警去重状态，到期提示会在后续运行继续出现。
- 安全：沿用主流程的基线检查；以提交运行的报告为准，不能仅凭退出码决定静默。

创建后核对调度器返回的任务 ID、频率、命令/提示词与投递目标。用该任务配置完成一次实际运行，并确认基线提交及输出符合规则，才报告监控已配置。
