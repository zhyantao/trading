# 量化交易研究：基金经理 / 选基选股 / 回测

基于公开数据接口（东方财富、天天基金、新浪，AkShare 封装）的研究型项目：抓取基金经理与基金业绩、构建形式化的选基 / 选股评分、生成调仓信号与优化持仓、回测历史表现，并发布为**纯静态站点**。

线上站点：<https://zhyantao.github.io/trading/>

- 数据由 GitHub Actions 每个交易日自动更新，站点无需 Python 服务端。
- 本地也提供 FastAPI 动态站，便于调试与手动跑流水线。
- **仅用于数据研究与学习，不构成任何投资建议。**

---

## 1. 架构总览

```
公开行情接口
    │  增量抓取（只补缺口）
    ▼
out/  ── CSV / MD / PNG ──►  src/generate_static.py  ──►  docs/  ──►  GitHub Pages
    │                              │                        │
    └──► FastAPI 动态站 ◄──────────┴── 共用评分口径 ────────┴──► 静态站 JSON
```

三条口径保证一致：

| 层 | 模块 | 职责 |
| --- | --- | --- |
| 评分 | `src/factor_scoring.py`、`src/selection_formula.py` | 多因子打分、全局选基/选股、股票排名得分 |
| 页面内容 | `src/formula_doc.py`、`src/stock_rankings.py` | 形式化公式文档、股票共识排名 |
| 数据管道 | `src/incremental.py`、`src/market_snapshot.py` | 时序缓存只补缺口、当日快照复用 |

静态站与动态站**共用同一批 Python 模块**，不会出现两边排名不一致。

---

## 2. 目录结构

```
.
├── .github/workflows/update.yml       # 定时更新 + 缓存持久化 + 自动生成/提交 docs
├── requirements.txt
├── README.md
├── src/
│   ├── 数据管道
│   │   ├── build_manager_fund_returns.py           # 经理-基金收益率明细
│   │   ├── rank_fund_managers.py                   # 经理排名（多因子评分）
│   │   ├── rank_all_funds_by_annualized_return.py  # 全市场基金年化排序
│   │   ├── link_fund_annualized_and_manager_rank.py
│   │   ├── pick_elite_managers_targets.py          # 候选池 + 全局 Top3/Top10
│   │   ├── optimize_holdings.py                    # 组合权重
│   │   ├── daily_rebalance_signal.py               # 每日调仓信号
│   │   └── daily_run.py                            # 一键全流程
│   ├── 算法与口径
│   │   ├── factor_scoring.py        # 多因子评分（回报/风险/稳定性/质量）
│   │   ├── selection_formula.py     # 形式化评分、全局选基选股、参数常量
│   │   ├── stock_rankings.py        # 去重股票池 → 综合得分排名
│   │   ├── formula_doc.py           # 「公式」页 MathML 内容源
│   │   ├── economic_cycle.py        # Dalio 周期定位与因子权重调整
│   │   ├── incremental.py           # 时序缓存、增量补数、快照 TTL
│   │   ├── market_snapshot.py       # 全市场排行/经理列表/交易日历当日复用
│   │   └── fund_holdings_source.py  # F10 直连持仓抓取 + 缓存降级
│   ├── 回测
│   │   ├── backtest_common.py                  # 共享引擎、指标、绘图（每行一张）
│   │   ├── backtest_fund_portfolio.py          # 基金净值组合
│   │   ├── backtest_elite_manager_portfolio.py # 重仓股组合
│   │   └── backtest_series.py                 # 净值曲线 → 交互图表 JSON
│   ├── 站点
│   │   ├── generate_static.py        # 生成 docs/
│   │   ├── static_site/*.html        # 10 个静态壳（含 formulas.html）
│   │   ├── webui/                   # FastAPI 动态站（routes / templates / static）
│   │   └── webui/static/
│   │       ├── app.js                # 静态站全部页面渲染
│   │       ├── backtest-chart.js     # 纯 SVG 交互图表（悬浮显示日期与数值）
│   │       └── style.css             # Tufte 风格
├── docs/                              # GitHub Pages 发布目录（自动生成，勿手改）
│   ├── *.html, app.js, style.css, fonts/, favicon.svg, charts/
│   └── data/{YYYYMMDD}/*.json        # 仅保留最近一个日期
└── out/                               # 运行产物（不进仓库）
    ├── 我的持仓.csv
    ├── cache_series/                  # 按标的固定命名的时序缓存
    ├── cache_meta/                    # 全市场排行/经理列表/交易日历快照
    └── 绩优标的_全局{基金Top3,股票Top10}_*.csv
```

