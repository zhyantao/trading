#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成“优化后的我的持仓”，并以追加方式写入 out/我的持仓.csv（记录调仓历史）。

默认做法（与你当前偏好一致，可用参数调整）：
- 目标持仓总数：5 个
- 股票/基金大类比例：股票30% / 基金70%
- 股票权重：使用 out/绩优基金经理_股票Top10_*.csv 的“汇总占净值比例”作为得分，取 TopK 后按得分归一
- 基金权重：使用 out/绩优基金经理_基金Top3_*.csv 的“成立来年化(>0)”作为得分，取 TopK 后按得分归一

输出文件（只保留一个）：out/我的持仓.csv
格式（长表，便于记录历史）：
日期,类型,代码,名称,数量,比例(%)
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd


def _latest(out_dir: Path, pattern: str) -> Path:
    files = sorted(out_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"未在 {out_dir} 找到文件：{pattern}")
    return files[-1]


def _split_counts(total_n: int, stock_pct: float, fund_pct: float) -> tuple[int, int]:
    if total_n <= 0:
        raise ValueError("total_n 必须 > 0")
    if stock_pct < 0 or fund_pct < 0 or abs(stock_pct + fund_pct - 100.0) > 1e-6:
        raise ValueError("stock_pct + fund_pct 必须 = 100")
    n_stock = int(round(total_n * stock_pct / 100.0))
    n_stock = max(0, min(total_n, n_stock))
    n_fund = total_n - n_stock
    # 如果两边比例都>0，尽量保证两边至少1个
    if stock_pct > 0 and fund_pct > 0:
        if n_stock == 0:
            n_stock, n_fund = 1, total_n - 1
        if n_fund == 0:
            n_fund, n_stock = 1, total_n - 1
    return n_stock, n_fund


def _normalize_to_bucket(df: pd.DataFrame, score_col: str, bucket: float) -> pd.Series:
    s = pd.to_numeric(df[score_col], errors="coerce").fillna(0.0)
    if s.sum() <= 0:
        return pd.Series([bucket / len(df)] * len(df), index=df.index)
    return (s / s.sum()) * bucket


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-n", type=int, default=5, help="目标持仓标的总数，默认 5")
    parser.add_argument("--stock-pct", type=float, default=30.0, help="股票大类比例(%%)，默认 30")
    parser.add_argument("--fund-pct", type=float, default=70.0, help="基金大类比例(%%)，默认 70")
    parser.add_argument("--date", default="", help="记录日期(YYYY-MM-DD)；不填则用今天")
    parser.add_argument("--out", default="out/我的持仓.csv", help="输出/追加到该文件，默认 out/我的持仓.csv")
    parser.add_argument("--elite-funds", default="", help="基金Top3文件；不填则 out/ 下自动取最新")
    parser.add_argument("--elite-stocks", default="", help="股票Top10文件；不填则 out/ 下自动取最新")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = args.date.strip() or datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (root / out_path).resolve()

    funds_path = Path(args.elite_funds) if args.elite_funds else _latest(out_dir, "绩优基金经理_基金Top3_*.csv")
    stocks_path = Path(args.elite_stocks) if args.elite_stocks else _latest(out_dir, "绩优基金经理_股票Top10_*.csv")
    if not funds_path.is_absolute():
        funds_path = (root / funds_path).resolve()
    if not stocks_path.is_absolute():
        stocks_path = (root / stocks_path).resolve()

    funds = pd.read_csv(funds_path, dtype={"基金代码": str})
    stocks = pd.read_csv(stocks_path, dtype={"股票代码": str})

    # 股票得分：汇总占净值比例（越高越好）
    stocks["汇总占净值比例"] = pd.to_numeric(stocks.get("汇总占净值比例"), errors="coerce").fillna(0.0)
    stock_score = (
        stocks.groupby(["股票代码", "股票名称"], dropna=False)["汇总占净值比例"]
        .sum()
        .reset_index(name="score")
        .sort_values("score", ascending=False)
    )
    stock_score["股票代码"] = stock_score["股票代码"].astype(str).str.zfill(6)

    # 基金得分：成立来年化（正值，越高越好）
    funds["成立来年化"] = pd.to_numeric(funds.get("成立来年化"), errors="coerce")
    fund_score = (
        funds.dropna(subset=["成立来年化"])
        .query("成立来年化 > 0")
        .groupby(["基金代码", "基金简称"], dropna=False)["成立来年化"]
        .max()
        .reset_index(name="score")
        .sort_values("score", ascending=False)
    )
    fund_score["基金代码"] = fund_score["基金代码"].astype(str).str.zfill(6)

    n_stock, n_fund = _split_counts(args.total_n, args.stock_pct, args.fund_pct)

    picked_stock = stock_score.head(n_stock).copy() if n_stock > 0 else pd.DataFrame(columns=stock_score.columns)
    picked_fund = fund_score.head(n_fund).copy() if n_fund > 0 else pd.DataFrame(columns=fund_score.columns)

    rows: list[dict] = []

    if not picked_stock.empty:
        picked_stock["比例(%)"] = _normalize_to_bucket(picked_stock, "score", args.stock_pct)
        for _, r in picked_stock.iterrows():
            rows.append(
                {
                    "日期": stamp,
                    "类型": "股票",
                    "代码": str(r["股票代码"]).zfill(6),
                    "名称": r["股票名称"],
                    "数量": "",
                    "比例(%)": float(r["比例(%)"]),
                }
            )

    if not picked_fund.empty:
        picked_fund["比例(%)"] = _normalize_to_bucket(picked_fund, "score", args.fund_pct)
        for _, r in picked_fund.iterrows():
            rows.append(
                {
                    "日期": stamp,
                    "类型": "基金",
                    "代码": str(r["基金代码"]).zfill(6),
                    "名称": r["基金简称"],
                    "数量": "",
                    "比例(%)": float(r["比例(%)"]),
                }
            )

    if not rows:
        raise RuntimeError("未生成任何持仓（可能是基金/股票得分为空或过滤过严）")

    alloc = pd.DataFrame(rows)
    alloc["比例(%)"] = pd.to_numeric(alloc["比例(%)"], errors="coerce").fillna(0.0).round(2)
    # 四舍五入误差修正到最大权重行
    err = round(100.0 - float(alloc["比例(%)"].sum()), 2)
    if abs(err) >= 0.01:
        i = alloc["比例(%)"].idxmax()
        alloc.loc[i, "比例(%)"] = round(float(alloc.loc[i, "比例(%)"]) + err, 2)

    # 追加写入：若存在同日期记录则先删除（方便重跑）
    if out_path.exists():
        old = pd.read_csv(out_path, dtype={"代码": str})
        if "日期" not in old.columns:
            # 兼容旧格式：把旧数据视为当天一条历史快照
            old.insert(0, "日期", stamp)
        old["日期"] = old["日期"].astype(str)
        old = old[old["日期"] != stamp].copy()
        new_df = pd.concat([old, alloc], ignore_index=True)
    else:
        new_df = alloc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成：{out_path}（已追加日期={stamp} 的持仓快照） 行数={len(new_df):,}")


if __name__ == "__main__":
    main()
