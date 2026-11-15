#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多因子评分引擎 —— 基于《经济机器是怎么运行的》原理。

Dalio 框架映射：
  - 生产力驱动长期增长 → 多周期回报因子（重视长期一致性）
  - 债务周期波动 → 风险调整因子（惩罚高波动/大回撤）
  - 效率提升 → 稳定性因子（回报的平稳性）
  - 优胜劣汰 → 质量因子（成立时长、费率、经验）

因子权重（可通过 economic_cycle.py 按周期阶段动态调整）：
  长期回报 35% / 风险调整 25% / 稳定性 20% / 质量 20%

数值稳健性约定（v2 优化）：
  1. 所有输入先做有限化（inf → NaN）与 1%/99% 缩尾，避免单个极端值
     把 min-max 压成一条「所有样本都得 0」的退化分布；
  2. 缺失值一律按「中性」处理（z-score 记 0、min-max 记中位数），
     不再隐式当成 0 分而惩罚数据不全的标的；
  3. 多周期合成按「每行实际可用周期的权重和」归一，
     不同标的可用周期数不同时仍可公平比较；
  4. 不同周期的收益量纲不同（近1月 vs 成立来年化），风险/稳定性因子
     先逐列标准化再计算横向离散度，不再直接对原始百分数求标准差。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── 基金因子 ──────────────────────────────────────────────

# 多周期回报列及其在回报因子中的权重（越长期权重越高）
FUND_RETURN_PERIODS: dict[str, float] = {
    "近1月": 0.05,
    "近3月": 0.10,
    "近6月": 0.10,
    "近1年": 0.20,
    "近2年": 0.20,
    "近3年": 0.20,
    "成立来年化": 0.15,
}

# 默认因子权重（总计 1.0）
DEFAULT_FUND_FACTOR_WEIGHTS: dict[str, float] = {
    "return": 0.35,
    "risk": 0.25,
    "stability": 0.20,
    "quality": 0.20,
}

DEFAULT_MANAGER_FACTOR_WEIGHTS: dict[str, float] = {
    "return": 0.35,
    "consistency": 0.25,
    "experience": 0.20,
    "quality": 0.20,
}


# ── 稳健数值工具 ──────────────────────────────────────────

def finite_series(values: pd.Series) -> pd.Series:
    """转数值并把 ±inf 变成 NaN。"""
    return pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan)


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """1%/99% 缩尾，样本太少时原样返回。"""
    s = finite_series(series)
    if s.notna().sum() < 5:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return s
    return s.clip(lo, hi)


def _robust_zscore(series: pd.Series) -> pd.Series:
    """缩尾后用中位数和 IQR 做稳健标准化；缺失取 0（中性），并裁到 ±3。"""
    s = winsorize(series)
    med = s.median()
    iqr = s.quantile(0.75) - s.quantile(0.25)
    scale = iqr
    if not np.isfinite(scale) or scale <= 0:
        scale = s.std()
    if not np.isfinite(scale) or scale <= 0:
        return pd.Series(0.0, index=s.index)
    return ((s - med) / scale).clip(-3.0, 3.0).fillna(0.0)


def _neutral_minmax(series: pd.Series) -> pd.Series:
    """Min-Max 归一化到 [0, 1]，缺失值用中位数补齐（中性），常量序列记 0.5。"""
    s = finite_series(series)
    fill = s.median() if s.notna().any() and np.isfinite(s.median()) else 0.0
    s = s.fillna(fill)
    lo, hi = s.min(), s.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def _minmax(series: pd.Series) -> pd.Series:
    """兼容旧调用名的公开别名。"""
    return _neutral_minmax(series)


# 对外公开的函数名（供 selection_formula.py 复用，避免私有名跨模块）
robust_zscore = _robust_zscore
minmax = _neutral_minmax


def _weighted_period_zscore(df: pd.DataFrame, periods: dict[str, float]) -> pd.Series:
    """多周期稳健 z-score 加权平均；按每行实际可用周期的权重和归一。"""
    score = pd.Series(0.0, index=df.index)
    weight = pd.Series(0.0, index=df.index)
    for col, w in periods.items():
        if col not in df.columns:
            continue
        vals = finite_series(df[col])
        score += _robust_zscore(vals) * w
        weight += vals.notna().astype(float) * w
    weight = weight.replace(0.0, np.nan)
    return (score / weight).fillna(0.0)


def _standardized_period_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """逐列标准化后的周期收益矩阵（消除不同周期的量纲差异）。"""
    cols = [c for c in FUND_RETURN_PERIODS if c in df.columns]
    if not cols:
        return pd.DataFrame(index=df.index)
    return pd.DataFrame({c: _robust_zscore(df[c]) for c in cols}, index=df.index)


