#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天天基金 F10 数据抓取（重仓股 / 重大变动）+ 季度级缓存。

背景 / 为什么不再用 akshare 的 fund_portfolio_hold_em、fund_portfolio_change_em：
  1. 这两个接口的请求未携带 ``Referer`` 头，天天基金现在会直接返回 404；
  2. 它们的 ``requests.get`` 没有 timeout，接口挂起时能把整条流水线卡死；
  3. 调用方把异常静默吞掉，导致「看起来像超时/没数据」，实际是接口被拒。

本模块直接调用 F10 接口，带 Referer / UA、显式超时、有限重试；并把结果落到
仓库内的 ``data/fund_holdings_cache.json``。持仓与重大变动都按季度披露，没必要
每个交易日重抓上百次：缓存默认 7 天内复用，抓取失败时回退旧缓存，保证当天
的调仓信号与静态页面仍能正常生成。

代理：遵循标准 ``HTTP_PROXY`` / ``NO_PROXY`` 环境变量。GitHub Actions 无代理，
本地若配置了代理会自动走代理；都失败时还有缓存兜底。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import demjson3
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "fund_holdings_cache.json"
URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
HOLD_COLS = ["股票代码", "股票名称", "占净值比例", "季度"]
CHANGE_COLS = ["股票代码", "股票名称", "占期初基金资产净值比例", "季度"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    # 缺少 Referer 会被服务端返回 404（这是 akshare 老接口失效的根因）
    "Referer": "https://fundf10.eastmoney.com/",
    "Accept": "*/*",
}

# 缓存有效期（天）。F10 数据按季度更新，7 天足够捕捉季报发布
MAX_AGE_DAYS = int(os.environ.get("HOLDINGS_MAX_AGE_DAYS", "7"))
REQUEST_TIMEOUT = (5, 12)  # (连接, 读取) 秒，防止无期限挂起


def _empty(cols: list[str] | None = None) -> pd.DataFrame:
    return pd.DataFrame(columns=cols or HOLD_COLS)


