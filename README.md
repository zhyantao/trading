# 基金经理/基金数据抓取与信号分析（公开接口版）

基于公开数据接口（东方财富/天天基金，使用 AkShare 封装）实现：

- 抓取 **基金经理 → 现任基金** 列表，以及各基金常见区间收益率字段
- 计算基金 **成立来年化收益率** 并对全市场基金排序
- 按基金业绩对基金经理排名
- 建立「基金年化收益率 ↔ 基金经理排名」关联
- 从绩优基金经理名下基金提取 **重仓股 Top10** 与 **基金 Top3** 投资标的
- 每日生成基于"基金重大变动（季度口径）"的 **调仓信号**（继续关注/关注买入/关注卖出）
- 根据绩优标的自动生成优化后的持仓配置
- 回测绩优基金经理组合的历史表现

> 免责声明：本项目仅用于数据研究与学习，不构成任何投资建议。

---

## 1. 目录结构

```
.
├── requirements.txt
├── src/
│   ├── build_manager_fund_returns.py       # 基金经理-基金收益率明细
│   ├── rank_fund_managers.py               # 基金经理排名
│   ├── rank_all_funds_by_annualized_return.py  # 全市场基金年化排序
│   ├── link_fund_annualized_and_manager_rank.py # 基金-经理关联表
│   ├── pick_elite_managers_targets.py      # 绩优经理筛选 + 投资标的
│   ├── daily_rebalance_signal.py           # 每日调仓信号
│   ├── optimize_holdings.py                # 自动生成优化持仓
│   ├── daily_run.py                        # 一键跑全流程
│   ├── backtest_common.py                  # 回测共享引擎
│   ├── backtest_elite_manager_portfolio.py # 重仓股回测
│   ├── backtest_fund_portfolio.py          # 基金净值回测
│   └── webui/                              # Web 界面
│       ├── app.py                          # FastAPI 入口
│       ├── routes.py                       # 路由和 API
│       ├── data_service.py                 # 数据读取层
│       ├── templates/                      # Jinja2 模板
│       └── static/                         # CSS 等静态文件
└── out/                                    # 运行输出（CSV/MD）
    ├── 我的持仓.csv                         # 持仓清单（用于每日信号对照）
    └── cache_prices/                        # 回测行情缓存
```

---

## 2. 环境准备

Python 3.10+，安装依赖：

```bash
pip install -r requirements.txt
```

依赖：`akshare` `pandas` `requests` `demjson3` `fastapi` `uvicorn` `jinja2` `apscheduler` `matplotlib`

> **中文图表字体**：回测图表需要系统中文字体，否则中文会显示为方框/乱码。
>
> **macOS** 自带中文字体，无需额外安装。
>
> **Windows** 自带微软雅黑/宋体，无需额外安装。
>
> **Linux (含 WSL2)**：
> ```bash
> # 方式一：安装系统字体（需要 sudo）
> sudo apt install fonts-wqy-microhei -y
>
> # 方式二：用户级安装（无需 sudo）
> mkdir -p ~/.fonts
> wget -O ~/.fonts/NotoSansSC-Regular.ttf \
>   https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf
> rm -rf ~/.cache/matplotlib  # 清除字体缓存
> ```
> 安装后重新运行回测脚本即可正常显示中文。

---

## 3. 分步运行

### 3.1 基金经理-基金收益率明细

```bash
python3 src/build_manager_fund_returns.py
```

参数：

- `--symbol`：基金类型范围，可选 `全部`（默认）/`股票型`/`混合型`/`债券型`/`指数型`/`QDII`/`FOF`/`LOF`
- `--out`：自定义输出路径（默认 `out/基金经理_基金收益率明细_YYYYMMDD.csv`）

### 3.2 基金经理排名

默认按"近1年收益率 + 多基金简单平均"排名：

```bash
python3 src/rank_fund_managers.py
```

参数：

