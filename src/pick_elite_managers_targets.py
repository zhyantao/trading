#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选“绩优且无历史负业绩”的基金经理，并基于其管理基金的重仓股输出投资标的：
  - 每位经理：前 10 个股票投资标的（来自其 Top3 基金的最新季度重仓股，持仓占比求和排序）
  - 每位经理：3 个基金投资标的（按成立来年化排序）

默认数据输入（均在 out/）：
  - 基金_经理_年化_排名关联_*.csv（包含：经理排名、基金成立来年化、近1年、成立来等）

过滤/规则（默认与用户选择一致）：
  - 经理候选：经理排名靠前（默认取 Top 20）并且名下基金满足：近1年>=0 且 成立来>=0（在可用样本内）
  - 新基金过滤：成立天数 >= 180（从关联表已带出）
  - 选基金：成立来年化最高的 Top3（若持仓抓取失败则顺延补足）
  - 选股票：Top3 基金最新季度重仓股，按“占净值比例”求和排序取 Top10

输出（写入 out/）：
  - 绩优基金经理_基金Top3_YYYYMMDD.csv
  - 绩优基金经理_股票Top10_YYYYMMDD.csv
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


def _latest(out_dir: Path, pattern: str) -> Path:
    files = sorted(out_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"未在 {out_dir} 找到文件：{pattern}")
    return files[-1]


