#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成静态 HTML 页面，用于 GitHub Pages 托管。
从 out/ 目录读取最新 CSV 数据，用 Jinja2 模板渲染后输出到 docs/。

用法: python3 src/generate_static.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

# 确保 src/ 在 path 中
_src_dir = str(Path(__file__).resolve().parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from jinja2 import Environment, FileSystemLoader, Template

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
# 自定义 Jinja2 Loader：将 base.html 替换为 base_static.html
# ------------------------------------------------------------------


class StaticLoader(FileSystemLoader):
    def get_source(self, environment: Environment, template: str) -> tuple[str, str, callable]:
        if template == "base.html":
            template = "base_static.html"
        return super().get_source(environment, template)


# ------------------------------------------------------------------
# 初始化
# ------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
TPL_DIR = Path(__file__).resolve().parent / "webui" / "templates"
DOCS_DIR = ROOT / "docs"

env = Environment(loader=StaticLoader(str(TPL_DIR)), auto_reload=False)
env.filters["num2"] = lambda v: f"{float(v):.2f}"

ds = DataService()


def _static_context(extra: dict | None = None) -> dict:
    """构建静态页面的公共上下文（含日期选择信息）。"""
    dates = ds.available_dates()
    ctx: dict = {
        "is_static": True,
        "available_dates": dates,
        "selected_date": dates[0] if dates else "",
    }
    if extra:
        ctx.update(extra)
    return ctx


def _render(name: str, context: dict | None = None) -> str:
    ctx = _static_context(context)
    tpl = env.get_template(name)
    return tpl.render(**ctx)


# ------------------------------------------------------------------
# URL 后处理：将绝对路径转换为静态站点的相对路径
# ------------------------------------------------------------------


def _fix_urls(html: str) -> str:
    """将动态路由 URL 转为静态 .html 相对路径，保留 date 参数。"""
    # 图表图片路径
    html = html.replace('src="/out/charts/', 'src="charts/')
    html = html.replace("src='/out/charts/", "src='charts/")

    # 通用规则：路径?date=YYYYMMDD 在 URL 转换时保留 date 参数

    # 首页 / 或 /?date=YYYYMMDD -> index.html 或 index.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/(\?date=\d{8})?["\']', r'href="index.html\1"', html)

    # /pipeline 或 /pipeline?date=YYYYMMDD -> pipeline.html
    html = re.sub(r'href=["\']\/pipeline(\?date=\d{8})?["\']', r'href="pipeline.html\1"', html)

    # /signals 或 /signals?date=YYYYMMDD -> signals.html
    html = re.sub(r'href=["\']\/signals(\?date=\d{8})?["\']', r'href="signals.html\1"', html)
    # /signals?date=YYYYMMDD&type=XXX -> signals.html?date=YYYYMMDD (丢弃 type)
    html = re.sub(r'href=["\']\/signals\?date=(\d{8})&type=[^"\']*["\']', r'href="signals.html?date=\1"', html)
    # /signals?type=XXX -> signals.html (丢弃过滤参数)
    html = re.sub(r'href=["\']\/signals\?type=[^"\']*["\']', 'href="signals.html"', html)

    # /holdings 或 /holdings?date=YYYYMMDD -> holdings.html
    html = re.sub(r'href=["\']\/holdings(\?date=\d{8})?["\']', r'href="holdings.html\1"', html)

    # /managers 或 /managers?date=YYYYMMDD -> managers.html
    html = re.sub(r'href=["\']\/managers(\?date=\d{8})?["\']', r'href="managers.html\1"', html)
    # /managers?page=1 -> managers.html
    html = re.sub(r'href=["\']\/managers\?page=1["\']', 'href="managers.html"', html)
    # /managers?date=YYYYMMDD&page=1 -> managers.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/managers\?date=(\d{8})&page=1["\']', r'href="managers.html?date=\1"', html)
    # /managers?page=N (N>1) -> managers_pageN.html
    html = re.sub(r'href=["\']\/managers\?page=(\d+)["\']', r'href="managers_page\1.html"', html)
    # /managers?date=YYYYMMDD&page=N (N>1) -> managers_pageN.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/managers\?date=(\d{8})&page=(\d+)["\']', r'href="managers_page\2.html?date=\1"', html)

    # /funds 或 /funds?date=YYYYMMDD -> funds.html
    html = re.sub(r'href=["\']\/funds(\?date=\d{8})?["\']', r'href="funds.html\1"', html)
    # /funds?min_days=XXX -> funds.html
    html = re.sub(r'href=["\']\/funds\?min_days=\d+["\']', 'href="funds.html"', html)
    # /funds?date=YYYYMMDD&min_days=XXX -> funds.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/funds\?date=(\d{8})&min_days=\d+["\']', r'href="funds.html?date=\1"', html)
    # /funds?page=1&min_days=XXX -> funds.html
    html = re.sub(r'href=["\']\/funds\?page=1&min_days=\d+["\']', 'href="funds.html"', html)
    # /funds?date=YYYYMMDD&page=1&min_days=XXX -> funds.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/funds\?date=(\d{8})&page=1&min_days=\d+["\']', r'href="funds.html?date=\1"', html)
    # /funds?page=N&min_days=XXX (N>1) -> funds_pageN.html
    html = re.sub(r'href=["\']\/funds\?page=(\d+)&min_days=\d+["\']', r'href="funds_page\1.html"', html)
    # /funds?date=YYYYMMDD&page=N&min_days=XXX (N>1) -> funds_pageN.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/funds\?date=(\d{8})&page=(\d+)&min_days=\d+["\']', r'href="funds_page\2.html?date=\1"', html)

    # /elite 或 /elite?date=YYYYMMDD -> elite.html
    html = re.sub(r'href=["\']\/elite(\?date=\d{8})?["\']', r'href="elite.html\1"', html)

    # /backtest 或 /backtest?date=YYYYMMDD -> backtest.html
    html = re.sub(r'href=["\']\/backtest(\?date=\d{8})?["\']', r'href="backtest.html\1"', html)
    # /backtest?view=XXX -> backtest_XXX.html
    html = re.sub(r'href=["\']\/backtest\?view=([^"\']+)["\']', r'href="backtest_\1.html"', html)
    # /backtest?date=YYYYMMDD&view=XXX -> backtest_XXX.html?date=YYYYMMDD
    html = re.sub(r'href=["\']\/backtest\?date=(\d{8})&view=([^"\']+)["\']', r'href="backtest_\2.html?date=\1"', html)

    # CSS /static/style.css -> style.css
    html = html.replace('href="/static/style.css"', 'href="style.css"')
    html = html.replace("href='/static/style.css'", "href='style.css'")

    return html


# ------------------------------------------------------------------
# 帮助函数
# ------------------------------------------------------------------


def _write(filename: str, html: str) -> None:
    html = _fix_urls(html)
    path = DOCS_DIR / filename
    path.write_text(html, encoding="utf-8")
    print(f"  {filename}")


def _copy_assets() -> None:
    """复制 CSS 和图表图片到 docs/。"""
    # CSS
    css_src = TPL_DIR.parent / "static" / "style.css"
    shutil.copy2(css_src, DOCS_DIR / "style.css")
    print("  style.css")

    # 图表图片
    charts_dir = DOCS_DIR / "charts"
    charts_dir.mkdir(exist_ok=True)
    for png in ds.out_dir.glob("回测_*图表*.png"):
        shutil.copy2(png, charts_dir / png.name)
        print(f"  charts/{png.name}")


# ------------------------------------------------------------------
# 页面生成
# ------------------------------------------------------------------

PER_PAGE = 50


def generate_index() -> None:
    """总览页（/ -> index.html）"""
    status = ds.get_data_status()
    holdings = ds.get_holdings()
    signals = ds.get_signals()
    managers = ds.get_manager_rankings()

    # 信号统计
    signal_stats = {"buy": 0, "sell": 0, "hold": 0, "total": 0}
    if signals is not None and not signals.empty:
        if "建议标签(非投资建议)" in signals.columns:
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

    top_managers = managers.head(5).to_dict("records") if not managers.empty else []

    # 状态卡片链接 → 静态 .html 路径（含日期参数）
    _dates = ds.available_dates()
    _sel_date = _dates[0] if _dates else ""
    _dq = f"?date={_sel_date}" if _sel_date else ""
    status_links = {
        "每日调仓信号": f"signals.html{_dq}",
        "基金经理-基金收益率明细": f"managers.html{_dq}",
        "基金经理业绩排名": f"managers.html{_dq}",
        "基金年化收益率排序": f"funds.html{_dq}",
        "基金-经理-年化-排名关联": f"funds.html{_dq}",
        "绩优基金经理-基金Top3": f"elite.html{_dq}",
        "绩优基金经理-股票Top10": f"elite.html{_dq}",
        "回测-净值曲线(股票)": f"backtest.html{_dq}",
        "回测-净值曲线(基金)": f"backtest.html{_dq}",
    }

    # 经济周期检测
    cycle_info = None
    if _HAS_CYCLE:
        try:
            ca = detect_cycle_phase()
            cycle_info = {
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
            cycle_info = None

    html = _render("dashboard.html", {
        "active_page": "dashboard",
        "status": status,
        "status_links": status_links,
        "signal_stats": signal_stats,
        "holdings": holdings.to_dict("records"),
        "stock_sum": stock_sum,
        "fund_sum": fund_sum,
        "top_managers": top_managers,
        "cycle_info": cycle_info,
    })
    _write("index.html", html)


def generate_signals() -> None:
    """每日调仓信号页"""
    signals = ds.get_signals()
    rows = signals.to_dict("records") if signals is not None and not signals.empty else []
    has_data = signals is not None and not signals.empty
    html = _render("signals.html", {
        "active_page": "signals",
        "signals": rows,
        "has_data": has_data,
        "filter_type": "",
    })
    _write("signals.html", html)


def generate_holdings() -> None:
    """我的持仓页"""
    holdings = ds.get_holdings()
    html = _render("holdings.html", {
        "active_page": "holdings",
        "holdings": holdings.to_dict("records"),
    })
    _write("holdings.html", html)


def generate_managers() -> None:
    """经理排名页（含分页）"""
    managers = ds.get_manager_rankings()
    total = len(managers)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    for page in range(1, total_pages + 1):
        start = (page - 1) * PER_PAGE
        paged = managers.iloc[start:start + PER_PAGE].to_dict("records")
        filename = "managers.html" if page == 1 else f"managers_page{page}.html"
        html = _render("managers.html", {
            "active_page": "managers",
            "managers": paged,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        })
        _write(filename, html)


def generate_funds() -> None:
    """基金排名页（默认 min_days=180）"""
    min_days = 180
    funds = ds.get_fund_annual_returns(min_days=min_days)
    total = len(funds)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    for page in range(1, total_pages + 1):
        start = (page - 1) * PER_PAGE
        paged = funds.iloc[start:start + PER_PAGE].to_dict("records")
        filename = "funds.html" if page == 1 else f"funds_page{page}.html"
        html = _render("funds.html", {
            "active_page": "funds",
            "funds": paged,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "min_days": min_days,
        })
        _write(filename, html)


def generate_elite() -> None:
    """绩优标的页"""
    funds = ds.get_elite_funds()
    stocks = ds.get_elite_stocks()
    html = _render("elite.html", {
        "active_page": "elite",
        "elite_funds": funds.to_dict("records"),
        "elite_stocks": stocks.to_dict("records"),
    })
    _write("elite.html", html)


def generate_backtest() -> None:
    """回测列表页 + 各回测详情页"""
    results = ds.get_backtest_results()

    # 回测列表页
    html = _render("backtest.html", {
        "active_page": "backtest",
        "results": results,
        "view_id": "",
        "summary_html": "",
        "chart_file": "",
    })
    _write("backtest.html", html)

    # 每个回测的详情页
    backtest_tpl = env.get_template("backtest.html")
    for r in results:
        summary_html = ""
        if "md" in r:
            md_text = ds.read_md_file(r["md"])
            summary_html = _md_to_html(md_text)
        chart_file = r.get("chart", "")
        detail_html = backtest_tpl.render(**_static_context({
            "active_page": "backtest",
            "results": results,
            "view_id": r["id"],
            "summary_html": summary_html,
            "chart_file": chart_file,
        }))
        _write(f"backtest_{r['id']}.html", detail_html)


def generate_pipeline() -> None:
    """流水线页（静态版）"""
    html = _render("pipeline_static.html", {
        "active_page": "pipeline",
    })
    _write("pipeline.html", html)


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    print("生成静态页面 → docs/")
    print()

    print("页面:")
    generate_index()
    generate_signals()
    generate_holdings()
    generate_managers()
    generate_funds()
    generate_elite()
    generate_backtest()
    generate_pipeline()

    print()
    print("静态资源:")
    _copy_assets()

    print()
    print(f"完成。打开 docs/index.html 即可预览。")


if __name__ == "__main__":
    main()
