#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI 入口：FastAPI 应用 + APScheduler 每日定时任务。

启动方式（从项目根目录执行）:
  python3 src/webui/app.py

或:
  PYTHONPATH=src python3 -m uvicorn webui.app:app --host 0.0.0.0 --port 8000

访问: http://localhost:8000
"""

from __future__ import annotations

import os
import sys
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# 绕过 macOS 系统代理（SystemConfiguration 代理未运行时 DNS 返回假 IP 导致所有 API 调用失败）
import urllib.request as _ur
_ur.getproxies = lambda: {}
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

# 确保 src/ 在 path 中（必须在导入 webui 之前）
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from webui.routes import router

# ------------------------------------------------------------------
# 日志
# ------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("webui")

# ------------------------------------------------------------------
# FastAPI 应用
# ------------------------------------------------------------------

app = FastAPI(title="量化交易研究", version="1.0", docs_url=None, redoc_url=None)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
app.include_router(router)

# ------------------------------------------------------------------
# 每日定时任务
# ------------------------------------------------------------------

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def daily_pipeline_job() -> None:
    """每日凌晨执行全流程。"""
    logger.info("定时任务：开始执行 daily_run.py ...")
    root = Path(__file__).resolve().parent.parent
    log_file = root / "out" / "webui_scheduler.log"
    try:
        proc = subprocess.run(
            [sys.executable, str(root / "src" / "daily_run.py")],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n=== {ts} rc={proc.returncode} ===\n")
            f.write(proc.stdout)
            if proc.stderr:
                f.write("STDERR:\n")
                f.write(proc.stderr)
        if proc.returncode == 0:
            logger.info("定时任务：daily_run.py 执行成功")
        else:
            logger.error(f"定时任务：daily_run.py 返回 {proc.returncode}")
    except subprocess.TimeoutExpired:
        logger.error("定时任务：daily_run.py 超时（>1h）")
    except Exception:
        logger.exception("定时任务：执行异常")


# 每天凌晨 2:00 触发，±5分钟随机偏移
scheduler.add_job(
    daily_pipeline_job,
    "cron",
    hour=2,
    minute=0,
    jitter=300,
    id="daily_pipeline",
)

scheduler.start()
logger.info("APScheduler 已启动：每日 02:00 (+-5min) 执行 daily_run.py")


# ------------------------------------------------------------------
# 关闭
# ------------------------------------------------------------------

@app.on_event("shutdown")
def shutdown() -> None:
    scheduler.shutdown(wait=False)


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webui.app:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