def _quarter_key(s: str) -> tuple[int, int]:
    """
    解析类似 '2025年1季度股票投资明细' -> (2025, 1)
    """
    m = re.search(r"(\d{4})年(\d)季度", str(s))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def fetch_latest_stock_holding(fund_code: str, years_back: int = 6, sleep_s: float = 0.2) -> pd.DataFrame:
    """
    抓取基金最新季度股票持仓（重仓股）。
    返回字段：股票代码, 股票名称, 占净值比例
    """
    import akshare as ak

    this_year = datetime.now().year
    last_exc: Exception | None = None
    for y in range(this_year, this_year - years_back, -1):
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(y))
            time.sleep(sleep_s)
            if df is None or df.empty:
                continue
            # 取最新季度
            df = df.copy()
            df["_qkey"] = df["季度"].map(_quarter_key)
            latest = df["_qkey"].max()
            df = df[df["_qkey"] == latest].copy()
            df["占净值比例"] = pd.to_numeric(df["占净值比例"], errors="coerce")
            df = df.dropna(subset=["占净值比例"])
            return df[["股票代码", "股票名称", "占净值比例", "季度"]].reset_index(drop=True)
        except Exception as e:
            last_exc = e
            continue
    if last_exc:
        raise last_exc
    return pd.DataFrame(columns=["股票代码", "股票名称", "占净值比例", "季度"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", default="", help="关联表路径；不填则自动取 out/ 下最新的 基金_经理_年化_排名关联_*.csv")
    parser.add_argument("--top-n", type=int, default=20, help="经理目标数量（过滤前按经理排名向下扫描补足），默认 20")
    parser.add_argument("--min-days", type=int, default=180, help="成立天数过滤阈值，默认 180")
    parser.add_argument("--fund-topk", type=int, default=3, help="每位经理输出基金数量，默认 3")
    parser.add_argument("--stock-topk", type=int, default=10, help="每位经理输出股票数量，默认 10")
    parser.add_argument("--sleep", type=float, default=0.2, help="抓取持仓的间隔秒数，默认 0.2")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    link_path = Path(args.link) if args.link else _latest(out_dir, "基金_经理_年化_排名关联_*.csv")
    if not link_path.is_absolute():
        link_path = (project_root / link_path).resolve()

    df = pd.read_csv(link_path, dtype={"基金代码": str})

    # 基础过滤：成立天数>=阈值
    df["成立天数"] = pd.to_numeric(df.get("成立天数"), errors="coerce")
    df = df[df["成立天数"].fillna(-1) >= args.min_days].copy()

    # “无历史负业绩”：在当前可用样本内，要求近1年>=0 且 成立来>=0
    df["近1年"] = pd.to_numeric(df.get("近1年"), errors="coerce")
    df["成立来"] = pd.to_numeric(df.get("成立来"), errors="coerce")
    df["成立来年化"] = pd.to_numeric(df.get("成立来年化"), errors="coerce")
    df["经理排名"] = pd.to_numeric(df.get("经理排名"), errors="coerce")

    mgr_cols = [c for c in ["序号", "姓名", "所属公司"] if c in df.columns]
    if len(mgr_cols) < 2:
        raise KeyError("关联表缺少基金经理标识列（期望至少包含：姓名、所属公司；最好还有序号）")

    # 先按经理聚合，得到负业绩判定与经理排名
    mgr_agg = (
        df.groupby(mgr_cols, dropna=False)
        .agg(
            经理排名=("经理排名", "min"),
            名下基金数=("基金代码", "nunique"),
            min_近1年=("近1年", "min"),
            min_成立来=("成立来", "min"),
            max_成立来年化=("成立来年化", "max"),
        )
        .reset_index()
    )
    mgr_agg = mgr_agg.sort_values(["经理排名", "max_成立来年化"], ascending=[True, False])

    # 向下扫描补足 TopN：只保留无负业绩经理
    picked_mgr_rows = []
    for _, r in mgr_agg.iterrows():
        if pd.isna(r["经理排名"]):
            continue
        if pd.isna(r["min_近1年"]) or pd.isna(r["min_成立来"]):
            continue
        if r["min_近1年"] < 0 or r["min_成立来"] < 0:
            continue
        picked_mgr_rows.append(r)
        if len(picked_mgr_rows) >= args.top_n:
            break
    picked_mgr = pd.DataFrame(picked_mgr_rows)
    if picked_mgr.empty:
        raise RuntimeError("未筛选到满足条件的基金经理（可能过滤条件过严或数据缺失）")

    # 输出：基金Top3
    stamp = datetime.now().strftime("%Y%m%d")
    funds_out = out_dir / f"绩优基金经理_基金Top3_{stamp}.csv"
    stocks_out = out_dir / f"绩优基金经理_股票Top10_{stamp}.csv"

    fund_rows: list[dict] = []
    stock_rows: list[dict] = []

    # 避免重复抓取同一基金持仓
    holding_cache: dict[str, pd.DataFrame] = {}

    for _, mgr in picked_mgr.iterrows():
        mgr_key = tuple(mgr[c] for c in mgr_cols)
        sub = df.copy()
        for c, v in zip(mgr_cols, mgr_key):
            sub = sub[sub[c] == v]

        # 候选基金：按成立来年化降序
        sub = sub.drop_duplicates(subset=["基金代码"])
        sub = sub.sort_values(["成立来年化", "基金年化排名"], ascending=[False, True])

        chosen_funds = []
        for _, fr in sub.iterrows():
            code = str(fr["基金代码"]).zfill(6)
            if code in holding_cache:
                ok = not holding_cache[code].empty
            else:
                try:
                    holding_cache[code] = fetch_latest_stock_holding(code, sleep_s=args.sleep)
                    ok = not holding_cache[code].empty
                except Exception:
                    holding_cache[code] = pd.DataFrame()
                    ok = False
            if not ok:
                continue
            chosen_funds.append(fr)
            if len(chosen_funds) >= args.fund_topk:
                break

        if not chosen_funds:
            # 该经理无法抓到持仓数据，跳过
            continue

        # 记录基金 Top3
        for rank_i, fr in enumerate(chosen_funds, start=1):
            fund_rows.append(
                {
                    "数据生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "经理排名": int(mgr["经理排名"]),
                    **{c: mgr[c] for c in mgr_cols},
                    "基金Top": rank_i,
                    "基金代码": str(fr["基金代码"]).zfill(6),
                    "基金简称": fr.get("基金简称"),
                    "基金年化排名": fr.get("基金年化排名"),
                    "成立日": fr.get("成立日"),
                    "成立天数": fr.get("成立天数"),
                    "成立来": fr.get("成立来"),
                    "成立来年化": fr.get("成立来年化"),
                    "近1年": fr.get("近1年"),
                }
            )

        # 汇总股票 Top10（占净值比例求和）
        all_hold = []
        for fr in chosen_funds:
            code = str(fr["基金代码"]).zfill(6)
            h = holding_cache.get(code)
            if h is None or h.empty:
                continue
            tmp = h.copy()
            tmp["基金代码"] = code
            tmp["基金简称"] = fr.get("基金简称")
            all_hold.append(tmp)
        if not all_hold:
            continue
        hold_df = pd.concat(all_hold, ignore_index=True)
        hold_df["占净值比例"] = pd.to_numeric(hold_df["占净值比例"], errors="coerce")

        agg = (
            hold_df.groupby(["股票代码", "股票名称"], dropna=False)
            .agg(
                汇总占净值比例=("占净值比例", "sum"),
                出现基金数=("基金代码", "nunique"),
                最新季度=("季度", "max"),
            )
            .reset_index()
        )
        agg = agg.sort_values(["汇总占净值比例", "出现基金数"], ascending=[False, False]).head(args.stock_topk)
        for i, sr in enumerate(agg.itertuples(index=False), start=1):
            stock_rows.append(
                {
                    "数据生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "经理排名": int(mgr["经理排名"]),
                    **{c: mgr[c] for c in mgr_cols},
                    "股票Top": i,
                    "股票代码": sr.股票代码,
                    "股票名称": sr.股票名称,
                    "汇总占净值比例": sr.汇总占净值比例,
                    "出现基金数": sr.出现基金数,
                    "最新季度": sr.最新季度,
                    "Top3基金列表": ",".join([str(fr["基金代码"]).zfill(6) for fr in chosen_funds]),
                }
            )

    fund_df = pd.DataFrame(fund_rows)
    stock_df = pd.DataFrame(stock_rows)

    fund_df.to_csv(funds_out, index=False, encoding="utf-8-sig")
    stock_df.to_csv(stocks_out, index=False, encoding="utf-8-sig")
    print(f"完成：{funds_out}  行数={len(fund_df):,}")
    print(f"完成：{stocks_out}  行数={len(stock_df):,}")


if __name__ == "__main__":
    main()
