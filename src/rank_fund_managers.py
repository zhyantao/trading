#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据基金经理名下基金的区间收益率，对基金经理进行排名。

默认使用 out/ 下最新的“基金经理_基金收益率明细_YYYYMMDD.csv”，并输出到 out/：
  - 基金经理业绩排名_YYYYMMDD.csv

排名口径（本脚本默认）：
  - 近1年收益率（列名：近1年）
  - 同一经理多基金：简单平均
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd


def find_latest_detail_csv(out_dir: Path) -> Path:
    files = sorted(out_dir.glob("基金经理_基金收益率明细_*.csv"))
    if not files:
        raise FileNotFoundError(f"未在 {out_dir} 找到明细文件：基金经理_基金收益率明细_*.csv")
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="",
        help="输入明细 CSV 路径；不填则自动使用 out/ 下最新的基金经理_基金收益率明细_*.csv",
    )
    parser.add_argument(
        "--metric",
        default="近1年",
        help="用于排名的收益率列名，默认 近1年",
    )
    parser.add_argument(
        "--composite",
        action="store_true",
        help="使用多因子复合评分（Dalio 框架）替代单一指标排名",
    )
    parser.add_argument(
        "--out",
        default="",
        help="输出排名 CSV 路径；不填则写入 out/基金经理业绩排名_YYYYMMDD.csv",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"

    input_path = Path(args.input) if args.input else find_latest_detail_csv(out_dir)
    if not input_path.is_absolute():
        input_path = (project_root / input_path).resolve()

    metric = args.metric
    if not args.out:
        stamp = datetime.now().strftime("%Y%m%d")
        out_path = out_dir / f"基金经理业绩排名_{stamp}.csv"
    else:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (project_root / out_path).resolve()

    df = pd.read_csv(input_path, dtype={"基金代码": str})
    if metric not in df.columns:
        raise KeyError(f"输入文件缺少列：{metric}；可用列：{list(df.columns)}")

    # 清洗：只保留 metric 有效的行
    df[metric] = pd.to_numeric(df[metric], errors="coerce")

    group_cols = [c for c in ["序号", "姓名", "所属公司"] if c in df.columns]
    if not group_cols:
        raise KeyError("输入文件缺少基金经理标识列（期望至少包含：序号/姓名/所属公司 之一）")

    g = df.groupby(group_cols, dropna=False)
    agg = g.agg(
        管理基金数=("基金代码", "nunique"),
        有效基金数=(metric, lambda s: int(s.notna().sum())),
        平均收益率=(metric, "mean"),
        中位数收益率=(metric, "median"),
        最佳收益率=(metric, "max"),
        最差收益率=(metric, "min"),
    ).reset_index()

    # 只对至少有 1 只有效基金的经理排名
    ranked = agg[agg["有效基金数"] > 0].copy()

    if args.composite:
        from factor_scoring import compute_manager_composite_score
        ranked["_composite"] = compute_manager_composite_score(ranked)
        ranked = ranked.sort_values("_composite", ascending=False)
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", "复合得分(Dalio多因子)")
        ranked = ranked.drop(columns=["_composite"])
    else:
        ranked = ranked.sort_values(["平均收益率", "有效基金数", "管理基金数"], ascending=[False, False, False])
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", metric)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成：{out_path}  行数={len(ranked):,}  列数={len(ranked.columns)}  input={input_path.name}")


if __name__ == "__main__":
    main()

