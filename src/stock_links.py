#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股票行情外链（多市场）。

站内股票代码来自基金季报重仓明细，含四种口径：

  * A 股：6 位纯数字，按首位判交易所（6/9→沪、0/2/3→深、4/8→北）；
  * 港股：6 位纯数字 = "0" + 5 位港股代码（009988 → 09988.HK）；
  * 韩股：6 位纯数字 KRX 代码（005930 三星电子 / 000660 SK海力士）；
  * 美股："00" + ticker（000TSM → TSM、00GOOG → GOOG、0000MU → MU）。

**港股与 A 股撞码**：000700 在 A 股是模塑科技、在港股口径是腾讯控股，
只按首位数字判前缀会把腾讯错链到深市个股。因此必须先用
``out/cache_series/_stock_meta.json``（抓取时按证券名称校验过的市场分类）
消歧，查不到再按代码形态推断。

``out/`` 不进版本库，静态站的已落盘 JSON 里没有 meta 可用，
故同时支持把「代码 → 市场」映射随数据下发（见 generate_static）。

外链目标：
  * A 股 / 港股 / 美股 → 雪球（SH/SZ/BJ + 代码、5 位港股码、美股 ticker）；
  * 韩股 → Naver Finance（雪球不收录 KRX 个股）。

仅用于跳转公开行情页，不构成投资建议。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
META_PATH = ROOT / "out" / "cache_series" / "_stock_meta.json"

# 韩股：雪球不收录 KRX 个股，改用 Naver Finance 原生行情页
NAVER_STOCK_URL = "https://finance.naver.com/item/main.naver?code={code}"
XUEQIU_URL = "https://xueqiu.com/S/{symbol}"

_MARKETS = ("A", "HK", "KR", "US")

_META_CACHE: dict[str, dict[str, Any]] | None = None


def load_stock_meta(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """读取抓取器落盘的市场分类（进程内缓存）。缺失时返回空表。"""
    global _META_CACHE
    if path is None and _META_CACHE is not None:
        return _META_CACHE
    p = path or META_PATH
    meta: dict[str, dict[str, Any]] = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            meta = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except (OSError, ValueError):
        meta = {}
    if path is None:
        _META_CACHE = meta
    return meta


def reset_meta_cache() -> None:
    """抓取器刷新 meta 后调用，避免同进程读到旧分类。"""
    global _META_CACHE
    _META_CACHE = None


def us_ticker(code: str) -> str | None:
    """"00" + ticker 口径还原美股 ticker；非法返回 None。

    与 fetch_stock_series._resolve_us 保持同一规则：去掉前导 0 后
    必须是 1–5 位字母数字，过长（如 ISIN）不是 ticker。
    """
    ticker = str(code).lstrip("0")
    return ticker.upper() if re.fullmatch(r"[A-Za-z0-9]{1,5}", ticker) else None


def guess_market(code: str) -> str | None:
    """无 meta 时按代码形态推断市场。

    含字母 → 美股（"00" + ticker 形态唯一，不会撞码）。
    6 位纯数字**不推断港股**：港股内部码 "0" + 5 位（001024）与
    A 股 001xxx（如 001979 招商蛇口）形态完全相同，靠数字无法区分，
    猜错会把用户引到另一只标的。这类代码一律按 A 股口径处理，
    港股必须由抓取时按证券名称校验过的 meta 认定。
    """
    c = str(code).strip()
    if not c:
        return None
    if not c.isdigit():
        return "US" if us_ticker(c) else None
    return "A" if len(c) == 6 else None


def resolve_market(code: str, meta: dict[str, Any] | None = None) -> str | None:
    """代码 → 市场。优先用抓取时校验过的 meta，其次按形态推断。"""
    c = str(code).strip()
    if not c:
        return None
    m = meta if meta is not None else load_stock_meta()
    info = m.get(c)
    if isinstance(info, dict):
        market = str(info.get("market") or "").upper()
        if market in _MARKETS:
            return market
    elif isinstance(info, str) and info.upper() in _MARKETS:
        # 随数据下发的精简映射：{code: "HK"}
        return info.upper()
    return guess_market(c)


def _a_share_prefix(code: str) -> str:
    if code.startswith("92"):
        return "BJ"  # 920xxx 北交所新代码段（920045 蘅东光等）
    head = code[:1]
    if head in ("6", "9"):
        return "SH"
    if head in ("0", "2", "3"):
        return "SZ"
    if head in ("4", "8"):
        return "BJ"
    return ""


def stock_target(code: Any, meta: dict[str, Any] | None = None) -> dict[str, str] | None:
    """代码 → {'market': 'A/HK/KR/US', 'target': URL 用标的代码}；无法定位返回 None。

    target 口径：
      * A：交易所前缀 + 6 位代码（000063 → SZ000063、600519 → SH600519）；
      * HK：5 位港股代码（内部码 009988 → 09988）；
      * US：美股 ticker（000TSM → TSM、00SNDK → SNDK）；
      * KR：6 位 KRX 代码（KR7000660001 → 000660）。

    宁可不给链接，也不给指向错误标的的链接——港股/A 股撞码时
    若无 meta 且形态无法区分，交由调用方决定是否降级。
    """
    c = str(code or "").strip()
    if not c or c == "000000":
        return None
    # ISIN 口径（KR7000660001 / US80004C2008）先还原成站内代码，
    # 复用 price_estimate 的别名机制，避免两处各维护一份映射。
    if len(c) > 8:
        try:
            from price_estimate import _alias_target
            target = _alias_target(c)
        except Exception:
            target = None
        if not target:
            return None
        c = target
    market = resolve_market(c, meta)
    if market == "US":
        t = us_ticker(c)
        return {"market": "US", "target": t} if t else None
    if market == "KR":
        return {"market": "KR", "target": c} if re.fullmatch(r"\d{6}", c) else None
    if market == "HK":
        # 内部码 "0" + 5 位港股码 → 雪球用 5 位（009988 → 09988）
        return {"market": "HK", "target": c[1:]} if re.fullmatch(r"0\d{5}", c) else None
    if market == "A":
        if not re.fullmatch(r"\d{6}", c):
            return None
        p = _a_share_prefix(c)
        return {"market": "A", "target": p + c} if p else None
    return None


def stock_url(code: Any, meta: dict[str, Any] | None = None) -> str:
    """股票行情外链；无法可靠定位时返回空串（页面按纯文本显示）。"""
    t = stock_target(code, meta)
    if not t:
        return ""
    if t["market"] == "KR":
        # 雪球不收录 KRX 个股，用 Naver Finance 原生行情页
        return NAVER_STOCK_URL.format(code=t["target"])
    return XUEQIU_URL.format(symbol=t["target"])


def stock_link_map(codes: Any) -> dict[str, dict[str, str]]:
    """静态站数据下发用：代码 → {'market', 'target'}。

    前端据此生成多市场行情外链（out/ 不进版本库，静态 JSON 必须自带分类）；
    含 ISIN 别名解析，找不到可靠口径的代码不入表。
    """
    meta = load_stock_meta()
    out: dict[str, dict[str, str]] = {}
    for code in codes or []:
        c = str(code).strip()
        if not c:
            continue
        t = stock_target(c, meta)
        if t:
            out[c] = t
    return out