#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""页面路由和 API 端点。"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from html import escape as _html_escape
from pathlib import Path
from typing import Any
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

import pandas as pd

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from .data_service import DataService
from formula_doc import render_formula_doc
from manager_index import build_manager_index
from selection_formula import TOP_FUNDS, TOP_STOCKS, select_global_funds, select_global_stocks
from stock_rankings import build_stock_rankings

# 周期检测（可选，失败则降级）
try:
    from economic_cycle import detect_cycle_phase, CyclePhase
    _HAS_CYCLE = True
except Exception:
    _HAS_CYCLE = False

# ------------------------------------------------------------------
# 初始化
# ------------------------------------------------------------------

router = APIRouter()
ds = DataService()

_tpl_dir = Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_tpl_dir)), auto_reload=True, cache_size=0)


def _num2(v: Any) -> str:
    """数值格式化；基金信号等场景可能没有数值，空值保持空白。"""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return ""


def _num2safe(v: Any) -> str:
    """个人页里的数值可能是空字符串（例如基金信号没有净强度）。"""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


_jinja_env.filters["num2"] = _num2
_jinja_env.filters["num2s"] = _num2safe


def _mgr_link(name: Any, date: str = "") -> Markup:
    """经理个人页链接（动态站 /manager）。"""
    name = str(name or "").strip()
    if not name:
        return Markup("")
    href = "/manager?date=" + _url_quote(str(date)) + "&name=" + _url_quote(name)
    return Markup(
        '<a class="mgr-link" href="' + _html_escape(href, quote=True) +
        '" title="' + _html_escape(f"查看 {name} 的个人页面", quote=True) +
        '">' + _html_escape(name) + '</a>'
    )


_MGR_WITH_COMPANY = re.compile(r"^([^()]+?)\(([^)]*)\)\s*(.*)$")
_MGR_MORE = re.compile(r"\s*等\s*\d+\s*位\s*$")
_MGR_PLAIN_NAME = re.compile(r"^[^()：:；;、\s]{2,12}$")


def _mgr_cell(text: Any, date: str = "") -> Markup:
    """把「关联经理」纯文本渲染成逐条链接的 <td>，与静态站 app.js 同口径。

    信号列：`姓名(公司):数值; …`；股票/绩优列：`姓名、姓名 等 N 位`。
    输出已全部转义，返回 Markup 以兼容 autoescape。
    """
    raw = str(text or "").strip()
    if not raw:
        return Markup('<td class="mgr-cell">—</td>')
    items: list[str] = []
    for part in re.split(r"\s*;\s*", raw):
        p = part.strip()
        if not p:
            continue
        more = ""
        m_more = _MGR_MORE.search(p)
        if m_more:
            more = m_more.group(0).strip()
            p = p[:m_more.start()].strip()
        entries = re.split(r"\s*、\s*", p) if "、" in p else [p]
        for entry in entries:
            e = entry.strip()
            if not e:
                continue
            m = _MGR_WITH_COMPANY.match(e)
            if m and m.group(1).strip():
                name = m.group(1).strip()
                meta_bits = [m.group(2).strip(),
                             re.sub(r"^[:：]\s*", "", m.group(3)).strip()]
                meta = " · ".join(x for x in meta_bits if x)
                items.append(
                    '<div class="mgr-item">' + str(_mgr_link(name, date)) +
                    ('<span class="mgr-meta">' + _html_escape(meta) + '</span>' if meta else '') +
                    '</div>'
                )
            elif _MGR_PLAIN_NAME.match(e):
                items.append('<div class="mgr-item">' + str(_mgr_link(e, date)) + '</div>')
            else:
                items.append('<div class="mgr-item">' + _html_escape(e) + '</div>')
        if more:
            items.append('<div class="mgr-item mgr-more">' + _html_escape(more) + '</div>')
    return Markup('<td class="mgr-cell">' + "".join(items) + '</td>')


_jinja_env.filters["mgrcell"] = _mgr_cell
_jinja_env.filters["mgrlink"] = _mgr_link


