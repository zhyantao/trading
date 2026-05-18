#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每天生成“基金经理调仓信号”报告（不构成投资建议）。

核心思路：
1) 读取 out/ 下最新的“绩优基金经理_基金Top3_*.csv”，得到需要跟踪的经理及其 Top3 基金
2) 对每只基金抓取“重大变动”（累计买入/累计卖出）的最新季度数据
3) 将 Top3 基金的调仓数据按经理聚合到股票层面（占期初基金资产净值比例求和）
4) 读取 out/我的持仓.csv，对照输出“继续关注/关注买入/关注卖出”标签（仅为信号提示）

输出（out/）：
  - 每日调仓信号_YYYYMMDD.csv   （含：持仓对照 + 全市场机会Top）
  - 每日调仓信号_YYYYMMDD.md    （简短摘要）
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


def _latest(out_dir: Path, pattern: str) -> Path:
    files = sorted(out_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"未在 {out_dir} 找到文件：{pattern}")
    return files[-1]


def _quarter_key(s: str) -> tuple[int, int]:
    m = re.search(r"(\d{4})年(\d)季度", str(s))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def fetch_latest_change_one_fund(
    fund_code: str,
    indicator: str,
    years_back: int = 6,
    sleep_s: float = 0.2,
) -> pd.DataFrame:
    """
    获取某基金“重大变动”最新季度数据（累计买入/累计卖出）。
    """
    import akshare as ak

    this_year = datetime.now().year
    last_exc: Exception | None = None
    for y in range(this_year, this_year - years_back, -1):
        try:
            df = ak.fund_portfolio_change_em(symbol=fund_code, indicator=indicator, date=str(y))
            time.sleep(sleep_s)
            if df is None or df.empty:
                continue
            df = df.copy()
            df["_qkey"] = df["季度"].map(_quarter_key)
            latest = df["_qkey"].max()
            df = df[df["_qkey"] == latest].copy()
            # 统一数值字段
            if "占期初基金资产净值比例" in df.columns:
                df["占期初基金资产净值比例"] = pd.to_numeric(df["占期初基金资产净值比例"], errors="coerce")
            if "本期累计买入金额" in df.columns:
                df["本期累计买入金额"] = pd.to_numeric(df["本期累计买入金额"], errors="coerce")
            if "本期累计卖出金额" in df.columns:
                df["本期累计卖出金额"] = pd.to_numeric(df["本期累计卖出金额"], errors="coerce")
            return df.reset_index(drop=True)
        except Exception:
            last_exc = sys.exc_info()
            continue
    if last_exc:
        raise last_exc[1].with_traceback(last_exc[2])
    return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elite-funds", default="", help="绩优经理基金Top3文件；不填则自动取最新 out/绩优基金经理_基金Top3_*.csv")
    parser.add_argument("--holdings", default="out/我的持仓.csv", help="你的持仓表，默认 out/我的持仓.csv")
    parser.add_argument("--top-opportunities", type=int, default=30, help="额外输出买入/卖出机会 TopN，默认 30")
    parser.add_argument("--threshold", type=float, default=1.0, help="净强度阈值（占比百分点），默认 1.0")
    parser.add_argument("--sleep", type=float, default=0.2, help="接口抓取间隔秒数，默认 0.2")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    elite_path = Path(args.elite_funds) if args.elite_funds else _latest(out_dir, "绩优基金经理_基金Top3_*.csv")
    if not elite_path.is_absolute():
        elite_path = (project_root / elite_path).resolve()
    holdings_path = Path(args.holdings)
    if not holdings_path.is_absolute():
        holdings_path = (project_root / holdings_path).resolve()
    if not holdings_path.exists():
        holdings_path.parent.mkdir(parents=True, exist_ok=True)
        holdings_path.write_text("日期,类型,代码,名称,数量,比例(%)\n", encoding="utf-8")
        print(f"[init] 创建默认持仓文件: {holdings_path}")

    stamp = datetime.now().strftime("%Y%m%d")
    out_csv = out_dir / f"每日调仓信号_{stamp}.csv"
    out_md = out_dir / f"每日调仓信号_{stamp}.md"

    elite = pd.read_csv(elite_path, dtype={"基金代码": str})
    elite["基金代码"] = elite["基金代码"].astype(str).str.zfill(6)
    mgr_cols = [c for c in ["经理排名", "序号", "姓名", "所属公司"] if c in elite.columns]
    if not {"经理排名", "姓名", "所属公司"}.issubset(set(mgr_cols)):
        raise KeyError("绩优基金经理_基金Top3 文件缺少关键字段：经理排名/姓名/所属公司")

    # 逐基金抓取最新季度的买/卖重大变动
    fund_list = elite[["基金代码", "基金简称", "经理排名", "姓名", "所属公司"]].drop_duplicates()
    cache: dict[tuple[str, str], pd.DataFrame] = {}

    rows = []
    for fc in fund_list["基金代码"].unique().tolist():
        for ind in ["累计买入", "累计卖出"]:
            df = fetch_latest_change_one_fund(fc, ind, sleep_s=args.sleep)
            cache[(fc, ind)] = df
            if df is None or df.empty:
                continue
            df = df.copy()
            df["基金代码"] = fc
            df["方向"] = ind
            rows.append(df)
    change = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if change.empty:
        raise RuntimeError("未抓取到任何基金的调仓（重大变动）数据，可能接口临时不可用")

    # 与 elite 合并，挂上经理信息（多经理多基金会重复）
    change = pd.merge(change, elite, on="基金代码", how="left", suffixes=("", "(elite)"))

    # 聚合：按经理 + 股票 计算买入/卖出强度（占比求和）
    key_cols = ["经理排名", "姓名", "所属公司", "股票代码", "股票名称"]
    pct_col = change.get("占期初基金资产净值比例")
    change["占比"] = pd.to_numeric(pct_col, errors="coerce") if pct_col is not None else 0.0
    change["占比"] = change["占比"].fillna(0.0)

    buy = change[change["方向"] == "累计买入"].groupby(key_cols, dropna=False)["占比"].sum().reset_index(name="买入强度")
    sell = change[change["方向"] == "累计卖出"].groupby(key_cols, dropna=False)["占比"].sum().reset_index(name="卖出强度")
    ms = pd.merge(buy, sell, on=key_cols, how="outer").fillna(0.0)
    ms["净强度"] = ms["买入强度"] - ms["卖出强度"]

    # 经理维度 Top10（用于解释）
    mgr_top = (
        ms.sort_values(["经理排名", "净强度"], ascending=[True, False])
        .groupby(["经理排名", "姓名", "所属公司"], dropna=False)
        .head(10)
        .copy()
    )

    # 全局机会（跨经理合并）
    global_agg = (
        ms.groupby(["股票代码", "股票名称"], dropna=False)
        .agg(买入强度=("买入强度", "sum"), 卖出强度=("卖出强度", "sum"), 覆盖经理数=("经理排名", "nunique"))
        .reset_index()
    )
    global_agg["净强度"] = global_agg["买入强度"] - global_agg["卖出强度"]

    # 读取持仓（支持“追加记录调仓历史”的长表格式：含 日期 列时默认取最新一期）
    holdings = pd.read_csv(holdings_path, dtype={"代码": str})
    if "日期" in holdings.columns:
        holdings["日期"] = pd.to_datetime(holdings["日期"], errors="coerce")
        latest_dt = holdings["日期"].max()
        holdings = holdings[holdings["日期"] == latest_dt].copy()
    holdings["代码"] = holdings["代码"].astype(str).str.strip()
    holdings["类型"] = holdings["类型"].astype(str).str.strip()

    held_stock = holdings[holdings["类型"] == "股票"].copy()
    held_fund = holdings[holdings["类型"] == "基金"].copy()
    held_stock["代码"] = held_stock["代码"].str.zfill(6)
    held_fund["代码"] = held_fund["代码"].str.zfill(6)

    # 持仓股票信号
    gmap = global_agg.set_index("股票代码")
    signal_rows: list[dict] = []

    def _label(net: float) -> str:
        if net >= args.threshold:
            return "关注买入"
        if net <= -args.threshold:
            return "关注卖出"
        return "继续关注"

    # 为解释取 top3 经理贡献
    contrib = ms.copy()
    contrib["股票代码"] = contrib["股票代码"].astype(str).str.zfill(6)
    for _, r in held_stock.iterrows():
        code = str(r["代码"]).zfill(6)
        name = r.get("名称", "")
        if code in gmap.index:
            gr = gmap.loc[code]
            net = float(gr["净强度"])
            buy_s = float(gr["买入强度"])
            sell_s = float(gr["卖出强度"])
            top3 = (
                contrib[contrib["股票代码"] == code]
                .sort_values("净强度", ascending=False)
                .head(3)[["姓名", "所属公司", "净强度"]]
            )
            mgr_text = "; ".join([f"{x.姓名}({x.所属公司}):{x.净强度:.2f}" for x in top3.itertuples(index=False)])
        else:
            net, buy_s, sell_s, mgr_text = 0.0, 0.0, 0.0, ""
        signal_rows.append(
            {
                "数据生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "资产类型": "股票",
                "代码": code,
                "名称": name,
                "是否持有": "是",
                "建议标签(非投资建议)": _label(net),
                "买入强度": round(buy_s, 4),
                "卖出强度": round(sell_s, 4),
                "净强度": round(net, 4),
                "关联经理Top3(净强度)": mgr_text,
            }
        )

    # 持仓基金信号：是否为绩优经理 Top3 基金
    elite_fund_map = elite.drop_duplicates(subset=["基金代码"])[["基金代码", "基金简称", "经理排名", "姓名", "所属公司"]]
    elite_fund_map = elite_fund_map.set_index("基金代码")
    for _, r in held_fund.iterrows():
        code = str(r["代码"]).zfill(6)
        name = r.get("名称", "")
        if code in elite_fund_map.index:
            er = elite_fund_map.loc[code]
            tag = "继续关注"
            note = f"{er['姓名']}({er['所属公司']}) 经理排名={er['经理排名']}"
        else:
            tag = "无信号"
            note = ""
        signal_rows.append(
            {
                "数据生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "资产类型": "基金",
                "代码": code,
                "名称": name,
                "是否持有": "是",
                "建议标签(非投资建议)": tag,
                "买入强度": "",
                "卖出强度": "",
                "净强度": "",
                "关联经理Top3(净强度)": note,
            }
        )

    # 额外机会：Top 买入 / Top 卖出（未持有）
    held_codes = set(held_stock["代码"].tolist())
    buy_op = global_agg.sort_values("净强度", ascending=False).head(args.top_opportunities)
    sell_op = global_agg.sort_values("净强度", ascending=True).head(args.top_opportunities)

    def _add_ops(df_ops: pd.DataFrame, tag: str) -> None:
        for rr in df_ops.itertuples(index=False):
            code = str(rr.股票代码).zfill(6)
            if code in held_codes:
                continue
            top3 = (
                contrib[contrib["股票代码"] == code]
                .sort_values("净强度", ascending=False)
                .head(3)[["姓名", "所属公司", "净强度"]]
            )
            mgr_text = "; ".join([f"{x.姓名}({x.所属公司}):{x.净强度:.2f}" for x in top3.itertuples(index=False)])
            signal_rows.append(
                {
                    "数据生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "资产类型": "股票",
                    "代码": code,
                    "名称": rr.股票名称,
                    "是否持有": "否",
                    "建议标签(非投资建议)": tag,
                    "买入强度": round(float(rr.买入强度), 4),
                    "卖出强度": round(float(rr.卖出强度), 4),
                    "净强度": round(float(rr.净强度), 4),
                    "关联经理Top3(净强度)": mgr_text,
                }
            )

    _add_ops(buy_op, "关注买入")
    _add_ops(sell_op, "关注卖出")

    out_df = pd.DataFrame(signal_rows)
    out_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # Markdown 摘要
    hold_sell = (out_df["是否持有"] == "是") & (out_df["建议标签(非投资建议)"] == "关注卖出") & (out_df["资产类型"] == "股票")
    hold_buy = (out_df["是否持有"] == "是") & (out_df["建议标签(非投资建议)"] == "关注买入") & (out_df["资产类型"] == "股票")
    md = [
        f"# 每日调仓信号（{stamp}）",
        "",
        "> 说明：本报告仅基于公开披露的基金重大变动（季度口径）做“信号提示”，不构成任何投资建议。",
        "",
        f"- 跟踪经理数：{elite[['姓名','所属公司']].drop_duplicates().shape[0]}",
        f"- 跟踪基金数（Top3 合计去重）：{elite['基金代码'].nunique()}",
        f"- 持仓股票：{held_stock.shape[0]}（关注买入：{int(hold_buy.sum())}，关注卖出：{int(hold_sell.sum())}）",
        f"- 持仓基金：{held_fund.shape[0]}",
        "",
        "生成文件：",
        f"- {out_csv.name}",
    ]
    out_md.write_text("\\n".join(md), encoding="utf-8")
    print(f"完成：{out_csv}")
    print(f"完成：{out_md}")


if __name__ == "__main__":
    main()
