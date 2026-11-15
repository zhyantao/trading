#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成纯静态站点，用于 GitHub Pages 托管（无需任何服务端）。

思路：数据与页面分离。
- 页面：src/static_site/ 下的静态壳 HTML，原样拷贝到 docs/；
- 数据：从 out/ 读取各日期的 CSV/MD，输出为 docs/data/{date}/*.json；
- 前端：docs/app.js 在浏览器里 fetch JSON 完成全部渲染（日期切换/分页/筛选）。

数据更新由 GitHub Actions 定时跑 src/daily_run.py 后重新生成本目录实现。

用法: python3 src/generate_static.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 确保 src/ 在 path 中
_src_dir = str(Path(__file__).resolve().parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from webui.data_service import DataService
from webui.routes import _md_to_html
from backtest_series import build_series
from formula_doc import render_formula_doc
from manager_index import build_manager_index
from price_estimate import build_price_estimates
from fetch_stock_series import ensure_stock_series
from selection_formula import (
    TOP_FUNDS,
    TOP_STOCKS,
    select_global_funds,
    select_global_stocks,
)
from stock_rankings import build_stock_rankings

# 周期检测（可选，失败则降级）
try:
    from economic_cycle import detect_cycle_phase

    _HAS_CYCLE = True
except Exception:
    _HAS_CYCLE = False

import pandas as pd

# ------------------------------------------------------------------
# 初始化
# ------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = Path(__file__).resolve().parent / "static_site"  # 静态壳 HTML
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"

# 数据 JSON 保留最近多少个日期。只保留最新一天：旧日期目录与图表会自动删除，
# 页眉日期下拉也就不会出现过期选项。
RETAIN_DATES = 1

# 前端分页大小（与 JS 端保持一致，仅用于提示）
PER_PAGE = 50

ds = DataService()


def _records(df: pd.DataFrame | None) -> list[dict]:
    """DataFrame → JSON 友好的 records（DataService 读入均为 str）。"""
    if df is None or df.empty:
        return []
    d = df.copy()
    for c in d.columns:
        d[c] = d[c].fillna("").astype(str)
    return d.to_dict("records")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  {path.relative_to(DOCS_DIR)}  ({path.stat().st_size // 1024} KB)")


def _copy_static_assets() -> None:
    """拷贝静态壳、CSS、JS、字体、favicon、图表。"""
    print("静态资源:")

    # 静态壳 HTML；公式页由 formula_doc.py 注入正文（静态/动态站共用同一份内容）
    for f in sorted(SITE_DIR.glob("*.html")):
        if f.name == "formulas.html":
            shell = f.read_text(encoding="utf-8")
            (DOCS_DIR / f.name).write_text(
                shell.replace("<!--FORMULA_CONTENT-->", render_formula_doc(static=True)),
                encoding="utf-8",
            )
        else:
            shutil.copy2(f, DOCS_DIR / f.name)
        print(f"  {f.name}")

    # CSS / JS
    static_dir = Path(__file__).resolve().parent / "webui" / "static"
    shutil.copy2(static_dir / "style.css", DOCS_DIR / "style.css")
    shutil.copy2(static_dir / "app.js", DOCS_DIR / "app.js")
    shutil.copy2(static_dir / "backtest-chart.js", DOCS_DIR / "backtest-chart.js")
    print("  style.css")
    print("  app.js")
    print("  backtest-chart.js")

    # 字体（ET Book）
    fonts_src = static_dir / "fonts"
    if fonts_src.is_dir():
        (DOCS_DIR / "fonts").mkdir(exist_ok=True)
        for woff in fonts_src.rglob("*.woff"):
            shutil.copy2(woff, DOCS_DIR / "fonts" / woff.name)
        print("  fonts/")

    # Favicon
    favicon_src = static_dir / "favicon.svg"
    if favicon_src.is_file():
        shutil.copy2(favicon_src, DOCS_DIR / "favicon.svg")
        print("  favicon.svg")

    # 图表图片（全部日期的 PNG，供回测详情页按日期引用）
    charts_dir = DOCS_DIR / "charts"
    charts_dir.mkdir(exist_ok=True)
    n = 0
    for png in ds.out_dir.glob("回测_*图表*.png"):
        shutil.copy2(png, charts_dir / png.name)
        n += 1
    print(f"  charts/ ({n} 个 PNG)")


# ------------------------------------------------------------------
# 经济周期（全局，与日期无关）
# ------------------------------------------------------------------


def _cycle_info() -> dict | None:
    if not _HAS_CYCLE:
        return None
    try:
        ca = detect_cycle_phase()
        return {
            "phase": ca.phase.value,
            "phase_label": ca.phase_label,
            "confidence": f"{ca.confidence:.0%}",
            "description": ca.description,
            "metrics": ca.metrics,
            "reasons": ca.reasons,
            "weights": ca.adjusted_weights,
        }
    except Exception:
        return None


# ------------------------------------------------------------------
# 各日期数据 JSON
# ------------------------------------------------------------------

FUNDS_MAX_ROWS = 2000  # 基金排名只保留前 N 名（按 CSV 已排序顺序）


def generate_data_for_date(date: str) -> None:
    """为一个日期生成全部数据 JSON 到 docs/data/{date}/。"""
    out = DATA_DIR / date

    # --- 公共数据源 ---
    signals = ds.get_signals(date)
    holdings = ds.get_holdings()
    managers = ds.get_manager_rankings(date)
    signal_records = _records(signals)
    holding_records = _records(holdings)

    # 候选池（按经理分组）→ 全站股票排名 / 全局绩优标的，三处共用同一份数据
    elite_fund_records = _records(ds.get_elite_funds(date))
    elite_stock_records = _records(ds.get_elite_stocks(date))

    # --- 估算价格册：只复用仓库内已有的净值/行情缓存与公开区间收益率 ---
    funds_all = ds.get_fund_annual_returns(min_days=90, date=date)
    funds_rows = _records(funds_all.iloc[:FUNDS_MAX_ROWS])
    fund_codes = {str(r.get("基金代码", "")).zfill(6) for r in funds_rows}
    fund_codes |= {str(r.get("基金代码", "")).zfill(6) for r in elite_fund_records}
    fund_codes |= {str(r.get("代码", "")).zfill(6) for r in holding_records if r.get("类型") == "基金"}
    fund_codes |= {str(r.get("代码", "")).zfill(6) for r in signal_records if r.get("资产类型") == "基金"}
    fund_codes.discard("000000")
    fund_est_rows = []
    if not funds_all.empty and "基金代码" in funds_all.columns:
        mask = funds_all["基金代码"].astype(str).str.zfill(6).isin(fund_codes)
        fund_est_rows = _records(funds_all[mask])

    stock_codes = {str(r.get("股票代码", "")).zfill(6) for r in elite_stock_records}
    stock_codes |= {str(r.get("代码", "")).zfill(6) for r in holding_records if r.get("类型") == "股票"}
    stock_codes |= {str(r.get("代码", "")).zfill(6) for r in signal_records if r.get("资产类型") == "股票"}
    stock_codes.discard("000000")

    # 代码 → 名称映射：行情抓取用名称校验区分 A 股 / 港股 / 韩股 / 美股
    # （基金季报里 000700 是腾讯控股、000TSM 是台积电 ADR，须消歧）。
    stock_names = {str(r.get("股票代码", "")).zfill(6): str(r.get("股票名称", ""))
                   for r in elite_stock_records}
    for r in holding_records + signal_records:
        if str(r.get("类型", r.get("资产类型", ""))) == "股票":
            stock_names[str(r.get("代码", "")).zfill(6)] = str(r.get("名称", ""))

    # 抓取/刷新股票前复权日线（东财 A/HK/US + 雅虎 KR，本地已有新鲜序列则跳过）。
    # 失败个股自动回退「重仓基金净值代理」口径，不影响整站生成。
    try:
        ensure_stock_series({c: stock_names.get(c, "") for c in sorted(stock_codes)})
    except Exception as exc:  # 网络全挂也不阻断静态站产出
        print(f"  [行情] 股票日线抓取跳过：{exc}")

    price_book = build_price_estimates(
        ROOT, fund_est_rows, sorted(stock_codes), stock_proxy_records=elite_stock_records
    )
    _write_json(out / "price_estimates.json", price_book)
    cov = price_book["coverage"]
    print(f"  [估算价格] 基金 {cov['funds']} 只 / 股票 {cov['stocks']} 只"
          f"（真实行情 {cov['stock_priced']}、基金净值代理 {cov['stock_proxy']}）")

    stock_ranking = build_stock_rankings(elite_stock_records, price_book)
    global_funds = select_global_funds(elite_fund_records, TOP_FUNDS, price_book)
    global_stocks = select_global_stocks(elite_stock_records, TOP_STOCKS, price_book)

    signal_stats = {"buy": 0, "sell": 0, "hold": 0, "total": 0}
    if signals is not None and not signals.empty and "建议标签(非投资建议)" in signals.columns:
        tag_col = "建议标签(非投资建议)"
        signal_stats["buy"] = int((signals[tag_col] == "关注买入").sum())
        signal_stats["sell"] = int((signals[tag_col] == "关注卖出").sum())
        signal_stats["hold"] = int((signals[tag_col] == "继续关注").sum())
        signal_stats["total"] = len(signals)

    stock_sum = fund_sum = 0.0
    if not holdings.empty and "比例(%)" in holdings.columns:
        h = holdings.copy()
        h["比例(%)"] = pd.to_numeric(h["比例(%)"], errors="coerce").fillna(0)
        stock_sum = float(h[h["类型"] == "股票"]["比例(%)"].sum())
        fund_sum = float(h[h["类型"] == "基金"]["比例(%)"].sum())

    top_managers = managers.head(5)
    dashboard = {
        "date": date,
        "signal_stats": signal_stats,
        "holdings": _records(holdings),
        "stock_sum": round(stock_sum, 2),
        "fund_sum": round(fund_sum, 2),
        "top_managers": _records(top_managers),
        "manager_count": len(managers),
        "top_stocks": stock_ranking["rows"][:5],
        "stock_count": stock_ranking["stock_count"],
        "cycle_info": _cycle_info(),
    }
    _write_json(out / "dashboard.json", dashboard)

    # --- signals ---
    _write_json(out / "signals.json", {"rows": signal_records})

    # --- managers（全部行，前端分页）---
    _write_json(out / "managers.json", {"rows": _records(managers)})

    # --- 基金经理个人页索引：按姓名聚合排名 / 信号 / 基金 / 股票 ---
    _write_json(out / "manager_index.json", build_manager_index(
        _records(managers), _records(signals), elite_fund_records, elite_stock_records,
    ))

    # --- funds（成立天数>=90，取前 2000 名，前端再做 min_days 筛选）---
    _write_json(out / "funds.json", {"rows": funds_rows, "max_rows": FUNDS_MAX_ROWS})

    # --- elite：跨所有经理的唯一榜单（固定 3 只基金 / 10 只股票）---
    _write_json(out / "elite.json", {
        "funds": global_funds,
        "stocks": global_stocks,
        "candidate_funds": len(elite_fund_records),
        "candidate_stocks": len(elite_stock_records),
        "manager_count": stock_ranking["manager_count"],
        "top_funds": TOP_FUNDS,
        "top_stocks": TOP_STOCKS,
    })
    # --- 完整去重股票池：按形式化综合得分 S_s 排序 ---
    _write_json(out / "stocks.json", stock_ranking)

    # --- backtest（含 md 预渲染 HTML + 交互图表数据）---
    # 曲线数据单独成文件，前端只在用户查看对应回测时按需加载，
    # 避免把所有日期的几百个交易日一次性塞进 backtest.json。
    results = ds.get_backtest_results(date)
    for r in results:
        r["summary_html"] = _md_to_html(ds.read_md_file(r["md"])) if "md" in r else ""
        nav_file = r.get("nav")
        if nav_file:
            series = build_series(ds.out_dir / nav_file, r["id"], r.get("type", "fund"))
            if series:
                name = f"series_{r['id']}.json"
                _write_json(out / name, series)
                r["series"] = name
    _write_json(out / "backtest.json", {"results": results})


def generate_global_data() -> None:
    """无日期概念的全局数据（「我的持仓」页已并入总览，不再单独出数据文件）。"""
    print("全局数据: 无（持仓配置随 dashboard.json 输出）")


def generate_manifest(dates: list[str]) -> None:
    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": dates,
        "latest": dates[0] if dates else "",
        "retain": RETAIN_DATES,
    }
    _write_json(DATA_DIR / "manifest.json", manifest)


# ------------------------------------------------------------------
# 清理过期文件（旧分页/详情页、超保留期的数据、过期图表）
# ------------------------------------------------------------------


def _cleanup_stale(retained_dates: set[str]) -> None:
    print("清理过期文件:")
    removed = 0

    # 1) 旧版分页 HTML / 回测详情 HTML
    for f in DOCS_DIR.iterdir():
        if not f.is_file():
            continue
        name = f.name
        is_old = (
            (name.startswith("funds_page") or name.startswith("managers_page"))
            and name.endswith(".html")
        ) or (
            name.startswith("backtest_") and name != "backtest.html" and name.endswith(".html")
        )
        if is_old:
            f.unlink()
            removed += 1

    # 2) data/ 下超出保留期的日期目录
    if DATA_DIR.is_dir():
        for d in DATA_DIR.iterdir():
            if d.is_dir() and d.name not in retained_dates:
                shutil.rmtree(d)
                removed += 1

    # 3) charts/ 下日期不在保留期的 PNG
    charts_dir = DOCS_DIR / "charts"
    if charts_dir.is_dir():
        for f in charts_dir.iterdir():
            m = re.search(r"(\d{8})$", f.stem)
            if m and m.group(1) not in retained_dates:
                f.unlink()
                removed += 1

    print(f"  共删除 {removed} 个过期文件")


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------


def _date_is_complete(date: str) -> bool:
    """数据管道是否跑完整：核心文件必须存在且有数据行。

    本地或 CI 里管道中途失败时，out/ 会留下半成品日期（例如只有排名、
    没有调仓信号与绩优标的）。若不跳过，前端会把残缺日期当成「最新数据」。
    """
    # 信号 / 基金排名 / 基金标的必须有数据行；股票标的允许只有表头
    # （重仓股接口临时不可用时，缓存回退可能为空，但基金标的仍应正常发布）
    with_rows = [
        f"每日调仓信号_{date}.csv",
        f"基金年化收益率排序_{date}.csv",
        f"绩优基金经理_基金Top3_{date}.csv",
    ]
    must_exist = [f"绩优基金经理_股票Top10_{date}.csv"]
    for name in with_rows:
        fp = ds.out_dir / name
        if not fp.is_file():
            return False
        with fp.open("r", encoding="utf-8-sig", errors="ignore") as f:
            if sum(1 for _ in f) < 2:  # 只有表头 → 视为空数据
                return False
    return all((ds.out_dir / name).is_file() for name in must_exist)


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    print("生成纯静态站点 → docs/")
    print()

    all_dates = ds.available_dates()
    complete = [d for d in all_dates if _date_is_complete(d)]
    skipped = [d for d in all_dates if d not in complete]
    if skipped:
        print(f"跳过数据不完整的日期: {', '.join(skipped)}")

    # 若最新日期残缺，绝不能「退而求其次」把旧日期当成最新发布，
    # 否则站点数据会退回到几个月前。此时保持上一版站点原样不动。
    if not all_dates or not complete or complete[0] != all_dates[0]:
        print("[WARN] 最新日期数据不完整（或 out/ 无数据）：保留上一版站点，不生成、不清理")
        return
    retained = complete[:RETAIN_DATES]

    print(f"数据日期: {len(complete)} 个完整日期，只保留最近 {len(retained)} 个（{retained[0]} 起）")
    print()
    print(f"页面: {len(list(SITE_DIR.glob('*.html')))} 个静态壳（src/static_site/ 原样拷贝）")
    print()

    if retained:
        print("数据 JSON:")
        for i, d in enumerate(retained):
            print(f"  [{d}]")
            generate_data_for_date(d)
        generate_global_data()
        generate_manifest(retained)
        print()

    _copy_static_assets()
    print()

    _cleanup_stale(set(retained))

    print()
    print("完成。打开 docs/index.html 即可预览（数据由前端 fetch JSON 渲染）。")


if __name__ == "__main__":
    main()
