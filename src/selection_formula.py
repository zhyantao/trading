#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选基 / 选股的形式化评分与全局选样（单一口径来源）。

旧口径：每位绩优经理各自取 Top3 基金 / Top10 股票 → 20 位经理得到
        37 条基金、200 条股票，「绩优标的」实际是 20 份榜单的拼接。
新口径：先把所有经理的候选并入统一候选池，按下面的综合得分排序，
        全站只选 3 只基金 / 10 只股票；候选人池仍完整保留，
        供「股票排名」与「优化持仓」使用。

    S_f = α·ñ(z(R_a)) + β·ñ(z(R_1)) + γ·ñ(ln(1+C_f))
          + δ·ñ(Q_f) + ε·ñ(ln(1+D_f)) − λ·1[R_1<0 或 R_<0]

    S_s = a·ñ(ln(1+M_s)) + b·ñ(ln(1+F_s)) + c·ñ(ln(1+P_s))
          + d·(1−ñ(T_s)) + e·ñ(Q_s)

其中 ñ(·) 为缩尾后的 min-max 归一化，z(·) 为中位数/IQR 稳健标准化，
C_f 为推荐该基金的经理数，M_s/F_s 为重仓该股票的经理数/基金数，
P_s 为平均占净值比例，T_s 为最好名次，Q 为经理质量 1/rank 的均值。
页面展示的「综合得分」为 100·S（满分 100）。

静态站生成器、动态站路由、流水线与「公式」页面共用本模块的常量，
保证文档里的公式与线上实际计算完全一致。
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from factor_scoring import minmax, robust_zscore, winsorize

# ── 形式化参数（公式页面与 README 直接引用） ──────────────────

FUND_WEIGHTS: dict[str, float] = {
    "annualized": 0.32,       # α 成立来年化
    "recent_1y": 0.13,        # β 近1年
    "consensus": 0.25,        # γ 跨经理共识
    "manager_quality": 0.20,  # δ 经理质量
    "longevity": 0.10,        # ε 成立时长
}
FUND_NEGATIVE_PENALTY = 0.15  # λ 负收益惩罚

STOCK_WEIGHTS: dict[str, float] = {
    "managers": 0.34,         # a 入选经理数
    "funds": 0.18,            # b 出现基金数
    "holding_ratio": 0.18,    # c 平均占净值比例
    "best_rank": 0.12,        # d 最好名次（越小越好）
    "manager_quality": 0.18,  # e 经理质量
}

TOP_FUNDS = 3
TOP_STOCKS = 10
SHRINKAGE_K = 1.5  # 与 factor_scoring 的稳定性先验一致


def formula_parameters() -> dict[str, Any]:
    """返回公式页面需要的全部参数（权重、TopK、经理筛选阈值）。"""
    from factor_scoring import (
        DEFAULT_FUND_FACTOR_WEIGHTS,
        DEFAULT_MANAGER_FACTOR_WEIGHTS,
        FUND_RETURN_PERIODS,
    )

    return {
        "fund_weights": FUND_WEIGHTS,
        "fund_penalty": FUND_NEGATIVE_PENALTY,
        "stock_weights": STOCK_WEIGHTS,
        "top_funds": TOP_FUNDS,
        "top_stocks": TOP_STOCKS,
        "fund_factor_weights": DEFAULT_FUND_FACTOR_WEIGHTS,
        "manager_factor_weights": DEFAULT_MANAGER_FACTOR_WEIGHTS,
        "return_periods": FUND_RETURN_PERIODS,
        "risk_parity": True,
    }


# ── 数值工具 ──────────────────────────────────────────────

def _num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(str(v).strip())
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _fund_codes(v: Any) -> set[str]:
    return {x.strip() for x in _text(v).replace("，", ",").split(",") if x.strip()}


def _share_base(name: str) -> str:
    """去掉 A/B/C 份额后缀，避免同一只基金的不同份额重复占位。"""
    name = name.strip()
    if re.search(r"[A-Z]{2,}$", name):
        return name
    m = re.match(r"^(.+?)(?:类)?[A-Z]$", name)
    return m.group(1) if m else name


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _norm(values: list[float], log: bool = False, invert: bool = False) -> list[float]:
    """缩尾 + min-max 归一化；可选对数压缩与反转。"""
    s = pd.Series([math.log1p(max(0.0, v)) for v in values] if log else values, dtype="float64")
    out = minmax(winsorize(s))
    if invert:
        out = 1 - out
    return [float(v) for v in out]


def _z_norm(values: list[float]) -> list[float]:
    """稳健 z-score 后再 min-max 到 [0,1]。"""
    s = pd.Series(values, dtype="float64")
    return [float(v) for v in minmax(robust_zscore(s))]


# ── 全局选基 ──────────────────────────────────────────────

