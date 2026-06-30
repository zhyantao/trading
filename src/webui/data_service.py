#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据服务层：读取 out/ 下最新 CSV 文件，封装为结构化数据供 WebUI 使用。
所有方法只读取文件，不发起网络请求。

支持通过 date 参数（YYYYMMDD）查看历史某一天的数据。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _latest(out_dir: Path, pattern: str) -> Path | None:
    files = sorted(out_dir.glob(pattern))
    return files[-1] if files else None


def _latest_or_date(out_dir: Path, pattern: str, date: str = "") -> Path | None:
    """获取匹配 pattern 的最新文件，或指定日期的文件。"""
    if date:
        # 将 pattern 中的 * 替换为日期戳，精确匹配
        specific_pattern = pattern.replace("*", date)
        f = out_dir / specific_pattern
        return f if f.exists() else None
    return _latest(out_dir, pattern)


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    kwargs.setdefault("dtype", str)
    kwargs.setdefault("keep_default_na", False)
    return pd.read_csv(path, **kwargs)


def _extract_date_stamps(out_dir: Path) -> list[str]:
    """扫描 out/ 目录，提取所有 YYYYMMDD 日期戳，按倒序排列。"""
    stamps: set[str] = set()
    for f in out_dir.iterdir():
        if not f.is_file():
            continue
        # 从文件名中提取 8 位连续数字作为候选日期戳
        for part in f.stem.split("_"):
            if len(part) == 8 and part.isdigit():
                # 验证是否为合法日期
                try:
                    datetime.strptime(part, "%Y%m%d")
                    stamps.add(part)
                except ValueError:
                    pass
    return sorted(stamps, reverse=True)


