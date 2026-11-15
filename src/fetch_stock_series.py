#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股票前复权日线抓取（多市场自动识别）。

股票代码来自基金季报重仓明细，包含 A 股、港股、韩股与美股四种口径：

  * A 股：6 位纯数字（60/00/30/68/… 前缀）；
  * 港股：6 位纯数字 = "0" + 5 位港股代码（如 009988 → 09988.HK），
    与 A 股代码空间撞车（000700 在 A 股是模塑科技、在港股口径是腾讯控股），
    因此必须用「股票名称」校验来消歧；
  * 韩股：6 位纯数字 KRX 代码（005930 三星电子 / 000660 SK海力士）；
  * 美股："00" + 代码（000TSM → TSM、00GOOG → GOOG、0000MU → MU）。

数据源（均为公开行情页背后同一套接口）：
  * 东方财富 push2his：A 股（secid 0./1.）、港股（116.xxxxx）、美股
    （105./106./107. + 代码），前复权日 K，响应带证券名称可用于校验；
  * Naver Finance：韩股（KRX）日线（雅虎 chart 接口对数据中心 IP 限流）；
  * 腾讯财经 fqkline：A 股备选源（部分网络环境拒连东财时）。

分类结果写入 ``out/cache_series/_stock_meta.json``，价格序列按市场分文件：
``{code}_qfq.csv``（A 股）/ ``{code}_hk_qfq.csv`` / ``{code}_kr_qfq.csv`` /
``{code}_us_qfq.csv``，均为「日期,收盘」两列，price_estimate 直接可读。

新鲜度策略：对应市场文件的最近日期 7 天内即跳过。失败个股只记录告警、
不中断整站生成（页面回退「重仓基金净值代理」口径）。

仅用于「按公开历史价格外推 T+1 估算价」，不是实时报价、不构成投资建议。
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "out" / "cache_series"
META_PATH = SERIES_DIR / "_stock_meta.json"

EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
NAVER_URL = "https://api.stock.naver.com/chart/domestic/item/{code}/day"

LOOKBACK_DAYS = 900         # 东财按日期区间取约 2.5 年日线
MAX_STALE_DAYS = 7          # 序列最近日期 7 天内视为新鲜（覆盖节假日）
SLEEP_BETWEEN = 0.35        # 逐股限速，礼貌抓取

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


# ── 基础工具 ──────────────────────────────────────────────