def _est_cell(code: Any, kind: str = "基金") -> Markup:
    """估算价格单元格（动态站），与静态站 app.js 的 priceCell() 同口径。"""
    from price_estimate import estimate_for, load_latest_estimates

    book = load_latest_estimates()
    section = "funds" if kind == "基金" else "stocks"
    e = estimate_for(book, section, code)
    if not e:
        return Markup('<td class="est-cell">—</td>')
    last = _html_escape(str(e.get("最新价格", "")))
    est = _html_escape(str(e.get("估算价格", "")))
    try:
        chg = f"{float(e.get('估算涨跌')):+.2f}%"
    except (TypeError, ValueError):
        chg = ""
    lo, hi = e.get("估算下界", ""), e.get("估算上界", "")
    band = f"{lo}–{hi}" if lo and hi else ""
    method = _html_escape(str(e.get("估算口径", "")))
    asof = _html_escape(str(e.get("数据截至", "")))
    title = " · ".join(x for x in (method, f"截至 {asof}" if asof else "",
                                   f"±1σ {band}" if band else "") if x)
    main = f"{last} → {est}" if last and est else "暂无价格"
    sub = " · ".join(x for x in (chg, "代理" if not est else "", method) if x)
    return Markup(
        '<td class="est-cell" title="' + _html_escape(title, quote=True) + '">' +
        '<div class="est-main">' + _html_escape(main) + '</div>' +
        '<div class="est-sub">' + _html_escape(sub) + '</div></td>'
    )


_jinja_env.filters["estcell"] = _est_cell