---

## 3. 环境准备

Python 3.10+：

```bash
pip install -r requirements.txt
```

主要依赖：`akshare` `pandas` `numpy` `requests` `fastapi` `uvicorn` `jinja2` `apscheduler` `matplotlib`。

> **中文图表字体**：Linux / WSL 需要安装中文字体（如 `fonts-wqy-microhei` 或 Noto Sans SC），否则回测图中文显示为方框；macOS / Windows 自带。

---

## 4. 数据流水线

### 4.1 分步运行

```bash
python3 src/build_manager_fund_returns.py                       # 经理-基金明细
python3 src/rank_fund_managers.py                               # 经理排名
python3 src/rank_all_funds_by_annualized_return.py              # 全市场基金年化排序
python3 src/link_fund_annualized_and_manager_rank.py --min-days 180
python3 src/pick_elite_managers_targets.py --top-n 20 --min-days 180
python3 src/optimize_holdings.py --total-n 5 --stock-pct 30 --fund-pct 70
python3 src/daily_rebalance_signal.py --holdings out/我的持仓.csv
```

常用参数：

| 脚本 | 参数 | 默认 |
| --- | --- | --- |
| `pick_elite_managers_targets.py` | `--top-n` / `--min-days` / `--fund-topk` / `--stock-topk` / `--sleep` | 20 / 180 / 3 / 10 / 0.2 |
| `optimize_holdings.py` | `--total-n` / `--stock-pct` / `--fund-pct` / `--composite` / `--risk-parity` | 5 / 30 / 70 / 关 / 关 |
| `daily_rebalance_signal.py` | `--threshold` / `--top-opportunities` / `--sleep` | 1.0 / 30 / 0.2 |

### 4.2 一键全流程

```bash
python3 src/daily_run.py
```

依次执行：明细 → 经理排名 → 基金年化 → 关联表 → 候选池与全局榜单 → 优化持仓 → 调仓信号 →（可选）两个回测 → 清理旧日期（只保留最新一天）。回测失败只告警，不阻断当日发布。

### 4.3 输出文件

| 类别 | 文件 | 说明 |
| --- | --- | --- |
| 候选池 | `绩优基金经理_基金Top3_*.csv`、`绩优基金经理_股票Top10_*.csv` | 每位经理的候选，供排名 / 优化持仓 / 回测使用 |
| **全局榜单** | `绩优标的_全局基金Top3_*.csv`、`绩优标的_全局股票Top10_*.csv` | 跨所有经理按 S_f / S_s 选出的**唯一 3 只基金 / 10 只股票** |
| 信号 | `每日调仓信号_*.csv` / `.md` | 持仓对照 + 全市场机会 |
| 持仓 | `我的持仓.csv` | 长表追加，记录调仓历史 |
| 回测 | `回测_基金净值曲线_*.csv`、`回测_图表_*.png`、`回测_基金摘要_*.md` 等 | 见第 6 节 |

---

## 5. 选股与选基公式

完整的 MathML 形式化推导见线上「**公式**」页（`formulas.html` / 动态站 `/formulas`），内容由 `src/formula_doc.py` 从代码常量生成。核心如下（`ñ` 为缩尾后 min-max 归一化，`z̃` 为中位数/IQR 稳健标准化）：

**绩优经理集合**（排名前 20、名下基金无负收益、成立 ≥ 180 天）

```
M* = { m | r_m ≤ 20, ∀f∈F_m : R_1(f) ≥ 0 ∧ R_Σ(f) ≥ 0 ∧ D(f) ≥ 180 }
```

**基金多因子基准分**（用于「基金排名」与 `--composite`）

```
S^fac(f) = (1/Σ_k w_k) · Σ_k w_k φ_k(f)
k ∈ {ret 0.35, risk 0.25, stab 0.20, qual 0.20}
```

**全局选基**：所有经理的 Top3 候选并入统一候选池 `F`，按 S_f 只取 3 只（同一基金 A/B/C 份额只留一只）

```
S_f = 0.32·z̃(R_a) + 0.13·z̃(R_1) + 0.25·lñ(1+C_f)
      + 0.20·Q̃_f + 0.10·lñ(1+D_f) − 0.15·1[R_1<0 ∨ R_Σ<0]
F*  = Top_3 { S_f | f ∈ F }
```

