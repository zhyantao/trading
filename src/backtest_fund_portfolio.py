#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以基金净值为基础，对绩优基金经理的 Top3 基金组合进行历史回测（不构成投资建议）。

默认做法：
- 回测区间：近 3 年
- 标的：绩优基金经理的 Top3 基金（取最新 out/绩优基金经理_基金Top3_*.csv）
- 权重：基金等权，经理之间也等权
- 再平衡：月度（默认），通过 --rebalance 可切换为季度
- 交易成本：单边 0.1%（默认可通过 --fee 调整）
- 无最低申购限制，允许份额拆分到小数
- 基准对比：沪深300（默认），可通过 --benchmark 切换

数据来源（公开接口，AkShare 封装）：
- 基金净值历史：fund_open_fund_info_em（天天基金）
- 基准指数：stock_zh_index_daily（东方财富）
- 交易日历：tool_trade_date_hist_sina（新浪）

输入（默认 out/ 下最新文件）：
- 绩优基金经理_基金Top3_*.csv

输出（out/）：
- 回测_基金净值曲线_YYYYMMDD.csv
- 回测_基金调仓记录_YYYYMMDD.csv
- 回测_基金摘要_YYYYMMDD.md
- 回测_基金图表_YYYYMMDD.png
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from backtest_common import (
    BacktestConfig,
    calc_performance_metrics,
    fetch_benchmark,
    format_summary_md,
    plot_backtest_result,
)


def _latest(out_dir: Path, pattern: str) -> Path:
    files = sorted(out_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"未在 {out_dir} 找到文件：{pattern}")
    return files[-1]


def _to_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_fund_nav(
    fund_code: str,
    start: date | None = None,
    end: date | None = None,
    cache_dir: Path | None = None,
    sleep_s: float = 0.2,
) -> pd.Series:
    """
    抓取基金单位净值历史，返回 index=date, values=单位净值 的 Series。
    带缓存到 cache_dir/nav_{fund_code}_*.csv。
    """
    import akshare as ak
    import requests

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fp = cache_dir / f"nav_{fund_code}_{_to_yyyymmdd(start) if start else 'all'}_{_to_yyyymmdd(end) if end else 'all'}.csv"
        if fp.exists() and fp.stat().st_size > 0:
            df = pd.read_csv(fp)
            if not df.empty and "日期" in df.columns and "单位净值" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"]).dt.date
                s = pd.Series(df["单位净值"].values, index=df["日期"].values, name=fund_code)
                if not s.empty:
                    if start:
                        s = s[s.index >= start]
                    if end:
                        s = s[s.index <= end]
                    return s
        if fp.exists():
            fp.unlink()

    last_exc: Exception | None = None
    df = None
    for _ in range(3):
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            if df is not None and not df.empty:
                break
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"网络连接失败（远端关闭连接），基金 {fund_code} 净值下载中止") from e
        except Exception as e:
            last_exc = e
            time.sleep(max(1.0, sleep_s) * 2)
    time.sleep(sleep_s)

    if df is None or df.empty:
        return pd.Series(dtype="float64", name=fund_code)

    # 列名可能为中文：净值日期, 单位净值
    date_col = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
    nav_col = next((c for c in df.columns if "单位净值" in str(c)), df.columns[1])
    df = df.rename(columns={date_col: "日期", nav_col: "单位净值"})
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
    df = df.dropna(subset=["单位净值"])
    df = df.sort_values("日期")

    if cache_dir is not None and not df.empty:
        df[["日期", "单位净值"]].to_csv(fp, index=False, encoding="utf-8")

    s = pd.Series(df["单位净值"].values, index=df["日期"].values, name=fund_code)
    if start:
        s = s[s.index >= start]
    if end:
        s = s[s.index <= end]
    return s


def fetch_trade_calendar() -> pd.Series:
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    cal["trade_date"] = pd.to_datetime(cal["trade_date"])
    return cal["trade_date"].sort_values().reset_index(drop=True)


def _nearest_trade_day(trade_days: pd.Series, d: date, direction: str = "next") -> date | None:
    """找最近交易日：next=之后第一个, prev=之前最后一个"""
    dts = pd.to_datetime(trade_days)
    if direction == "next":
        idx = dts.searchsorted(pd.to_datetime(d))
        return dts.iloc[idx].date() if idx < len(dts) else None
    else:
        idx = dts.searchsorted(pd.to_datetime(d)) - 1
        return dts.iloc[idx].date() if idx >= 0 else None