def score_fund_candidates(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """对候选池里的每只基金计算 S_f，按得分降序返回全部候选（含排名）。"""
    groups: dict[str, dict[str, Any]] = {}
    for r in records or []:
        if not isinstance(r, dict):
            continue
        code = _text(r.get("基金代码")).zfill(6)
        if not code or code == "000000":
            continue
        rank = _int(r.get("经理排名"), 9999)
        g = groups.setdefault(code, {
            "基金代码": code,
            "基金简称": _text(r.get("基金简称")),
            "_managers": {},
            "_annual": [], "_r1": [], "_total": [], "_days": [],
            "_negative": False,
        })
        if not g["基金简称"]:
            g["基金简称"] = _text(r.get("基金简称"))
        key = rank if rank > 0 else 9999
        if key not in g["_managers"]:
            g["_managers"][key] = {
                "姓名": _text(r.get("姓名")),
                "所属公司": _text(r.get("所属公司")),
            }
        g["_annual"].append(_num(r.get("成立来年化")))
        g["_r1"].append(_num(r.get("近1年")))
        g["_total"].append(_num(r.get("成立来")))
        g["_days"].append(max(0.0, _num(r.get("成立天数"))))
        if _num(r.get("近1年")) < 0 or _num(r.get("成立来")) < 0:
            g["_negative"] = True

    if not groups:
        return []

    gs = list(groups.values())
    metrics = {
        "annual": [_mean(g["_annual"]) for g in gs],
        "r1": [_mean(g["_r1"]) for g in gs],
        "total": [_mean(g["_total"]) for g in gs],
        "days": [_mean(g["_days"]) for g in gs],
        "consensus": [len(g["_managers"]) for g in gs],
        "quality": [_mean([1.0 / k for k in g["_managers"] if k < 9999]) for g in gs],
        "negative": [1.0 if g["_negative"] else 0.0 for g in gs],
    }
    z_annual = _z_norm(metrics["annual"])
    z_r1 = _z_norm(metrics["r1"])
    n_cons = _norm(metrics["consensus"], log=True)
    n_qual = _norm(metrics["quality"])
    n_days = _norm(metrics["days"], log=True)

    rows: list[dict[str, Any]] = []
    for i, g in enumerate(gs):
        s = (
            FUND_WEIGHTS["annualized"] * z_annual[i]
            + FUND_WEIGHTS["recent_1y"] * z_r1[i]
            + FUND_WEIGHTS["consensus"] * n_cons[i]
            + FUND_WEIGHTS["manager_quality"] * n_qual[i]
            + FUND_WEIGHTS["longevity"] * n_days[i]
            - FUND_NEGATIVE_PENALTY * metrics["negative"][i]
        )
        best_rank = min(g["_managers"]) if g["_managers"] else 9999
        mgr = g["_managers"].get(best_rank, {})
        rows.append({
            "基金代码": g["基金代码"],
            "基金简称": g["基金简称"],
            "经理排名": "" if best_rank >= 9999 else best_rank,
            "姓名": mgr.get("姓名", ""),
            "所属公司": mgr.get("所属公司", ""),
            "入选经理数": len(g["_managers"]),
            "经理质量分": round(metrics["quality"][i] * 100, 2),
            "成立来年化": round(metrics["annual"][i], 4),
            "成立来": round(metrics["total"][i], 4),
            "近1年": round(metrics["r1"][i], 4),
            "成立天数": round(metrics["days"][i], 0),
            "共识分": round(n_cons[i] * 100, 2),
            "年化分": round(z_annual[i] * 100, 2),
            "综合得分": round(max(0.0, min(1.0, s)) * 100, 2),
        })

    rows.sort(key=lambda r: (-r["综合得分"], -r["入选经理数"], -r["成立来年化"], r["基金代码"]))
    for i, r in enumerate(rows, 1):
        r["基金排名"] = i
    return rows


def select_global_funds(records: list[dict[str, Any]] | None, top_k: int = TOP_FUNDS) -> list[dict[str, Any]]:
    """全局选基：所有经理候选中按 S_f 取前 top_k，同一基金不同份额只留一只。"""
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in score_fund_candidates(records):
        base = _share_base(str(r["基金简称"]))
        key = base or str(r["基金代码"])
        if key in seen:
            continue
        seen.add(key)
        picked.append(r)
        if len(picked) >= top_k:
            break
    for i, r in enumerate(picked, 1):
        r["基金排名"] = i
    return picked


# ── 全局选股 / 股票排名 ─────────────────────────────────────

def score_stock_candidates(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """对候选池里的每只股票计算 S_s，按得分降序返回全部候选（含排名）。"""
    groups: dict[str, dict[str, Any]] = {}
    managers_all: set[str] = set()
    valid = 0

    for r in records or []:
        if not isinstance(r, dict):
            continue
        valid += 1
        code = _text(r.get("股票代码"))
        if not code:
            continue
        rank = _int(r.get("经理排名"), 9999)
        name = _text(r.get("姓名"))
        if name:
            managers_all.add(name)
        g = groups.setdefault(code, {
            "股票代码": code,
            "股票名称": _text(r.get("股票名称")),
            "_managers": {},
            "_funds": set(),
            "_ratios": [],
            "_tops": [],
            "_quarters": [],
        })
        if not g["股票名称"]:
            g["股票名称"] = _text(r.get("股票名称"))
        key = rank if rank > 0 else 9999
        m = g["_managers"].setdefault(key, name or f"经理{key}")
        if not m and name:
            g["_managers"][key] = name
        g["_funds"] |= _fund_codes(r.get("Top3基金列表"))
        ratio = _num(r.get("汇总占净值比例"))
        if ratio > 0:
            g["_ratios"].append(ratio)
        top = _int(r.get("股票Top"), 0)
        if top > 0:
            g["_tops"].append(top)
        quarter = _text(r.get("最新季度"))
        if quarter:
            g["_quarters"].append(quarter)

    if not groups:
        return []

    gs = list(groups.values())
    metrics = {
        "managers": [len(g["_managers"]) for g in gs],
        "funds": [len(g["_funds"]) for g in gs],
        "ratio": [_mean(g["_ratios"]) for g in gs],
        "top": [min(g["_tops"]) if g["_tops"] else TOP_STOCKS + 1 for g in gs],
        "quality": [_mean([1.0 / k for k in g["_managers"] if k < 9999]) for g in gs],
    }
    n_mgr = _norm(metrics["managers"], log=True)
    n_fund = _norm(metrics["funds"], log=True)
    n_ratio = _norm(metrics["ratio"], log=True)
    n_top = _norm(metrics["top"], invert=True)
    n_qual = _norm(metrics["quality"])

    rows: list[dict[str, Any]] = []
    for i, g in enumerate(gs):
        s = (
            STOCK_WEIGHTS["managers"] * n_mgr[i]
            + STOCK_WEIGHTS["funds"] * n_fund[i]
            + STOCK_WEIGHTS["holding_ratio"] * n_ratio[i]
            + STOCK_WEIGHTS["best_rank"] * n_top[i]
            + STOCK_WEIGHTS["manager_quality"] * n_qual[i]
        )
        names = sorted(g["_managers"].items(), key=lambda kv: (kv[0], kv[1]))
        shown = [n for _, n in names[:3]]
        extra = len(names) - len(shown)
        rows.append({
            "股票代码": g["股票代码"],
            "股票名称": g["股票名称"],
            "入选经理数": len(names),
            "出现基金数": len(g["_funds"]),
            "平均占净值比例": round(metrics["ratio"][i], 2),
            "最高名次": min(g["_tops"]) if g["_tops"] else 0,
            "关联经理": "、".join(shown) + (f" 等 {len(names)} 位" if extra > 0 else ""),
            "最新季度": max(g["_quarters"]) if g["_quarters"] else "",
            "共识分": round(n_mgr[i] * 100, 2),
            "覆盖分": round(n_fund[i] * 100, 2),
            "仓位分": round(n_ratio[i] * 100, 2),
            "综合得分": round(max(0.0, min(1.0, s)) * 100, 2),
        })

    rows.sort(key=lambda r: (
        -r["综合得分"], -r["入选经理数"], -r["出现基金数"],
        -r["平均占净值比例"], r["最高名次"] or 9999, r["股票代码"],
    ))
    for i, r in enumerate(rows, 1):
        r["排名"] = i
    return rows


def select_global_stocks(records: list[dict[str, Any]] | None, top_k: int = TOP_STOCKS) -> list[dict[str, Any]]:
    """全局选股：所有经理候选中按 S_s 取前 top_k。"""
    return score_stock_candidates(records)[:top_k]


def ranking_meta(records: list[dict[str, Any]] | None) -> dict[str, int]:
    """股票排名页需要的统计口径。"""
    managers = {
        _text(r.get("姓名"))
        for r in (records or [])
        if isinstance(r, dict) and _text(r.get("姓名"))
    }
    return {
        "manager_count": len(managers),
        "record_count": len([r for r in (records or []) if isinstance(r, dict)]),
    }


# ── CLI：用本地候选池检查选样结果 ────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    out = Path(__file__).resolve().parent.parent / "out"
    f_funds = sorted(out.glob("绩优基金经理_基金Top3_*.csv"))
    f_stocks = sorted(out.glob("绩优基金经理_股票Top10_*.csv"))

    if f_funds:
        recs = pd.read_csv(f_funds[-1], dtype={"基金代码": str}).to_dict("records")
        print(f"基金候选 {len(recs)} 条 → 全局 Top{TOP_FUNDS}:")
        for r in select_global_funds(recs):
            print(f"  {r['基金排名']}. {r['基金代码']} {r['基金简称']} 得分={r['综合得分']}")
    if f_stocks:
        recs = pd.read_csv(f_stocks[-1], dtype={"股票代码": str}).to_dict("records")
        print(f"\n股票候选 {len(recs)} 条 → 全局 Top{TOP_STOCKS}:")
        for r in select_global_stocks(recs):
            print(f"  {r['排名']}. {r['股票代码']} {r['股票名称']} 得分={r['综合得分']} "
                  f"经理={r['入选经理数']} 基金={r['出现基金数']}")
