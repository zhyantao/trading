#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经济周期检测模块 —— 基于《经济机器是怎么运行的》框架。

Dalio 的三大驱动力：
  1. 生产率增长（长期趋势）—— 决定长期回报中枢
  2. 短期债务周期（5-8 年）—— 信贷扩张/收缩驱动商业周期
  3. 长期债务周期（50-75 年）—— 债务/GDP 达到极限后去杠杆

四个周期阶段及对应的因子权重调整：
  扩张期 → 重回报、轻风险
  过热期 → 重质量、轻动量
  收缩期 → 重稳定、重风险
  去杠杆期 → 重质量、重风险、轻回报

当前版本使用市场代理指标（指数趋势、波动率）推断周期阶段，
后续可扩展接入宏观数据（利率、CPI、信用利差）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class CyclePhase(Enum):
    """经济周期阶段。"""
    EARLY_EXPANSION = "early_expansion"    # 早期扩张
    LATE_EXPANSION = "late_expansion"      # 后期扩张
    OVERHEATING = "overheating"            # 过热
    CONTRACTION = "contraction"            # 收缩
    DELEVERAGING = "deleveraging"          # 去杠杆
    UNKNOWN = "unknown"                    # 无法判断


# 不同周期阶段的因子权重调整
# 格式：{factor_name: weight_adjustment_multiplier}
CYCLE_FACTOR_WEIGHTS: dict[CyclePhase, dict[str, float]] = {
    CyclePhase.EARLY_EXPANSION: {
        # 早期扩张：增长恢复、利率低 → 重回报、轻风险
        "return": 0.40,
        "risk": 0.15,
        "stability": 0.20,
        "quality": 0.25,
    },
    CyclePhase.LATE_EXPANSION: {
        # 后期扩张：增长强劲、通胀抬头 → 均衡配置
        "return": 0.30,
        "risk": 0.25,
        "stability": 0.20,
        "quality": 0.25,
    },
    CyclePhase.OVERHEATING: {
        # 过热：高通胀、政策收紧 → 重质量、轻动量
        "return": 0.20,
        "risk": 0.30,
        "stability": 0.20,
        "quality": 0.30,
    },
    CyclePhase.CONTRACTION: {
        # 收缩：增长放缓、信用收紧 → 重稳定、重风险
        "return": 0.15,
        "risk": 0.35,
        "stability": 0.30,
        "quality": 0.20,
    },
    CyclePhase.DELEVERAGING: {
        # 去杠杆：债务危机 → 极度防御
        "return": 0.10,
        "risk": 0.35,
        "stability": 0.25,
        "quality": 0.30,
    },
    CyclePhase.UNKNOWN: {
        # 无法判断时使用默认均衡权重
        "return": 0.35,
        "risk": 0.25,
        "stability": 0.20,
        "quality": 0.20,
    },
}


@dataclass
class CycleAssessment:
    """周期评估结果。"""
    phase: CyclePhase
    confidence: float          # 0-1，判断置信度
    description: str           # 中文描述
    adjusted_weights: dict[str, float]  # 调整后的因子权重


def _fetch_benchmark_prices(
    symbol: str = "sh000300",
    lookback_days: int = 504,  # ~2 年交易日
) -> Optional[pd.DataFrame]:
    """获取基准指数日线数据。"""
    try:
        import akshare as ak
        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=lookback_days + 30)).strftime("%Y%m%d")
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df = df[df["date"] >= pd.Timestamp(start)].copy()
        return df
    except Exception:
        return None


