#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量数据缓存层：让每日流水线只拉取「上次缓存之后新增」的数据。

问题背景
--------
原先回测把行情缓存写成 out/cache_prices/nav_{code}_{start}_{end}.csv，
文件名里含运行日期，而 end 恒为今天 —— 于是缓存永不命中；再加上 out/ 不进
仓库、CI 每次都是全新 runner，等于每天把全部标的的完整历史重拉一遍。

本模块提供
----------
* ``SeriesCache``          : 按标的固定命名的时序缓存，只补缺口，可跨天持久
* ``MetaCache``            : 带 TTL 的快照缓存（全市场排行 / 经理列表 / 交易日历）
* ``fetch_fund_nav_range`` : 天天基金 F10 lsjz 按日期区间增量拉取净值
* ``get_trade_calendar`` / ``get_manager_list`` / ``latest_nav_date`` : 低频数据共享缓存

设计原则：所有网络失败都回退到调用方提供的全量抓取函数（或沿用旧缓存），
绝不因为缓存层异常而阻断 CI 当天的数据发布。
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SERIES_DIR = ROOT / "out" / "cache_series"
META_DIR = ROOT / "out" / "cache_meta"
LEGACY_DIR = ROOT / "out" / "cache_prices"

# 本次进程内的请求统计（每个子进程各自打印一份）
STATS: dict[str, int] = {"hit": 0, "delta": 0, "full": 0, "reuse": 0, "fallback": 0}


def _bump(k: str) -> None:
    STATS[k] = STATS.get(k, 0) + 1


def report(prefix: str = "[incremental]") -> None:
    """打印本进程的网络请求统计，便于在 CI 日志里直观看到增量效果。"""
    print(
        f"{prefix} 缓存命中 {STATS['hit']} 次（零请求）、增量补数 {STATS['delta']} 次、"
        f"全量建仓 {STATS['full']} 次、当日已刷新复用 {STATS['reuse']} 次、失败沿用旧缓存 {STATS['fallback']} 次"
    )


def force_refresh() -> bool:
    """环境变量 INCREMENTAL_FORCE=1 时强制重新联网（手动重跑用）。"""
    return os.environ.get("INCREMENTAL_FORCE", "").strip() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# 带 TTL 的元数据 / 快照缓存
# ---------------------------------------------------------------------------


