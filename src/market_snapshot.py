#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
当日全市场快照：一份数据，多处复用。

原先 ``build_manager_fund_returns.py``（AkShare 封装的 rankhandler）与
``rank_all_funds_by_annualized_return.py``（自行解析的 rankhandler）在同一天
各拉一次约两万只基金的全市场排行 —— 内容高度重复，却产生两次大请求。

本模块把 rankhandler 的抓取收敛为「当天一次」，落盘到
``out/cache_meta/``（由 GitHub Actions 的 actions/cache 跨天持久化），
两个脚本读取同一份 DataFrame，只是各自投影成自己需要的列结构。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def _one_year_ago_yyyymmdd(d: date) -> str:
    return (d - timedelta(days=365)).strftime("%Y-%m-%d")


def fetch_open_fund_rank_raw(symbol: str = "全部", pn: int = 30000) -> pd.DataFrame:
    """获取开放基金排行原始数据，保留 AkShare 丢弃的「成立日」等字段。"""
    import demjson3 as demjson
    import requests

    today = date.today()
    current_date = today.strftime("%Y-%m-%d")
    last_date = _one_year_ago_yyyymmdd(today)

    url = "https://fund.eastmoney.com/data/rankhandler.aspx"
    type_map = {
        "全部": ["all", "1nzf"],
        "股票型": ["gp", "1nzf"],
        "混合型": ["hh", "1nzf"],
        "债券型": ["zq", "1nzf"],
        "指数型": ["zs", "1nzf"],
        "QDII": ["qdii", "1nzf"],
        "LOF": ["lof", "1nzf"],
        "FOF": ["fof", "1nzf"],
    }
    if symbol not in type_map:
        raise ValueError(f"symbol 必须为 {list(type_map.keys())} 之一，当前={symbol}")

    params = {
        "op": "ph", "dt": "kf", "ft": type_map[symbol][0], "rs": "", "gs": "0",
        "sc": type_map[symbol][1], "st": "desc", "sd": last_date, "ed": current_date,
        "qdii": "", "tabSubtype": ",,,,,", "pi": "1", "pn": str(pn), "dx": "1", "v": "0.1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://fund.eastmoney.com/fundguzhi.html",
    }
    r = requests.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    text = r.text

    idx = text.find("{")
    if idx == -1:
        raise ValueError("API 返回格式异常，未找到 JSON 起始位置")
    j = demjson.decode(text[idx:-1])
    temp_df = pd.DataFrame(j["datas"])
    split_df = temp_df.iloc[:, 0].str.split(",", expand=True)

    col_map = {
        0: "基金代码", 1: "基金简称", 3: "日期", 4: "单位净值", 5: "累计净值",
        6: "日增长率", 7: "近1周", 8: "近1月", 9: "近3月", 10: "近6月",
        11: "近1年", 12: "近2年", 13: "近3年", 14: "今年来", 15: "成立来",
        16: "成立日", 20: "手续费", 24: "近1年同类排名百分位(原始)",
    }
    keep = [i for i in sorted(col_map) if i < split_df.shape[1]]
    df = split_df.iloc[:, keep].rename(columns={i: col_map[i] for i in keep})

    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["成立日"] = pd.to_datetime(df["成立日"], errors="coerce").dt.date
    for c in ["单位净值", "累计净值", "日增长率", "近1周", "近1月", "近3月",
              "近6月", "近1年", "近2年", "近3年", "今年来", "成立来"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# 与 AkShare ``fund_open_fund_rank_em`` 对齐的列顺序，保证下游明细表列不变
_AK_RANK_COLUMNS = [
    "序号", "基金代码", "基金简称", "日期", "单位净值", "累计净值", "日增长率",
    "近1周", "近1月", "近3月", "近6月", "近1年", "近2年", "近3年",
    "今年来", "成立来", "自定义", "手续费",
]


def get_fund_rank_snapshot(symbol: str = "全部") -> pd.DataFrame:
    """当天只联网一次；同一进程/同一 CI 运行内的后续调用直接读缓存。"""
    from incremental import MetaCache, STATS, force_refresh

    meta = MetaCache()
    key = f"fund_rank_{symbol}"
    if not force_refresh():
        cached = meta.read_df(key, 0, dtype={"基金代码": str})
        if cached is not None and not cached.empty:
            STATS["hit"] = STATS.get("hit", 0) + 1
            print(f"[snapshot] 复用当日全市场排行快照（{len(cached):,} 行，零网络请求）")
            return cached

    df = fetch_open_fund_rank_raw(symbol=symbol, pn=30000)
    if df.empty:
        raise RuntimeError("全市场基金排行为空，疑似接口异常")
    df["基金代码"] = df["基金代码"].astype(str).str.zfill(6)
    meta.write_df(key, df)
    STATS["full"] = STATS.get("full", 0) + 1
    print(f"[snapshot] 已缓存当日全市场排行快照（{len(df):,} 行），后续脚本复用")
    return df


def as_akshare_rank_columns(df: pd.DataFrame) -> pd.DataFrame:
    """投影成 AkShare ``fund_open_fund_rank_em`` 的列结构，供经理明细表 merge。"""
    rank = df.copy()
    if "序号" not in rank.columns:
        rank.insert(0, "序号", range(1, len(rank) + 1))
    rank["自定义"] = ""
    for c in ("成立日", "近1年同类排名百分位(原始)"):
        if c in rank.columns:
            rank = rank.drop(columns=[c])
    extra = [c for c in rank.columns if c not in _AK_RANK_COLUMNS]
    if extra:
        rank = rank.drop(columns=extra)
    return rank[[c for c in _AK_RANK_COLUMNS if c in rank.columns]]
