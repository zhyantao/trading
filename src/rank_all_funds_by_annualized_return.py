#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对所有基金按照“年化收益率”排序（默认：成立来年化）。

数据来源：东方财富-开放基金排行 rankhandler.aspx（公开接口）。
说明：
  - 接口返回包含：基金代码、基金简称、净值、各区间收益、成立来、成立日等字段
  - “成立来年化”按复合年化计算：
        annualized = (1 + total_return) ** (365 / days_since_inception) - 1
    其中 total_return = 成立来 / 100

输出：out/基金年化收益率排序_YYYYMMDD.csv（UTF-8 with BOM）
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import demjson3 as demjson


def _one_year_ago_yyyymmdd(d: date) -> str:
    # 与 AkShare 的逻辑类似：用 365 天近似回退一年
    return (d - timedelta(days=365)).strftime("%Y-%m-%d")


def fetch_open_fund_rank_raw(symbol: str = "全部", pn: int = 30000) -> pd.DataFrame:
    """
    获取开放基金排行原始数据，并保留“成立日”等 AkShare 丢弃的字段。
    """
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
        "op": "ph",
        "dt": "kf",
        "ft": type_map[symbol][0],
        "rs": "",
        "gs": "0",
        "sc": type_map[symbol][1],
        "st": "desc",
        "sd": last_date,
        "ed": current_date,
        "qdii": "",
        "tabSubtype": ",,,,,",
        "pi": "1",
        "pn": str(pn),
        "dx": "1",
        "v": "0.1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://fund.eastmoney.com/fundguzhi.html",
    }
    r = requests.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    text = r.text

    # 返回内容形如：var rankData = {...}; 取 {...} 部分
    idx = text.find("{")
    if idx == -1:
        raise ValueError(f"API 返回格式异常，未找到 JSON 起始位置")
    j = demjson.decode(text[idx: -1])
    temp_df = pd.DataFrame(j["datas"])
    split_df = temp_df.iloc[:, 0].str.split(",", expand=True)

    # 该接口目前常见为 25 列（不同时间可能略有变化）
    # 参考：AkShare fund_open_fund_rank_em 的列映射 + 补充“成立日”等
    # 我们只取关键字段并保留原始成立日/基金类型等可能信息。
    col_map = {
        0: "基金代码",
        1: "基金简称",
        3: "日期",
        4: "单位净值",
        5: "累计净值",
        6: "日增长率",
        7: "近1周",
        8: "近1月",
        9: "近3月",
        10: "近6月",
        11: "近1年",
        12: "近2年",
        13: "近3年",
        14: "今年来",
        15: "成立来",
        16: "成立日",
        20: "手续费",
        24: "近1年同类排名百分位(原始)",
    }

    keep = [i for i in sorted(col_map.keys()) if i < split_df.shape[1]]
    df = split_df.iloc[:, keep].rename(columns={i: col_map[i] for i in keep})

    # 类型转换
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["成立日"] = pd.to_datetime(df["成立日"], errors="coerce").dt.date

    for c in [
        "单位净值",
        "累计净值",
        "日增长率",
        "近1周",
        "近1月",
        "近3月",
        "近6月",
        "近1年",
        "近2年",
        "近3年",
        "今年来",
        "成立来",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def calc_annualized_since_inception(df: pd.DataFrame) -> pd.Series:
    """
    成立来年化复合收益率（%）
    """
    if "成立来" not in df.columns or "成立日" not in df.columns:
        raise KeyError("缺少 成立来 或 成立日 字段，无法计算成立来年化")

    today = date.today()
    days = (pd.to_datetime(today) - pd.to_datetime(df["成立日"])).dt.days
    total = df["成立来"] / 100.0

    # 防止除零/负数：days<=0 或 total<=-1 均视为无效
    valid = (days > 0) & (total > -1)
    # 用 NaN 初始化 float 列，避免 pd.NA -> float 转换报错
    ann = pd.Series(float("nan"), index=df.index, dtype="float64")
    ann.loc[valid] = ((1.0 + total.loc[valid]) ** (365.0 / days.loc[valid]) - 1.0) * 100.0
    return ann


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbol",
        default="全部",
        choices=["全部", "股票型", "混合型", "债券型", "指数型", "QDII", "FOF", "LOF"],
        help="基金类型范围，默认 全部",
    )
    parser.add_argument(
        "--out",
        default="",
        help="输出 CSV 路径；不填则写入 out/基金年化收益率排序_YYYYMMDD.csv",
    )
    parser.add_argument(
        "--composite",
        action="store_true",
        help="使用多因子复合评分（Dalio 框架）替代成立来年化排名",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (project_root / out_path).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        out_path = out_dir / f"基金年化收益率排序_{stamp}.csv"

    df = fetch_open_fund_rank_raw(symbol=args.symbol, pn=30000)
    # 成立天数：用于用户后续筛除“太新”的基金（新基金年化会被极端放大）
    df["成立天数"] = (pd.to_datetime(date.today()) - pd.to_datetime(df["成立日"])).dt.days
    df["成立来年化"] = calc_annualized_since_inception(df)

    ranked = df[df["成立来年化"].notna()].copy()

    if args.composite:
        from factor_scoring import compute_fund_composite_score
        ranked["_composite"] = compute_fund_composite_score(ranked)
        ranked = ranked.sort_values("_composite", ascending=False)
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", "复合得分(Dalio多因子)")
        ranked = ranked.drop(columns=["_composite"])
    else:
        ranked = ranked.sort_values(["成立来年化", "成立来"], ascending=[False, False])
        ranked.insert(0, "排名", range(1, len(ranked) + 1))
        ranked.insert(0, "数据生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ranked.insert(1, "排名指标", "成立来年化")

    ranked.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成：{out_path}  行数={len(ranked):,}  列数={len(ranked.columns)}")


if __name__ == "__main__":
    main()
