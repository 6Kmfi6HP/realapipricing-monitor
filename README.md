# realapipricing-monitor

> AI 订阅与按量价格监控技能（基于 [realapipricing.com](https://realapipricing.com) 数据接口）

用于跟踪主流 AI 模型订阅价格、真实单价（$/MTok）、可用月额度（亿 token）、促销生命周期及官方按量报价变动。具备基线差分、防误覆盖安全保护及离线容灾测试。

## 目录结构

```text
.
├── SKILL.md                  # 技能定义与 Agent 4 步执行流（符合 writing-great-skills 规范）
├── REFERENCE.md              # 渐进披露参考（价格口径、数据源端点、证据链审计与定时任务）
├── scripts/
│   ├── fetch_and_diff.py     # 核心抓取、差分、预演与基线提交脚本
│   └── test_failure_safety.py# 离线安全单元测试（网络失败、筛选不匹配与强制覆盖）
├── LICENSE                   # MIT 许可证
└── README.md
```

## 核心特性

- **真实单价计算**：以订阅月费除以可用月 token（$/MTok），还原真实使用成本，不等同于官方按量标价。
- **多维监控与差分**：监控价格变动、可用月额度（`monthly_yi`）、促销截止日（`promo_until`）、免额度状态（`unmetered`）及置信度（`confidence`）。
- **基线防投毒保护**：检测基线筛选范围（`filter`）；当基线与当前筛选条件不匹配时，预演输出告警，`--commit` 自动拦截并拒绝覆写，避免因局部筛选导致全量基线丢失。
- **到期扫描与促销活动**：自动归类已截止与未来 30 天内即将到期的促销活动；支持结合 `site.json` 渲染官方活动说明与汇率口径。

## 快速使用

### 1. 抓取并预演（Dry Run）

默认使用订阅筛选，不修改基线：

```bash
python3 scripts/fetch_and_diff.py --state ~/.hermes/realapipricing/state.json
```

常用参数组合：

```bash
# 监控特定厂商（如 OpenAI）
python3 scripts/fetch_and_diff.py --vendor OpenAI --state ~/.hermes/realapipricing/openai.json

# 监控按量计费套餐
python3 scripts/fetch_and_diff.py --only metered --state ~/.hermes/realapipricing/metered.json

# 同时拉取汇率与官方促销元数据
python3 scripts/fetch_and_diff.py --with-conventions --top 10
```

### 2. 提交更新基线

确认预演报告无误后，添加 `--commit` 写入状态文件：

```bash
python3 scripts/fetch_and_diff.py --state ~/.hermes/realapipricing/state.json --commit
```

### 3. 运行离线安全测试

验证主数据抓取异常及筛选不匹配时的基线保护机制：

```bash
python3 scripts/test_failure_safety.py
```

## 退出码规范

- `0`：无价格/增删变动（仍须查看其他信号与促销到期）。
- `2`：检测到价格变化、新增或移除（首次运行亦返回 `2`）。
- `1`：抓取失败或基线筛选不匹配，原基线字节不变。

## 许可证

[MIT License](LICENSE)