- `--metric`：排名指标列名，默认 `近1年`（也可用 `近6月`/`近2年`/`成立来` 等）
- `--input`/`--out`：自定义输入/输出路径

输出：`out/基金经理业绩排名_YYYYMMDD.csv`

### 3.3 全市场基金成立来年化排序

直接调用东方财富排行接口计算复合年化：

```bash
python3 src/rank_all_funds_by_annualized_return.py
```

参数：

- `--symbol`：基金类型范围，同 3.1
- `--out`：自定义输出路径

输出：`out/基金年化收益率排序_YYYYMMDD.csv`（含 `成立天数`、`成立来年化` 字段）

### 3.4 基金-经理关联表

关联基金年化排名与经理排名，默认过滤成立不足 180 天的新基金：

```bash
python3 src/link_fund_annualized_and_manager_rank.py --min-days 180
```

参数：

- `--min-days`：成立天数阈值（默认 180）
- `--detail`/`--manager-rank`/`--fund-annual`：指定输入文件（默认自动取最新）

输出：`out/基金_经理_年化_排名关联_YYYYMMDD.csv`

### 3.5 绩优经理筛选 + 投资标的

筛选"绩优 + 无历史负业绩"的基金经理，输出每人 Top3 基金和 Top10 重仓股：

```bash
python3 src/pick_elite_managers_targets.py --top-n 20 --min-days 180
```

参数：

- `--top-n`：经理目标数量（默认 20）
- `--min-days`：成立天数阈值（默认 180）
- `--fund-topk`/`--stock-topk`：每位经理输出的基金/股票数（默认 3/10）
- `--sleep`：抓取持仓接口间隔秒数（默认 0.2）

输出：

- `out/绩优基金经理_基金Top3_YYYYMMDD.csv`
- `out/绩优基金经理_股票Top10_YYYYMMDD.csv`

### 3.6 自动生成优化持仓

根据绩优标的自动计算持仓权重，追加快照到 `out/我的持仓.csv`：

```bash
python3 src/optimize_holdings.py --total-n 5 --stock-pct 30 --fund-pct 70
```

参数：

- `--total-n`：目标持仓总数（默认 5）
- `--stock-pct`/`--fund-pct`：股票/基金大类比例（默认 30/70，两者之和必须为 100）
- `--date`：记录日期（默认今天）
- `--elite-funds`/`--elite-stocks`：指定输入文件（默认自动取最新）

输出文件格式（长表，便于记录调仓历史）：

| 日期       | 类型 | 代码   | 名称              | 数量 | 比例(%) |
| ---------- | ---- | ------ | ----------------- | ---- | ------- |
| 2026-05-12 | 股票 | 300308 | 中际旭创          |      | 30      |
| 2026-05-12 | 基金 | 016370 | 信澳业绩驱动混合A |      | 70      |

当前版本的每日信号不依赖 `数量` 和 `比例(%)` 列，仅用于展示。

### 3.7 每日调仓信号

对照持仓给出"继续关注/关注买入/关注卖出"信号：

```bash
python3 src/daily_rebalance_signal.py --holdings out/我的持仓.csv
```

参数：

- `--holdings`：持仓文件路径（默认 `out/我的持仓.csv`）
- `--threshold`：净强度阈值（百分点），默认 1.0；越高越保守
- `--top-opportunities`：额外输出机会 TopN（默认 30）
- `--sleep`：接口抓取间隔秒数（默认 0.2）

输出：

- `out/每日调仓信号_YYYYMMDD.csv`（持仓对照 + 全市场机会 Top）
- `out/每日调仓信号_YYYYMMDD.md`（简短摘要）

逻辑：

1. 读取最新的绩优基金经理基金 Top3 作为跟踪集合
2. 对每只基金抓取"重大变动"（累计买入/累计卖出）最新季度数据
3. 按经理聚合到股票层面，计算净强度：`净强度 = 买入强度 - 卖出强度`
4. 与持仓对照，输出信号标签

---

