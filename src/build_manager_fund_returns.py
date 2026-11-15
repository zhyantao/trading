#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用公开接口（东方财富/天天基金，AkShare 封装）获取：
  1) 全市场基金经理-现任基金列表（manager 大全页）
  2) 开放基金排行页提供的区间收益率与净值字段

并将两者按“基金代码”合并，输出到 out 目录下的 CSV 文件。

注意：
- 该公开排行接口目前包含：近1周/近1月/近3月/近6月/近1年/近2年/近3年/今年来/成立来（不含近5年）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from incremental import get_manager_id_map, get_manager_list, report  # noqa: E402
from market_snapshot import as_akshare_rank_columns, get_fund_rank_snapshot  # noqa: E402


def build_out_path(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    return out_dir / f"基金经理_基金收益率明细_{stamp}.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="",
        help="输出 CSV 文件路径；不填则自动写入 out/基金经理_基金收益率明细_YYYYMMDD.csv",
    )
    parser.add_argument(
        "--out-dir",
        default="out",
        help="默认输出目录（当 --out 为空时生效），默认 out",
    )
    parser.add_argument(
        "--symbol",
        default="全部",
        choices=["全部", "股票型", "混合型", "债券型", "指数型", "QDII", "FOF", "LOF"],
        help="开放基金排行类型（影响可匹配到的基金范围）",
    )
    args = parser.parse_args()

    # 将相对路径基于“项目根目录”（即 src 的上一级）
    project_root = Path(__file__).resolve().parent.parent
    out_path = Path(args.out) if args.out else build_out_path(project_root / args.out_dir)
    if not out_path.is_absolute():
        out_path = (project_root / out_path).resolve()

    print("[1/3] 获取基金经理-现任基金列表（7 天缓存）...")
    mgr_df = get_manager_list()
    mgr_df = mgr_df.rename(
        columns={
            "现任基金代码": "基金代码",
            "现任基金": "基金简称(经理页)",
        }
    )
    mgr_df = mgr_df.drop_duplicates(subset=["序号", "姓名", "所属公司", "基金代码"])

    # 经理 ID / 公司代码（姓名+公司匹配），用于个人页直链东方财富经理主页
    id_df = get_manager_id_map()
    if id_df is not None and not id_df.empty:
        mgr_df = mgr_df.merge(id_df, on=["姓名", "所属公司"], how="left")
        matched = int(mgr_df["经理ID"].notna().sum())
        print(f"    经理 ID 映射：{matched:,} 行已匹配（共 {len(mgr_df):,} 行）")
    else:
        print("    [WARN] 经理 ID 映射不可用，个人页外链将回退为搜索")

    print("[2/3] 获取开放基金收益率排行（当日全市场快照，与年化排序共用）...")
    rank_df = as_akshare_rank_columns(get_fund_rank_snapshot(args.symbol))
    if "日期" in rank_df.columns:
        rank_df["日期"] = pd.to_datetime(rank_df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")

    print("[3/3] 合并并导出 ...")
    out_df = pd.merge(
        mgr_df,
        rank_df,
        on="基金代码",
        how="left",
        suffixes=("", "(排行页)"),
    )
    out_df.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    sort_cols = [c for c in ["序号", "姓名", "所属公司", "基金代码"] if c in out_df.columns]
    if sort_cols:
        out_df = out_df.sort_values(sort_cols, kind="mergesort")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成：{out_path}  行数={len(out_df):,}  列数={len(out_df.columns)}")
    report("[incremental] 经理明细")


if __name__ == "__main__":
    main()

