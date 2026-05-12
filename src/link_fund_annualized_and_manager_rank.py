#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建立“基金年化收益率排序”与“基金经理排名”之间的关系（关联明细表）。

输入（默认取 out/ 下最新文件）：
  - 基金经理_基金收益率明细_*.csv
  - 基金经理业绩排名_*.csv
  - 基金年化收益率排序_*.csv

输出：
  - out/基金_经理_年化_排名关联_YYYYMMDD.csv

规则（按用户选择的默认口径实现）：
  - 多经理：每位经理各记一条（基金-经理多行）
  - 新基金过滤：成立天数 >= 180（来自“基金年化收益率排序”文件的 成立天数 字段）
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", default="", help="基金经理-基金明细 CSV；不填则自动取最新")
    parser.add_argument("--manager-rank", default="", help="基金经理排名 CSV；不填则自动取最新")
    parser.add_argument("--fund-annual", default="", help="基金年化排序 CSV；不填则自动取最新")
    parser.add_argument("--min-days", type=int, default=180, help="过滤成立天数阈值，默认 180")
    parser.add_argument("--out", default="", help="输出 CSV；不填则写入 out/基金_经理_年化_排名关联_YYYYMMDD.csv")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"

    detail_path = Path(args.detail) if args.detail else _latest(out_dir, "基金经理_基金收益率明细_*.csv")
    manager_rank_path = (
        Path(args.manager_rank) if args.manager_rank else _latest(out_dir, "基金经理业绩排名_*.csv")
    )
    fund_annual_path = Path(args.fund_annual) if args.fund_annual else _latest(out_dir, "基金年化收益率排序_*.csv")

    def _abs(p: Path) -> Path:
        return p if p.is_absolute() else (project_root / p).resolve()

    detail_path, manager_rank_path, fund_annual_path = map(_abs, [detail_path, manager_rank_path, fund_annual_path])

    if args.out:
        out_path = _abs(Path(args.out))
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        out_path = out_dir / f"基金_经理_年化_排名关联_{stamp}.csv"

    # 读取数据
    detail_df = pd.read_csv(detail_path, dtype={"基金代码": str})
    mgr_rank_df = pd.read_csv(manager_rank_path)
    fund_ann_df = pd.read_csv(fund_annual_path, dtype={"基金代码": str})

    # 过滤新基金（成立天数来自 fund_ann_df）
    if "成立天数" not in fund_ann_df.columns:
        raise KeyError("基金年化排序文件缺少列：成立天数；请先运行 src/rank_all_funds_by_annualized_return.py 生成最新文件")
    fund_ann_df["成立天数"] = pd.to_numeric(fund_ann_df["成立天数"], errors="coerce")
    fund_ann_df = fund_ann_df[fund_ann_df["成立天数"].fillna(-1) >= args.min_days].copy()

    # 为避免字段名冲突，先重命名两张“排名”列
    if "排名" in mgr_rank_df.columns:
        mgr_rank_df = mgr_rank_df.rename(columns={"排名": "经理排名"})
    if "排名" in fund_ann_df.columns:
        fund_ann_df = fund_ann_df.rename(columns={"排名": "基金年化排名"})

    # 明细表去重（同一经理-基金可能重复出现）
    dedup_cols = [c for c in ["序号", "姓名", "所属公司", "基金代码"] if c in detail_df.columns]
    if dedup_cols:
        detail_df = detail_df.drop_duplicates(subset=dedup_cols)

    # 1) 基金-经理 明细  +  基金年化
    fund_keep_cols = [
        c
        for c in [
            "基金年化排名",
            "基金代码",
            "基金简称",
            "日期",
            "成立日",
            "成立天数",
            "成立来",
            "成立来年化",
            "近1年",
            "近3年",
            "今年来",
            "单位净值",
            "累计净值",
        ]
        if c in fund_ann_df.columns
    ]
    merged = pd.merge(
        detail_df,
        fund_ann_df[fund_keep_cols],
        on="基金代码",
        how="inner",  # 只保留能匹配到年化数据的基金
        suffixes=("", "(年化表)"),
    )

    # 2) 加上经理排名
    mgr_key = [c for c in ["序号", "姓名", "所属公司"] if c in merged.columns and c in mgr_rank_df.columns]
    if not mgr_key:
        raise KeyError("无法用（序号/姓名/所属公司）与经理排名表匹配，请检查输入文件字段")

    merged = pd.merge(
        merged,
        mgr_rank_df,
        on=mgr_key,
        how="left",
        suffixes=("", "(经理排名表)"),
    )

    # 统一增加生成时间
    # 可能来自输入表的同名列，先删除再插入，保证是本次生成时间
    for c in ["数据生成时间", "成立天数过滤阈值"]:
        if c in merged.columns:
            merged = merged.drop(columns=[c])
    merged.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    merged.insert(1, "成立天数过滤阈值", args.min_days)

    # 输出字段排序：优先把核心关系字段放前面
    front_cols = [
        "数据生成时间",
        "成立天数过滤阈值",
        "基金年化排名",
        "基金代码",
        "基金简称",
        "成立日",
        "成立天数",
        "成立来",
        "成立来年化",
        "序号",
        "姓名",
        "所属公司",
        "经理排名",
        "平均收益率",
        "有效基金数",
        "管理基金数",
    ]
    cols = []
    for c in front_cols:
        if c in merged.columns and c not in cols:
            cols.append(c)
    cols += [c for c in merged.columns if c not in cols]
    merged = merged[cols]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(
        f"完成：{out_path}  行数={len(merged):,}  列数={len(merged.columns)}  "
        f"fund_filter_days>={args.min_days}"
    )


if __name__ == "__main__":
    main()