`C_f` 为推荐该基金的经理数（共识度），`Q_f = (1/C_f)·Σ 1/r_m` 为经理质量。

**全局选股**：所有经理的 Top10 候选并入 `G`，按 S_s 只取 10 只；完整去重池在「股票排名」页按 S_s 展示

```
S_s = 0.34·lñ(1+M_s) + 0.18·lñ(1+F_s) + 0.18·lñ(1+P_s)
      + 0.12·(1−T̃_s) + 0.18·Q̃_s
G*  = Top_10 { S_s | s ∈ G }
```

`M_s` / `F_s` 为持有该股票的经理数 / 基金数，`P_s` 为平均占净值比例，`T_s` 为最好名次。

**组合权重与信号**

```
w_i   = B · S_i / Σ_j S_j          (w_i ≤ w_max)
w_i^RP= B · (S_i/σ_i) / Σ_j (S_j/σ_j)
N_s   = Σ_{m∈M*} Σ_{f∈F_m} ( B⁺_{f,s} − B⁻_{f,s} )
```

`B` 为大类权重桶（股票 30% / 基金 70%），`N_s` 为季度「重大变动」累计买入减卖出，按阈值 τ=1.0 输出信号标签。

### v2 算法改进点

1. 多周期合成按**每行实际可用周期的权重和**归一，缺失字段按中性值处理，不再隐性扣分。
2. 风险/稳定性因子先逐列标准化，再算跨周期离散度；旧版把「近1月」和「成立来年化」直接混算 std，量纲不一致。
3. 缩尾（1%/99%）+ `inf → NaN` 防护，避免极端值或除零让整列 min-max 退化成常量。
4. 经理回报因子乘样本可靠性 `n/(n+2)`，只管 1 只基金的经理不再靠单只极端收益冲榜。
5. 股票得分由「占净值比例求和」升级为五因子 S_s；共识度权重最大，但仓位与经理质量也参与排序。
6. **全局选样**：`绩优标的` 页不再拼接 20 份「每人 3 / 10 条」榜单，而是综合所有经理只选 3 只基金 / 10 只股票。

---

## 6. 回测

```bash
python3 src/backtest_fund_portfolio.py --years 3 --manager-topn 10 --rebalance M --fee 0.001
python3 src/backtest_elite_manager_portfolio.py --years 3 --manager-topn 20 --fee 0.001
```

输出：净值曲线 CSV、调仓记录 CSV、摘要 MD、图表 PNG（`figsize=(16,18)`、`dpi=200`、**每行一张图**，字号加大）。

指标：累计/年化收益、年化波动、夏普、索提诺、Calmar、最大回撤及持续天数、胜率/盈亏比、Alpha/Beta/信息比率。

静态站的回测页不是一张图片：`backtest-chart.js` 用纯 SVG 绘制，**鼠标悬浮可看当日日期、净值、基准、回撤、资产构成**，支持十字准星、区间切换与年度收益提示；数据来自按需加载的 `series_{id}.json`，加载失败自动回退高清 PNG。

---

## 7. Web 界面

### 7.1 本地动态站

```bash
python3 src/webui/app.py          # http://localhost:8000
```

| 页面 | 静态站 | 动态站 | 说明 |
| --- | --- | --- | --- |
| 总览 | `index.html` | `/` | 信号摘要、紧凑环形图、**股票排名 Top5**、经理 Top5、持仓明细 |
| 每日信号 | `signals.html` | `/signals` | 按标签过滤、分页 |
| 我的持仓 | `holdings.html` | `/holdings` | 当前配置、触发重算 |
| 经理排名 | `managers.html` | `/managers` | 分页，姓名可进入个人页 |
| **基金经理个人页** | `manager.html?name=姓名` | `/manager?name=姓名` | 业绩排名、绩优基金 Top3、重仓股 Top10、相关每日信号、外部经理搜索 |
| 基金排名 | `funds.html` | `/funds` | 成立天数过滤 |
| 股票排名 | `stocks.html` | `/stocks` | 按 S_s 排序的完整去重股票池，支持入选经理数筛选 |
| 绩优标的 | `elite.html` | `/elite` | 全局唯一 Top3 / Top10，含综合得分 |
| 回测 | `backtest.html` | `/backtest` | 交互式曲线 + 汇总 + 交易明细 |
| **公式** | `formulas.html` | `/formulas` | MathML 形式化选股/选基公式与参数表 |
| 流水线 | `pipeline.html` | `/pipeline` | 分步/一键运行，实时日志 |

