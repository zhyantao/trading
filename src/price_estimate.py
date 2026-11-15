#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""估算价格（T+1 外推）与估值信号。

只使用仓库里已有的公开数据，不新增任何联网请求：
  * 基金日净值序列：``out/cache_series/nav_{code}.csv``（旧版
    ``out/cache_prices/nav_{code}_*.csv`` 亦可）；
  * 股票前复权收盘价序列：``out/cache_series/{code}_qfq.csv``（旧版
    ``out/cache_prices/{code}_qfq_*.csv`` 亦可）；
  * 全市场基金排行快照落盘的 CSV：``单位净值``、``近1周/近1月/近3月``
    区间收益率，用于没有日净值序列的基金降级估算。

方法（EWMA 漂移 + 波动率，样本量收缩）：

    r_t     = clip(ln(P_t / P_{t−1}), med ± c·MAD)   # 分红/折算跳变稳健缩尾
    μ̂_t     = λ·μ̂_{t−1} + (1−λ)·r_t
    σ̂²_t    = λ·σ̂²_{t−1} + (1−λ)·(r_t − μ̂_{t−1})²
    n_eff   = (1−λⁿ)/(1−λ)
    μ̃       = clip( μ̂_n · n_eff/(n_eff+K), −3σ₀, +3σ₀ )
    P̂_{t+1} = P_t · exp(μ̃),  区间 [P_t·e^{μ̃−σ̂}, P_t·e^{μ̃+σ̂}]
    V_raw   = clip(μ̃ / σ₀, −3, 3)

σ̂ 为标的自身的 EWMA 日波动（用于参考区间），σ₀ 为资产类别统一先验
（基金 1.2% / 股票 2.2%，用于风险尺度归一）。V_raw 是「风险调整后的
日漂移」（信息比率口径），由
``selection_formula.py`` 在候选池横截面上缩尾 + min-max 归一化成
估值因子 Ṽ；没有行情序列的标的取中性值 0.5，不因缺数据受奖惩。

