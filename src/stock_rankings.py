#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「每位绩优经理的股票 Top10」汇总成全站股票排名。

数据来源：out/绩优基金经理_股票Top10_*.csv（静态站里是 elite.json 的候选池）。
每位经理的 Top10 是该经理 Top3 基金最新季度重仓股按占净值比例求和后的前 10 名。

v2 口径：不再用「入选经理数 → 出现基金数 → 占比 → 名次」的字典序硬排，
改用 selection_formula.score_stock_candidates() 的形式化综合得分

    S_s = a·ñ(ln(1+M)) + b·ñ(ln(1+F)) + c·ñ(ln(1+P))
          + d·(1−ñ(T)) + e·ñ(Q)

降序排列（得分相同时使用共识度、覆盖基金数、占比、名次依次打破平局）。
共识度仍是最大权重，但仓位与经理质量也会实质参与排序。

静态站生成器与本地动态站共用本模块，保证两边排名完全一致。
"""

from __future__ import annotations

from typing import Any

from selection_formula import ranking_meta, score_stock_candidates


def build_stock_rankings(stocks: list[dict[str, Any]] | None) -> dict[str, Any]:
    """返回 {"rows": [...], "manager_count", "stock_count", "record_count"}。"""
    records = [r for r in (stocks or []) if isinstance(r, dict)]
    rows = score_stock_candidates(records)
    meta = ranking_meta(records)
    return {
        "rows": rows,
        "manager_count": meta["manager_count"],
        "stock_count": len(rows),
        "record_count": meta["record_count"],
        "score_formula": "S_s = 0.34·ñ(ln(1+M)) + 0.18·ñ(ln(1+F)) + 0.18·ñ(ln(1+P)) + 0.12·(1−ñ(T)) + 0.18·ñ(Q)",
    }
