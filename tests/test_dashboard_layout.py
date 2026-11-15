#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染 dashboard.html 并断言：两列信号摘要 + 持仓占比横条。"""
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
        {"类型": "基金", "代码": "000000", "名称": "越界测试", "比例(%)": 130.0},
    ],
    "stock_sum": 12.5,
    "fund_sum": 87.4,
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
    ("summary-cols", "信号摘要两列容器"),
    ("summary-left", "左列（环形图）"),
    ("summary-stats", "右列（买卖统计）"),
    ('sig-label">关注买入 · 34.3%', "右列买入统计+占比"),
    ('sig-label">关注卖出 · 8.6%', "右列卖出统计+占比"),
    ('stroke="var(--yellow)"', "继续关注弧段"),
    ('<th>占比</th>', "持仓表新增表头"),
    ('class="bar-fill is-stock" style="width:12.5%;"', "股票横条 12.5%"),
    ('class="bar-fill is-fund" style="width:87.4%;"', "基金横条 87.4%"),
    ('width:100%;"', "越界值截断为 100%"),
    ("cycle-divider", "市场周期分隔线保留"),
    ('stroke="var(--red)" stroke-width="24" stroke-dasharray="{{', "不出现未渲染的 Jinja 残留"),
]
fails = []
for key, desc in checks:
    if key == "cycle-divider" and "{{" in key:
        continue
    if key.startswith("stroke") and "{{" in key:
        if "{{" in html:
            fails.append("Jinja 残留未渲染")
        continue
    if key not in html:
        fails.append(desc)

# 旧的 stat-strip 三联布局应已移除
if 'stat-label">关注买入' in html or 'stat-label">继续关注' in html:
    fails.append("旧 stat-strip 布局残留")

if fails:
    print("FAIL:", fails)
    sys.exit(1)
print("dashboard.html 渲染断言 %d 项全部通过" % len(checks))
