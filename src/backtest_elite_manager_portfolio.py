#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以 1 万元为本金，对"选定的绩优基金经理"进行历史回测（不构成投资建议）。

用户设定（本脚本默认实现）：
- 回测区间：近 3 年
- 标的：股票（使用基金披露的季度前十大重仓股）
- 权重：按基金披露的重仓股"占净值比例"聚合，经理之间等权
- 再平衡：季度（使用基金季度持仓数据；在每个季度末后的第一个交易日调仓）
- 交易成本：单边 0.1%（买入/卖出都收取），不计滑点
- A 股交易单位：按 100 股一手向下取整（多余现金保留）
- 基准对比：沪深300（默认），可通过 --benchmark 切换

数据来源（公开接口，AkShare 封装）：
- 基金季度持仓：fund_portfolio_hold_em（天天基金）
- 股票日行情：stock_zh_a_hist（东方财富，建议前复权 qfq）
- 交易日历：tool_trade_date_hist_sina（新浪）
- 基准指数：stock_zh_index_daily（东方财富）

输入（默认 out/ 下最新文件）：
- 绩优基金经理_基金Top3_*.csv
- 绩优基金经理_股票Top10_*.csv（可选；仅在开启 --restrict-to-selected-stocks 时用于限制股票池）

输出（out/）：
- 回测_净值曲线_YYYYMMDD.csv
- 回测_调仓记录_YYYYMMDD.csv
- 回测摘要_YYYYMMDD.md
- 回测_图表_YYYYMMDD.png
"""

from __future__ import annotations

import argparse
import math
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


def _quarter_end(y: int, q: int) -> date:
    if q == 1:
        return date(y, 3, 31)
    if q == 2:
        return date(y, 6, 30)
    if q == 3:
        return date(y, 9, 30)
    if q == 4:
        return date(y, 12, 31)
    raise ValueError(q)


def _parse_quarter_text(s: str) -> tuple[int, int]:
    import re
    m = re.search(r"(\d{4})年(\d)季度", str(s))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def _nearest_next_trade_day(trade_days: pd.Series, d: date) -> date | None:
    dts = pd.to_datetime(trade_days)
    idx = dts.searchsorted(pd.to_datetime(d))
    if idx >= len(dts):
        return None
    return dts.iloc[idx].date()


def _to_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _lot_round_down(shares: float, lot: int = 100) -> int:
    if shares <= 0:
        return 0
    return int(math.floor(shares / lot) * lot)


def fetch_trade_calendar() -> pd.Series:
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    cal["trade_date"] = pd.to_datetime(cal["trade_date"])
    return cal["trade_date"].sort_values().reset_index(drop=True)


def fetch_fund_quarter_holdings(
    fund_code: str,
    start_year: int,
    end_year: int,
    sleep_s: float = 0.2,
) -> dict[date, pd.DataFrame]:
    """返回：{季度末日期 -> DataFrame(股票代码, 股票名称, 占净值比例)}"""
    import akshare as ak

    out: dict[date, pd.DataFrame] = {}
    for y in range(end_year, start_year - 1, -1):
        df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(y))
        time.sleep(sleep_s)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["_yq"] = df["季度"].map(_parse_quarter_text)
        df["占净值比例"] = pd.to_numeric(df["占净值比例"], errors="coerce")
        df = df.dropna(subset=["占净值比例"])
        for (yy, qq), g in df.groupby("_yq"):
            if yy == 0:
                continue
            qe = _quarter_end(yy, qq)
            gg = g[["股票代码", "股票名称", "占净值比例", "季度"]].copy()
            gg["股票代码"] = gg["股票代码"].astype(str).str.zfill(6)
            out[qe] = gg.reset_index(drop=True)
    return out


def fetch_stock_prices(
    code: str,
    start: date,
    end: date,
    adjust: str = "qfq",
    cache_dir: Path | None = None,
    sleep_s: float = 0.05,
) -> pd.Series:
    """返回：index=日期(date), value=收盘(float)"""
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fp = cache_dir / f"{code}_{adjust}_{_to_yyyymmdd(start)}_{_to_yyyymmdd(end)}.csv"
        if fp.exists():
            df = pd.read_csv(fp)
            df["日期"] = pd.to_datetime(df["日期"]).dt.date
            return pd.Series(df["收盘"].values, index=df["日期"].values, name=code)

    import akshare as ak

    df = None
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=_to_yyyymmdd(start),
                end_date=_to_yyyymmdd(end),
                adjust=adjust,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            time.sleep(max(1.0, sleep_s) * 2)
    time.sleep(sleep_s)
    if df is None or df.empty:
        s = pd.Series(dtype="float64", name=code)
    else:
        df = df.rename(columns={"日期": "日期", "收盘": "收盘"})
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")
        df = df.dropna(subset=["收盘"])
        s = pd.Series(df["收盘"].values, index=df["日期"].values, name=code)

    if cache_dir is not None:
        pd.DataFrame({"日期": list(s.index), "收盘": list(s.values)}).to_csv(fp, index=False, encoding="utf-8")
    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=3, help="回测年数（向前），默认 3")
    parser.add_argument("--initial", type=float, default=10000.0, help="初始本金，默认 10000")
    parser.add_argument("--fee", type=float, default=0.001, help="单边手续费比例，默认 0.001=0.1%%")
    parser.add_argument(
        "--manager-topn",
        type=int,
        default=20,
        help="参与回测的基金经理数量（按经理排名从高到低取前 N），默认 20",
    )
    parser.add_argument(
        "--restrict-to-selected-stocks",
        action="store_true",
        help="是否把股票池限制为 out/绩优基金经理_股票Top10_*.csv 中的股票（默认不限制）",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=50,
        help="每次调仓仅保留权重最高的 TopK 股票以控制规模，默认 50；设为 0 不截断",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="抓取基金持仓接口间隔秒数，默认 0.2")
    parser.add_argument("--price-sleep", type=float, default=0.05, help="抓取股票行情接口间隔秒数，默认 0.05")
    parser.add_argument("--fund-top3", default="", help="基金Top3文件；不填则 out/ 下自动取最新")
    parser.add_argument("--stock-top10", default="", help="股票Top10文件；不填则 out/ 下自动取最新")
    parser.add_argument("--benchmark", default="sh000300", help="基准指数代码，默认 sh000300（沪深300）；设为空串跳过基准")
    parser.add_argument("--no-plot", action="store_true", help="跳过图表生成")
    args = parser.parse_args()

    cfg = BacktestConfig(initial_cash=args.initial, fee_rate=args.fee, benchmark=args.benchmark)

    root = Path(__file__).resolve().parent.parent
    # 确保可以从 src 目录导入 backtest_common
    import sys
    src_dir = str(root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    out_dir = root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache_prices"

    fund_top3_path = Path(args.fund_top3) if args.fund_top3 else _latest(out_dir, "绩优基金经理_基金Top3_*.csv")
    stock_top10_path = Path(args.stock_top10) if args.stock_top10 else _latest(out_dir, "绩优基金经理_股票Top10_*.csv")
    if not fund_top3_path.is_absolute():
        fund_top3_path = (root / fund_top3_path).resolve()
    if not stock_top10_path.is_absolute():
        stock_top10_path = (root / stock_top10_path).resolve()

    fund_top3 = pd.read_csv(fund_top3_path, dtype={"基金代码": str})
    stock_top10 = pd.read_csv(stock_top10_path, dtype={"股票代码": str})
    fund_top3["基金代码"] = fund_top3["基金代码"].astype(str).str.zfill(6)
    stock_top10["股票代码"] = stock_top10["股票代码"].astype(str).str.zfill(6)

    mgr_cols = [c for c in ["经理排名", "序号", "姓名", "所属公司"] if c in fund_top3.columns]
    if not {"经理排名", "姓名", "所属公司"}.issubset(set(mgr_cols)):
        raise KeyError("基金Top3文件缺少关键列：经理排名/姓名/所属公司")

    # 仅取经理排名 TopN
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
    stock_top10 = stock_top10[
        stock_top10.apply(lambda r: (r["经理排名"], r["姓名"], r["所属公司"]) in mgr_keys, axis=1)
    ].copy()

    # 每位经理：Top3 基金清单
    mgr_funds = (
        fund_top3.sort_values(["经理排名", "基金Top"])
        .groupby(["经理排名", "姓名", "所属公司"], dropna=False)["基金代码"]
        .apply(list)
        .to_dict()
    )
    # 每位经理：选定股票集合
    mgr_stocks = (
        stock_top10.sort_values(["经理排名", "股票Top"])
        .groupby(["经理排名", "姓名", "所属公司"], dropna=False)["股票代码"]
        .apply(lambda s: set(s.tolist()))
        .to_dict()
    ) if not stock_top10.empty else {}

    end_d = date.today()
    start_d = end_d - timedelta(days=365 * args.years)
    start_year = start_d.year - 1
    end_year = end_d.year

    # 交易日历
    print("[1/6] 获取交易日历 ...")
    trade_days = fetch_trade_calendar()
    trade_days = trade_days[(trade_days.dt.date >= start_d) & (trade_days.dt.date <= end_d)].reset_index(drop=True)
    if trade_days.empty:
        raise RuntimeError("交易日历为空")

    # 季度调仓点
    q_ends = [p.end_time.date() for p in pd.period_range(start=start_d, end=end_d, freq="Q")]
    rebalance_points: list[tuple[date, date]] = []
    for qe in sorted(set(q_ends)):
        rd = _nearest_next_trade_day(trade_days, qe)
        if rd is None:
            continue
        if rd < start_d or rd > end_d:
            continue
        rebalance_points.append((qe, rd))
    rebalance_points = sorted(set(rebalance_points), key=lambda x: x[1])
    if not rebalance_points:
        raise RuntimeError("未生成任何调仓点")

    # 抓取基金季度持仓
    fund_codes = sorted(set(fund_top3["基金代码"].tolist()))
    print(f"[2/6] 抓取基金季度持仓 ... 基金数={len(fund_codes)} 年份={start_year}~{end_year}")
    fund_holdings: dict[str, dict[date, pd.DataFrame]] = {}
    for fc in fund_codes:
        fund_holdings[fc] = fetch_fund_quarter_holdings(fc, start_year=start_year, end_year=end_year, sleep_s=args.sleep)

    # 计算每期目标权重
    print(f"[3/6] 计算每期目标权重（经理等权；按基金占比聚合）... 调仓点={len(rebalance_points)}")
    weights_by_date: dict[date, dict[str, float]] = {}
    for qe, rd in rebalance_points:
        per_mgr = {}
        active_mgr = 0
        for mgr_key, funds in mgr_funds.items():
            allow = mgr_stocks.get(mgr_key, set()) if args.restrict_to_selected_stocks else None
            w = {}
            for fc in funds:
                h = fund_holdings.get(fc, {}).get(qe)
                if h is None or h.empty:
                    continue
                for r in h.itertuples(index=False):
                    code = str(r.股票代码).zfill(6)
                    if allow is not None and code not in allow:
                        continue
                    w[code] = w.get(code, 0.0) + float(r.占净值比例)
            if not w:
                continue
            s = sum(w.values())
            if s <= 0:
                continue
            w = {k: v / s for k, v in w.items()}
            per_mgr[mgr_key] = w
            active_mgr += 1
        if active_mgr == 0:
            continue
        # 经理之间等权
        combined: dict[str, float] = {}
        for w in per_mgr.values():
            for k, v in w.items():
                combined[k] = combined.get(k, 0.0) + v / active_mgr
        s2 = sum(combined.values())
        if s2 <= 0:
            continue
        combined = {k: v / s2 for k, v in combined.items()}

        # TopK 截断
        if args.topk and args.topk > 0 and len(combined) > args.topk:
            top_items = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)[: args.topk]
            combined = dict(top_items)
            s3 = sum(combined.values())
            combined = {k: v / s3 for k, v in combined.items()}
        weights_by_date[rd] = combined

    if not weights_by_date:
        raise RuntimeError("所有调仓点都未生成有效权重（可能持仓数据缺失）")

    # 下载股票价格
    universe = sorted({c for w in weights_by_date.values() for c in w.keys()})
    print(f"[4/6] 下载股票价格 ... 股票数={len(universe)} 区间={start_d}~{end_d} 复权={cfg.adjust}")
    price_map: dict[str, pd.Series] = {}
    for code in universe:
        price_map[code] = fetch_stock_prices(
            code=code, start=start_d, end=end_d,
            adjust=cfg.adjust, cache_dir=cache_dir, sleep_s=args.price_sleep,
        )

    # 构建价格矩阵
    print("[5/6] 构建价格矩阵并运行回测 ...")
    cal = trade_days.dt.date.tolist()
    price_df = pd.DataFrame(index=cal)
    for code, s in price_map.items():
        price_df[code] = s.reindex(cal)
        price_df[code] = price_df[code].ffill()

    # 回测主循环
    cash = cfg.initial_cash
    pos: dict[str, int] = {}
    trades = []
    equity_rows = []

    rebalance_dates = sorted(weights_by_date.keys())
    rebalance_set = set(rebalance_dates)

    for d0 in cal:
        if d0 in rebalance_set:
            w = weights_by_date[d0]
            w = {k: v for k, v in w.items() if pd.notna(price_df.at[d0, k])}
            if w:
                sw = sum(w.values())
                w = {k: v / sw for k, v in w.items()}

                cur_value = cash + sum(pos.get(k, 0) * float(price_df.at[d0, k]) for k in pos if pd.notna(price_df.at[d0, k]))

                target_pos: dict[str, int] = {}
                for code, wt in w.items():
                    px = float(price_df.at[d0, code])
                    if px <= 0:
                        continue
                    target_shares = _lot_round_down((cur_value * wt) / px, 100)
                    if target_shares > 0:
                        target_pos[code] = target_shares

                # 先卖
                for code, cur_sh in list(pos.items()):
                    tgt = target_pos.get(code, 0)
                    delta = tgt - cur_sh
                    if delta >= 0:
                        continue
                    px = float(price_df.at[d0, code])
                    sell_sh = -delta
                    amount = sell_sh * px
                    fee = amount * cfg.fee_rate
                    cash += amount - fee
                    pos[code] = cur_sh - sell_sh
                    if pos[code] <= 0:
                        pos.pop(code, None)
                    trades.append({
                        "日期": d0, "方向": "卖出", "代码": code,
                        "价格": px, "股数": sell_sh, "成交额": amount, "手续费": fee,
                    })
                # 后买
                for code, tgt_sh in sorted(target_pos.items(), key=lambda kv: w.get(kv[0], 0.0), reverse=True):
                    cur_sh = pos.get(code, 0)
                    delta = tgt_sh - cur_sh
                    if delta <= 0:
                        continue
                    px = float(price_df.at[d0, code])
                    amount = delta * px
                    fee = amount * cfg.fee_rate
                    if cash >= amount + fee:
                        cash -= amount + fee
                        pos[code] = cur_sh + delta
                        trades.append({
                            "日期": d0, "方向": "买入", "代码": code,
                            "价格": px, "股数": delta, "成交额": amount, "手续费": fee,
                        })

        hold_value = 0.0
        for code, sh in pos.items():
            px = price_df.at[d0, code]
            if pd.isna(px):
                continue
            hold_value += sh * float(px)
        equity = cash + hold_value
        equity_rows.append({"日期": d0, "现金": cash, "持仓市值": hold_value, "总资产": equity, "持仓股票数": len(pos)})

    equity_df = pd.DataFrame(equity_rows)
    equity_df["日期"] = pd.to_datetime(equity_df["日期"])
    equity_df = equity_df.sort_values("日期")
    equity_df["日收益率"] = equity_df["总资产"].pct_change().fillna(0.0)
    equity_df["累计收益率"] = equity_df["总资产"] / cfg.initial_cash - 1.0
    equity_df["峰值"] = equity_df["总资产"].cummax()
    equity_df["回撤"] = equity_df["总资产"] / equity_df["峰值"] - 1.0

    # ---- 获取基准数据 ----
    benchmark_s = None
    if args.benchmark:
        print(f"[6/6] 获取基准指数 {args.benchmark} ...")
        benchmark_s = fetch_benchmark(
            symbol=args.benchmark, start=start_d, end=end_d,
            cache_dir=cache_dir, sleep_s=args.price_sleep,
        )
        if not benchmark_s.empty:
            # 在 equity_df 中增加基准列
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
        print("[6/6] 跳过基准对比")

    stamp = datetime.now().strftime("%Y%m%d")
    curve_out = out_dir / f"回测_净值曲线_{stamp}.csv"
    trades_out = out_dir / f"回测_调仓记录_{stamp}.csv"
    md_out = out_dir / f"回测摘要_{stamp}.md"
    chart_out = out_dir / f"回测_图表_{stamp}.png"

    # 导出 CSV
    equity_df.to_csv(curve_out, index=False, encoding="utf-8-sig")
    pd.DataFrame(trades).to_csv(trades_out, index=False, encoding="utf-8-sig")

    # 计算绩效指标
    metrics = calc_performance_metrics(equity_df, benchmark_s, cfg)

    # 生成图表
    if not args.no_plot:
        title = f"绩优基金经理股票组合回测（Top{args.manager_topn}）"
        plot_backtest_result(equity_df, metrics, chart_out, benchmark_s, title)

    # 生成摘要
    out_files = [curve_out, trades_out, md_out]
    if not args.no_plot:
        out_files.append(chart_out)
    extra_info = {
        "再平衡": "季度（季度末后第一交易日）",
        "标的": f"选定绩优基金经理 Top10 重仓股集合（股票数 {len(universe)}）",
        "基准": args.benchmark if args.benchmark else "无",
    }
    md_text = format_summary_md(metrics, cfg, out_files, extra_info)
    # 追加局限说明
    md_text += "\n## 局限/注意\n"
    md_text += "- 基金持仓披露为季度口径，真实披露存在滞后；本回测按「季度末后首个交易日」立即调仓，偏乐观。\n"
    md_text += "- 仅使用基金披露的前十大重仓股，无法代表基金全部持仓。\n"
    md_text += "- 未处理停牌/涨跌停导致无法成交等交易约束；估值对缺失价格做了向前填充。\n"
    md_text += "- A 股按 100 股一手向下取整，可能导致现金占用较高。\n"
    md_out.write_text(md_text, encoding="utf-8")

    print(f"完成：{curve_out}")
    print(f"完成：{trades_out}")
    print(f"完成：{md_out}")
    if not args.no_plot:
        print(f"完成：{chart_out}")

    # 打印关键指标
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
