#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对所有基金按照“年化收益率”排序（默认：成立来年化）。

数据来源：东方财富-开放基金排行 rankhandler.aspx（公开接口）。
说明：
  - 接口返回包含：基金代码、基金简称、净值、各区间收益、成立来、成立日等字段
  - “成立来年化”按复合年化计算：
        annualized = (1 + total_return) ** (365 / days_since_inception) - 1
    其中 total_return = 成立来 / 100
  - 全市场排行从 ``market_snapshot`` 读取当日快照，与「基金经理明细」共用
    同一次请求，不再单独重复拉取全市场数据。

输出：out/基金年化收益率排序_YYYYMMDD.csv（UTF-8 with BOM）
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from incremental import report  # noqa: E402
# 保留原导出名，避免其他脚本/笔记本按旧方式 import 时报错
from market_snapshot import fetch_open_fund_rank_raw, get_fund_rank_snapshot  # noqa: E402,F401


def calc_annualized_since_inception(df: pd.DataFrame) -> pd.Series:
    """
    成立来年化复合收益率（%）
    """
    if "成立来" not in df.columns or "成立日" not in df.columns:
        raise KeyError("缺少 成立来 或 成立日 字段，无法计算成立来年化")

    today = date.today()
    days = (pd.to_datetime(today) - pd.to_datetime(df["成立日"])).dt.days
    total = df["成立来"] / 100.0

    # 防止除零/负数：days<=0 或 total<=-1 均视为无效
    valid = (days > 0) & (total > -1)
    # 用 NaN 初始化 float 列，避免 pd.NA -> float 转换报错
    ann = pd.Series(float("nan"), index=df.index, dtype="float64")
    ann.loc[valid] = ((1.0 + total.loc[valid]) ** (365.0 / days.loc[valid]) - 1.0) * 100.0
    return ann


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbol",
        default="全部",
        choices=["全部", "股票型", "混合型", "债券型", "指数型", "QDII", "FOF", "LOF"],
        help="基金类型范围，默认 全部",
    )
    parser.add_argument(
        "--out",
        default="",
        help="输出 CSV 路径；不填则写入 out/基金年化收益率排序_YYYYMMDD.csv",
    )
    parser.add_argument(
        "--composite",
        action="store_true",
        help="使用多因子复合评分（Dalio 框架）替代成立来年化排名",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (project_root / out_path).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        out_path = out_dir / f"基金年化收益率排序_{stamp}.csv"

    df = get_fund_rank_snapshot(symbol=args.symbol).copy()
    # 成立天数：用于用户后续筛除“太新”的基金（新基金年化会被极端放大）
    df["成立天数"] = (pd.to_datetime(date.today()) - pd.to_datetime(df["成立日"])).dt.days
    df["成立来年化"] = calc_annualized_since_inception(df)

    ranked = df[df["成立来年化"].notna()].copy()

    if args.composite:
        from factor_scoring import compute_fund_composite_score
        ranked["_composite"] = compute_fund_composite_score(ranked)
        ranked = ranked.sort_values("_composite", ascending=False)
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", "复合得分(Dalio多因子)")
        ranked = ranked.drop(columns=["_composite"])
    else:
        ranked = ranked.sort_values(["成立来年化", "成立来"], ascending=[False, False])
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", "成立来年化")

    ranked.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成：{out_path}  行数={len(ranked):,}  列数={len(ranked.columns)}")
    report("[incremental] 年化排序")


if __name__ == "__main__":
    main()
