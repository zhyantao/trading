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

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 绕过 macOS 系统代理
import urllib.request as _ur
_ur.getproxies = lambda: {}
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"


def run(cmd: list[str], retries: int = 3, delay: float = 5.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            print(f"[RUN] {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            return
        except subprocess.CalledProcessError:
            if attempt == retries:
                raise
            wait = delay * attempt
            print(f"[RETRY] attempt {attempt}/{retries} failed, waiting {wait:.0f}s ...")
            time.sleep(wait)


def cleanup_old_files(out_dir: Path, keep_days: int = 3) -> None:
    """删除 out/ 中超过 keep_days 天的旧数据文件，避免仓库无限膨胀。"""
    # 收集所有文件中的日期戳
    date_stamps: set[str] = set()
    for f in out_dir.iterdir():
        if not f.is_file():
            continue
        for part in f.stem.split("_"):
            if len(part) == 8 and part.isdigit():
                try:
                    datetime.strptime(part, "%Y%m%d")
                    date_stamps.add(part)
                except ValueError:
                    pass

    if not date_stamps:
        print("[cleanup] 没有找到带日期戳的文件")
        return

    # 保留最近 keep_days 个日期
    keep_stamps = sorted(date_stamps, reverse=True)[:keep_days]
    keep_set = set(keep_stamps)

    # 删除过期日期的所有文件
    removed = 0
    for f in out_dir.iterdir():
        if not f.is_file():
            continue
        for part in f.stem.split("_"):
            if len(part) == 8 and part.isdigit() and part in date_stamps:
                if part not in keep_set:
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        pass
                break

    print(f"[cleanup] 保留最近 {keep_days} 天: {', '.join(keep_stamps)}，删除 {removed} 个旧文件")


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
    run([py, str(root / "src" / "backtest_fund_portfolio.py")])
    run([py, str(root / "src" / "backtest_elite_manager_portfolio.py")])

    # 清理 3 天前的旧数据文件，避免仓库膨胀
    cleanup_old_files(out_dir, keep_days=3)


if __name__ == "__main__":
    main()

