#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测共享引擎：配置、指标计算、基准获取、图表绘制、摘要生成。

供 backtest_elite_manager_portfolio.py 和 backtest_fund_portfolio.py 共用。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    initial_cash: float = 10000.0
    fee_rate: float = 0.001
    adjust: str = "qfq"
    # 基准
    benchmark: str = "sh000300"
    risk_free_rate: float = 0.0


# ---------------------------------------------------------------------------
# 绩效指标结果
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """结构化存放全部绩效指标。"""

    # 基础
    start_date: date | None = None
    end_date: date | None = None
    n_days: int = 0
    initial_cash: float = 10000.0
    final_value: float = 10000.0
    # 收益
    total_return: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    # 回撤
    max_drawdown: float = 0.0
    max_drawdown_days: int = 0
    # 交易
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    # 基准相关（可选）
    benchmark_return: float | None = None
    excess_return: float | None = None
    alpha: float | None = None
    beta: float | None = None
    information_ratio: float | None = None
    # 年度明细
    yearly_returns: dict[int, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------


def calc_performance_metrics(
    equity_df: pd.DataFrame,
    benchmark_s: pd.Series | None = None,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """
    从净值 DataFrame 计算全部绩效指标。

    equity_df 必须包含列：日期, 总资产
    """
    if config is None:
        config = BacktestConfig()

    n_days = max(1, equity_df.shape[0])
    total_ret = float(equity_df["总资产"].iloc[-1] / config.initial_cash - 1.0)
    ann_ret = (1.0 + total_ret) ** (252.0 / n_days) - 1.0 if n_days > 0 else 0.0

    daily_ret = equity_df["日收益率"].dropna()
    vol = float(daily_ret.std() * math.sqrt(252.0))
    sharpe = float((daily_ret.mean() / (daily_ret.std() + 1e-12)) * math.sqrt(252.0))

    # 下行波动率 & 索提诺
    down = daily_ret[daily_ret < 0]
    down_std = float(down.std() * math.sqrt(252.0)) if len(down) > 1 else vol
    sortino = float((daily_ret.mean() / (down_std + 1e-12)) * math.sqrt(252.0))

    mdd = float(equity_df["回撤"].min()) if "回撤" in equity_df.columns else 0.0
    calmar = ann_ret / (abs(mdd) + 1e-12)

    # 胜率
    win_rate = float((daily_ret > 0).sum() / max(1, len(daily_ret)))

    # 盈亏比
    pos_avg = float(daily_ret[daily_ret > 0].mean()) if (daily_ret > 0).any() else 0.0
    neg_avg = abs(float(daily_ret[daily_ret < 0].mean())) if (daily_ret < 0).any() else 1e-12
    pl_ratio = pos_avg / (neg_avg + 1e-12)

    # 最大回撤持续天数
    if "回撤" in equity_df.columns:
        in_dd = (equity_df["回撤"].values < 0).astype(int)
        max_dd_days = 0
        cur = 0
        for v in in_dd:
            if v:
                cur += 1
                max_dd_days = max(max_dd_days, cur)
            else:
                cur = 0
    else:
        max_dd_days = 0

    # 年度收益
    if "日期" in equity_df.columns:
        eq = equity_df.copy()
        eq["日期"] = pd.to_datetime(eq["日期"])
        eq["年"] = eq["日期"].dt.year
        yearly = eq.groupby("年").apply(lambda g: float(g["总资产"].iloc[-1] / g["总资产"].iloc[0] - 1.0), include_groups=False)  # type: ignore[reportUnknownMemberType]
        yearly_returns = {int(k): float(v) for k, v in yearly.items()}
    else:
        yearly_returns = {}

    # 基准相关
    benchmark_return = None
    excess_return = None
    alpha = None
    beta = None
    information_ratio = None

    if benchmark_s is not None and not benchmark_s.empty:
        # 对齐日期
        eq = equity_df.copy()
        eq["日期_d"] = pd.to_datetime(eq["日期"]).dt.date
        bm = benchmark_s.reset_index()
        bm.columns = ["日期_d", "基准净值"]
        bm["日期_d"] = pd.to_datetime(bm["日期_d"]).dt.date
        merged = eq.merge(bm, on="日期_d", how="inner")
        if len(merged) > 10:
            bm_ret = merged["基准净值"].pct_change().dropna()
            st_ret = merged["总资产"].pct_change().dropna()
            # 对齐长度
            common_len = min(len(bm_ret), len(st_ret))
            bm_ret = bm_ret.iloc[-common_len:]
            st_ret = st_ret.iloc[-common_len:]

            benchmark_return = float(merged["基准净值"].iloc[-1] / merged["基准净值"].iloc[0] - 1.0)
            excess = st_ret - bm_ret
            excess_return = float((1.0 + total_ret) / (1.0 + benchmark_return + 1e-12) - 1.0)

            # Beta / Alpha (Jensen)
            cov = float(bm_ret.cov(st_ret))
            var = float(bm_ret.var())
            if var > 1e-12:
                beta = cov / var
                alpha = float((st_ret.mean() - config.risk_free_rate / 252.0 - beta * (bm_ret.mean() - config.risk_free_rate / 252.0)) * 252.0)
            else:
                beta = None
                alpha = None

            # 信息比率
            te = float(excess.std() * math.sqrt(252.0))
            information_ratio = float(excess.mean() / (te + 1e-12)) * math.sqrt(252.0)

    return BacktestResult(
        start_date=pd.to_datetime(equity_df["日期"].iloc[0]).date(),
        end_date=pd.to_datetime(equity_df["日期"].iloc[-1]).date(),
        n_days=n_days,
        initial_cash=config.initial_cash,
        final_value=float(equity_df["总资产"].iloc[-1]),
        total_return=total_ret,
        annual_return=ann_ret,
        annual_volatility=vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=mdd,
        max_drawdown_days=max_dd_days,
        win_rate=win_rate,
        profit_loss_ratio=pl_ratio,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        alpha=alpha,
        beta=beta,
        information_ratio=information_ratio,
        yearly_returns=yearly_returns,
    )


# ---------------------------------------------------------------------------
# 基准指数获取
# ---------------------------------------------------------------------------


def fetch_benchmark(
    symbol: str = "sh000300",
    start: date | None = None,
    end: date | None = None,
    cache_dir: Path | None = None,
    sleep_s: float = 0.1,
) -> pd.Series:
    """
    获取基准指数日线，返回 index=date, values=收盘价 的 Series。
    支持缓存到 cache_dir。
    """
    import akshare as ak

    if start is None:
        start = date.today().replace(year=date.today().year - 3)
    if end is None:
        end = date.today()

    def _yyyymmdd(d: date) -> str:
        return d.strftime("%Y%m%d")

    # 检查缓存
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fp = cache_dir / f"benchmark_{symbol}_{_yyyymmdd(start)}_{_yyyymmdd(end)}.csv"
        if fp.exists() and fp.stat().st_size > 0:
            df = pd.read_csv(fp)
            if not df.empty and "日期" in df.columns and "收盘" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"]).dt.date
                s = pd.Series(df["收盘"].values, index=df["日期"].values, name=symbol)
                if not s.empty:
                    return s
        if fp.exists():
            fp.unlink()

    import akshare as ak

    last_exc: Exception | None = None
    for _ in range(3):
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                break
        except Exception as e:
            last_exc = e
            time.sleep(max(1.0, sleep_s) * 2)
    time.sleep(sleep_s)

    if df is None or df.empty:
        s = pd.Series(dtype="float64", name=symbol)
    else:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        s = pd.Series(df["close"].values, index=df["date"].values, name=symbol)

    if cache_dir is not None and not s.empty:
        pd.DataFrame({"日期": list(s.index), "收盘": list(s.values)}).to_csv(fp, index=False, encoding="utf-8")

    return s


# ---------------------------------------------------------------------------
# 图表绘制
# ---------------------------------------------------------------------------


def plot_backtest_result(
    equity_df: pd.DataFrame,
    metrics: BacktestResult,
    out_path: Path,
    benchmark_s: pd.Series | None = None,
    title: str = "回测结果",
) -> None:
    """
    生成 2x2 组合图：净值走势、回撤曲线、年度收益、月度收益热力图。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    # 中文字体
    _setup_chinese_font()

    eq = equity_df.copy()
    eq["日期"] = pd.to_datetime(eq["日期"])
    eq = eq.sort_values("日期")

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(title, fontsize=16, fontweight="bold")

    # ---- (0,0) 净值走势 ----
    ax0 = axes[0, 0]
    ax0.plot(eq["日期"], eq["总资产"] / metrics.initial_cash, color="#1f77b4", linewidth=1.2, label="策略净值")
    if benchmark_s is not None and not benchmark_s.empty:
        bm = benchmark_s.reset_index()
        bm.columns = ["日期", "基准净值"]
        bm["日期"] = pd.to_datetime(bm["日期"])
        bm = bm.sort_values("日期")
        bm["基准净值"] = bm["基准净值"] / bm["基准净值"].iloc[0]
        ax0.plot(bm["日期"], bm["基准净值"], color="#ff7f0e", linewidth=0.8, linestyle="--", label="基准净值")
    ax0.axhline(y=1.0, color="gray", linewidth=0.5, linestyle=":")
    ax0.set_title("净值走势")
    ax0.legend(loc="upper left", fontsize=8)
    ax0.set_ylabel("净值")
    ax0.grid(True, alpha=0.3)

    # ---- (0,1) 回撤曲线 ----
    ax1 = axes[0, 1]
    if "回撤" in eq.columns:
        ax1.fill_between(eq["日期"], 0, eq["回撤"] * 100, color="#d62728", alpha=0.3, linewidth=0)
        ax1.plot(eq["日期"], eq["回撤"] * 100, color="#d62728", linewidth=0.8)
    ax1.set_title("回撤曲线")
    ax1.set_ylabel("回撤 (%)")
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax1.grid(True, alpha=0.3)
    ax1.invert_yaxis()

    # ---- (1,0) 年度收益柱状图 ----
    ax2 = axes[1, 0]
    yrs = sorted(metrics.yearly_returns.keys())
    if yrs:
        vals = [metrics.yearly_returns[y] * 100 for y in yrs]
        colors = ["#2ca02c" if v >= 0 else "#d62728" for v in vals]
        bars = ax2.bar([str(y) for y in yrs], vals, color=colors, edgecolor="white")
        ax2.axhline(y=0, color="gray", linewidth=0.5)
        ax2.set_title("年度收益")
        ax2.set_ylabel("收益率 (%)")
        ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
        # 柱顶标注
        for bar, val in zip(bars, vals):
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (0.5 if val >= 0 else -1.5),
                     f"{val:.1f}%", ha="center", fontsize=8)
    else:
        ax2.text(0.5, 0.5, "不足一年", transform=ax2.transAxes, ha="center", va="center")
    ax2.grid(True, alpha=0.3, axis="y")

    # ---- (1,1) 信息/指标表 ----
    ax3 = axes[1, 1]
    ax3.axis("off")
    lines = [
        f"累计收益: {metrics.total_return*100:.2f}%",
        f"年化收益: {metrics.annual_return*100:.2f}%",
        f"年化波动: {metrics.annual_volatility*100:.2f}%",
        f"夏普比率: {metrics.sharpe_ratio:.2f}",
        f"索提诺:   {metrics.sortino_ratio:.2f}",
        f"Calmar:   {metrics.calmar_ratio:.2f}",
        f"最大回撤: {metrics.max_drawdown*100:.2f}%",
        f"回撤持续: {metrics.max_drawdown_days} 天",
        f"胜率:     {metrics.win_rate*100:.1f}%",
        f"盈亏比:   {metrics.profit_loss_ratio:.2f}",
    ]
    if metrics.beta is not None:
        lines += [
            f"Beta:     {metrics.beta:.2f}",
            f"Alpha:    {metrics.alpha*100:.2f}%",
            f"信息比率: {metrics.information_ratio:.2f}",
        ]
    # 左对齐
    text = "\n".join(lines)
    ax3.text(0.05, 0.95, text, transform=ax3.transAxes, fontsize=9, verticalalignment="top", fontfamily="sans-serif")
    ax3.set_title("绩效指标")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"图表已保存：{out_path}")


def _setup_chinese_font() -> None:
    """尝试设置中文字体，失败则用英文 fallback。"""
    import matplotlib.pyplot as plt

    candidates = [
        "PingFang HK",
        "Heiti TC",
        "STHeiti",
        "Hiragino Sans GB",
        "Lantinghei SC",
        "Arial Unicode MS",
        "Songti SC",
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
    ]
    import matplotlib.font_manager as fm
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# 摘要 Markdown
# ---------------------------------------------------------------------------


def format_summary_md(
    metrics: BacktestResult,
    config: BacktestConfig,
    out_files: list[Path],
    extra_info: dict[str, Any] | None = None,
    trades_df: pd.DataFrame | None = None,
) -> str:
    """生成回测摘要 Markdown 文本。"""
    now = datetime.now().strftime("%Y%m%d")
    lines = [
        f"# 回测摘要（{now}）",
        "",
        "> 说明：本回测仅用于研究与学习，不构成任何投资建议。",
        "",
        "## 参数",
        f"- 初始本金：{config.initial_cash:,.0f} 元",
        f"- 回测区间：{metrics.start_date} ~ {metrics.end_date}（交易日 {metrics.n_days} 天）",
        f"- 手续费：单边 {config.fee_rate*100:.2f}%",
    ]
    if extra_info:
        for k, v in extra_info.items():
            lines.append(f"- {k}：{v}")

    lines += [
        "",
        "## 绩效指标",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 累计收益率 | {metrics.total_return*100:.2f}% |",
        f"| 年化收益率 | {metrics.annual_return*100:.2f}% |",
        f"| 年化波动率 | {metrics.annual_volatility*100:.2f}% |",
        f"| 夏普比率 | {metrics.sharpe_ratio:.2f} |",
        f"| 索提诺比率 | {metrics.sortino_ratio:.2f} |",
        f"| Calmar 比率 | {metrics.calmar_ratio:.2f} |",
        f"| 最大回撤 | {metrics.max_drawdown*100:.2f}% |",
        f"| 最大回撤持续 | {metrics.max_drawdown_days} 天 |",
        f"| 胜率 | {metrics.win_rate*100:.1f}% |",
        f"| 盈亏比 | {metrics.profit_loss_ratio:.2f} |",
    ]

    if metrics.benchmark_return is not None:
        lines += [
            f"| 基准累计收益 | {metrics.benchmark_return*100:.2f}% |",
            f"| 超额收益 | {metrics.excess_return*100:.2f}% |",
        ]
    if metrics.beta is not None:
        lines += [
            f"| Beta | {metrics.beta:.2f} |",
            f"| Alpha | {metrics.alpha*100:.2f}% |",
            f"| 信息比率 | {metrics.information_ratio:.2f} |",
        ]

    # 年度收益表
    if metrics.yearly_returns:
        lines += ["", "## 年度收益", "", "| 年份 | 收益率 |", "|------|--------|"]
        for yr in sorted(metrics.yearly_returns.keys()):
            lines.append(f"| {yr} | {metrics.yearly_returns[yr]*100:.2f}% |")

    # 交易明细摘要
    if trades_df is not None and not trades_df.empty:
        lines += ["", "## 交易明细", ""]
        lines.append(f"共 {len(trades_df)} 笔交易")
        lines.append("")
        lines.append("| 日期 | 方向 | 代码 | 名称 | 价格 | 股数/份额 | 成交额 | 手续费 |")
        lines.append("|------|------|------|------|------|-----------|--------|--------|")
        for _, t in trades_df.iterrows():
            lines.append(
                f"| {t.get('日期', '')} | {t.get('方向', '')} | {t.get('代码', '')} "
                f"| {t.get('名称', '')} | {t.get('价格', '')} | {t.get('股数', t.get('份额', ''))} "
                f"| {t.get('成交额', '')} | {t.get('手续费', '')} |"
            )

        # 按标的汇总
        lines += ["", "## 标的交易汇总", ""]
        lines.append("| 代码 | 名称 | 买入次数 | 卖出次数 |")
        lines.append("|------|------|----------|----------|")
        for code in sorted(trades_df["代码"].unique()):
            sub = trades_df[trades_df["代码"] == code]
            name = sub["名称"].iloc[0] if "名称" in sub.columns else ""
            buys = int((sub["方向"] == "买入").sum())
            sells = int((sub["方向"] == "卖出").sum())
            lines.append(f"| {code} | {name} | {buys} | {sells} |")

    lines += ["", "## 输出文件"]
    for fp in out_files:
        lines.append(f"- {fp.name}")
    lines.append("")

    return "\n".join(lines)
