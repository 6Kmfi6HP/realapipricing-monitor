---
name: realapipricing-monitor
description: "监控 AI 订阅价格与促销变化、查询 realapipricing 套餐真实单价、审计榜分依据，或配置定时监控时使用。"
version: 1.0.0
author: Hermes Agent
license: MIT
category: web
metadata:
  hermes:
    tags: [pricing, ai-subscription, monitoring, json-api, price-alert]
    related_skills: [product-price-monitor, web-api-reverse-engineering, priceai-api]
---

# realapipricing.com 价格监控

以**基线**区分当前报价与历史变化。数据来自社区实测及用户面板反推；真实单价是订阅月费除以可用月 token（$/MTok），不等同于官方按量报价。

## 1. 固定比较范围

确定计费类型、厂商、套餐筛选和基线路径。默认订阅、全部厂商，基线为 `~/.hermes/realapipricing/state.json`。

- 日常监控：继续第 2 步。
- 查询当前报价或审计依据：读取 [REFERENCE.md 的「当前报价与数据审计」](REFERENCE.md#当前报价与数据审计)，按当前数据或上游证据链回答，不依赖历史基线。
- 配置定时监控：读取 [REFERENCE.md 的「定时监控」](REFERENCE.md#定时监控)，再按规则创建任务。

已有基线时，核对状态文件中的 `filter`：筛选必须与本次一致；筛选范围不同时使用独立的 `--state` 文件，避免产生虚假的增删信号。缺失或空基线建立当前快照；无历史快照时仅输出当前报价。

**完成标准：** 明确本次分支（日常监控/即时查询/数据审计/定时任务）、筛选范围（计费类型、厂商、套餐正则）与基线路径；若已有基线，确认其筛选范围与本次一致。

## 2. 抓取并预演

在技能目录运行，默认不写基线：

```bash
python3 scripts/fetch_and_diff.py \
  --state ~/.hermes/realapipricing/state.json
```

| 参数 | 选择规则 |
|---|---|
| `--only subscription\|metered\|all` | 默认 `subscription`；仅订阅的 `price_usd` 按月费解读 |
| `--vendor OpenAI` | 厂商名，不区分大小写的精确匹配 |
| `--plan-regex '^chatgpt_plus::'` | 不区分大小写，搜索 `id + 空格 + plan`；用稳定 ID 前缀锁定套餐 |
| `--top 15` | 默认 15；限制新增、移除、其他信号及排行行数，价格变化与到期扫描不受限 |
| `--with-conventions` | 额外抓取口径数据（如汇率与负载混合比） |
| `--commit` | 成功抓取后写入基线，包含首次运行；仅在第 4 步使用 |
| `--force` | 强制在基线筛选不匹配时覆盖基线（日常慎用） |

退出码按实现解读：
- `2`：检测到价格变化、新增或移除（非空数据首次运行亦返回 `2`）。
- `0`：上述三类均无；仍须核对「其他信号」与促销到期。
- `1`：抓取失败或基线筛选不匹配，基线保持原样。结合 stderr 区分具体原因。

**完成标准：** 执行预演并完整读取报告与 stderr；确认数据日期、匹配数量及退出码；若出现基线筛选不匹配告警或抓取失败，保留原基线并查明原因。

## 3. 判读信号

监控字段以脚本 `WATCHED` 为准：`price_usd`、`real_usd_per_mtok`、`monthly_yi`（月额度）、`promo_until`、`unmetered`、`confidence`，另比较 point 的新增与移除。

- 以 `id`（`plan_id::model`）计数和关联。报告的“套餐数”实际是 point 数；同套餐多个模型可重复出现。
- 首次运行的“新增”是初始化快照清单，不是市场新增；后续移除表示数据源不再包含该 point，不直接等同于厂商下架。
- 报告所有变化类别、数据日期和比较日期；价格变化保留旧值、新值及置信度。低置信度变化应表述为测量值变化。
- 促销到期仅表示截止日期已过（按运行机器日期）；必须依据价格变化明细或来源证据判定是否已恢复原价。
- 无变动时的划算排行仅列出真实单价非零的条目；若表格达到 `--top` 上限，需在答复中注明已省略其余条目。

**完成标准：** 价格、新增、移除、其他信号及到期促销均已逐项判读；初始化快照与真实变动已区分；省略范围已如实说明。

## 4. 提交或保留基线
单次查询、预演保留原基线。用户要求建立基线、更新基线或执行已配置监控时，用相同路径和筛选参数加 `--commit` 运行。

提交会重新抓取并更新基线：以本次抓取报告作为最终结果。核对输出包含 `[baseline written]` 或 `[baseline updated]`，且状态文件的 `filter`、`generatedAt`、`count` 与本次运行一致，方可确认提交成功。

**完成标准：** 仅在用户明确要求更新基线或执行定时监控时带 `--commit` 运行；最终答复包含变动结论、数据日期、比较范围及基线更新状态；失败时报告具体错误，无历史数据时报告当前快照并注明缺乏历史基线。

## 脚本与环境验证

修改脚本或验证运行安全时：
1. 运行 `python3 scripts/test_failure_safety.py`，验证网络失败与筛选不匹配时基线字节不变且返回退出码 `1`。
2. 使用临时状态文件（如 `/tmp/test_state.json`）测试受影响的 CLI 参数组合，严禁直接使用生产基线进行破坏性测试。