def generate_rebalance_dates(
    trade_days: pd.Series,
    start: date,
    end: date,
    freq: str = "M",
) -> list[date]:
    """生成再平衡日期列表（每月/每季第一个交易日）。"""
    if freq == "Q":
        offsets = pd.period_range(start=start, end=end, freq="Q")
    else:
        offsets = pd.period_range(start=start, end=end, freq="M")

    points = set()
    for p in offsets:
        # 取下一个交易日
        rd = _nearest_trade_day(trade_days, p.end_time.date(), "next")
        if rd and start <= rd <= end:
            points.add(rd)
    return sorted(points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=3, help="回测年数（向前），默认 3")
    parser.add_argument("--initial", type=float, default=10000.0, help="初始本金，默认 10000")
    parser.add_argument("--fee", type=float, default=0.001, help="单边手续费比例，默认 0.001=0.1%%")
    parser.add_argument(
        "--manager-topn",
        type=int,
        default=10,
        help="参与回测的基金经理数量（按经理排名取前 N），默认 10",
    )
    parser.add_argument(
        "--fund-topk",
        type=int,
        default=3,
        help="每位经理选取的基金数，默认 3（对齐基金Top3文件）",
    )
    parser.add_argument(
        "--rebalance",
        default="M",
        choices=["M", "Q"],
        help="再平衡频率：M=月度, Q=季度，默认 M",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="抓取净值接口间隔秒数，默认 0.2")
    parser.add_argument("--benchmark", default="sh000300", help="基准指数代码，默认 sh000300；设为空串跳过")
    parser.add_argument("--no-plot", action="store_true", help="跳过图表生成")
    parser.add_argument("--fund-top3", default="", help="基金Top3文件；不填则 out/ 下自动取最新")
    args = parser.parse_args()

    cfg = BacktestConfig(initial_cash=args.initial, fee_rate=args.fee, benchmark=args.benchmark)

    root = Path(__file__).resolve().parent.parent
    src_dir = str(root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    out_dir = root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache_prices"

    # 读取基金 Top3
    fund_top3_path = Path(args.fund_top3) if args.fund_top3 else _latest(out_dir, "绩优基金经理_基金Top3_*.csv")
    if not fund_top3_path.is_absolute():
        fund_top3_path = (root / fund_top3_path).resolve()
    fund_top3 = pd.read_csv(fund_top3_path, dtype={"基金代码": str})
    fund_top3["基金代码"] = fund_top3["基金代码"].astype(str).str.zfill(6)

    mgr_cols = [c for c in ["经理排名", "序号", "姓名", "所属公司"] if c in fund_top3.columns]
    if not {"经理排名", "姓名", "所属公司"}.issubset(set(mgr_cols)):
        raise KeyError("基金Top3文件缺少关键列：经理排名/姓名/所属公司")

    # 取经理排名 TopN
    mgr_list = (
        fund_top3[["经理排名", "姓名", "所属公司"]]
        .drop_duplicates()
        .sort_values(["经理排名", "姓名", "所属公司"])
        .head(args.manager_topn)
    )
    mgr_keys = set(tuple(x) for x in mgr_list[["经理排名", "姓名", "所属公司"]].itertuples(index=False, name=None))
    fund_top3 = fund_top3[
        fund_top3.apply(lambda r: (r["经理排名"], r["姓名"], r["所属公司"]) in mgr_keys, axis=1)
    ].copy()

    # 每位经理取 TopK 基金
    selected_funds = (
        fund_top3.sort_values(["经理排名", "基金Top"])
        .groupby(["经理排名", "姓名", "所属公司"], dropna=False)
        .head(args.fund_topk)
        .copy()
    )
    fund_codes = sorted(selected_funds["基金代码"].unique().tolist())
    fund_name_map = dict(zip(fund_top3["基金代码"], fund_top3["基金简称"]))
    n_managers = selected_funds[["经理排名", "姓名", "所属公司"]].drop_duplicates().shape[0]
    print(f"选中 {len(fund_codes)} 只基金，来自 {n_managers} 位经理")

    end_d = date.today()
    start_d = end_d - timedelta(days=365 * args.years)

    # 交易日历
    print("[1/5] 获取交易日历 ...")
    trade_days = fetch_trade_calendar()
    trade_days = trade_days[(trade_days.dt.date >= start_d) & (trade_days.dt.date <= end_d)].reset_index(drop=True)
    if trade_days.empty:
        raise RuntimeError("交易日历为空")

    cal = trade_days.dt.date.tolist()

    # 抓取基金净值
    print(f"[2/5] 抓取基金净值历史 ... 基金数={len(fund_codes)}")
    nav_map: dict[str, pd.Series] = {}
    for fc in fund_codes:
        nav_map[fc] = fetch_fund_nav(fc, start=start_d, end=end_d, cache_dir=cache_dir, sleep_s=args.sleep)

    # 构建净值矩阵（索引=交易日，向前填充处理非交易日）
    print("[3/5] 构建净值矩阵 ...")
    nav_df = pd.DataFrame(index=cal)
    for fc, s in nav_map.items():
        nav_df[fc] = s.reindex(cal)
        nav_df[fc] = nav_df[fc].ffill()

    # 目标权重：每位经理等权，每只基金在经理内等权
    # 最终权重 = 1/n_managers * (1/基金数在经理内)
    fund_weights: dict[str, float] = {}
    for _, grp in selected_funds.groupby(["经理排名", "姓名", "所属公司"], dropna=False):
        codes = grp["基金代码"].tolist()
        w = 1.0 / n_managers / len(codes)
        for c in codes:
            fund_weights[c] = fund_weights.get(c, 0.0) + w

    # 归一
    sw = sum(fund_weights.values())
    fund_weights = {k: v / sw for k, v in fund_weights.items()}

    # 生成再平衡日期
    rebalance_dates = generate_rebalance_dates(trade_days, start_d, end_d, freq=args.rebalance)
    if not rebalance_dates:
        raise RuntimeError("未生成任何再平衡日期")
    rebalance_set = set(rebalance_dates)
    print(f"[4/5] 运行回测 ... 再平衡日期={len(rebalance_dates)}")

    # 回测主循环
    cash = cfg.initial_cash
    pos: dict[str, float] = {}  # fund_code -> shares (可小数)
    trades = []
    equity_rows = []

    for d0 in cal:
        # 再平衡日
        if d0 in rebalance_set:
            # 筛选当日有净值的基金
            active = {fc: nav_df.at[d0, fc] for fc in fund_weights if pd.notna(nav_df.at[d0, fc])}
            if active:
                # 重新归一权重
                active_w = {fc: fund_weights[fc] for fc in active}
                aw_sum = sum(active_w.values())
                active_w = {fc: w / aw_sum for fc, w in active_w.items()}

                # 当前总资产
                cur_value = cash + sum(pos.get(fc, 0.0) * float(nav_df.at[d0, fc]) for fc in pos if pd.notna(nav_df.at[d0, fc]))

                # 目标份额
                target_pos: dict[str, float] = {}
                for fc, wt in active_w.items():
                    px = float(nav_df.at[d0, fc])
                    if px <= 0:
                        continue
                    target_pos[fc] = (cur_value * wt) / px

                # 先卖
                for fc, cur_sh in list(pos.items()):
                    tgt = target_pos.get(fc, 0.0)
                    delta = tgt - cur_sh
                    if delta >= 0:
                        continue
                    px = float(nav_df.at[d0, fc])
                    sell_sh = -delta
                    amount = sell_sh * px
                    fee = amount * cfg.fee_rate
                    cash += amount - fee
                    pos[fc] = cur_sh - sell_sh
                    if pos[fc] <= 1e-8:
                        pos.pop(fc, None)
                    trades.append({
                        "日期": d0, "方向": "卖出", "代码": fc,
                        "名称": fund_name_map.get(fc, ""),
                        "价格": round(px, 2), "份额": round(sell_sh, 2), "成交额": round(amount, 2), "手续费": round(fee, 2),
                    })
                # 后买
                for fc, tgt_sh in sorted(target_pos.items(), key=lambda kv: active_w.get(kv[0], 0), reverse=True):
                    cur_sh = pos.get(fc, 0.0)
                    delta = tgt_sh - cur_sh
                    if delta <= 1e-8:
                        continue
                    px = float(nav_df.at[d0, fc])
                    amount = delta * px
                    fee = amount * cfg.fee_rate
                    if cash >= amount + fee:
                        cash -= amount + fee
                        pos[fc] = cur_sh + delta
                        trades.append({
                            "日期": d0, "方向": "买入", "代码": fc,
                            "名称": fund_name_map.get(fc, ""),
                            "价格": round(px, 2), "份额": round(delta, 2), "成交额": round(amount, 2), "手续费": round(fee, 2),
                        })

        hold_value = 0.0
        for fc, sh in pos.items():
            px = nav_df.at[d0, fc]
            if pd.isna(px):
                continue
            hold_value += sh * float(px)
        equity = cash + hold_value
        equity_rows.append({"日期": d0, "现金": cash, "持仓市值": hold_value, "总资产": equity, "持仓基金数": len(pos)})

    equity_df = pd.DataFrame(equity_rows)
    equity_df["日期"] = pd.to_datetime(equity_df["日期"])
    equity_df = equity_df.sort_values("日期")
    equity_df["日收益率"] = equity_df["总资产"].pct_change().fillna(0.0)
    equity_df["累计收益率"] = equity_df["总资产"] / cfg.initial_cash - 1.0
    equity_df["峰值"] = equity_df["总资产"].cummax()
    equity_df["回撤"] = equity_df["总资产"] / equity_df["峰值"] - 1.0

    # 基准数据
    benchmark_s = None
    if args.benchmark:
        print(f"[5/5] 获取基准指数 {args.benchmark} ...")
        benchmark_s = fetch_benchmark(
            symbol=args.benchmark, start=start_d, end=end_d,
            cache_dir=cache_dir, sleep_s=args.sleep,
        )
        if not benchmark_s.empty:
            bm = benchmark_s.reset_index()
            bm.columns = ["日期", "基准价格"]
            bm["日期"] = pd.to_datetime(bm["日期"]).dt.date
            equity_df["日期_d"] = equity_df["日期"].dt.date
            bm_map = dict(zip(bm["日期"], bm["基准价格"]))
            equity_df["基准价格"] = equity_df["日期_d"].map(bm_map)
            equity_df["基准价格"] = equity_df["基准价格"].ffill()
            bm0 = benchmark_s.iloc[0] if len(benchmark_s) > 0 else 1.0
            equity_df["基准累计收益率"] = equity_df["基准价格"] / bm0 - 1.0
            equity_df["超额收益"] = equity_df["累计收益率"] - equity_df["基准累计收益率"]
            equity_df = equity_df.drop(columns=["日期_d"])
    else:
        print("[5/5] 跳过基准对比")

    stamp = datetime.now().strftime("%Y%m%d")
    prefix = "回测_基金"
    curve_out = out_dir / f"{prefix}净值曲线_{stamp}.csv"
    trades_out = out_dir / f"{prefix}调仓记录_{stamp}.csv"
    md_out = out_dir / f"{prefix}摘要_{stamp}.md"
    chart_out = out_dir / f"{prefix}图表_{stamp}.png"

    equity_df.to_csv(curve_out, index=False, encoding="utf-8-sig")
    pd.DataFrame(trades).to_csv(trades_out, index=False, encoding="utf-8-sig")

    metrics = calc_performance_metrics(equity_df, benchmark_s, cfg)

    if not args.no_plot:
        title = f"绩优基金经理基金组合回测（Top{n_managers}经理，{args.rebalance}频再平衡）"
        plot_backtest_result(equity_df, metrics, chart_out, benchmark_s, title)

    out_files = [curve_out, trades_out, md_out]
    if not args.no_plot:
        out_files.append(chart_out)
    extra_info = {
        "再平衡": f"{args.rebalance}频（{'月度' if args.rebalance == 'M' else '季度'}）",
        "标的": f"绩优基金经理 Top{args.manager_topn} × 每经理 Top{args.fund_topk} 基金组合（基金数 {len(fund_codes)}）",
        "权重": "经理等权 + 基金等权",
        "基准": args.benchmark if args.benchmark else "无",
    }
    md_text = format_summary_md(metrics, cfg, out_files, extra_info, trades_df=pd.DataFrame(trades))
    md_text += "\n## 局限/注意\n"
    md_text += "- 回测使用基金单位净值，未计入分红（分红通常反映在净值中）。\n"
    md_text += "- 基金申赎存在确认延迟（T+1/T+2），本回测按当日净值即时成交，偏乐观。\n"
    md_text += "- 未考虑基金限购、大额赎回限制等实际约束。\n"
    md_text += "- 历史表现不代表未来收益。\n"
    md_out.write_text(md_text, encoding="utf-8")

    print(f"完成：{curve_out}")
    print(f"完成：{trades_out}")
    print(f"完成：{md_out}")
    if not args.no_plot:
        print(f"完成：{chart_out}")

    print(f"\n====== 回测结果 ======")
    print(f"累计收益率: {metrics.total_return*100:.2f}%")
    print(f"年化收益率: {metrics.annual_return*100:.2f}%")
    print(f"夏普比率:   {metrics.sharpe_ratio:.2f}")
    print(f"最大回撤:   {metrics.max_drawdown*100:.2f}%")
    if metrics.benchmark_return is not None:
        print(f"基准收益:   {metrics.benchmark_return*100:.2f}%")
        print(f"超额收益:   {metrics.excess_return*100:.2f}%")


if __name__ == "__main__":
    main()