def _render(name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    template = _jinja_env.get_template(name)
    return HTMLResponse(template.render(**(context or {})))


def _get_date(request: Request) -> str:
    """提取并校验 ?date=YYYYMMDD 查询参数，未指定时返回最新日期。"""
    date = request.query_params.get("date", "")
    if date and re.match(r"^\d{8}$", date):
        return date
    # 默认返回最新可用日期
    dates = ds.available_dates()
    return dates[0] if dates else ""


def _base_context(request: Request, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """构建页面渲染的公共上下文（含日期选择信息）。"""
    dates = ds.available_dates()
    selected_date = _get_date(request)
    ctx: dict[str, Any] = {
        "request": request,
        "available_dates": dates,
        "selected_date": selected_date,
    }
    if extra:
        ctx.update(extra)
    return ctx

# 后台任务跟踪 {task_id: {status, start, end, log_lines}}
_task_store: dict[str, dict[str, Any]] = {}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _run_script(script_name: str, *args: str) -> subprocess.Popen[str]:
    """在子进程中运行 src/ 脚本，实时捕获输出行。"""
    root = _project_root()
    cmd = [sys.executable, "-u", str(root / "src" / script_name), *args]
    env = {**__import__("os").environ, "PYTHONUNBUFFERED": "1", "no_proxy": "*", "NO_PROXY": "*"}
    return subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


def _run_in_background(task_id: str, script_name: str, *args: str) -> None:
    """后台线程执行脚本，收集日志。"""
    task = _task_store.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task["start"] = datetime.now().strftime("%H:%M:%S")
    task["start_ts"] = datetime.now().timestamp()
    proc = _run_script(script_name, *args)
    for line in proc.stdout:
        task["log_lines"].append(line.rstrip())
    proc.wait()
    task["status"] = "done" if proc.returncode == 0 else "failed"
    task["end"] = datetime.now().strftime("%H:%M:%S")
    task["end_ts"] = datetime.now().timestamp()
    task["rc"] = proc.returncode


def _start_task(script_name: str, *args: str) -> str:
    task_id = uuid.uuid4().hex[:8]
    _task_store[task_id] = {"status": "pending", "start": "", "end": "", "log_lines": [], "rc": -1, "script": script_name}
    t = threading.Thread(target=_run_in_background, args=(task_id, script_name, *args), daemon=True)
    t.start()
    return task_id


# ------------------------------------------------------------------
# 页面路由
# ------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    date = _get_date(request)
    holdings = ds.get_holdings()
    signals = ds.get_signals(date=date)
    managers = ds.get_manager_rankings(date=date)

    # 信号统计
    signal_stats = {"buy": 0, "sell": 0, "hold": 0, "total": 0}
    if signals is not None and not signals.empty:
        if "建议标签(非投资建议)" in signals.columns:
            tag_col = "建议标签(非投资建议)"
            signal_stats["buy"] = int((signals[tag_col] == "关注买入").sum())
            signal_stats["sell"] = int((signals[tag_col] == "关注卖出").sum())
            signal_stats["hold"] = int((signals[tag_col] == "继续关注").sum())
            signal_stats["total"] = len(signals)

    # 持仓摘要
    stock_sum = fund_sum = 0.0
    if not holdings.empty and "比例(%)" in holdings.columns:
        h = holdings.copy()
        h["比例(%)"] = pd.to_numeric(h["比例(%)"], errors="coerce").fillna(0)
        stock_sum = float(h[h["类型"] == "股票"]["比例(%)"].sum())
        fund_sum = float(h[h["类型"] == "基金"]["比例(%)"].sum())

    top_managers = managers.head(5).to_dict("records") if not managers.empty else []

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

    stock_ranking = build_stock_rankings(
        ds.get_elite_stocks(date=date).to_dict("records")
    )
    return _render("dashboard.html", _base_context(request, {
        "active_page": "dashboard",
        "signal_stats": signal_stats,
        "holdings": holdings.to_dict("records"),
        "stock_sum": stock_sum,
        "fund_sum": fund_sum,
        "top_managers": top_managers,
        "manager_count": len(managers) if not managers.empty else 0,
        "top_stocks": stock_ranking["rows"][:5],
        "stock_count": stock_ranking["stock_count"],
        "cycle_info": cycle_info,
    }))


@router.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request) -> Any:
    date = _get_date(request)
    signals = ds.get_signals(date=date)
    # 过滤参数
    signal_type = request.query_params.get("type", "")
    rows = signals.to_dict("records") if signals is not None and not signals.empty else []
    if signal_type and rows:
        tag_col = "建议标签(非投资建议)"
        rows = [r for r in rows if r.get(tag_col, "") == signal_type]
    return _render("signals.html", _base_context(request, {
        "active_page": "signals",
        "signals": rows,
        "has_data": signals is not None and not signals.empty,
        "filter_type": signal_type,
    }))


@router.get("/holdings", response_class=HTMLResponse)
async def holdings_page(request: Request) -> Any:
    holdings = ds.get_holdings()
    return _render("holdings.html", _base_context(request, {
        "active_page": "holdings",
        "holdings": holdings.to_dict("records"),
    }))


@router.get("/managers", response_class=HTMLResponse)
async def managers_page(request: Request) -> Any:
    date = _get_date(request)
    managers = ds.get_manager_rankings(date=date)
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = 50
    total = len(managers)
    start = (page - 1) * per_page
    paged = managers.iloc[start:start + per_page].to_dict("records")
    return _render("managers.html", _base_context(request, {
        "active_page": "managers",
        "managers": paged,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total": total,
    }))


@router.get("/manager", response_class=HTMLResponse)
async def manager_page(request: Request) -> Any:
    """基金经理个人页：按姓名聚合业绩排名、绩优基金、重仓股与调仓信号。"""
    date = _get_date(request)
    name = request.query_params.get("name", "").strip()
    managers = ds.get_manager_rankings(date=date)
    signals = ds.get_signals(date=date)
    funds = ds.get_elite_funds(date=date)
    stocks = ds.get_elite_stocks(date=date)
    index = build_manager_index(
        managers.to_dict("records") if not managers.empty else [],
        signals.to_dict("records") if signals is not None and not signals.empty else [],
        funds.to_dict("records") if not funds.empty else [],
        stocks.to_dict("records") if not stocks.empty else [],
    )
    profile = index["managers"].get(name) if name else None
    ranks = (profile or {}).get("ranks", [])
    return _render("manager.html", _base_context(request, {
        "active_page": "manager",
        "name": name,
        "profile": profile or {},
        "rank": ranks[0] if ranks else {},
        "url_quote": _url_quote,
    }))


@router.get("/funds", response_class=HTMLResponse)
async def funds_page(request: Request) -> Any:
    date = _get_date(request)
    min_days = int(request.query_params.get("min_days", "180"))
    funds = ds.get_fund_annual_returns(min_days=min_days, date=date)
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = 50
    total = len(funds)
    start = (page - 1) * per_page
    paged = funds.iloc[start:start + per_page].to_dict("records")
    return _render("funds.html", _base_context(request, {
        "active_page": "funds",
        "funds": paged,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total": total,
        "min_days": min_days,
    }))


@router.get("/stocks", response_class=HTMLResponse)
async def stocks_page(request: Request) -> Any:
    """全站股票排名：由每位绩优经理的股票 Top10 聚合，按综合得分 S_s 排序。"""

    def positive_int(key: str, default: int = 1) -> int:
        try:
            return max(1, int(request.query_params.get(key, str(default))))
        except (TypeError, ValueError):
            return default

    date = _get_date(request)
    ranking = build_stock_rankings(ds.get_elite_stocks(date=date).to_dict("records"))
    min_mgr = positive_int("min_mgr")
    rows = [r for r in ranking["rows"] if r["入选经理数"] >= min_mgr]
    per_page = 50
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = min(positive_int("page"), total_pages)
    shown = rows[(page - 1) * per_page: page * per_page]
    for r in shown:
        code = str(r.get("股票代码", ""))
        prefix = ("SH" if code[:1] in ("6", "9") else
                  "SZ" if code[:1] in ("0", "2", "3") else
                  "BJ" if code[:1] in ("4", "8") else "")
        r["_url"] = (f"https://xueqiu.com/S/{prefix}{code}"
                     if prefix and len(code) == 6 and code.isdigit() else "")

    return _render("stocks.html", _base_context(request, {
        "active_page": "stocks",
        "stocks": shown,
        "total": len(rows),
        "page": page,
        "total_pages": total_pages,
        "min_mgr": min_mgr,
        "manager_count": ranking["manager_count"],
        "stock_count": ranking["stock_count"],
        "record_count": ranking["record_count"],
    }))


@router.get("/elite", response_class=HTMLResponse)
async def elite_page(request: Request) -> Any:
    date = _get_date(request)
    fund_pool = ds.get_elite_funds(date=date).to_dict("records")
    stock_pool = ds.get_elite_stocks(date=date).to_dict("records")

    # 跨所有经理按 S_f / S_s 选出唯一榜单：固定 3 只基金 / 10 只股票。
    # 候选池仍完整保留，供「股票排名」与「优化持仓」使用。
    top_funds = select_global_funds(fund_pool, TOP_FUNDS)
    top_stocks = select_global_stocks(stock_pool, TOP_STOCKS)
    for r in top_stocks:
        code = str(r.get("股票代码", ""))
        prefix = ("SH" if code[:1] in ("6", "9") else
                  "SZ" if code[:1] in ("0", "2", "3") else
                  "BJ" if code[:1] in ("4", "8") else "")
        r["_url"] = (f"https://xueqiu.com/S/{prefix}{code}"
                     if prefix and len(code) == 6 and code.isdigit() else "")
    manager_count = len({str(r.get("经理排名")) for r in fund_pool + stock_pool})

    return _render("elite.html", _base_context(request, {
        "active_page": "elite",
        "top_funds": top_funds,
        "top_stocks": top_stocks,
        "fund_total": len(fund_pool),
        "stock_total": len(stock_pool),
        "manager_count": manager_count,
    }))


@router.get("/formulas", response_class=HTMLResponse)
async def formulas_page(request: Request) -> Any:
    """选股与选基公式：与静态站共用 formula_doc.py 的内容源。"""
    return _render("formulas.html", _base_context(request, {
        "active_page": "formulas",
        "formula_content": render_formula_doc(static=False),
    }))


@router.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request) -> Any:
    date = _get_date(request)
    results = ds.get_backtest_results(date=date)
    # 查看特定回测的摘要
    view_id = request.query_params.get("view", "")
    summary_html = ""
    chart_file = ""
    if view_id and results:
        for r in results:
            if r["id"] == view_id:
                if "md" in r:
                    md_text = ds.read_md_file(r["md"])
                    summary_html = _md_to_html(md_text)
                if "chart" in r:
                    chart_file = r["chart"]
                break
    return _render("backtest.html", _base_context(request, {
        "active_page": "backtest",
        "results": results,
        "view_id": view_id,
        "summary_html": summary_html,
        "chart_file": chart_file,
    }))


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request) -> Any:
    return _render("pipeline.html", _base_context(request, {
        "active_page": "pipeline",
    }))


