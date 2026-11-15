#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染 dashboard.html 并断言：信号环形图与市场周期同行两列、持仓无环形图、横条相对刻度。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "src" / "webui" / "templates"),
    autoescape=select_autoescape(["html"]),
)
env.filters["num2"] = lambda v: ("%.2f" % float(v)) if v not in (None, "", "-") else v
env.filters["mgrlink"] = lambda name, date: '<a class="mgr-link" href="#">%s</a>' % name

tpl = env.get_template("dashboard.html")

ctx = {
    "selected_date": "20261115",
    "holdings": [
        {"类型": "股票", "代码": "600519", "名称": "贵州茅台", "比例(%)": 12.5},
        {"类型": "基金", "代码": "161725", "名称": "招商中证白酒", "比例(%)": 87.4},
        {"类型": "基金", "代码": "000000", "名称": "最大占比测试", "比例(%)": 130.0},
    ],
    "stock_sum": 12.5,
    "fund_sum": 217.4,
    "signal_stats": {"buy": 12, "hold": 20, "sell": 3, "total": 35},
    "cycle_info": {
        "phase_label": "中性偏暖",
        "confidence": "中",
        "description": "测试描述",
        "weights": {"return": 0.4, "risk": 0.3, "stability": 0.2, "quality": 0.1},
    },
    "top_stocks": [{"排名": 1, "股票代码": "600519", "股票名称": "贵州茅台", "入选经理数": 5, "综合得分": 88.8}],
    "top_managers": [{"排名": 1, "姓名": "张三", "所属公司": "某基金", "管理基金数": 3, "平均收益率": 21.3, "最佳收益率": 55.0}],
    "stock_count": 129,
    "manager_count": 20,
}

html = tpl.render(**ctx)

checks = [
    ("summary-cols", "信号摘要+市场周期同行两列容器"),
    ('class="sum-col"', "左列（信号摘要）"),
    ('class="sum-col sum-cycle"', "右列（市场周期）"),
    ('sig-label">关注买入 · 34.3%', "买入统计+占比"),
    ('sig-label">关注卖出 · 8.6%', "卖出统计+占比"),
    ('stroke="var(--yellow)"', "继续关注弧段"),
    ("sum-cycle-desc", "周期描述块"),
    ('>权重</text>', "权重环形图在右列"),
    ("hold-sum-note", "持仓汇总行（替代环形图）"),
    ("横条以最大占比为满格", "横条刻度说明"),
    ('<th>占比</th>', "持仓表占比表头"),
    ('class="bar-fill is-stock" style="width:9.6%;"', "股票横条 12.5/130=9.6%"),
    ('class="bar-fill is-fund" style="width:67.2%;"', "基金横条 87.4/130=67.2%"),
    ('class="bar-fill is-fund" style="width:100.0%;"', "最大占比横条=满格(单位1)"),
]
fails = [desc for key, desc in checks if key not in html]

# 持仓环形图应已删除
if ">比例</text>" in html:
    fails.append("持仓环形图未删除")
# 分隔线应移除（两列并排后不再需要）
if "cycle-divider" in html:
    fails.append("cycle-divider 应已移除")
# 不出现未渲染的 Jinja 残留
if "{{" in html:
    fails.append("Jinja 残留未渲染")
# 旧结构类名不应残留
if "summary-left" in html or "summary-stats" in html:
    fails.append("旧两列类名残留")

if fails:
    print("FAIL:", fails)
    sys.exit(1)
print("dashboard.html 渲染断言 %d 项全部通过" % len(checks))