站内只保留**最近一个交易日**的数据，因此没有日期下拉；URL 里残留的旧 `?date=` 会自动纠正。页眉提供「更新数据」按钮跳转到 Actions 手动运行页。

### 7.2 定时任务与缓存

动态站内置 APScheduler（每日凌晨 2:00 ±5 分钟）。线上以 GitHub Actions 为准。

---

## 8. 静态站部署（GitHub Pages）

### 8.1 生成

```bash
python3 src/generate_static.py
```

从 `out/` 读取 CSV/MD → 写 `docs/data/{date}/*.json` + `docs/` 页面壳与资源。其中 `manager_index.json` 由 `src/manager_index.py` 按姓名聚合经理排名、绩优基金、重仓股与调仓信号，供基金经理个人页使用（静态站与动态站共用同一口径）。页面里的「关联经理」姓名均为指向个人页的超链接，长文本逐条换行，不会撑破表格。若最新日期数据不完整，生成器会**保持上一版站点不动**，绝不退回发布旧日期。

### 8.2 Pages 设置

**Settings → Pages → Deploy from a branch**：分支 `master`，目录 `/docs`。

### 8.3 自动更新

`.github/workflows/update.yml`：

- 定时：工作日 UTC 14:00（**北京时间 22:00**），支持 `workflow_dispatch` 手动触发。
- 流程：`daily_run.py` → `generate_static.py` → 提交 `docs/` 与缓存 → 推送 → Pages 自动部署。
- `actions/cache@v4` 跨天持久化 `out/cache_series`、`out/cache_meta`（`save-always: true`），缓存不进仓库。
- `docs/data` 只保留最近一个日期（`RETAIN_DATES = 1`），旧日期目录与图表自动清理。

增量策略（详见第 1 节表格）：行情时序缓存按标的固定命名，只请求「缓存最后日期 → 最新净值日」的缺口；全市场排行当天只拉一次，经理列表 7 天、交易日历 30 天复用；前复权行情每 7 天重建一次以防除权基准漂移。所有增量失败只告警并沿用旧缓存，**不会退化成全量重拉**。首次运行会建一次缓存，之后每天只有少量小请求。

手动更新（备用）：

```bash
python3 src/daily_run.py
python3 src/generate_static.py
git add docs/ && git commit -m "chore: daily data update" && git push origin master
```

---

## 9. 数据口径与已知限制

1. 经理口径取天天基金「基金经理大全」的现任基金；收益字段来自开放基金排行接口（不含近 5 年）。
2. 「成立来年化」是复合年化近似，成立时间短会被放大，故默认过滤成立 < 180 天的基金。
3. 重仓股与「重大变动」均为**季度披露**，滞后且非实时调仓；前十大重仓股只覆盖基金部分仓位。
4. 回测按季度末后首个交易日调仓（偏乐观），未处理停牌/涨跌停，按 100 股一手向下取整。
5. 公开接口可能限流或偶发断开；基金 F10 直连带 `Referer` 与超时，失败时回退季度缓存，最差情况沿用历史缓存。
6. 静态站的 JSON 有 CDN 缓存（约 10 分钟），数据更新后如未生效请强刷（`Cmd/Ctrl + Shift + R`）。
7. 页面展示的「综合得分」为 `100 · S`（满分 100），S 截断到 `[0,1]`。

---

## 10. 常见问题

**Q：为什么绩优标的只有 3 / 10 条，以前有几百条？**
这是刻意的口径变更：现在综合所有经理统一评分，全站只选 3 只基金 / 10 只股票。想看全部候选的去重榜单，请用「股票排名」页（129 只，按 S_s 排序）。

**Q：想改选股 / 选基权重？**
改 `src/selection_formula.py` 顶部的 `FUND_WEIGHTS` / `STOCK_WEIGHTS` / `TOP_FUNDS` / `TOP_STOCKS`，公式页、静态站、动态站、优化持仓会一起更新。多因子权重在 `src/factor_scoring.py`。

**Q：为什么 CI 第一次很慢，之后很快？**
首次需要建立完整行情缓存；之后 `actions/cache` 复用缓存，每天只补 1~2 个交易日。

**Q：静态站打开本地文件报 `fetch` 失败？**
`file://` 会被浏览器拦截。请用线上站点，或在 `docs/` 下起本地 HTTP 服务（例如 `python3 -m http.server`）。
