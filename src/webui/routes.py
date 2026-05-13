#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""页面路由和 API 端点。"""

from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

import pandas as pd

from jinja2 import Environment, FileSystemLoader

from .data_service import DataService

# ------------------------------------------------------------------
# 初始化
# ------------------------------------------------------------------

router = APIRouter()
ds = DataService()

_tpl_dir = Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_tpl_dir)), auto_reload=True, cache_size=0)
_jinja_env.filters["num2"] = lambda v: f"{float(v):.2f}"


def _render(name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    template = _jinja_env.get_template(name)
    return HTMLResponse(template.render(**(context or {})))

# 后台任务跟踪 {task_id: {status, start, end, log_lines}}
_task_store: dict[str, dict[str, Any]] = {}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _run_script(script_name: str, *args: str) -> subprocess.Popen[str]:
    """在子进程中运行 src/ 脚本，实时捕获输出行。"""
    root = _project_root()
    cmd = [sys.executable, "-u", str(root / "src" / script_name), *args]
    env = {**__import__("os").environ, "PYTHONUNBUFFERED": "1"}
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
    proc = _run_script(script_name, *args)
    for line in proc.stdout:
        task["log_lines"].append(line.rstrip())
    proc.wait()
    task["status"] = "done" if proc.returncode == 0 else "failed"
    task["end"] = datetime.now().strftime("%H:%M:%S")
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

    # 持仓摘要
    stock_sum = fund_sum = 0.0
    if not holdings.empty and "比例(%)" in holdings.columns:
        h = holdings.copy()
        h["比例(%)"] = pd.to_numeric(h["比例(%)"], errors="coerce").fillna(0)
        stock_sum = float(h[h["类型"] == "股票"]["比例(%)"].sum())
        fund_sum = float(h[h["类型"] == "基金"]["比例(%)"].sum())

    top_managers = managers.head(5).to_dict("records") if not managers.empty else []

    return _render("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "status": status,
        "signal_stats": signal_stats,
        "holdings": holdings.to_dict("records"),
        "stock_sum": stock_sum,
        "fund_sum": fund_sum,
        "top_managers": top_managers,
    })


@router.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request) -> Any:
    signals = ds.get_signals()
    # 过滤参数
    signal_type = request.query_params.get("type", "")
    rows = signals.to_dict("records") if signals is not None and not signals.empty else []
    if signal_type and rows:
        tag_col = "建议标签(非投资建议)"
        rows = [r for r in rows if r.get(tag_col, "") == signal_type]
    return _render("signals.html", {
        "request": request,
        "active_page": "signals",
        "signals": rows,
        "has_data": signals is not None and not signals.empty,
        "filter_type": signal_type,
    })


@router.get("/holdings", response_class=HTMLResponse)
async def holdings_page(request: Request) -> Any:
    holdings = ds.get_holdings()
    return _render("holdings.html", {
        "request": request,
        "active_page": "holdings",
        "holdings": holdings.to_dict("records"),
    })


@router.get("/managers", response_class=HTMLResponse)
async def managers_page(request: Request) -> Any:
    managers = ds.get_manager_rankings()
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = 50
    total = len(managers)
    start = (page - 1) * per_page
    paged = managers.iloc[start:start + per_page].to_dict("records")
    return _render("managers.html", {
        "request": request,
        "active_page": "managers",
        "managers": paged,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total": total,
    })


@router.get("/funds", response_class=HTMLResponse)
async def funds_page(request: Request) -> Any:
    min_days = int(request.query_params.get("min_days", "180"))
    funds = ds.get_fund_annual_returns(min_days=min_days)
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = 50
    total = len(funds)
    start = (page - 1) * per_page
    paged = funds.iloc[start:start + per_page].to_dict("records")
    return _render("funds.html", {
        "request": request,
        "active_page": "funds",
        "funds": paged,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total": total,
        "min_days": min_days,
    })


@router.get("/elite", response_class=HTMLResponse)
async def elite_page(request: Request) -> Any:
    funds = ds.get_elite_funds()
    stocks = ds.get_elite_stocks()
    return _render("elite.html", {
        "request": request,
        "active_page": "elite",
        "elite_funds": funds.to_dict("records"),
        "elite_stocks": stocks.to_dict("records"),
    })


