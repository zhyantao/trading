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


def _robust_zscore(series: pd.Series) -> pd.Series:
    """用中位数和 IQR 做稳健标准化（避免极端值扭曲）。"""
    med = series.median()
    iqr = series.quantile(0.75) - series.quantile(0.25)
    if iqr == 0:
        iqr = series.std()
    if iqr == 0:
        return pd.Series(0.0, index=series.index)
    return (series - med) / iqr


def _minmax(series: pd.Series) -> pd.Series:
    """Min-Max 归一化到 [0, 1]。"""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.5, index=series.index)
    return (series - lo) / (hi - lo)


# ── 基金综合评分 ──────────────────────────────────────────

def compute_fund_return_score(df: pd.DataFrame) -> pd.Series:
    """多周期回报得分：加权各周期的稳健 z-score。"""
    score = pd.Series(0.0, index=df.index)
    for col, w in FUND_RETURN_PERIODS.items():
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        score += _robust_zscore(vals).fillna(0.0) * w
    return _minmax(score)


def compute_fund_risk_score(df: pd.DataFrame) -> pd.Series:
    """
    风险调整得分（越高 = 风险越低）。
    用多周期回报的离散度作为波动率代理，加入最大回撤惩罚（若有历史数据）。
    """
    period_cols = [c for c in FUND_RETURN_PERIODS if c in df.columns]
    if not period_cols:
        return pd.Series(0.5, index=df.index)

    period_data = df[period_cols].apply(pd.to_numeric, errors="coerce")
    # 跨周期标准差 → 波动率代理
    dispersion = period_data.std(axis=1, skipna=True)
    # 负收益周期数 → 下行风险代理
    neg_count = (period_data < 0).sum(axis=1)

    risk_raw = dispersion.fillna(0) + neg_count.fillna(0) * 0.5
    # 得分反转：风险越低分越高
    score = -_robust_zscore(risk_raw)
    return _minmax(score)


def compute_fund_stability_score(df: pd.DataFrame) -> pd.Series:
    """
    稳定性得分：多周期正收益占比 + 收益一致性。
    Dalio：生产力增长是平稳的，暴涨暴跌说明杠杆/投机成分重。
    """
    period_cols = [c for c in FUND_RETURN_PERIODS if c in df.columns]
    if not period_cols:
        return pd.Series(0.5, index=df.index)

    period_data = df[period_cols].apply(pd.to_numeric, errors="coerce")
    # 正收益周期占比
    pos_ratio = (period_data > 0).sum(axis=1) / period_data.notna().sum(axis=1)
    # 收益一致性：各周期排名的标准差（越小说明各周期表现越一致）
    ranks = period_data.rank(axis=0, pct=True)
    rank_std = ranks.std(axis=1, skipna=True)

    score = pos_ratio.fillna(0) * 0.6 + (1 - _minmax(rank_std.fillna(0.5))) * 0.4
    return _minmax(score)


def compute_fund_quality_score(df: pd.DataFrame) -> pd.Series:
    """
    质量得分：成立时长 + 低费率 + 规模适中。
    Dalio：长期存活本身就是竞争力的证明。
    """
    score = pd.Series(0.0, index=df.index)

    # 成立天数（越长越好）
    if "成立天数" in df.columns:
        days = pd.to_numeric(df["成立天数"], errors="coerce").fillna(180)
        score += _minmax(np.log1p(days)) * 0.5
    elif "成立日" in df.columns:
        days = (pd.Timestamp.today() - pd.to_datetime(df["成立日"], errors="coerce")).dt.days
        score += _minmax(np.log1p(days.fillna(180))) * 0.5

    # 手续费（越低越好）
    fee_col = None
    for c in ["手续费", "费率"]:
        if c in df.columns:
            fee_col = c
            break
    if fee_col:
        fee = pd.to_numeric(df[fee_col].astype(str).str.replace("%", "", regex=False), errors="coerce")
        fee = fee.fillna(fee.median() if fee.notna().any() else 0.15)
        score += (1 - _minmax(fee)) * 0.5

    return _minmax(score)