def _http_json(url: str, params: dict[str, str], attempts: int = 10) -> dict[str, Any] | None:
    """GET JSON：requests 与 curl 交替重试（本地代理对 push2his 波动极大，
    单次成功率低；失败返回快，多轮重试整体可靠性足够）。"""
    import urllib.parse

    qs = urllib.parse.urlencode(params)
    for i in range(attempts):
        try:
            import requests

            r = requests.get(url, params=params, headers=_HEADERS, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            pass
        try:
            cmd = ["curl", "-s", "--max-time", "10",
                   "-H", "User-Agent: " + _HEADERS["User-Agent"], f"{url}?{qs}"]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if out.returncode == 0 and out.stdout.strip().startswith("{"):
                return json.loads(out.stdout)
        except Exception:
            pass
        if i < attempts - 1:
            time.sleep(0.3 + 0.2 * i)
    return None


def _norm_name(s: Any) -> str:
    """归一化证券名称：去空白与星号、去 -W/-S 后缀（港股常见）。"""
    t = re.sub(r"[\s*＊·]+", "", str(s or ""))
    t = re.sub(r"-(W|S|SS)$", "", t, flags=re.IGNORECASE)
    return t.upper()


def _name_matches(expected: Any, fetched: Any) -> bool:
    a, b = _norm_name(expected), _norm_name(fetched)
    if not a or not b:
        return False
    return a == b or (len(a) >= 2 and a in b) or (len(b) >= 2 and b in a)


def _market_file(code: str, market: str) -> Path:
    suffix = {"A": "", "HK": "_hk", "KR": "_kr", "US": "_us"}[market]
    return SERIES_DIR / f"{code}{suffix}_qfq.csv"


def _is_fresh(path: Path, max_stale_days: int = MAX_STALE_DAYS) -> bool:
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
        last = datetime.strptime(rows[-1][0], "%Y-%m-%d")
    except (ValueError, IndexError):
        return False
    return last >= datetime.now() - timedelta(days=max_stale_days)


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日期", "收盘"])
        for row in rows:
            date, close = str(row[0]), str(row[1])
            try:
                if not float(close) > 0:
                    continue
            except ValueError:
                continue
            writer.writerow([date, close])


# ── 各市场抓取 ────────────────────────────────────────────

def _em_klines(secid: str) -> tuple[str, list[list[str]]] | None:
    """东财日 K：返回 (证券名称, [[日期, 收盘], ...])，无数据返回 None。"""
    beg = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    data = _http_json(EM_KLINE_URL, {
        "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f53",
        "klt": "101", "fqt": "1", "beg": beg, "end": "20500101",
    })
    d = (data or {}).get("data") or {}
    klines = [k.split(",")[:2] for k in (d.get("klines") or []) if "," in k]
    if not klines:
        return None
    return str(d.get("name") or ""), klines


def _naver_kr(code: str) -> list[list[str]] | None:
    """Naver Finance 取韩股（KRX）日线（雅虎 chart 接口对数据中心 IP 限流）。"""
    beg = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    data = _http_json(NAVER_URL.format(code=code),
                      {"startDateTime": beg, "endDateTime": "20991231"})
    if not isinstance(data, list):
        return None
    rows = []
    for item in data:
        date, close = item.get("localDate"), item.get("closePrice")
        if not date or close is None or float(close) <= 0:
            continue
        d = str(date)
        rows.append([f"{d[:4]}-{d[4:6]}-{d[6:8]}", str(float(close))])
    return rows or None


# ── 市场识别与主入口 ──────────────────────────────────────

def _resolve_digit(code: str, name: str):
    """纯数字 6 位码：按 A 股 → 港股 → 韩股顺序，用名称校验消歧。

    返回 (market, rows) 或 None。A 股名称对不上但港股/韩股都查不到时，
    若 A 股数据本身新鲜，也接受（基金季报名称与交易所简称偶有出入）。
    """
    a_res = _em_klines(("1." if code.startswith(("6", "9")) else "0.") + code)
    if a_res and _name_matches(name, a_res[0]):
        return "A", a_res[1]

    # 港股：内部码 = "0" + 5 位港股代码（000700 → 00700、000038 → 00038）
    hk_res = None
    if code.startswith("0") and len(code) == 6:
        hk_res = _em_klines("116." + code[1:].zfill(5))
        if hk_res and _name_matches(name, hk_res[0]):
            return "HK", hk_res[1]

    kr_rows = _naver_kr(code)
    if kr_rows:
        return "KR", kr_rows

    # 回退：A 股名称对不上（季报简称差异），但 A 股数据存在且新鲜
    if a_res and hk_res is None:
        try:
            fresh = (datetime.now() - datetime.strptime(a_res[1][-1][0], "%Y-%m-%d")).days <= MAX_STALE_DAYS
        except ValueError:
            fresh = False
        if fresh:
            return "A", a_res[1]
    return None


def _resolve_us(code: str):
    """字母数字码（"00" + ticker）：依次尝试 NASDAQ / NYSE / AMEX。

    过长代码（如 ISIN「KR7000660001」）不是 ticker，直接放弃——
    price_estimate 里的别名机制会用站内代码补齐。
    """
    ticker = code.lstrip("0")
    if not re.fullmatch(r"[A-Za-z0-9]{1,5}", ticker):
        return None
    for mkt in ("105", "106", "107"):
        res = _em_klines(f"{mkt}.{ticker}")
        if res:
            return "US", res[1]
    return None


def ensure_stock_series(
    items: Iterable[tuple[str, Any]] | dict[str, Any],
    verbose: bool = True,
) -> tuple[int, int]:
    """确保这些股票（code → 名称）的本地前复权日线存在且新鲜。

    返回 (成功只数, 失败只数)。失败不抛异常，页面会自动回退到
    「重仓基金净值代理」口径（只有估算涨跌、没有绝对价）。
    """
    pairs = list(items.items()) if isinstance(items, dict) \
        else [(str(c), n) for c, n in items]

    meta: dict[str, dict[str, Any]] = {}
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}

    ok = fail = skipped = 0
    for code, name in sorted(pairs):
        code = str(code).strip()
        if not code or code == "000000":
            continue
        info = meta.get(code) or {}
        # 已有同市场新鲜序列且名称对得上（上次抓取已校验）→ 跳过
        if info and _is_fresh(_market_file(code, info.get("market", "A"))) \
                and (info.get("verified") or _name_matches(name, info.get("name"))):
            skipped += 1
            continue

        result = (_resolve_us(code) if not code.isdigit()
                  else _resolve_digit(code, str(name)))
        if not result:
            fail += 1
            if verbose:
                print(f"  [行情] {code} {name} 未能定位行情（保留代理口径）")
            meta.pop(code, None)
            continue

        market, rows = result
        # 港/韩/美股覆盖同名 A 股缓存，避免 price_estimate 读到错市场数据
        if market != "A" and _market_file(code, "A").exists():
            try:
                _market_file(code, "A").unlink()
            except OSError:
                pass
        _write_csv(_market_file(code, market), rows)
        meta[code] = {"market": market, "verified": True, "name": str(name)}
        ok += 1
        time.sleep(SLEEP_BETWEEN)

    if verbose:
        print(f"  [行情] 股票日线更新：成功 {ok} / 跳过(缓存新鲜) {skipped}"
              f" / 失败 {fail}（东财 A/HK/US + Naver KR）")
    try:
        SERIES_DIR.mkdir(parents=True, exist_ok=True)
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    except OSError:
        pass
    return ok, fail


if __name__ == "__main__":
    import sys

    args = [a.strip() for a in sys.argv[1:] if a.strip()]
    if args:
        ensure_stock_series({a: "" for a in args})
    else:
        print("用法: python fetch_stock_series.py 000063 000700 00TSM ...")