@router.get("/backtest", response_class=HTMLResponse)
async def backtest_page(request: Request) -> Any:
    results = ds.get_backtest_results()
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
    return _render("backtest.html", {
        "request": request,
        "active_page": "backtest",
        "results": results,
        "view_id": view_id,
        "summary_html": summary_html,
        "chart_file": chart_file,
    })


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request) -> Any:
    return _render("pipeline.html", {
        "request": request,
        "active_page": "pipeline",
    })


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
    {"id": "rank_fund_managers", "name": "基金经理排名", "script": "rank_fund_managers.py"},
    {"id": "rank_all_funds_by_annualized_return", "name": "基金年化收益率排序", "script": "rank_all_funds_by_annualized_return.py"},
    {"id": "link_fund_annualized_and_manager_rank", "name": "基金-经理关联表", "script": "link_fund_annualized_and_manager_rank.py", "args": ["--min-days", "180"]},
    {"id": "pick_elite_managers_targets", "name": "绩优经理筛选+投资标的", "script": "pick_elite_managers_targets.py", "args": ["--top-n", "20", "--min-days", "180"]},
    {"id": "optimize_holdings", "name": "优化持仓", "script": "optimize_holdings.py"},
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


@router.post("/api/run/all")
async def api_run_all() -> Any:
    """一键运行全流程（等同于 daily_run.py）。"""
    task_id = _start_task("daily_run.py")
    return JSONResponse({"task_id": task_id, "step": "全流程"})


@router.post("/api/run/optimize")
async def api_run_optimize(
    total_n: int = Form(5),
    stock_pct: float = Form(30),
    fund_pct: float = Form(70),
) -> Any:
    args = ["--total-n", str(total_n), "--stock-pct", str(stock_pct), "--fund-pct", str(fund_pct)]
    task_id = _start_task("optimize_holdings.py", *args)
    return JSONResponse({"task_id": task_id, "step": "优化持仓"})


@router.post("/api/run/backtest")
async def api_run_backtest(
    years: int = Form(3),
    manager_topn: int = Form(20),
    fee: float = Form(0.001),
    benchmark: str = Form("sh000300"),
) -> Any:
    args = ["--years", str(years), "--manager-topn", str(manager_topn), "--fee", str(fee), "--benchmark", benchmark]
    task_id = _start_task("backtest_elite_manager_portfolio.py", *args)
    return JSONResponse({"task_id": task_id, "step": "股票回测"})


@router.post("/api/run/backtest-fund")
async def api_run_backtest_fund(
    years: int = Form(3),
    manager_topn: int = Form(10),
    rebalance: str = Form("M"),
) -> Any:
    args = ["--years", str(years), "--manager-topn", str(manager_topn), "--rebalance", rebalance]
    task_id = _start_task("backtest_fund_portfolio.py", *args)
    return JSONResponse({"task_id": task_id, "step": "基金回测"})


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
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.startswith("---") for c in cells if c):
                # 分隔行，跳过
                if not in_table:
                    html_lines.append("<table>")
                    in_table = True
                continue
            if in_table:
                is_header = not html_lines or html_lines[-1] == "<table>" or html_lines[-1].startswith("</thead>")
                cell_tag = "th" if is_header else "td"
                row = "".join(f"<{cell_tag}>{c}</{cell_tag}>" for c in cells)
                if is_header:
                    html_lines.append(f"<thead><tr>{row}</tr></thead><tbody>")
                else:
                    html_lines.append(f"<tr>{row}</tr>")
            else:
                html_lines.append("<table>")
                in_table = True
                html_lines.append(f"<tr>{''.join(f'<th>{c}</th>' for c in cells)}</tr>")
        elif line.strip() == "":
            if in_table:
                html_lines.append("</tbody></table>")
                in_table = False
        elif line.startswith(">"):
            html_lines.append(f"<blockquote>{line[1:].strip()}</blockquote>")
        else:
            html_lines.append(f"<p>{line}</p>")
    if in_table:
        html_lines.append("</tbody></table>")
    return "\n".join(html_lines)