def compute_fund_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """
    基金综合评分（0-1，越高越好）。
    可传入自定义因子权重以适应不同经济周期阶段。
    """
    w = weights or DEFAULT_FUND_FACTOR_WEIGHTS
    total = 0.0
    score = pd.Series(0.0, index=df.index)

    if w.get("return", 0) > 0:
        score += compute_fund_return_score(df) * w["return"]
        total += w["return"]
    if w.get("risk", 0) > 0:
        score += compute_fund_risk_score(df) * w["risk"]
        total += w["risk"]
    if w.get("stability", 0) > 0:
        score += compute_fund_stability_score(df) * w["stability"]
        total += w["stability"]
    if w.get("quality", 0) > 0:
        score += compute_fund_quality_score(df) * w["quality"]
        total += w["quality"]

    if total > 0:
        score = score / total
    return _minmax(score)


# ── 经理综合评分 ──────────────────────────────────────────

def compute_manager_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """
    基金经理综合评分（0-1，越高越好）。
    使用的列：平均收益率、中位数收益率、最佳收益率、最差收益率、
              有效基金数、管理基金数、累计从业时间。
    """
    w = weights or DEFAULT_MANAGER_FACTOR_WEIGHTS
    score = pd.Series(0.0, index=df.index)

    # 回报因子：平均 + 中位数（稳健）+ 最佳
    if w.get("return", 0) > 0:
        ret_score = pd.Series(0.0, index=df.index)
        for col, rw in [("平均收益率", 0.4), ("中位数收益率", 0.3), ("最佳收益率", 0.3)]:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                ret_score += _robust_zscore(vals).fillna(0.0) * rw
        score += _minmax(ret_score) * w["return"]

    # 一致性因子：最差收益不要太差 + 中位/最佳比值
    if w.get("consistency", 0) > 0:
        cons_score = pd.Series(0.0, index=df.index)
        if "最差收益率" in df.columns:
            worst = pd.to_numeric(df["最差收益率"], errors="coerce")
            # 最差收益越接近 0 或正值越好
            cons_score += _minmax(worst.fillna(worst.min())) * 0.4
        if "中位数收益率" in df.columns and "最佳收益率" in df.columns:
            med = pd.to_numeric(df["中位数收益率"], errors="coerce")
            best = pd.to_numeric(df["最佳收益率"], errors="coerce")
            ratio = med / best.abs().replace(0, np.nan)
            cons_score += _minmax(ratio.fillna(0.5)) * 0.6
        score += _minmax(cons_score) * w["consistency"]

    # 经验因子：从业年限 + 管理规模
    if w.get("experience", 0) > 0:
        exp_score = pd.Series(0.0, index=df.index)
        if "累计从业时间" in df.columns:
            # 格式可能是 "5年200天" 或纯数字
            career = df["累计从业时间"].astype(str).str.extract(r"(\d+)").iloc[:, 0]
            career = pd.to_numeric(career, errors="coerce")
            exp_score += _minmax(np.log1p(career.fillna(1))) * 0.6
        if "现任基金资产总规模" in df.columns:
            scale = pd.to_numeric(df["现任基金资产总规模"], errors="coerce")
            exp_score += _minmax(np.log1p(scale.fillna(1))) * 0.4
        score += _minmax(exp_score) * w["experience"]

    # 质量因子：有效基金占比 + 管理广度
    if w.get("quality", 0) > 0:
        qual_score = pd.Series(0.0, index=df.index)
        if "有效基金数" in df.columns and "管理基金数" in df.columns:
            eff = pd.to_numeric(df["有效基金数"], errors="coerce")
            total_m = pd.to_numeric(df["管理基金数"], errors="coerce")
            ratio = eff / total_m.replace(0, np.nan)
            qual_score += _minmax(ratio.fillna(0.5)) * 0.5
        if "管理基金数" in df.columns:
            mgr_cnt = pd.to_numeric(df["管理基金数"], errors="coerce")
            # 管理 3-10 只最优，过多则精力分散
            ideal = 1.0 - np.abs(np.log1p(mgr_cnt.fillna(3)) - np.log1p(5))
            qual_score += _minmax(pd.Series(ideal, index=df.index)) * 0.5
        score += _minmax(qual_score) * w["quality"]

    return _minmax(score)


# ── CLI 调试入口 ──────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    out_dir = root / "out"

    # 读取最新基金排名数据测试因子评分
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
        top10 = df_fund.nlargest(10, "composite")
        for _, r in top10.iterrows():
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
        top10 = df_mgr.nlargest(10, "composite")
        for _, r in top10.iterrows():
            print(f"  {r.get('姓名','')}({r.get('所属公司','')}) 复合={r['composite']:.4f}")
    else:
        print("未找到经理排行数据，跳过经理因子测试")
