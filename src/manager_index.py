#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基金经理个人页的数据索引。

按「姓名」把散落在四份榜单里的信息聚合起来：
  - 经理业绩排名（managers）
  - 每日调仓信号（signals，经理信息藏在纯文本列里）
  - 绩优经理的基金 Top3 / 股票 Top10 原始记录

静态站由 generate_static.py 生成 data/{date}/manager_index.json，前端按需读取；
动态站由 webui/routes.py 直接调用 build_manager_index() 渲染 /manager。
两端共用同一口径，避免个人页显示不一致。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 从「杨宗昌(易方达基金):31.89; …」或「杨宗昌(易方达基金) 经理排名=1」中提取姓名
_SIG_MGR = re.compile(r"([^();、]+?)\(([^)]*)\)")

_STOCK_KEYS = (
    "经理排名", "股票Top", "股票代码", "股票名称", "汇总占净值比例",
    "出现基金数", "最新季度", "Top3基金列表",
)
_FUND_KEYS = (
    "经理排名", "基金Top", "基金代码", "基金简称", "基金年化排名",
    "成立天数", "成立来", "成立来年化", "近1年",
)
_SIGNAL_KEYS = (
    "资产类型", "代码", "名称", "是否持有", "建议标签(非投资建议)",
    "买入强度", "卖出强度", "净强度", "关联经理Top3(净强度)",
)
_RANK_KEYS = (
    "排名指标", "排名", "序号", "姓名", "所属公司", "管理基金数", "有效基金数",
    "平均收益率", "中位数收益率", "最佳收益率", "最差收益率",
    "经理ID", "公司代码",
)


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _pick(row: dict, keys: Iterable[str]) -> dict[str, str]:
    return {k: _s(row.get(k, "")) for k in keys}


def _signal_managers(text: Any) -> list[str]:
    names = []
    for match in _SIG_MGR.finditer(_s(text)):
        name = match.group(1).strip().lstrip(";、，, ")
        if name:
            names.append(name)
    return names


def build_manager_index(
    manager_rows: list[dict],
    signal_rows: list[dict],
    fund_rows: list[dict],
    stock_rows: list[dict],
) -> dict:
    """返回 {"managers": {姓名: {所属公司, ranks, funds, stocks, signals}}, "count": n}。

    只为「在标的或信号里出现过的经理」建索引，避免把 3800+ 行经理排名
    全量塞进个人页 JSON；经理排名仍按姓名精确匹配后保留最多 10 行。
    """
    names: set[str] = set()
    companies: dict[str, str] = {}

    def remember(row: dict) -> None:
        name = _s(row.get("姓名", "")).strip()
        if not name:
            return
        names.add(name)
        company = _s(row.get("所属公司", "")).strip()
        if company and not companies.get(name):
            companies[name] = company

    for row in fund_rows:
        remember(row)
    for row in stock_rows:
        remember(row)
    for row in signal_rows:
        for name in _signal_managers(row.get("关联经理Top3(净强度)", "")):
            names.add(name)

    index: dict[str, dict] = {
        name: {
            "姓名": name,
            "所属公司": companies.get(name, ""),
            "经理ID": "",
            "公司代码": "",
            "ranks": [],
            "funds": [],
            "stocks": [],
            "signals": [],
        }
        for name in sorted(names)
    }

    for row in manager_rows:
        bucket = index.get(_s(row.get("姓名", "")).strip())
        if bucket is None or len(bucket["ranks"]) >= 10:
            continue
        bucket["ranks"].append(_pick(row, _RANK_KEYS))
        if not bucket["所属公司"]:
            bucket["所属公司"] = _s(row.get("所属公司", "")).strip()
        if not bucket["经理ID"]:
            bucket["经理ID"] = _s(row.get("经理ID", "")).strip()
        if not bucket["公司代码"]:
            bucket["公司代码"] = _s(row.get("公司代码", "")).strip()

    for row in fund_rows:
        bucket = index.get(_s(row.get("姓名", "")).strip())
        if bucket is not None:
            bucket["funds"].append(_pick(row, _FUND_KEYS))

    for row in stock_rows:
        bucket = index.get(_s(row.get("姓名", "")).strip())
        if bucket is not None:
            bucket["stocks"].append(_pick(row, _STOCK_KEYS))

    for row in signal_rows:
        text = _s(row.get("关联经理Top3(净强度)", ""))
        for name in set(_signal_managers(text)):
            bucket = index.get(name)
            if bucket is not None:
                bucket["signals"].append(_pick(row, _SIGNAL_KEYS))

    return {"managers": index, "count": len(index)}
