#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「每位绩优经理的股票 Top10」汇总成全站股票排名。

数据来源：out/绩优基金经理_股票Top10_*.csv（静态站里是 elite.json 的 stocks）。
每位经理的 Top10 是该经理 Top3 基金最新季度重仓股按占净值比例求和后的前 10 名，
因此这里按「被多少位经理同时重仓」排序，反映绩优经理之间的共识度：

    入选经理数 ↓  →  出现基金数（去重）↓  →  平均占净值比例 ↓  →  最高名次 ↑

静态站生成器与本地动态站共用本模块，保证两边排名完全一致。
"""

from __future__ import annotations

from typing import Any


def _float(v: Any) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def _funds(v: Any) -> set[str]:
    """解析 Top3基金列表（逗号分隔），用于跨经理去重统计出现基金数。"""
    return {x.strip() for x in str(v or "").replace("，", ",").split(",") if x.strip()}


def build_stock_rankings(stocks: list[dict[str, Any]] | None) -> dict[str, Any]:
    """返回 {"rows": [...], "manager_count", "stock_count", "record_count"}。"""
    records = [r for r in (stocks or []) if isinstance(r, dict)]
    groups: dict[str, dict[str, Any]] = {}
    managers: set[str] = set()

    for r in records:
        code = str(r.get("股票代码") or "").strip()
        if not code:
            continue
        manager = str(r.get("姓名") or "").strip()
        rank = _int(r.get("经理排名"))
        if manager:
            managers.add(manager)
        g = groups.setdefault(
            code,
            {
                "股票代码": code,
                "股票名称": str(r.get("股票名称") or "").strip(),
                "_managers": {},
                "_funds": set(),
                "_ratios": [],
                "_top": [],
                "_quarters": [],
            },
        )
        if not g["股票名称"] and r.get("股票名称"):
            g["股票名称"] = str(r["股票名称"]).strip()
        if manager:
            g["_managers"][manager] = min(rank, g["_managers"].get(manager, rank))
        g["_funds"] |= _funds(r.get("Top3基金列表"))
        g["_ratios"].append(_float(r.get("汇总占净值比例")))
        top = _int(r.get("股票Top"))
        if top > 0:
            g["_top"].append(top)
        quarter = str(r.get("最新季度") or "").strip()
        if quarter:
            g["_quarters"].append(quarter)

    rows: list[dict[str, Any]] = []
    for g in groups.values():
        names = sorted(g["_managers"].items(), key=lambda kv: (kv[1] if kv[1] > 0 else 9999, kv[0]))
        shown = [n for n, _ in names[:3]]
        extra = len(names) - len(shown)
        ratios = g["_ratios"] or [0.0]
        rows.append(
            {
                "股票代码": g["股票代码"],
                "股票名称": g["股票名称"],
                "入选经理数": len(names),
                "出现基金数": len(g["_funds"]),
                "平均占净值比例": round(sum(ratios) / len(ratios), 2),
                "最高名次": min(g["_top"]) if g["_top"] else 0,
                "关联经理": "、".join(shown) + (f" 等 {len(names)} 位" if extra > 0 else ""),
                "最新季度": max(g["_quarters"]) if g["_quarters"] else "",
            }
        )

    rows.sort(
        key=lambda r: (
            -r["入选经理数"],
            -r["出现基金数"],
            -r["平均占净值比例"],
            r["最高名次"] or 9999,
            r["股票代码"],
        )
    )
    for i, r in enumerate(rows, 1):
        r["排名"] = i

    return {
        "rows": rows,
        "manager_count": len(managers),
        "stock_count": len(rows),
        "record_count": len(records),
    }