# ── 基金综合评分 ──────────────────────────────────────────

def compute_fund_return_score(df: pd.DataFrame) -> pd.Series:
    """多周期回报得分：加权各周期的稳健 z-score，按可用周期权重归一。"""
    return _neutral_minmax(_weighted_period_zscore(df, FUND_RETURN_PERIODS))


def compute_fund_risk_score(df: pd.DataFrame) -> pd.Series:
    """
    风险调整得分（越高 = 风险越低）。

    v2：先对每个周期列单独标准化，再计算「跨周期离散度」与「负收益周期占比」；
    旧版直接把近1月、近1年、成立来年化混在一起求 std，量纲不一致，
    会把长期年化高的基金系统性判成高风险。
    """
    mat = _standardized_period_matrix(df)
    if mat.empty:
        return pd.Series(0.5, index=df.index)

    dispersion = mat.std(axis=1, skipna=True).fillna(0.0)
    neg_ratio = (mat < 0).sum(axis=1) / mat.notna().sum(axis=1).replace(0, np.nan)
    neg_ratio = neg_ratio.fillna(0.0)

    risk_raw = dispersion + neg_ratio * 0.5
    # 若带历史最大回撤数据，额外惩罚（回撤通常为负数，取绝对值）
    if "最大回撤" in df.columns:
        dd = finite_series(df["最大回撤"]).abs().fillna(0.0)
        risk_raw += _neutral_minmax(dd) * 0.5

    return _neutral_minmax(-_robust_zscore(risk_raw))


def compute_fund_stability_score(df: pd.DataFrame) -> pd.Series:
    """
    稳定性得分：多周期正收益占比（贝叶斯收缩）+ 跨周期表现一致性。

    v2：样本少的基金不再因为 1 个周期恰好为正就拿到满分；
    一致性改用标准化后周期得分的离散度。
    """
    mat = _standardized_period_matrix(df)
    if mat.empty:
        return pd.Series(0.5, index=df.index)

    n = mat.notna().sum(axis=1)
    pos = (mat > 0).sum(axis=1)
    prior = 1.5  # 伪样本：先验收益为正的概率 0.5
    pos_ratio = (pos + prior * 0.5) / (n + prior).replace(0, np.nan)
    rank_std = mat.std(axis=1, skipna=True).fillna(0.5)

    score = pos_ratio.fillna(0.5) * 0.6 + (1 - _neutral_minmax(rank_std)) * 0.4
    return _neutral_minmax(score)


def compute_fund_quality_score(df: pd.DataFrame) -> pd.Series:
    """质量得分：成立时长 + 低费率（缺失费率时自动把时长权重补齐到 1）。"""
    parts: list[pd.Series] = []

    if "成立天数" in df.columns:
        days = finite_series(df["成立天数"]).fillna(180)
        parts.append(_neutral_minmax(np.log1p(days.clip(lower=0))))
    elif "成立日" in df.columns:
        days = (pd.Timestamp.today() - pd.to_datetime(df["成立日"], errors="coerce")).dt.days
        parts.append(_neutral_minmax(np.log1p(days.fillna(180).clip(lower=0))))

    fee_col = next((c for c in ["手续费", "费率"] if c in df.columns), None)
    if fee_col:
        fee = finite_series(df[fee_col].astype(str).str.replace("%", "", regex=False))
        fee = fee.fillna(fee.median() if fee.notna().any() else 0.15)
        parts.append(1 - _neutral_minmax(fee))

    if not parts:
        return pd.Series(0.5, index=df.index)
    return _neutral_minmax(sum(parts) / len(parts))


def compute_fund_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """基金综合评分（0-1，越高越好）；权重可按经济周期阶段调整。"""
    w = weights or DEFAULT_FUND_FACTOR_WEIGHTS
    score = pd.Series(0.0, index=df.index)
    total = 0.0

    builders = {
        "return": compute_fund_return_score,
        "risk": compute_fund_risk_score,
        "stability": compute_fund_stability_score,
        "quality": compute_fund_quality_score,
    }
    for key, fn in builders.items():
        weight = float(w.get(key, 0.0))
        if weight > 0:
            score += fn(df) * weight
            total += weight

    if total > 0:
        score /= total
    return _neutral_minmax(score)


# ── 经理综合评分 ──────────────────────────────────────────