def detect_cycle_phase(
    benchmark_symbol: str = "sh000300",
    lookback_short: int = 63,   # ~3 个月
    lookback_mid: int = 126,    # ~6 个月
    lookback_long: int = 252,   # ~1 年
) -> CycleAssessment:
    """
    基于市场代理指标检测当前经济周期阶段。

    判断逻辑（Dalio 简化框架）：
      1. 长期趋势：价格 vs 252日均线 → 扩张 or 收缩
      2. 短期动量：近3月 vs 近6月收益 → 加速 or 减速
      3. 波动率：近期波动率水平 → 压力程度
      4. 回撤：从高点回撤幅度 → 是否进入去杠杆
    """
    df = _fetch_benchmark_prices(benchmark_symbol)
    if df is None or df.empty:
        return CycleAssessment(
            phase=CyclePhase.UNKNOWN,
            confidence=0.0,
            description="无法获取基准指数数据，使用默认均衡权重",
            adjusted_weights=CYCLE_FACTOR_WEIGHTS[CyclePhase.UNKNOWN],
        )

    close = df["close"]
    if len(close) < lookback_long:
        return CycleAssessment(
            phase=CyclePhase.UNKNOWN,
            confidence=0.1,
            description=f"数据不足（{len(close)} 天 < {lookback_long}），使用默认权重",
            adjusted_weights=CYCLE_FACTOR_WEIGHTS[CyclePhase.UNKNOWN],
        )

    # 1. 长期趋势：价格相对 252 日均线
    ma_long = close.rolling(lookback_long, min_periods=1).mean()
    trend_ratio = close.iloc[-1] / ma_long.iloc[-1] - 1.0  # >0 = 在均线上方

    # 2. 中期动量
    if len(close) >= lookback_mid:
        ret_3m = close.iloc[-1] / close.iloc[-lookback_short] - 1.0
        ret_6m = close.iloc[-1] / close.iloc[-lookback_mid] - 1.0
    else:
        ret_3m, ret_6m = 0.0, 0.0

    # 3. 近期波动率（20 日年化）
    ret_daily = close.pct_change().dropna()
    vol_20d = float(ret_daily.tail(20).std() * np.sqrt(252)) if len(ret_daily) >= 20 else 0.0
    vol_60d = float(ret_daily.tail(60).std() * np.sqrt(252)) if len(ret_daily) >= 60 else vol_20d

    # 4. 从高点回撤
    peak = close.max()
    drawdown = close.iloc[-1] / peak - 1.0

    # ── 判断周期阶段 ──
    phase = CyclePhase.UNKNOWN
    confidence = 0.5
    reasons: list[str] = []

    is_expanding = trend_ratio > -0.03  # 在长期均线附近或上方
    is_accelerating = ret_3m > ret_6m  # 短期动能 > 中期动能
    high_vol = vol_20d > 0.30          # 年化波动 > 30%
    severe_dd = drawdown < -0.30       # 从高点回撤 > 30%

    if is_expanding:
        if is_accelerating and vol_20d < 0.25:
            phase = CyclePhase.EARLY_EXPANSION
            confidence = 0.7
            reasons = ["指数在长期均线上方", "短期动能强于中期", "波动率适中"]
        elif vol_20d > 0.30 or ret_3m > 0.30:
            phase = CyclePhase.OVERHEATING
            confidence = 0.6
            reasons = ["指数在高位", "波动率或短期涨幅偏高", "存在过热风险"]
        else:
            phase = CyclePhase.LATE_EXPANSION
            confidence = 0.6
            reasons = ["指数在长期均线上方", "动能趋稳"]
    else:
        if severe_dd or (high_vol and trend_ratio < -0.10):
            phase = CyclePhase.DELEVERAGING
            confidence = 0.7
            reasons = ["从高点大幅回撤", "波动率上升", "可能进入去杠杆阶段"]
        else:
            phase = CyclePhase.CONTRACTION
            confidence = 0.65
            reasons = ["指数在长期均线下方", "处于收缩阶段"]

    # 构建描述
    desc = (
        f"趋势={trend_ratio*100:.1f}% "
        f"3月收益={ret_3m*100:.1f}% "
        f"6月收益={ret_6m*100:.1f}% "
        f"20日波动率={vol_20d*100:.1f}% "
        f"回撤={drawdown*100:.1f}% → "
        f"{phase.value}（置信度 {confidence:.0%}）"
    )
    if reasons:
        desc += f"：{'、'.join(reasons)}"

    return CycleAssessment(
        phase=phase,
        confidence=confidence,
        description=desc,
        adjusted_weights=CYCLE_FACTOR_WEIGHTS[phase],
    )


def get_cycle_adjusted_weights(
    benchmark_symbol: str = "sh000300",
) -> dict[str, float]:
    """便捷函数：获取当前周期调整后的因子权重。"""
    return detect_cycle_phase(benchmark_symbol).adjusted_weights


# ── CLI 调试入口 ──────────────────────────────────────────

if __name__ == "__main__":
    assessment = detect_cycle_phase()
    print(f"当前周期阶段: {assessment.phase.value}")
    print(f"置信度: {assessment.confidence:.0%}")
    print(f"描述: {assessment.description}")
    print(f"调整后因子权重: {assessment.adjusted_weights}")