# ------------------------------------------------------------------
# API 端点
# ------------------------------------------------------------------

@router.get("/api/data-status")
async def api_data_status() -> Any:
    return JSONResponse(ds.get_data_status())


@router.get("/api/run/status/{task_id}")
async def api_task_status(task_id: str) -> Any:
    task = _task_store.get(task_id)
    if not task:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(task)


# pipeline 步骤定义
PIPELINE_STEPS = [
    {"id": "build_manager_fund_returns", "name": "基金经理-基金收益率明细", "script": "build_manager_fund_returns.py"},
    {"id": "rank_fund_managers", "name": "基金经理排名（复合评分）", "script": "rank_fund_managers.py", "args": ["--composite"]},
    {"id": "rank_all_funds_by_annualized_return", "name": "基金年化收益率排序（复合评分）", "script": "rank_all_funds_by_annualized_return.py", "args": ["--composite"]},
    {"id": "link_fund_annualized_and_manager_rank", "name": "基金-经理关联表", "script": "link_fund_annualized_and_manager_rank.py", "args": ["--min-days", "180"]},
    {"id": "pick_elite_managers_targets", "name": "绩优经理筛选+投资标的", "script": "pick_elite_managers_targets.py", "args": ["--top-n", "20", "--min-days", "180"]},
    {"id": "optimize_holdings", "name": "优化持仓（Dalio 多因子+风险平价）", "script": "optimize_holdings.py", "args": ["--composite", "--risk-parity", "--max-position", "25"]},
    {"id": "daily_rebalance_signal", "name": "每日调仓信号", "script": "daily_rebalance_signal.py", "args": ["--holdings", "out/我的持仓.csv"]},
]