def compute_manager_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """
    基金经理综合评分（0-1，越高越好）。

    v2 修正：
      - 旧版 med/|best| 在 best=0 时产生 inf，会把整列 min-max 压成退化；
        现在分母下限 1.0 且比值裁到 [-2, 2]；
      - 回报因子乘以样本可靠性 n/(n+2)，只管 1 只基金的经理不再靠单只
        极端收益冲到榜首。
    """
    w = weights or DEFAULT_MANAGER_FACTOR_WEIGHTS
    score = pd.Series(0.0, index=df.index)

    if w.get("return", 0) > 0:
        ret_score = pd.Series(0.0, index=df.index)
        for col, rw in [("平均收益率", 0.4), ("中位数收益率", 0.3), ("最佳收益率", 0.3)]:
            if col in df.columns:
                ret_score += _robust_zscore(df[col]) * rw
        n = finite_series(df["有效基金数"]).fillna(1.0).clip(lower=1.0) if "有效基金数" in df.columns \
            else pd.Series(1.0, index=df.index)
        reliability = n / (n + 2.0)          # 1 只→0.33，3 只→0.60，10 只→0.83
        score += _neutral_minmax(ret_score * (0.5 + 0.5 * reliability)) * w["return"]

    if w.get("consistency", 0) > 0:
        cons_score = pd.Series(0.0, index=df.index)
        if "最差收益率" in df.columns:
            worst = finite_series(df["最差收益率"])
            cons_score += _neutral_minmax(worst) * 0.4
        if "中位数收益率" in df.columns and "最佳收益率" in df.columns:
            med = finite_series(df["中位数收益率"])
            best = finite_series(df["最佳收益率"])
            ratio = (med / best.abs().clip(lower=1.0)).replace([np.inf, -np.inf], np.nan).clip(-2.0, 2.0)
            cons_score += _neutral_minmax(ratio) * 0.6
        score += _neutral_minmax(cons_score) * w["consistency"]

    if w.get("experience", 0) > 0:
        exp_score = pd.Series(0.0, index=df.index)
        if "累计从业时间" in df.columns:
            career = df["累计从业时间"].astype(str).str.extract(r"(\d+)").iloc[:, 0]
            exp_score += _neutral_minmax(np.log1p(finite_series(career).fillna(1))) * 0.6
        if "现任基金资产总规模" in df.columns:
            scale = finite_series(df["现任基金资产总规模"]).fillna(1)
            exp_score += _neutral_minmax(np.log1p(scale.clip(lower=0))) * 0.4
        score += _neutral_minmax(exp_score) * w["experience"]

    if w.get("quality", 0) > 0:
        qual_score = pd.Series(0.0, index=df.index)
        if "有效基金数" in df.columns and "管理基金数" in df.columns:
            eff = finite_series(df["有效基金数"])
            total_m = finite_series(df["管理基金数"]).replace(0, np.nan)
            qual_score += _neutral_minmax((eff / total_m).clip(0, 1)) * 0.5
        if "管理基金数" in df.columns:
            cnt = finite_series(df["管理基金数"]).fillna(3).clip(lower=0)
            ideal = 1.0 - np.abs(np.log1p(cnt) - np.log1p(5))
            qual_score += _neutral_minmax(pd.Series(ideal, index=df.index)) * 0.5
        score += _neutral_minmax(qual_score) * w["quality"]

    return _neutral_minmax(score)


# ── CLI 调试入口 ──────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    out_dir = root / "out"

    fund_files = sorted(out_dir.glob("基金_年化排行_*.csv"))
    mgr_files = sorted(out_dir.glob("经理_排行_*.csv"))

    if fund_files:
        df_fund = pd.read_csv(fund_files[-1], dtype={"基金代码": str})
        print("=== 基金因子得分（前10） ===")
        df_fund["return_score"] = compute_fund_return_score(df_fund)
        df_fund["risk_score"] = compute_fund_risk_score(df_fund)
        df_fund["stability_score"] = compute_fund_stability_score(df_fund)
        df_fund["quality_score"] = compute_fund_quality_score(df_fund)
        df_fund["composite"] = compute_fund_composite_score(df_fund)
        for _, r in df_fund.nlargest(10, "composite").iterrows():
            print(
                f"  {r['基金代码']} {r.get('基金简称','')} "
                f"复合={r['composite']:.4f} "
                f"回报={r['return_score']:.3f} 风险={r['risk_score']:.3f} "
                f"稳定={r['stability_score']:.3f} 质量={r['quality_score']:.3f}"
            )
    else:
        print("未找到基金排行数据，跳过基金因子测试")

    if mgr_files:
        df_mgr = pd.read_csv(mgr_files[-1])
        print("\n=== 经理因子得分（前10） ===")
        df_mgr["composite"] = compute_manager_composite_score(df_mgr)
        for _, r in df_mgr.nlargest(10, "composite").iterrows():
            print(f"  {r.get('姓名','')}({r.get('所属公司','')}) 复合={r['composite']:.4f}")
    else:
        print("未找到经理排行数据，跳过经理因子测试")