class MetaCache:
    """键值缓存：value 为 DataFrame 或可 JSON 序列化的对象，附带 updated_at。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else META_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        d = self.root / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def updated_at(self, key: str) -> datetime | None:
        fp = self._dir(key) / "meta.json"
        if not fp.exists():
            return None
        try:
            return datetime.fromisoformat(json.loads(fp.read_text(encoding="utf-8"))["updated_at"])
        except Exception:
            return None

    def fresh(self, key: str, ttl_days: float = 0) -> bool:
        """ttl_days=0 表示「当天有效」，>0 表示 N*24 小时内有效。"""
        ts = self.updated_at(key)
        if ts is None or force_refresh():
            return False
        now = datetime.now()
        if ttl_days <= 0:
            return ts.date() == now.date()
        return now - ts <= timedelta(days=ttl_days)

    def _stamp(self, key: str) -> None:
        (self._dir(key) / "meta.json").write_text(
            json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )

    def read_df(self, key: str, ttl_days: float = 0, **read_kwargs) -> pd.DataFrame | None:
        if not self.fresh(key, ttl_days):
            return None
        fp = self._dir(key) / "data.csv.gz"
        if not fp.exists() or fp.stat().st_size == 0:
            return None
        try:
            return pd.read_csv(fp, compression="gzip", **read_kwargs)
        except Exception:
            return None

    def write_df(self, key: str, df: pd.DataFrame) -> None:
        tmp = self._dir(key) / "data.csv.gz.tmp"
        df.to_csv(tmp, index=False, compression="gzip", encoding="utf-8")
        tmp.replace(self._dir(key) / "data.csv.gz")
        self._stamp(key)

    def read_json(self, key: str, ttl_days: float = 0):
        if not self.fresh(key, ttl_days):
            return None
        fp = self._dir(key) / "data.json"
        if not fp.exists():
            return None
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None

    def write_json(self, key: str, value) -> None:
        (self._dir(key) / "data.json").write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
        self._stamp(key)


# ---------------------------------------------------------------------------
# 时序缓存（核心）
# ---------------------------------------------------------------------------


class SeriesCache:
    """
    以「标的」为单位持久化的完整历史序列，文件名不含运行日期。

    ``get`` 的三种结果：
      1. 缓存已覆盖到 end          -> 直接返回切片，零网络请求
      2. 缓存有历史但缺尾部        -> 只请求 (最后日期, end] 这一段，合并写回
      3. 完全没有缓存              -> 一次性建立历史缓存（之后进入 1/2）
    """

    def __init__(
        self,
        root: Path | None = None,
        meta_root: Path | None = None,
        migrate: bool = True,
    ) -> None:
        self.root = Path(root) if root else SERIES_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = MetaCache(meta_root)
        self.migrate = migrate

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.root / f"{safe}.csv"

    def load(self, key: str) -> pd.Series:
        fp = self._path(key)
        if fp.exists() and fp.stat().st_size > 0:
            try:
                df = pd.read_csv(fp)
                if not df.empty and {"日期", "value"}.issubset(df.columns):
                    idx = pd.to_datetime(df["日期"], errors="coerce").dt.date
                    s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values, index=idx, name=key)
                    return s.dropna().sort_index()
            except Exception:
                pass
        # 迁移旧版「带日期戳」的缓存，避免升级当天又全量拉一遍
        return self._migrate_legacy(key)

    def _migrate_legacy(self, key: str) -> pd.Series:
        if not self.migrate or not LEGACY_DIR.is_dir():
            return pd.Series(dtype="float64", name=key)
        candidates = sorted(
            LEGACY_DIR.glob(f"{key}_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for old in candidates[:3]:
            try:
                df = pd.read_csv(old)
                if df.empty or "日期" not in df.columns:
                    continue
                val_col = next(
                    (c for c in ("单位净值", "收盘", "value") if c in df.columns),
                    df.columns[-1],
                )
                idx = pd.to_datetime(df["日期"], errors="coerce").dt.date
                s = pd.Series(pd.to_numeric(df[val_col], errors="coerce").values, index=idx, name=key)
                s = s.dropna().sort_index()
                if s.empty:
                    continue
                self.save(key, s)
                print(f"[incremental] 迁移旧缓存 {old.name} -> {self._path(key).name} ({len(s)} 行)")
                return s
            except Exception:
                continue
        return pd.Series(dtype="float64", name=key)

    def save(self, key: str, s: pd.Series) -> None:
        if s is None or s.empty:
            return
        s = s.sort_index()
        s = s[~s.index.duplicated(keep="last")]
        fp = self._path(key)
        tmp = fp.with_suffix(".csv.tmp")
        pd.DataFrame(
            {"日期": [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in s.index],
             "value": list(s.values)}
        ).to_csv(tmp, index=False, encoding="utf-8")
        tmp.replace(fp)

    def last_date(self, key: str) -> date | None:
        s = self.load(key)
        return None if s.empty else s.index.max()

    @staticmethod
    def _slice(s: pd.Series, start: date | None, end: date | None) -> pd.Series:
        if s.empty:
            return s
        if start is not None:
            s = s[s.index >= start]
        if end is not None:
            s = s[s.index <= end]
        return s

    def get(
        self,
        key: str,
        start: date,
        end: date,
        fetch_range: Callable[[date, date], pd.Series] | None = None,
        fetch_full: Callable[[], pd.Series] | None = None,
        daily_refresh: bool = False,
        rebuild_after_days: int | None = None,
    ) -> pd.Series:
        """
        fetch_range(d0, d1) 返回该日期区间的数据（增量通道，优先使用）。
        fetch_full()        返回完整历史（首建缓存 / 无增量接口时的通道）。
        daily_refresh=True  表示 fetch_full 一天只需调用一次（如只能全量拉的指数日线）。
        rebuild_after_days  每隔 N 天重建一次缓存，用于前复权行情：除权会改变
                            整条历史价格，长期只追加尾部会让新老价格基准不一致。
        """
        end = min(end, date.today())
        cached = self.load(key)
        if rebuild_after_days and not cached.empty:
            built_at = self.meta.updated_at(f"built:{key}")
            if built_at is None or (datetime.now() - built_at).days >= rebuild_after_days:
                print(f"[incremental] {key} 缓存满 {rebuild_after_days} 天，重建一次以对齐前复权基准")
                self._path(key).unlink(missing_ok=True)
                cached = pd.Series(dtype="float64", name=key)
        last = cached.index.max() if not cached.empty else None

        # 只有全量接口、且当天已经刷新过 -> 零请求
        if daily_refresh and last is not None and self.meta.fresh(f"series:{key}", 0):
            _bump("reuse")
            return self._slice(cached, start, end)

        # 缓存已覆盖到 end -> 零请求
        if last is not None and last >= end and not force_refresh():
            _bump("hit")
            return self._slice(cached, start, end)

        if cached.empty:
            # 首次建仓：能按区间拉就直接拉 [start, end]，否则走全量接口
            built = self._fetch(fetch_range, fetch_full, start, end)
            if built is not None and not built.empty:
                self.save(key, built)
                _bump("full")
                if daily_refresh:
                    self.meta.write_json(f"series:{key}", {"refreshed": True})
                if rebuild_after_days:
                    self.meta.write_json(f"built:{key}", {"rebuilt": True})
                return self._slice(self.load(key), start, end)
            return pd.Series(dtype="float64", name=key)

        # 有历史，只补缺口
        delta_start = last + timedelta(days=1)
        if delta_start > end:
            _bump("hit")
            return self._slice(cached, start, end)

        # 有增量接口时，补缺口失败就沿用缓存（绝不回退成全量重拉）；
        # 没有增量接口（如只能全量返回的新浪指数日线）才允许整体刷新一次。
        delta = self._fetch(
            fetch_range, fetch_full if fetch_range is None else None, delta_start, end
        )
        if delta is None or delta.empty:
            # 净值尚未发布 / 接口暂时不可用：沿用已有历史，不丢数据
            _bump("fallback" if delta is None else "hit")
            if daily_refresh:
                self.meta.write_json(f"series:{key}", {"refreshed": True})
            return self._slice(cached, start, end)

        merged = pd.concat([cached, delta]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        self.save(key, merged)
        _bump("delta")
        if daily_refresh:
            self.meta.write_json(f"series:{key}", {"refreshed": True})
        return self._slice(self.load(key), start, end)

    @staticmethod
    def _fetch(
        fetch_range: Callable[[date, date], pd.Series] | None,
        fetch_full: Callable[[], pd.Series] | None,
        d0: date,
        d1: date,
    ) -> pd.Series | None:
        if fetch_range is not None:
            try:
                return fetch_range(d0, d1)
            except Exception as exc:
                print(f"[incremental][WARN] 区间抓取失败 {d0}~{d1}: {type(exc).__name__}: {exc}")
        if fetch_full is not None:
            try:
                return fetch_full()
            except Exception as exc:
                print(f"[incremental][WARN] 全量抓取失败: {type(exc).__name__}: {exc}")
        return None


# ---------------------------------------------------------------------------
# 天天基金 F10 历史净值：按日期区间增量
# ---------------------------------------------------------------------------

_F10_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/jjjz_{code}.html",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _f10_get(code: str, params: dict) -> dict:
    import requests

    headers = dict(_F10_HEADERS)
    headers["Referer"] = _F10_HEADERS["Referer"].format(code=code)
    r = requests.get(
        "https://api.fund.eastmoney.com/f10/lsjz",
        params=params,
        headers=headers,
        timeout=(5, 12),
    )
    r.raise_for_status()
    return r.json()


def fetch_fund_nav_range(code: str, start: date, end: date) -> pd.Series:
    """只取 [start, end] 的基金单位净值（F10 lsjz，分页）。"""
    if start > end:
        return pd.Series(dtype="float64", name=code)

    rows: list[tuple[date, float]] = []
    page_size = 50
    total = None
    for page in range(1, 21):
        data = _f10_get(
            code,
            {
                "fundCode": code,
                "pageIndex": page,
                "pageSize": page_size,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            },
        )
        payload = data.get("Data") or {}
        chunk = payload.get("LSJZList") or []
        if total is None:
            try:
                total = int(data.get("TotalCount") or payload.get("TotalCount") or 0)
            except (TypeError, ValueError):
                total = 0
        for item in chunk:
            d = pd.to_datetime(item.get("FSRQ"), errors="coerce")
            v = pd.to_numeric(item.get("DWJZ"), errors="coerce")
            if pd.isna(d) or pd.isna(v):
                continue
            rows.append((d.date(), float(v)))
        if len(chunk) < page_size or (total and len(rows) >= total):
            break
        time.sleep(0.05)

    if not rows:
        return pd.Series(dtype="float64", name=code)
    df = pd.DataFrame(rows, columns=["日期", "value"]).drop_duplicates("日期", keep="last")
    return pd.Series(df["value"].values, index=df["日期"].values, name=code).sort_index()


def latest_nav_date(probe_code: str = "000001") -> date | None:
    """探测市场已发布的最新净值日期，当日只请求一次。

    回测把抓取终点钳制到这一天，可以避免「净值未发布导致每个标的都空跑一次」。
    探测失败返回 None，调用方回退到 date.today()。
    """
    meta = MetaCache()
    cached = meta.read_json("nav_asof", 0)
    if isinstance(cached, dict) and cached.get("date"):
        try:
            return date.fromisoformat(cached["date"])
        except ValueError:
            pass
    try:
        data = _f10_get(probe_code, {"fundCode": probe_code, "pageIndex": 1, "pageSize": 1})
        rows = (data.get("Data") or {}).get("LSJZList") or []
        if not rows or not rows[0].get("FSRQ"):
            return None
        d = pd.to_datetime(rows[0]["FSRQ"]).date()
        meta.write_json("nav_asof", {"date": d.isoformat(), "code": probe_code})
        return d
    except Exception as exc:
        print(f"[incremental][WARN] 最新净值日期探测失败: {type(exc).__name__}: {exc}")
        return None


def effective_end(end: date) -> date:
    """把抓取终点钳制到已发布的最新净值日；探测失败则原样返回。"""
    d = latest_nav_date()
    return min(end, d) if d else end


# ---------------------------------------------------------------------------
# 低频共享数据：交易日历 / 基金经理列表
# ---------------------------------------------------------------------------


def get_trade_calendar(ttl_days: float = 30) -> pd.Series:
    """交易日历每年才变一次，30 天内复用缓存；两个回测脚本共享同一份。"""
    meta = MetaCache()
    cached = meta.read_df("trade_calendar", ttl_days)
    if cached is not None and not cached.empty and "trade_date" in cached.columns:
        _bump("hit")
        return pd.to_datetime(cached["trade_date"]).sort_values().reset_index(drop=True)

    import akshare as ak

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            cal = ak.tool_trade_date_hist_sina()
            s = pd.to_datetime(cal["trade_date"]).sort_values().reset_index(drop=True)
            meta.write_df("trade_calendar", pd.DataFrame({"trade_date": s.dt.strftime("%Y-%m-%d")}))
            _bump("full")
            return s
        except Exception as exc:
            last_exc = exc
            time.sleep(2)
    # 网络失败时允许用过期的日历，总比中断好
    stale = meta.read_df("trade_calendar", 3650)
    if stale is not None and not stale.empty and "trade_date" in stale.columns:
        print(f"[incremental][WARN] 交易日历联网失败，改用历史缓存: {last_exc}")
        _bump("fallback")
        return pd.to_datetime(stale["trade_date"]).sort_values().reset_index(drop=True)
    raise RuntimeError(f"交易日历获取失败且无缓存: {last_exc}")


def get_manager_list(ttl_days: float = 7) -> pd.DataFrame:
    """全市场基金经理列表变动很慢，7 天内复用缓存。"""
    meta = MetaCache()
    cached = meta.read_df("fund_managers", ttl_days, dtype={"现任基金代码": str})
    if cached is not None and not cached.empty:
        _bump("hit")
        return cached

    import akshare as ak

    df = ak.fund_manager_em()
    df["现任基金代码"] = df["现任基金代码"].astype(str)
    meta.write_df("fund_managers", df)
    _bump("full")
    return df


def get_manager_id_map(ttl_days: float = 7) -> pd.DataFrame:
    """全市场基金经理 ID 映射（姓名+所属公司 → 经理ID / 公司代码）。

    akshare 的 fund_manager_em 会丢掉原始接口里的经理 ID，这里直接抓
    FundDataPortfolio_Interface 的原始 JSON，取出前三个字段：
    [经理ID, 姓名, 公司代码, 所属公司, ...]。
    经理 ID 用于拼天天基金个人主页 https://fund.eastmoney.com/manager/{id}.html，
    公司代码用于拼基金公司页 https://fund.eastmoney.com/company/{code}.html。
    失败时返回空表，页面外链自动回退为搜索。
    """
    meta = MetaCache()
    cached = meta.read_df("fund_manager_ids", ttl_days, dtype=str)
    if cached is not None and not cached.empty and {"姓名", "所属公司", "经理ID"}.issubset(cached.columns):
        _bump("hit")
        return cached

    import requests

    try:
        import demjson3 as demjson
    except ImportError:  # pragma: no cover - 兼容旧环境
        import demjson as demjson  # type: ignore

    url = "https://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx"
    params = {"dt": "14", "mc": "returnjson", "ft": "all", "pn": "500", "pi": 1, "sc": "abbname", "st": "asc"}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    rows: list[dict] = []
    try:
        with requests.Session() as sess:
            resp = sess.get(url, params=params, timeout=20, headers=headers)
            payload = demjson.decode(resp.text.split("=", 1)[1])
            total_pages = int(payload.get("pages", 1))
            for page in range(1, total_pages + 1):
                if page > 1:
                    params["pi"] = page
                    resp = sess.get(url, params=params, timeout=20, headers=headers)
                    payload = demjson.decode(resp.text.split("=", 1)[1])
                for rec in payload.get("data", []):
                    # 原始行：[经理ID, 姓名, 公司代码, 所属公司, 现任基金代码, ...]
                    if len(rec) >= 4 and rec[0] and rec[1]:
                        rows.append({
                            "经理ID": str(rec[0]),
                            "姓名": str(rec[1]),
                            "公司代码": str(rec[2] or ""),
                            "所属公司": str(rec[3] or ""),
                        })
    except Exception as exc:  # noqa: BLE001 - 网络失败不应拖垮主管道
        print(f"[incremental][WARN] 经理 ID 映射获取失败: {exc}")
        _bump("fallback")
        return pd.DataFrame(columns=["经理ID", "姓名", "公司代码", "所属公司"])

    df = pd.DataFrame(rows, columns=["经理ID", "姓名", "公司代码", "所属公司"])
    df = df.drop_duplicates(subset=["姓名", "所属公司"], keep="first")
    meta.write_df("fund_manager_ids", df)
    _bump("full")
    return df