@router.post("/api/run/step/{step_id}")
async def api_run_step(step_id: str) -> Any:
    step = next((s for s in PIPELINE_STEPS if s["id"] == step_id), None)
    if not step:
        return JSONResponse({"error": f"unknown step: {step_id}"}, status_code=400)
    args = step.get("args", [])
    task_id = _start_task(step["script"], *args)
    return JSONResponse({"task_id": task_id, "step": step["name"]})


def _run_all_steps(task_id: str) -> None:
    """后台线程：按顺序执行所有流水线步骤，更新进度。"""
    task = _task_store.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task["start"] = datetime.now().strftime("%H:%M:%S")
    task["start_ts"] = datetime.now().timestamp()
    task["log_lines"] = []
    total = len(PIPELINE_STEPS)

    for i, step in enumerate(PIPELINE_STEPS):
        step_start = datetime.now().timestamp()
        task["progress"] = {"current": i + 1, "total": total, "name": step["name"]}
        task["log_lines"].append(f"\n{'='*50}")
        task["log_lines"].append(f"[{i+1}/{total}] {step['name']}")
        task["log_lines"].append(f"脚本: src/{step['script']}")
        args = step.get("args", [])
        if args:
            task["log_lines"].append(f"参数: {' '.join(args)}")
        task["log_lines"].append(f"{'='*50}")

        args = step.get("args", [])
        proc = _run_script(step["script"], *args)
        line_count = 0
        for line in proc.stdout:
            line_count += 1
            task["log_lines"].append(line.rstrip())
        proc.wait()

        step_elapsed = datetime.now().timestamp() - step_start
        if proc.returncode != 0:
            task["status"] = "failed"
            task["end"] = datetime.now().strftime("%H:%M:%S")
            task["end_ts"] = datetime.now().timestamp()
            task["rc"] = proc.returncode
            task["log_lines"].append(f"\n===== 第{i+1}步失败 (rc={proc.returncode}) 耗时 {step_elapsed:.1f}s，流水线中止 =====")
            return

        # 步骤完成摘要
        task["log_lines"].append(f"\n--- 第{i+1}步完成 (耗时 {step_elapsed:.1f}s, 输出 {line_count} 行) ---")

        # 列出该步骤生成的输出文件
        out_dir = _project_root() / "out"
        step_out_files = sorted(out_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        newest = [f for f in step_out_files[:3] if f.stat().st_mtime >= step_start - 5]
        if newest:
            task["log_lines"].append("输出文件:")
            for f in newest:
                size_kb = f.stat().st_size / 1024
                task["log_lines"].append(f"  {f.name} ({size_kb:.1f} KB)")

    task["status"] = "done"
    task["end"] = datetime.now().strftime("%H:%M:%S")
    task["end_ts"] = datetime.now().timestamp()
    task["rc"] = 0
    total_elapsed = task["end_ts"] - task["start_ts"]
    task["log_lines"].append(f"\n===== 全流程完成 (总耗时 {total_elapsed:.1f}s) =====")


@router.post("/api/run/all")
async def api_run_all() -> Any:
    """一键运行全流程，按步执行并报告进度。"""
    task_id = uuid.uuid4().hex[:8]
    _task_store[task_id] = {
        "status": "pending", "start": "", "end": "", "log_lines": [],
        "rc": -1, "script": "全流程",
        "progress": {"current": 0, "total": len(PIPELINE_STEPS), "name": ""},
    }
    t = threading.Thread(target=_run_all_steps, args=(task_id,), daemon=True)
    t.start()
    return JSONResponse({"task_id": task_id, "step": "全流程"})


@router.post("/api/run/optimize")
async def api_run_optimize(
    total_n: int = Form(5),
    stock_pct: float = Form(30),
    fund_pct: float = Form(70),
    composite: bool = Form(False),
    risk_parity: bool = Form(False),
    max_position: float = Form(25),
) -> Any:
    args = ["--total-n", str(total_n), "--stock-pct", str(stock_pct), "--fund-pct", str(fund_pct)]
    if composite:
        args.append("--composite")
    if risk_parity:
        args.append("--risk-parity")
    args += ["--max-position", str(max_position)]
    task_id = _start_task("optimize_holdings.py", *args)
    return JSONResponse({"task_id": task_id, "step": "优化持仓"})


@router.post("/api/run/backtest")
async def api_run_backtest(
    years: int = Form(3),
    manager_topn: int = Form(20),
    fee: float = Form(0.001),
    benchmark: str = Form("sh000300"),
    max_position: float = Form(0),
) -> Any:
    args = ["--years", str(years), "--manager-topn", str(manager_topn), "--fee", str(fee), "--benchmark", benchmark]
    if max_position > 0:
        args += ["--max-position", str(max_position)]
    task_id = _start_task("backtest_elite_manager_portfolio.py", *args)
    return JSONResponse({"task_id": task_id, "step": "股票回测"})


@router.post("/api/run/backtest-fund")
async def api_run_backtest_fund(
    years: int = Form(3),
    manager_topn: int = Form(10),
    rebalance: str = Form("M"),
    max_position: float = Form(0),
) -> Any:
    args = ["--years", str(years), "--manager-topn", str(manager_topn), "--rebalance", rebalance]
    if max_position > 0:
        args += ["--max-position", str(max_position)]
    task_id = _start_task("backtest_fund_portfolio.py", *args)
    return JSONResponse({"task_id": task_id, "step": "基金回测"})


@router.get("/api/backtest-series")
async def api_backtest_series(request: Request) -> JSONResponse:
    """回测净值曲线数据，供交互图表使用（与静态站 series_*.json 同口径）。"""
    try:
        from backtest_series import build_series
    except ImportError:
        return JSONResponse({"dates": []})

    date = _get_date(request)
    view_id = request.query_params.get("view", "")
    results = ds.get_backtest_results(date=date)
    current = next((r for r in results if r["id"] == view_id), None)
    if current is None and results:
        current = results[0]
    if not current or "nav" not in current:
        return JSONResponse({"dates": []})
    series = build_series(
        ds.out_dir / current["nav"], current["id"], current.get("type", "fund")
    )
    return JSONResponse(series or {"dates": []})


@router.get("/out/charts/{filename}")
async def serve_chart(filename: str) -> Any:
    fp = ds.out_dir / filename
    if not fp.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(fp), media_type="image/png")


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _md_to_html(md: str) -> str:
    """简单 Markdown → HTML（仅处理本项目的 MD 输出格式）。"""
    lines = md.split("\n")
    html_lines = []
    in_table = False
    in_list = False
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append('<ul class="md-list">')
                in_list = True
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("|"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.startswith("---") for c in cells if c):
                # 分隔行，跳过
                if not in_table:
                    html_lines.append('<div class="table-wrap"><table>')
                    in_table = True
                continue
            if in_table:
                is_header = not html_lines or html_lines[-1].endswith("<table>") or html_lines[-1].startswith("</thead>")
                cell_tag = "th" if is_header else "td"
                row = "".join(f"<{cell_tag}>{c}</{cell_tag}>" for c in cells)
                if is_header:
                    html_lines.append(f"<thead><tr>{row}</tr></thead><tbody>")
                else:
                    html_lines.append(f"<tr>{row}</tr>")
            else:
                html_lines.append('<div class="table-wrap"><table>')
                in_table = True
                html_lines.append(f"<tr>{''.join(f'<th>{c}</th>' for c in cells)}</tr>")
        elif line.strip() == "":
            if in_table:
                html_lines.append("</tbody></table></div>")
                in_table = False
            if in_list:
                html_lines.append("</ul>")
                in_list = False
        elif line.startswith(">"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<blockquote>{line[1:].strip()}</blockquote>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{line}</p>")
    if in_table:
        html_lines.append("</tbody></table></div>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)
