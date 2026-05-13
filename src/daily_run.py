#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日自动跑全流程并生成“调仓信号”报告（不构成投资建议）。

执行步骤（依次生成 out/ 下的最新数据文件）：
1) 基金经理-基金收益率明细
2) 基金经理排名
3) 基金年化收益率排序（成立来年化）
4) 关联表（基金年化 <-> 经理排名）
5) 绩优经理筛选 + 基金Top3/股票Top10
6) 每日调仓信号（对照 out/我的持仓.csv）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable

    run([py, str(root / "src" / "build_manager_fund_returns.py")])
    run([py, str(root / "src" / "rank_fund_managers.py")])
    run([py, str(root / "src" / "rank_all_funds_by_annualized_return.py")])
    run([py, str(root / "src" / "link_fund_annualized_and_manager_rank.py"), "--min-days", "180"])
    run([py, str(root / "src" / "pick_elite_managers_targets.py"), "--top-n", "20", "--min-days", "180"])
    run([py, str(root / "src" / "optimize_holdings.py")])
    run([py, str(root / "src" / "daily_rebalance_signal.py"), "--holdings", "out/我的持仓.csv"])


if __name__ == "__main__":
    main()