## 4. 一键跑全流程

```bash
python3 src/daily_run.py
```

依次执行：3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.7（不含优化持仓和回测）。

全流程涉及多个公开接口，可能遇到限流/超时，建议必要时分步运行。

---

## 5. 回测

提供两种回测模式：基于重仓股的股票回测和基于净值的基金回测，均支持沪深300基准对比和图表输出。

### 5.1 股票回测（重仓股组合）

以基金季度披露的前十大重仓股为标的，按经理等权聚合、季度再平衡：

```bash
python3 src/backtest_elite_manager_portfolio.py --years 3 --manager-topn 20 --fee 0.001
```

参数：

- `--years`：回测年数（默认 3）
- `--initial`：初始本金（默认 10000）
- `--fee`：单边手续费比例（默认 0.001 即 0.1%）
- `--manager-topn`：参与回测的经理数量（默认 20）
- `--topk`：每期保留的 TopK 股票（默认 50，设 0 不截断）
- `--restrict-to-selected-stocks`：限制股票池为绩优经理股票 Top10
- `--benchmark`：基准指数代码（默认 `sh000300` 沪深300，设为空串跳过）
- `--no-plot`：跳过图表生成
- `--sleep`/`--price-sleep`：接口间隔秒数

### 5.2 基金回测（净值组合）

以绩优基金经理的 Top3 基金为标的，按经理等权 + 基金等权、月度再平衡：

```bash
python3 src/backtest_fund_portfolio.py --years 3 --manager-topn 10 --rebalance M --fee 0.001
```

参数：

- `--years`：回测年数（默认 3）
- `--initial`：初始本金（默认 10000）
- `--fee`：单边手续费比例（默认 0.001）
- `--manager-topn`：参与回测的经理数量（默认 10）
- `--fund-topk`：每位经理选取的基金数（默认 3）
- `--rebalance`：再平衡频率，`M`=月度（默认）/`Q`=季度
- `--benchmark`：基准指数代码（默认 `sh000300`，设为空串跳过）
- `--no-plot`：跳过图表生成

### 5.3 输出文件

两种回测均输出：

- `out/回测_净值曲线_YYYYMMDD.csv`（基金回测对应 `回测_基金净值曲线_*.csv`）
- `out/回测_调仓记录_YYYYMMDD.csv`
- `out/回测摘要_YYYYMMDD.md`（完整绩效指标表）
- `out/回测_图表_YYYYMMDD.png`（净值走势 + 回撤 + 年度收益 + 指标总览）

### 5.4 绩效指标

摘要 MD 和图表中输出以下指标：

| 指标                    | 说明                           |
| ----------------------- | ------------------------------ |
| 累计/年化收益率         | 总收益和按252交易日折算的年化  |
| 年化波动率              | 日收益标准差年化               |
| 夏普比率                | 单位风险的超额收益             |
| 索提诺比率              | 仅用下行波动率                 |
| Calmar 比率             | 年化收益 / 最大回撤            |
| 最大回撤 + 持续天数     | 历史最大亏损幅度和时长         |
| 胜率 / 盈亏比           | 日收益为正的比例和均值比       |
| Alpha / Beta / 信息比率 | 对基准的超额、敏感度和跟踪效率 |

回测会产生较多行情请求，运行耗时取决于接口速度与网络状况。

---

## 6. Web 界面

提供基于 FastAPI 的 Web 界面，可视化展示所有数据和信号，并支持手动触发流水线步骤。

### 6.1 启动

```bash
python3 src/webui/app.py
```

访问 `http://localhost:8000`，包含以下页面：