估算价是「按公开历史价格外推的下一交易日参考价」，不是实时报价、
不是目标价，也不构成投资建议。
"""

from __future__ import annotations

import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ── 形式化参数（公式页与 README 直接引用） ──────────────────
PRICE_LAMBDA = 0.94          # λ，RiskMetrics 衰减因子
SHRINKAGE_K = 20.0           # K，有效样本量收缩先验
MIN_SERIES = 40              # 少于约两个月交易日则不用序列口径（EWMA 尚未收敛）
SIGMA_FLOOR = 1e-4           # ε，避免除零
DRIFT_CLIP = 3.0             # μ̃ 与 V_raw 的截断倍数
RETURN_WINSOR_MAD = 5.0     # 输入收益按最近 120 日 MAD 缩尾的倍数
PERIOD_WINDOWS: dict[str, tuple[int, float]] = {
    "近1周": (5, 0.5),
    "近1月": (21, 0.3),
    "近3月": (63, 0.2),
}
FUND_SIGMA_PRIOR = 0.012     # 无序列时的基金日波动先验（约 1.2%）
STOCK_SIGMA_PRIOR = 0.022    # 无序列时的股票日波动先验（约 2.2%）
PERIOD_NEFF = 21.0           # 区间收益率口径的等效样本量

PRICE_PARAMS: dict[str, Any] = {
    "lambda": PRICE_LAMBDA,
    "shrinkage_k": SHRINKAGE_K,
    "min_series": MIN_SERIES,
    "sigma_floor": SIGMA_FLOOR,
    "drift_clip": DRIFT_CLIP,
    "return_winsor_mad": RETURN_WINSOR_MAD,
    "period_windows": PERIOD_WINDOWS,
    "fund_sigma_prior": FUND_SIGMA_PRIOR,
    "stock_sigma_prior": STOCK_SIGMA_PRIOR,
    "period_neff": PERIOD_NEFF,
}


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        f = float(str(v).strip())
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _read_series(path: Path) -> tuple[list[str], list[float]]:
    """读取「日期 + 价格」两列 CSV，兼容新旧缓存列名。"""
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return [], []
    if df.empty or "日期" not in df.columns:
        return [], []
    col = next((c for c in ("value", "单位净值", "收盘", "close") if c in df.columns), None)
    if col is None:
        return [], []
    dates = [str(d) for d in df["日期"].tolist()]
    vals = []
    for v in df[col].tolist():
        f = _num(v)
        vals.append(f if f is not None and f > 0 else None)
    pairs = [(d, v) for d, v in zip(dates, vals) if v is not None]
    pairs.sort(key=lambda x: x[0])
    return [d for d, _ in pairs], [v for _, v in pairs]


def _collect_series(root: Path) -> tuple[dict[str, tuple[list[str], list[float]]], dict[str, tuple[list[str], list[float]]]]:
    """扫描新旧缓存目录，返回 (基金净值序列, 股票前复权收盘价序列)。"""
    funds: dict[str, tuple[list[str], list[float]]] = {}
    stocks: dict[str, tuple[list[str], list[float]]] = {}

    def put(target: dict, code: str, series: tuple[list[str], list[float]]) -> None:
        if len(series[1]) < 2:
            return
        old = target.get(code)
        if old is None or len(series[1]) > len(old[1]):
            target[code] = series

    series_dir = root / "out" / "cache_series"
    legacy_dir = root / "out" / "cache_prices"

    if series_dir.is_dir():
        for f in series_dir.glob("*.csv"):
            m_nav = re.fullmatch(r"nav_(\d{6})\.csv", f.name)
            m_stock = re.fullmatch(r"(\d{6})_qfq\.csv", f.name)
            if m_nav:
                put(funds, m_nav.group(1), _read_series(f))
            elif m_stock:
                put(stocks, m_stock.group(1), _read_series(f))
    if legacy_dir.is_dir():
        for f in legacy_dir.glob("*.csv"):
            m_nav = re.match(r"nav_(\d{6})_", f.name)
            m_stock = re.match(r"(\d{6})_qfq_", f.name)
            if m_nav:
                put(funds, m_nav.group(1), _read_series(f))
            elif m_stock:
                put(stocks, m_stock.group(1), _read_series(f))
    return funds, stocks


def estimate_from_prices(
    dates: list[str], prices: list[float], sigma_ref: float = FUND_SIGMA_PRIOR
) -> dict[str, Any] | None:
    """由价格序列外推 T+1 估算价。序列不足 MIN_SERIES 时返回 None。"""
    if len(prices) < MIN_SERIES or len(dates) != len(prices):
        return None
    raw = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(raw) < MIN_SERIES - 1:
        return None
    # 净值分红、份额折算等会在单日造成 10%+ 的「假收益」。
    # 用最近 120 日的 MAD 做稳健缩尾，避免污染 EWMA 的漂移与波动。
    tail = raw[-120:]
    med = statistics.median(tail)
    mad = statistics.median([abs(x - med) for x in tail])
    cap = max(RETURN_WINSOR_MAD * 1.4826 * mad, 0.02)
    returns = [max(med - cap, min(med + cap, x)) for x in raw]

    lam = PRICE_LAMBDA
    init = returns[: min(20, len(returns))]
    mu = sum(init) / len(init)
    var = sum((x - mu) ** 2 for x in init) / max(1, len(init) - 1)
    sigma = math.sqrt(max(var, SIGMA_FLOOR ** 2))
    for r in returns:
        mu, var = lam * mu + (1 - lam) * r, lam * var + (1 - lam) * (r - mu) ** 2
        sigma = math.sqrt(max(var, SIGMA_FLOOR ** 2))

    n_eff = (1 - lam ** len(returns)) / (1 - lam)
    mu_tilde = mu * n_eff / (n_eff + SHRINKAGE_K)
    sigma_hat = max(sigma, SIGMA_FLOOR)       # 用于 ±1σ 参考区间
    ref = max(sigma_ref, SIGMA_FLOOR)         # 统一的风险尺度，用于 V_raw
    mu_tilde = max(-DRIFT_CLIP * ref, min(DRIFT_CLIP * ref, mu_tilde))

    last = prices[-1]
    est = last * math.exp(mu_tilde)
    lo = last * math.exp(mu_tilde - sigma_hat)
    hi = last * math.exp(mu_tilde + sigma_hat)
    return {
        "最新价格": round(last, 4),
        "估算价格": round(est, 4),
        "估算涨跌": round((est / last - 1) * 100, 2),
        "估算下界": round(lo, 4),
        "估算上界": round(hi, 4),
        "日波动": round(sigma_hat * 100, 2),
        "估值信号": round(max(-DRIFT_CLIP, min(DRIFT_CLIP, mu_tilde / ref)), 4),
        "数据截至": dates[-1],
        "估算口径": "EWMA 日价格序列",
        "样本数": len(returns) + 1,
    }


def estimate_from_period_returns(row: dict[str, Any], sigma_ref: float = FUND_SIGMA_PRIOR) -> dict[str, Any] | None:
    """基金降级口径：用公开区间收益率折算日均漂移。"""
    last = _num(row.get("单位净值"))
    if last is None or last <= 0:
        return None
    num = den = 0.0
    for col, (days, weight) in PERIOD_WINDOWS.items():
        r = _num(row.get(col))
        if r is None or r <= -100:
            continue
        mu_j = math.log1p(r / 100.0) / days
        num += weight * mu_j
        den += weight
    if den <= 0:
        return None
    mu_bar = num / den
    mu_tilde = mu_bar * PERIOD_NEFF / (PERIOD_NEFF + SHRINKAGE_K)
    sigma = max(sigma_ref, SIGMA_FLOOR)
    mu_tilde = max(-DRIFT_CLIP * sigma, min(DRIFT_CLIP * sigma, mu_tilde))
    est = last * math.exp(mu_tilde)
    return {
        "最新价格": round(last, 4),
        "估算价格": round(est, 4),
        "估算涨跌": round((est / last - 1) * 100, 2),
        "估算下界": round(last * math.exp(mu_tilde - sigma), 4),
        "估算上界": round(last * math.exp(mu_tilde + sigma), 4),
        "日波动": round(sigma * 100, 2),
        "估值信号": round(max(-DRIFT_CLIP, min(DRIFT_CLIP, mu_tilde / sigma)), 4),
        "数据截至": _text(row.get("日期")),
        "估算口径": "区间收益率折算",
        "样本数": 0,
    }


def _stock_proxy(
    records: list[dict[str, Any]], fund_estimates: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """股票无行情序列时的降级口径：用重仓它的基金净值漂移加权代理。

    权重取季报「汇总占净值比例」；基金估值信号 V_f 先还原成日漂移
    μ̃_f = V_f·σ₀(fund)，再按股票波动先验 σ₀(stock) 重新归一。
    只给出「估算涨跌」与估值信号，不虚构绝对价格。
    """
    agg: dict[str, dict[str, float]] = {}
    for r in records or []:
        code = _text(r.get("股票代码")).zfill(6)
        if not re.fullmatch(r"\d{6}", code):
            continue
        weight = _num(r.get("汇总占净值比例")) or 1.0
        funds = {x.strip().zfill(6) for x in
                 _text(r.get("Top3基金列表")).replace("，", ",").split(",") if x.strip()}
        entry = agg.setdefault(code, {"num": 0.0, "den": 0.0})
        for f in funds:
            e = fund_estimates.get(f)
            if not e:
                continue
            v = _num(e.get("估值信号"))
            if v is None:
                continue
            entry["num"] += weight * v * FUND_SIGMA_PRIOR
            entry["den"] += weight
    out: dict[str, dict[str, Any]] = {}
    for code, a in agg.items():
        if a["den"] <= 0:
            continue
        mu = a["num"] / a["den"]
        v = max(-DRIFT_CLIP, min(DRIFT_CLIP, mu / STOCK_SIGMA_PRIOR))
        out[code] = {
            "最新价格": "", "估算价格": "", "估算下界": "", "估算上界": "",
            "估算涨跌": round((math.exp(mu) - 1) * 100, 2),
            "日波动": round(STOCK_SIGMA_PRIOR * 100, 2),
            "估值信号": round(v, 4),
            "数据截至": "",
            "估算口径": "重仓基金净值代理",
            "样本数": 0,
        }
    return out


def build_price_estimates(
    root: Path,
    fund_rows: list[dict[str, Any]],
    stock_codes: list[str],
    extra_fund_rows: list[dict[str, Any]] | None = None,
    stock_proxy_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """生成估算价格册：{"funds": {code: ...}, "stocks": {code: ...}, ...}。

    fund_rows / extra_fund_rows 均为「含单位净值、区间收益率」的基金记录；
    stock_codes 为页面会展示的股票代码。有行情序列的股票给出绝对估算价；
    没有序列的股票用 stock_proxy_records（季报重仓记录）里的关联基金净值
    漂移做代理，只给估算涨跌与估值信号，不虚构绝对价格。
    """
    fund_series, stock_series = _collect_series(root)

    # 估值信号统一用资产类别日波动先验 σ₀ 归一（式 (11)），这样有日序列
    # 与「区间收益率降级」两种口径的 V_raw 处在同一量纲，可直接横截面比较。
    funds: dict[str, dict[str, Any]] = {}
    by_code: dict[str, dict[str, Any]] = {}
    for row in list(fund_rows or []) + list(extra_fund_rows or []):
        code = _text(row.get("基金代码")).zfill(6)
        if re.fullmatch(r"\d{6}", code) and code not in by_code:
            by_code[code] = row
    for code in sorted(by_code):
        s = fund_series.get(code)
        est = estimate_from_prices(s[0], s[1]) if s else None
        if est is None:
            est = estimate_from_period_returns(by_code[code])
        if est:
            funds[code] = est

    stocks: dict[str, dict[str, Any]] = {}
    proxy = _stock_proxy(stock_proxy_records or [], funds)
    priced = 0
    proxied = 0
    for code in sorted({_text(c).zfill(6) for c in stock_codes}):
        if not re.fullmatch(r"\d{6}", code):
            continue
        s = stock_series.get(code)
        est = estimate_from_prices(s[0], s[1], STOCK_SIGMA_PRIOR) if s else None
        if est:
            priced += 1
        elif code in proxy:
            est = proxy[code]
            proxied += 1
        if est:
            stocks[code] = est

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "funds": funds,
        "stocks": stocks,
        "params": PRICE_PARAMS,
        "coverage": {
            "funds": len(funds),
            "fund_candidates": len(by_code),
            "stocks": len(stocks),
            "stock_priced": priced,
            "stock_proxy": proxied,
            "stock_candidates": len({_text(c).zfill(6) for c in stock_codes if _text(c)}),
            "fund_series": len(fund_series),
            "stock_series": len(stock_series),
            "fund_sigma_ref": FUND_SIGMA_PRIOR,
            "stock_sigma_ref": STOCK_SIGMA_PRIOR,
        },
        "note": "估算价 = 按公开历史价格序列 EWMA 漂移外推的 T+1 参考价；"
                "无日序列的基金改用公开区间收益率折算；无行情序列的股票用重仓基金"
                "净值漂移代理（只给涨跌与估值信号，不虚构绝对价格，页面显示暂无）。",
    }


_LATEST_CACHE: dict[str, dict[str, Any]] = {}


def load_latest_estimates(root: Path | None = None) -> dict[str, Any]:
    """读取 docs/data/ 下最新一份 price_estimates.json（进程内缓存）。

    selection_formula 的评分函数在未显式传入估算册时调用它，让流水线脚本、
    动态站与静态站使用同一份估值数据；文件不存在时返回空册（全部中性）。
    """
    base = (root or Path(__file__).resolve().parent.parent) / "docs" / "data"
    key = str(base)
    if key in _LATEST_CACHE:
        return _LATEST_CACHE[key]
    book: dict[str, Any] = {"funds": {}, "stocks": {}}
    try:
        files = sorted((p for p in base.glob("*/price_estimates.json") if p.is_file()),
                       key=lambda p: p.parent.name, reverse=True)
        if files:
            book = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        pass
    _LATEST_CACHE[key] = book
    return book


def estimate_for(book: dict[str, Any] | None, section: str, code: Any) -> dict[str, Any] | None:
    """按代码查估算册（section = funds / stocks）。"""
    if not book:
        return None
    key = _text(code).zfill(6)
    item = (book.get(section) or {}).get(key)
    return item if isinstance(item, dict) else None