def _load_cache() -> dict:
    empty = {"updated_at": "", "entries": {}, "changes": {}}
    if not CACHE_PATH.is_file():
        return empty
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        for key in ("entries", "changes"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        return data
    except (OSError, ValueError) as exc:
        print(f"[f10] 缓存读取失败，忽略：{exc}", file=sys.stderr)
        return empty


def _save_cache(cache: dict) -> None:
    cache["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _cache_fresh(entry: dict) -> bool:
    try:
        fetched = date.fromisoformat(str(entry.get("fetched_at", ""))[:10])
    except ValueError:
        return False
    return (date.today() - fetched).days < MAX_AGE_DAYS


def _rows_to_df(rows: list[dict], cols: list[str], numeric_col: str) -> pd.DataFrame:
    if not rows:
        return _empty(cols)
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[numeric_col] = pd.to_numeric(df[numeric_col], errors="coerce")
    return df[cols].dropna(subset=[numeric_col]).reset_index(drop=True)


def _find_col(df: pd.DataFrame, *keywords: str) -> str | None:
    for col in df.columns:
        compact = str(col).replace(" ", "").replace("\xa0", "")
        if all(k in compact for k in keywords):
            return col
    return None


def _pct(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.strip(),
        errors="coerce",
    )


def _parse_tables(payload: dict) -> tuple[list[str], list[pd.DataFrame]]:
    content = payload.get("content") or ""
    if not content:
        return [], []
    quarters = [
        f"{y}年{q}季度"
        for y, q in re.findall(
            r"<h4[^>]*class=['\"]t['\"][^>]*>.*?(\d{4})年(\d)季度", content, re.S
        )
    ]
    try:
        tables = pd.read_html(StringIO(content))
    except ValueError:
        tables = []
    return quarters, tables


def _quarter(quarters: list[str], idx: int) -> str:
    if idx < len(quarters):
        return quarters[idx]
    return quarters[0] if quarters else ""


def _parse_holdings(payload: dict) -> pd.DataFrame:
    quarters, tables = _parse_tables(payload)
    frames = []
    for idx, tbl in enumerate(tables):
        code_col = _find_col(tbl, "股票代码")
        name_col = _find_col(tbl, "股票名称")
        ratio_col = _find_col(tbl, "占净值", "比例")
        if code_col is None or ratio_col is None:
            continue
        frames.append(pd.DataFrame({
            "股票代码": tbl[code_col].astype(str).str.strip().str.zfill(6),
            "股票名称": tbl[name_col].astype(str).str.strip() if name_col else "",
            "占净值比例": _pct(tbl[ratio_col]),
            "季度": _quarter(quarters, idx),
        }))
    if not frames:
        return _empty(HOLD_COLS)
    all_df = pd.concat(frames, ignore_index=True).dropna(subset=["占净值比例"])
    if all_df.empty:
        return _empty(HOLD_COLS)
    latest = max(str(q) for q in all_df["季度"].unique())
    return all_df[all_df["季度"] == latest][HOLD_COLS].reset_index(drop=True)


def _parse_changes(payload: dict) -> pd.DataFrame:
    quarters, tables = _parse_tables(payload)
    frames = []
    for idx, tbl in enumerate(tables):
        code_col = _find_col(tbl, "股票代码")
        name_col = _find_col(tbl, "股票名称")
        ratio_col = _find_col(tbl, "占期初", "比例")
        if code_col is None or ratio_col is None:
            continue
        frames.append(pd.DataFrame({
            "股票代码": tbl[code_col].astype(str).str.strip().str.zfill(6),
            "股票名称": tbl[name_col].astype(str).str.strip() if name_col else "",
            "占期初基金资产净值比例": _pct(tbl[ratio_col]),
            "季度": _quarter(quarters, idx),
        }))
    if not frames:
        return _empty(CHANGE_COLS)
    all_df = pd.concat(frames, ignore_index=True).dropna(subset=["占期初基金资产净值比例"])
    if all_df.empty:
        return _empty(CHANGE_COLS)
    latest = max(str(q) for q in all_df["季度"].unique())
    return all_df[all_df["季度"] == latest][CHANGE_COLS].reset_index(drop=True)


def _request_payload(session: requests.Session, params: dict) -> dict:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = session.get(URL, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            text = r.text
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("响应不是预期的 apidata JSON")
            return demjson3.decode(text[start:end + 1])
        except Exception as exc:  # 网络抖动 / 解析失败重试一次
            last_exc = exc
            if attempt == 0:
                time.sleep(0.6)
    raise last_exc or RuntimeError("F10 请求失败")


def _fetch_online_holdings(code: str, years_back: int, sleep_s: float) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)
    this_year = datetime.now().year
    for year in range(this_year, this_year - years_back, -1):
        payload = _request_payload(session, {
            "type": "jjcc", "code": code, "topline": "10000",
            "year": str(year), "month": "", "rt": f"{time.time():.6f}",
        })
        df = _parse_holdings(payload)
        time.sleep(sleep_s)
        if not df.empty:
            return df
    return _empty(HOLD_COLS)


def _fetch_online_changes(code: str, indicator: str, years_back: int, sleep_s: float) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)
    this_year = datetime.now().year
    for year in range(this_year, this_year - years_back, -1):
        payload = _request_payload(session, {
            "type": "zdbd", "code": code,
            "zdbd": "1" if indicator == "累计买入" else "2",
            "year": str(year), "rt": f"{time.time():.6f}",
        })
        df = _parse_changes(payload)
        time.sleep(sleep_s)
        if not df.empty:
            return df
    return _empty(CHANGE_COLS)


def get_holdings(
    code: str,
    years_back: int = 3,
    sleep_s: float = 0.3,
    force: bool = False,
) -> tuple[pd.DataFrame, str]:
    """返回 (重仓股 DataFrame, 来源)：online / cache / stale-cache / failed。"""
    code = str(code).zfill(6)
    cache = _load_cache()
    entry = cache["entries"].get(code)

    if entry and not force and _cache_fresh(entry):
        return _rows_to_df(entry.get("rows") or [], HOLD_COLS, "占净值比例"), "cache"

    try:
        df = _fetch_online_holdings(code, years_back, sleep_s)
        if not df.empty:
            cache["entries"][code] = {
                "quarter": str(df["季度"].iloc[0]),
                "fetched_at": date.today().isoformat(),
                "rows": df[HOLD_COLS].to_dict("records"),
            }
            _save_cache(cache)
            return df, "online"
        # 空结果也缓存（债券/货币基金没有股票持仓），避免每天重复请求 3 个年份
        cache["entries"][code] = {
            "quarter": "", "fetched_at": date.today().isoformat(), "rows": [],
        }
        _save_cache(cache)
        print(f"[f10] {code} 线上无重仓股数据（可能是债券/货币基金）", file=sys.stderr)
    except Exception as exc:
        print(f"[f10] {code} 重仓股抓取失败：{type(exc).__name__}: {exc}", file=sys.stderr)

    if entry and entry.get("rows"):
        print(f"[f10] {code} 回退重仓股缓存（{entry.get('quarter', '?')}）", file=sys.stderr)
        return _rows_to_df(entry["rows"], HOLD_COLS, "占净值比例"), "stale-cache"
    return _empty(HOLD_COLS), "failed"


def get_fund_changes(
    code: str,
    indicator: str,
    years_back: int = 3,
    sleep_s: float = 0.3,
    force: bool = False,
) -> tuple[pd.DataFrame, str]:
    """返回 (重大变动 DataFrame, 来源)。indicator: 累计买入 / 累计卖出。"""
    code = str(code).zfill(6)
    key = f"{code}:{indicator}"
    cache = _load_cache()
    entry = cache["changes"].get(key)

    if entry and not force and _cache_fresh(entry):
        return _rows_to_df(entry.get("rows") or [], CHANGE_COLS, "占期初基金资产净值比例"), "cache"

    try:
        df = _fetch_online_changes(code, indicator, years_back, sleep_s)
        if not df.empty:
            cache["changes"][key] = {
                "quarter": str(df["季度"].iloc[0]),
                "fetched_at": date.today().isoformat(),
                "rows": df[CHANGE_COLS].to_dict("records"),
            }
            _save_cache(cache)
            return df, "online"
        cache["changes"][key] = {
            "quarter": "", "fetched_at": date.today().isoformat(), "rows": [],
        }
        _save_cache(cache)
    except Exception as exc:
        print(f"[f10] {key} 重大变动抓取失败：{type(exc).__name__}: {exc}", file=sys.stderr)

    if entry and entry.get("rows"):
        print(f"[f10] {key} 回退重大变动缓存（{entry.get('quarter', '?')}）", file=sys.stderr)
        return _rows_to_df(entry["rows"], CHANGE_COLS, "占期初基金资产净值比例"), "stale-cache"
    return _empty(CHANGE_COLS), "failed"