| 页面     | 路径        | 说明                                    |
| -------- | ----------- | --------------------------------------- |
| 总览     | `/`         | 数据状态、信号摘要、持仓饼图、经理 Top5 |
| 每日信号 | `/signals`  | 调仓信号表格，按类型/标签过滤           |
| 我的持仓 | `/holdings` | 当前持仓配置，触发重新优化              |
| 经理排名 | `/managers` | 基金经理业绩排名（分页）                |
| 基金排名 | `/funds`    | 基金年化排序，按成立天数过滤            |
| 绩优标的 | `/elite`    | 绩优经理的基金 Top3 和股票 Top10        |
| 回测结果 | `/backtest` | 查看已有回测结果、图表，触发新回测      |
| 流水线   | `/pipeline` | 分步或一键运行全流程，实时日志          |

### 6.2 定时任务

内置 APScheduler，每日凌晨 2:00（±5分钟随机偏移）自动执行 `daily_run.py`，运行日志写入 `out/webui_scheduler.log`。

### 6.3 数据缓存

WebUI 只读取 `out/` 下的最新 CSV 文件，不直接发起网络请求。网络请求仅在脚本运行时产生（定时任务或手动触发）。同一天重复运行会覆盖同日期的输出文件。

---

## 7. 数据口径与已知限制

1. **基金经理口径**：以天天基金"基金经理大全页"的现任基金为准。
2. **收益率字段**：开放基金排行接口包含近1周/1月/3月/6月/1年/2年/3年/今年来/成立来，不含近5年。
3. **成立来年化**：复合年化近似计算，成立时间短的基金年化会被放大，关联表与筛选默认过滤成立不足 180 天的基金。
4. **调仓信号数据**：使用"重大变动（累计买入/累计卖出）"属于季度披露口径，并非实时调仓。
5. **回测局限**：仅使用前十大重仓股，按季度末后首个交易日调仓（偏乐观），未处理停牌/涨跌停，按 100 股一手向下取整。
6. **接口稳定性**：公开接口可能限流、偶发断开，脚本尽量容错，必要时重试或降低并发（加大 sleep）。

---

## 8. 常见问题

### Q1：为什么部分基金/股票数据为空？

可能是基金未披露对应季度持仓/重大变动、接口临时不可用或限流、历史行情缺失（新股/停牌）。

### Q2：如何更稳健地筛选绩优经理？

在 `pick_elite_managers_targets.py` 中调整过滤逻辑（增加成立天数阈值、要求更多区间收益率 >=0），或减小 `--top-n` 提高门槛。


---

## 9. 静态站点部署（GitHub Pages）

WebUI 支持生成为纯静态 HTML 页面，部署到 GitHub Pages 后无需服务器即可浏览。

### 9.1 生成静态页面

```bash
python3 src/generate_static.py
```

输出在 `docs/` 目录，包含所有页面的 HTML 及静态资源。

### 9.2 启用 GitHub Pages

在仓库 **Settings → Pages** 中：
- **Source**: Deploy from a branch
- **Branch**: `master`，文件夹 `/docs`

保存后站点部署到 `https://<用户名>.github.io/<仓库名>/`。

### 9.3 自动定时更新（推荐）

通过 **GitHub Actions** 免费定时运行数据流水线并自动部署，无需手动操作。

已在 `.github/workflows/daily-update.yml` 中配置：
- **定时触发**：每日 UTC 18:30（北京时间凌晨 2:30）自动执行
- **手动触发**：在仓库 **Actions → Daily Data Update → Run workflow** 一键运行
- **免费额度**：公开仓库无限分钟，私有仓库每月 2000 分钟（本流水线单次约 15-30 分钟）

工作流程：`daily_run.py` → `generate_static.py` → 自动提交 `docs/` 并推送 → GitHub Pages 自动更新站点。

#### 手动更新（备用）

如果不想使用 GitHub Actions，也可以手动执行：

```bash
# 1. 运行数据处理流水线
python3 src/daily_run.py

# 2. 重新生成静态页面
python3 src/generate_static.py

# 3. 提交并推送
git add docs/
git commit -m "chore: daily data update"
git push origin master
```

> 不需要单独推送 gh-pages 分支。GitHub Pages 直接从 master 分支的 docs/ 目录拉取。