class DataService:
    """封装所有 out/ 文件读取。支持按日期筛选。"""

    def __init__(self) -> None:
        self.out_dir = _project_root() / "out"

    # ------------------------------------------------------------------
    # 日期
    # ------------------------------------------------------------------

    def available_dates(self) -> list[str]:
        """返回 out/ 中所有可用日期（YYYYMMDD），最新在前。"""
        return _extract_date_stamps(self.out_dir)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _file_or_latest(self, pattern: str, date: str = "") -> Path | None:
        return _latest_or_date(self.out_dir, pattern, date)

    def get_data_status(self, date: str = "") -> dict[str, dict[str, Any]]:
        """返回各核心文件的存在状态、生成时间、行数。"""
        patterns = {
            "基金经理-基金收益率明细": "基金经理_基金收益率明细_*.csv",
            "基金经理业绩排名": "基金经理业绩排名_*.csv",
            "基金年化收益率排序": "基金年化收益率排序_*.csv",
            "基金-经理-年化-排名关联": "基金_经理_年化_排名关联_*.csv",
            "绩优基金经理-基金Top3": "绩优基金经理_基金Top3_*.csv",
            "绩优基金经理-股票Top10": "绩优基金经理_股票Top10_*.csv",
            "每日调仓信号": "每日调仓信号_*.csv",
            "回测-净值曲线(股票)": "回测_净值曲线_*.csv",
            "回测-净值曲线(基金)": "回测_基金净值曲线_*.csv",
        }
        result: dict[str, dict[str, Any]] = {}
        for name, pat in patterns.items():
            f = self._file_or_latest(pat, date)
            if f and f.exists():
                stat = f.stat()
                try:
                    df = _read_csv(f)
                    rows = len(df)
                except Exception:
                    rows = 0
                result[name] = {
                    "exists": True,
                    "path": str(f.name),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "size_kb": round(stat.st_size / 1024, 1),
                    "rows": rows,
                }
            else:
                result[name] = {"exists": False, "path": "", "modified": "", "size_kb": 0, "rows": 0}
        return result

    # ------------------------------------------------------------------
    # 持仓
    # ------------------------------------------------------------------

    def get_holdings(self) -> pd.DataFrame:
        """读取我的持仓.csv 最新日期数据。"""
        fp = self.out_dir / "我的持仓.csv"
        if not fp.exists():
            return pd.DataFrame(columns=["日期", "类型", "代码", "名称", "数量", "比例(%)"])
        df = _read_csv(fp)
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            latest_dt = df["日期"].max()
            df = df[df["日期"] == latest_dt].copy()
        return df

    # ------------------------------------------------------------------
    # 信号
    # ------------------------------------------------------------------

    def get_signals(self, date: str = "") -> pd.DataFrame | None:
        """读取最新（或指定日期）调仓信号。"""
        f = self._file_or_latest("每日调仓信号_*.csv", date)
        if not f:
            return None
        df = _read_csv(f)
        for c in ["净强度", "买入强度", "卖出强度"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # ------------------------------------------------------------------
    # 基金经理排名
    # ------------------------------------------------------------------

    def get_manager_rankings(self, date: str = "") -> pd.DataFrame:
        f = self._file_or_latest("基金经理业绩排名_*.csv", date)
        if not f:
            return pd.DataFrame()
        df = _read_csv(f)
        for c in ["排名", "管理基金数", "有效基金数", "平均收益率", "中位数收益率", "最佳收益率", "最差收益率"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # ------------------------------------------------------------------
    # 基金年化排名
    # ------------------------------------------------------------------

    def get_fund_annual_returns(self, min_days: int = 180, date: str = "") -> pd.DataFrame:
        f = self._file_or_latest("基金年化收益率排序_*.csv", date)
        if not f:
            return pd.DataFrame()
        df = _read_csv(f)
        for c in ["排名", "成立来年化", "成立来", "成立天数", "近1年", "近2年", "近3年", "今年来"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "成立天数" in df.columns:
            df = df[df["成立天数"].fillna(-1) >= min_days].copy()
        if "排名" in df.columns:
            df["排名"] = range(1, len(df) + 1)
        return df

    # ------------------------------------------------------------------
    # 绩优经理标的
    # ------------------------------------------------------------------

    def get_elite_funds(self, date: str = "") -> pd.DataFrame:
        f = self._file_or_latest("绩优基金经理_基金Top3_*.csv", date)
        if not f:
            return pd.DataFrame()
        df = _read_csv(f)
        for c in ["经理排名", "成立来年化", "成立来", "近1年"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    def get_elite_stocks(self, date: str = "") -> pd.DataFrame:
        f = self._file_or_latest("绩优基金经理_股票Top10_*.csv", date)
        if not f:
            return pd.DataFrame()
        df = _read_csv(f)
        for c in ["经理排名", "汇总占净值比例", "出现基金数"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    # ------------------------------------------------------------------
    # 回测
    # ------------------------------------------------------------------

    def get_backtest_results(self, date: str = "") -> list[dict[str, Any]]:
        """列出已有回测结果文件组。可按日期筛选。"""
        groups: dict[str, dict[str, Any]] = {}
        patterns = [
            ("回测_净值曲线_*.csv", "stock_nav"),
            ("回测_调仓记录_*.csv", "stock_trades"),
            ("回测摘要_*.md", "stock_md"),
            ("回测_图表_*.png", "stock_chart"),
            ("回测_基金净值曲线_*.csv", "fund_nav"),
            ("回测_基金调仓记录_*.csv", "fund_trades"),
            ("回测_基金摘要_*.md", "fund_md"),
            ("回测_基金图表_*.png", "fund_chart"),
        ]
        for pat, key in patterns:
            # 如果指定日期，只查找该日期的文件
            if date:
                specific = pat.replace("*", date)
                fp = self.out_dir / specific
                files = [fp] if fp.exists() else []
            else:
                files = sorted(self.out_dir.glob(pat))
            for fp in files:
                stem = fp.stem
                parts = stem.split("_")
                stamp = parts[-1] if len(parts[-1]) == 8 and parts[-1].isdigit() else ""
                gid = f"{'fund' if key.startswith('fund') else 'stock'}_{stamp}"
                if gid not in groups:
                    groups[gid] = {"id": gid, "stamp": stamp, "type": "stock" if "stock" in gid else "fund"}
                groups[gid][key.split("_", 1)[1]] = str(fp.name)
        return sorted(groups.values(), key=lambda x: x["stamp"], reverse=True)

    def read_md_file(self, filename: str) -> str:
        fp = self.out_dir / filename
        if not fp.exists():
            return ""
        return fp.read_text(encoding="utf-8")
