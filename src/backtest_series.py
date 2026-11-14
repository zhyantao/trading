#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把回测净值曲线 CSV 转成前端交互图表所需的精简列式 JSON。

静态站（generate_static.py）与本地动态站（webui/routes.py）共用本模块，
保证两边的数据口径完全一致。列式数组比 records 更省体积：
一份 3 年日频曲线约 40~60 KB。

输出字段：
    dates        YYYY-MM-DD
    nav          策略净值（总资产 / 初始本金）
    benchmark    基准净值（基准价格 / 首日基准价格），无基准时为空数组
    cum_return   累计收益率 (%)
    excess       超额收益 (%)
    drawdown     回撤 (%)，负值
    total_asset  总资产（元）
    cash         现金（元）
    position     持仓市值（元）
    holdings     持仓标的数
    yearly       [{year, ret}] 年内首末总资产计算的年度收益 (%)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_series(csv_path: Path, result_id: str, asset_type: str = "fund") -> dict | None:
    """读取单份净值曲线，返回可 JSON 序列化的 dict；文件缺失/无有效行时返回 None。"""
    if not csv_path.is_file():
        return None
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception:
        return None
    if df.empty or "日期" not in df.columns or "总资产" not in df.columns:
        return None

    df = df.sort_values("日期").reset_index(drop=True)
    dates = [str(v)[:10] for v in df["日期"].tolist()]
    if not dates:
        return None

    def values(name: str, scale: float = 1.0, digits: int = 4) -> list[float | None]:
        if name not in df.columns:
            return []
        s = pd.to_numeric(df[name], errors="coerce") * scale
        out: list[float | None] = []
        for v in s:
            out.append(None if pd.isna(v) else round(float(v), digits))
        return out

    assets = values("总资产", digits=2)
    initial_cash = next((v for v in assets if v), 10000.0) or 10000.0
    nav = [None if v is None else round(v / initial_cash, 6) for v in assets]

    # 基准净值：以首个有效价格为 1.0
    benchmark: list[float | None] = []
    if "基准价格" in df.columns:
        prices = values("基准价格", digits=6)
        base = next((v for v in prices if v), None)
        if base:
            benchmark = [None if v is None else round(v / base, 6) for v in prices]

    # 持仓标的数：股票/基金两份脚本列名不同
    holdings_name = "持仓基金数" if "持仓基金数" in df.columns else "持仓股票数"
    holdings = values(holdings_name, digits=0)

    yearly: list[dict] = []
    try:
        eq = pd.DataFrame({"日期": pd.to_datetime(dates), "总资产": pd.to_numeric(df["总资产"], errors="coerce")})
        for year, group in eq.groupby(eq["日期"].dt.year):
            g = group.dropna(subset=["总资产"])
            if len(g) < 2:
                continue
            first, last = float(g["总资产"].iloc[0]), float(g["总资产"].iloc[-1])
            if first > 0:
                yearly.append({"year": int(year), "ret": round((last / first - 1.0) * 100, 2)})
    except Exception:
        yearly = []

    return {
        "id": result_id,
        "type": asset_type,
        "initial_cash": round(float(initial_cash), 2),
        "dates": dates,
        "nav": nav,
        "benchmark": benchmark,
        "cum_return": values("累计收益率", scale=100, digits=3),
        "excess": values("超额收益", scale=100, digits=3),
        "drawdown": values("回撤", scale=100, digits=3),
        "total_asset": assets,
        "cash": values("现金", digits=2),
        "position": values("持仓市值", digits=2),
        "holdings": holdings,
        "yearly": yearly,
        "holdings_label": "持仓基金数" if holdings_name == "持仓基金数" else "持仓股票数",
    }
