#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股票前复权日线抓取（腾讯财经行情接口）。

数据源（均为公开行情页背后同一套接口）：
  * 腾讯财经 ``web.ifzq.gtimg.cn/appstock/app/fqkline/get``：前复权日 K，
    免登录、稳定、单次可取 620+ 根，足以支撑 EWMA 估算（MIN_SERIES=40）；
  * 备选：东方财富 push2his（akshare ``stock_zh_a_hist`` 用的就是它）、
    新浪 ``money.finance.sina.com.cn`` 日线。东财接口在部分网络环境下
    会拒绝代理/数据中心 IP，腾讯接口兼容性更好，故作为默认源。

输出格式与既有缓存完全一致（``price_estimate._read_series`` 直接可读）：

    out/cache_series/{code}_qfq.csv   # 两列：日期,收盘

新鲜度策略：本地序列的最近日期距今天不超过 ``MAX_STALE_DAYS`` 个自然日
即跳过抓取，避免重复请求；失败个股只记录告警、不中断整站生成。

仅用于「按公开历史价格外推 T+1 估算价」，不是实时报价、不构成投资建议。
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "out" / "cache_series"

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
REQUEST_DAYS = 620          # 一次拉约 2.5 年日线（含复权因子，够 EWMA 收敛）
MAX_STALE_DAYS = 7          # 本地序列最近日期 7 天内视为新鲜（覆盖节假日）
MAX_RETRIES = 3
RETRY_DELAY = 1.5
SLEEP_BETWEEN = 0.3         # 逐股限速，礼貌抓取

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}


def _symbol(code: str) -> str:
    """6 位代码 → 带交易所前缀的腾讯代码：6xxxxx→sh，其余→sz。"""
    return ("sh" if code.startswith(("6", "9")) else "sz") + code


def _series_path(code: str) -> Path:
    return SERIES_DIR / f"{code}_qfq.csv"


def _is_fresh(code: str, max_stale_days: int = MAX_STALE_DAYS) -> bool:
    """已有缓存序列的最近日期足够新则跳过抓取。"""
    path = _series_path(code)
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
    except OSError:
        return False
    if len(rows) < 2:
        return False
    try:
        last_date = datetime.strptime(rows[-1][0], "%Y-%m-%d")
    except (ValueError, IndexError):
        return False
    return last_date >= datetime.now() - timedelta(days=max_stale_days)


def _fetch_one(code: str, session) -> list[list[str]] | None:
    """抓单只股票的前复权日线，返回 [[日期, 收盘, ...], ...] 或 None。"""
    symbol = _symbol(code)
    params = {"param": f"{symbol},day,,,{REQUEST_DAYS},qfq"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(KLINE_URL, params=params, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", {}).get(symbol, {})
            rows = data.get("qfqday") or data.get("day")
            if rows:
                return rows
            return None  # 接口正常但没有数据（退市/代码错误），不重试
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    return None


def _write_csv(code: str, rows: list[list[str]]) -> None:
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    path = _series_path(code)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日期", "收盘"])
        for row in rows:
            date, close = str(row[0]), str(row[1])
            try:
                if not (float(close) > 0):
                    continue
            except ValueError:
                continue
            writer.writerow([date, close])


def ensure_stock_series(
    codes: Iterable[str],
    session=None,
    verbose: bool = True,
) -> tuple[int, int]:
    """确保这些股票的本地前复权日线存在且新鲜。

    返回 (成功只数, 失败只数)。失败不抛异常，页面会自动回退到
    「重仓基金净值代理」口径（只有估算涨跌、没有绝对价）。
    """
    import requests

    if session is None:
        session = requests.Session()

    todo = []
    for raw in codes:
        code = str(raw).strip().zfill(6)
        if not code.isdigit() or code == "000000" or _is_fresh(code):
            continue
        todo.append(code)
    if not todo:
        return 0, 0

    ok = fail = 0
    for code in sorted(todo):
        rows = _fetch_one(code, session)
        if rows:
            _write_csv(code, rows)
            ok += 1
        else:
            fail += 1
            if verbose:
                print(f"  [行情] {code} 抓取失败，保留代理口径")
        time.sleep(SLEEP_BETWEEN)
    if verbose:
        print(f"  [行情] 股票日线更新：成功 {ok} / 失败 {fail}（腾讯 qfq 接口）")
    return ok, fail


if __name__ == "__main__":
    import sys

    args = [a.strip().zfill(6) for a in sys.argv[1:] if a.strip()]
    if args:
        ensure_stock_series(args)
    else:
        print("用法: python fetch_stock_series.py 000063 600519 ...")
