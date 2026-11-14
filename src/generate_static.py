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

# 数据 JSON 保留最近多少个日期（控制仓库体积，旧日期自动清理）
RETAIN_DATES = 30

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

    # 静态壳 HTML
    for f in sorted(SITE_DIR.glob("*.html")):
        shutil.copy2(f, DOCS_DIR / f.name)
        print(f"  {f.name}")

    # CSS / JS
    static_dir = Path(__file__).resolve().parent / "webui" / "static"
    shutil.copy2(static_dir / "style.css", DOCS_DIR / "style.css")
    shutil.copy2(static_dir / "app.js", DOCS_DIR / "app.js")
    print("  style.css")
    print("  app.js")

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
            "phase_label": {
                "early_expansion": "早期扩张",
                "late_expansion": "后期扩张",
                "overheating": "过热",
                "contraction": "收缩",
                "deleveraging": "去杠杆",
                "unknown": "无法判断",
            }.get(ca.phase.value, ca.phase.value),
            "confidence": f"{ca.confidence:.0%}",
            "description": ca.description,
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

    # --- dashboard：信号统计 + 持仓 + Top5 经理 + 周期 ---
    signals = ds.get_signals(date)
    holdings = ds.get_holdings()
    managers = ds.get_manager_rankings(date)

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
        "cycle_info": _cycle_info(),
    }
    _write_json(out / "dashboard.json", dashboard)

    # --- signals ---
    _write_json(out / "signals.json", {"rows": _records(signals)})

    # --- managers（全部行，前端分页）---
    _write_json(out / "managers.json", {"rows": _records(managers)})

    # --- funds（成立天数>=90，取前 2000 名，前端再做 min_days 筛选）---
    funds = ds.get_fund_annual_returns(min_days=90, date=date)
    if funds is not None and not funds.empty and len(funds) > FUNDS_MAX_ROWS:
        funds = funds.iloc[:FUNDS_MAX_ROWS]
    _write_json(out / "funds.json", {"rows": _records(funds), "max_rows": FUNDS_MAX_ROWS})

    # --- elite ---
    _write_json(out / "elite.json", {
        "funds": _records(ds.get_elite_funds(date)),
        "stocks": _records(ds.get_elite_stocks(date)),
    })

    # --- backtest（含 md 预渲染 HTML）---
    results = ds.get_backtest_results(date)
    for r in results:
        r["summary_html"] = _md_to_html(ds.read_md_file(r["md"])) if "md" in r else ""
    _write_json(out / "backtest.json", {"results": results})


def generate_global_data() -> None:
    """无日期概念的全局数据。"""
    print("全局数据:")
    _write_json(DATA_DIR / "holdings.json", {"rows": _records(ds.get_holdings())})


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


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    print("生成纯静态站点 → docs/")
    print()

    dates = ds.available_dates()
    retained = dates[:RETAIN_DATES]

    print(f"数据日期: {len(dates)} 个，保留最近 {len(retained)} 个（{retained[0] if retained else '无'} 起）")
    print()
    print("页面: 8 个静态壳（src/static_site/ 原样拷贝）")
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
