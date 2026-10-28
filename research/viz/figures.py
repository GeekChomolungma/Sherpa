"""两种画布（plotly），都输出单个 HTML 文件：

- `overview_page`：一个 run 的总览，上下几行子图共用时间轴——滚动 RankIC、累计 RankIC、净值（附全部组合的分布带）、回撤、
  滚动净 Sharpe、换手；
- `compare_page`：多个 run 的同一批指标，一个指标一行子图，每条线是一个模型，颜色跟着模型走（各行同一个模型同一个颜色）。

背景灰色是验证段，细竖线是 ML 模型的重训时点。每个子图只有一个纵轴（量纲不同的指标分到不同子图）。页面顶部有分段小结表。
"""

from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from metrics import METRICS, Options, compare_series, cumulative, drawdown, equity, metric_title, rolling_mean, rolling_sharpe, segment_summary
from series import RunSeries

# 分类色（固定顺序，不循环；颜色跟着模型走，不跟排名走）和页面配色
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e8e7e3"
SEGMENT_FILL = "rgba(82, 81, 78, 0.07)"
EVENT_LINE = "rgba(82, 81, 78, 0.18)"
NEUTRAL = "#8a8984"

ROW_HEIGHT = 260


def _x(t: pd.Timestamp) -> str:
    """背景色块、竖线、标注的横坐标：跟数据一样用 ISO 字符串（直接传带时区的 Timestamp，plotly 会把它当成数字）。"""
    return pd.Timestamp(t).isoformat()


def _base_layout(fig: go.Figure, rows: int, title: str) -> None:
    height = ROW_HEIGHT * rows + 150
    top = 60
    fig.update_layout(
        title={"text": title, "x": 0.0, "xanchor": "left", "font": {"size": 18, "color": TEXT}},
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font={"family": "system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif", "size": 12, "color": TEXT_SECONDARY},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0 + 36 / (height - top - 40), "x": 0.0,
                "font": {"color": TEXT}},
        margin={"l": 70, "r": 30, "t": top, "b": 40},
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID, showspikes=True,
                     spikemode="across", spikethickness=1, spikecolor=NEUTRAL, spikedash="dot")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    for annotation in fig.layout.annotations:
        if annotation.xref == "paper":  # 只动子图标题（"验证段 →"之类按时间定位的标注 xref 是 x 轴）
            annotation.update(font={"size": 13, "color": TEXT}, x=0.0, xanchor="left")


def _decorate_time(fig: go.Figure, run: RunSeries, rows: int) -> None:
    """验证段灰底 + 重训时点竖线，铺满所有行。"""
    bounds = sorted(run.segments.items(), key=lambda kv: kv[1])
    for i, (segment, start) in enumerate(bounds):
        if segment != "验证段":
            continue
        end = bounds[i + 1][1] if i + 1 < len(bounds) else None
        for row in range(1, rows + 1):
            fig.add_vrect(x0=_x(start), x1=_x(end if end is not None else _last_time(run)), fillcolor=SEGMENT_FILL,
                          line_width=0, layer="below", row=row, col=1)
        fig.add_annotation(x=_x(start), y=1.0, xref="x", yref="paper", text="验证段 →", showarrow=False, xanchor="left",
                           yanchor="bottom", font={"size": 11, "color": TEXT_SECONDARY})
    # 重训时点：每个时点一条贯穿所有子图的竖线（逐子图各画一条会多出几百个图形，浏览器明显变卡）
    fig.update_layout(shapes=list(fig.layout.shapes) + [
        {"type": "line", "xref": "x", "yref": "paper", "x0": _x(t), "x1": _x(t), "y0": 0, "y1": 1,
         "line": {"width": 1, "color": EVENT_LINE}, "layer": "below"}
        for t in run.events
    ])


def _last_time(run: RunSeries) -> pd.Timestamp:
    ends = [s.index[-1] for s in (run.rank_ic, run.gross) if s is not None]
    return max(ends)


def _line(x, y, name: str, color: str, *, width: float = 2, dash: Optional[str] = None, group: Optional[str] = None,
          showlegend: bool = True, percent: bool = False) -> go.Scatter:
    fmt = "%{y:.2%}" if percent else "%{y:.4f}"
    return go.Scatter(x=x, y=y, name=name, mode="lines", line={"color": color, "width": width, "dash": dash},
                        legendgroup=group or name, showlegend=showlegend, hovertemplate=f"{fmt}<extra>{html.escape(name)}</extra>")


def _no_data(fig: go.Figure, row: int, text: str) -> None:
    fig.add_annotation(text=text, xref="x domain", yref="y domain", x=0.5, y=0.5, showarrow=False,
                       font={"color": TEXT_SECONDARY}, row=row, col=1)


def _table(frame: pd.DataFrame, percent_columns: tuple[str, ...] = ("最大回撤", "累计收益")) -> str:
    def cell(column: str, value) -> str:
        if isinstance(value, float):
            if pd.isna(value):
                return "—"
            return f"{value:.2%}" if column in percent_columns else f"{value:.3f}"
        return html.escape(str(value))
    head = "".join(f"<th>{html.escape(c)}</th>" for c in frame.columns)
    body = "".join("<tr>" + "".join(f"<td>{cell(c, v)}</td>" for c, v in row.items()) + "</tr>" for _, row in frame.iterrows())
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _page(title: str, intro: str, tables: str, fig: go.Figure) -> str:
    chart = fig.to_html(full_html=False, include_plotlyjs=True, config={"displaylogo": False, "responsive": True})
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ margin: 0; background: {SURFACE}; color: {TEXT}; font-family: system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif; }}
  main {{ max-width: 1400px; margin: 0 auto; padding: 24px 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  p.intro {{ color: {TEXT_SECONDARY}; margin: 0 0 16px; line-height: 1.6; font-size: 14px; }}
  table {{ border-collapse: collapse; font-size: 13px; margin: 0 0 18px; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 5px 12px; border-bottom: 1px solid {GRID}; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: {TEXT_SECONDARY}; font-weight: 600; }}
  .tables {{ overflow-x: auto; }}
</style></head>
<body><main>
<h1>{html.escape(title)}</h1>
<p class="intro">{intro}</p>
<div class="tables">{tables}</div>
{chart}
</main></body></html>
"""


def overview_page(run: RunSeries, opts: Options) -> str:
    rows = 6
    titles = [
        f"滚动 RankIC（{opts.ic_window_days:g} 天 / {opts.ic_long_window_days:g} 天均值）",
        "累计 RankIC（斜率 = IC 水平，变平 = 衰减）",
        f"净值（{opts.combo.label} · {opts.cost}；灰带 = 全部组合净值的 25%–75% 分位）",
        f"回撤（{opts.combo.label} · {opts.cost}）",
        f"滚动净 Sharpe（{opts.sharpe_window_days:g} 天，{opts.combo.label} · {opts.cost}）",
        f"单边换手（{opts.turnover_window_days:g} 天均值，{opts.combo.label}）",
    ]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.035, subplot_titles=titles)

    if run.rank_ic is not None:
        ic = run.rank_ic
        fig.add_trace(_line(ic.index, rolling_mean(ic, opts.ic_window_days), f"RankIC {opts.ic_window_days:g} 天", SERIES_COLORS[0], width=1.5), 1, 1)
        fig.add_trace(_line(ic.index, rolling_mean(ic, opts.ic_long_window_days), f"RankIC {opts.ic_long_window_days:g} 天", SERIES_COLORS[1]), 1, 1)
        fig.add_hline(y=0, line_width=1, line_color=NEUTRAL, row=1, col=1)
        fig.add_trace(_line(ic.index, cumulative(ic), "累计 RankIC", SERIES_COLORS[0], showlegend=False), 2, 1)
    else:
        for row in (1, 2):
            _no_data(fig, row, "无逐期 RankIC（非 ML 模型，或旧 run 没有 ic_by_bar.csv）")

    if run.gross is not None:
        net = run.net_returns(opts.combo, opts.cost)
        column = opts.combo.column(run.gross.columns)
        case = column.split(" | ")[0]
        band = run.all_net_returns(opts.cost, case).apply(equity)
        q = band.quantile([0.25, 0.5, 0.75], axis=1).T
        fig.add_trace(go.Scatter(x=q.index, y=q[0.75], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip",
                                   legendgroup="band"), 3, 1)
        fig.add_trace(go.Scatter(x=q.index, y=q[0.25], mode="lines", line={"width": 0}, fill="tonexty",
                                   fillcolor="rgba(138, 137, 132, 0.18)", name="全部组合 25%–75%", legendgroup="band",
                                   hoverinfo="skip"), 3, 1)
        fig.add_trace(_line(q.index, q[0.5], "全部组合中位数", NEUTRAL, width=1.5, dash="dot"), 3, 1)
        fig.add_trace(_line(net.index, equity(run.gross[column]), "毛净值（零成本）", SERIES_COLORS[1], width=1.5, dash="dash"), 3, 1)
        fig.add_trace(_line(net.index, equity(net), f"净值 · {opts.cost}", SERIES_COLORS[0]), 3, 1)
        fig.add_trace(_line(net.index, drawdown(net), "回撤", SERIES_COLORS[0], showlegend=False, percent=True), 4, 1)
        fig.add_trace(_line(net.index, rolling_sharpe(net, opts.sharpe_window_days), "滚动 Sharpe", SERIES_COLORS[0], showlegend=False), 5, 1)
        fig.add_hline(y=0, line_width=1, line_color=NEUTRAL, row=5, col=1)
        turnover = run.turnover[column]
        fig.add_trace(_line(turnover.index, rolling_mean(turnover, opts.turnover_window_days), "换手", SERIES_COLORS[0], showlegend=False), 6, 1)
        fig.update_yaxes(tickformat=".0%", row=4, col=1)
    else:
        for row in (3, 4, 5, 6):
            _no_data(fig, row, "无逐 bar 收益（旧 run 没有 friction/07_bar_gross_returns.csv）")

    _decorate_time(fig, run, rows)
    _base_layout(fig, rows, "")
    # 图例跟着各自的子图：RankIC 那行和净值那行各一个，放在子图右上角（共用一个图例时两行的蓝线分不清）
    for trace in fig.data:
        if trace.yaxis == "y3":
            trace.legend = "legend2"
    legend = {"orientation": "h", "yanchor": "bottom", "xanchor": "right", "x": 1.0, "font": {"color": TEXT},
              "bgcolor": "rgba(0,0,0,0)"}
    fig.update_layout(legend={**legend, "y": fig.layout.yaxis.domain[1] + 0.004},
                      legend2={**legend, "y": fig.layout.yaxis3.domain[1] + 0.004})
    summary = segment_summary(run, opts)
    notes = "；".join(f"{k}：{html.escape(v)}" for k, v in run.notes.items())
    intro = (f"来源 <code>{html.escape(str(run.source))}</code>（{run.stage}）。组合 <b>{html.escape(opts.combo.label)}</b>，成本 "
             f"<b>{html.escape(opts.cost)}</b>（{run.cost_bps.get(opts.cost, float('nan')):g} bps / 单边）。"
             f"RankIC 是主判据，收益只作确认。{notes}")
    return _page(f"{run.name} · 研究线总览", intro, _table(summary), fig)


def compare_page(runs: list[RunSeries], metrics: list[str], opts: Options, baseline: Optional[RunSeries] = None) -> str:
    colors = {run.name: SERIES_COLORS[i % len(SERIES_COLORS)] for i, run in enumerate(runs)}
    if len(runs) > len(SERIES_COLORS):
        raise ValueError(f"一张图最多比 {len(SERIES_COLORS)} 个模型（颜色不循环），这次 {len(runs)} 个：分几张图比")
    fig = make_subplots(rows=len(metrics), cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=[metric_title(m, opts) for m in metrics])
    legend_shown: set[str] = set()
    for row, name in enumerate(metrics, 1):
        series = compare_series(runs, name, opts, baseline)
        if not series:
            _no_data(fig, row, "这些 run 都没有这个指标的数据")
            continue
        for run in runs:
            if run.name not in series:
                continue
            s = series[run.name]
            fig.add_trace(_line(s.index, s, run.name, colors[run.name], group=run.name, showlegend=run.name not in legend_shown,
                                percent=METRICS[name].percent), row, 1)
            legend_shown.add(run.name)
        if METRICS[name].zero_line:
            fig.add_hline(y=0, line_width=1, line_color=NEUTRAL, row=row, col=1)
        if METRICS[name].percent:
            fig.update_yaxes(tickformat=".0%", row=row, col=1)
    reference = baseline or runs[0]
    _decorate_time(fig, RunSeries(name="", stage=reference.stage, source=reference.source, rank_ic=reference.rank_ic,
                                  gross=reference.gross, segments=reference.segments), len(metrics))
    _base_layout(fig, len(metrics), "")

    tables = []
    for run in runs:
        summary = segment_summary(run, opts)
        summary.insert(0, "模型", run.name)
        tables.append(summary)
    table = _table(pd.concat(tables, ignore_index=True)) if tables else ""
    names = "、".join(html.escape(r.name) for r in runs)
    intro = (f"模型：{names}。所有模型用同一个组合 <b>{html.escape(opts.combo.label)}</b>、同一个成本 <b>{html.escape(opts.cost)}</b>，"
             f"时间轴裁到共同区间、累计类曲线从同一起点出发。"
             + (f"基线：<b>{html.escape(baseline.name)}</b>。" if baseline is not None else "")
             + "RankIC 是主判据，收益只作确认。")
    return _page("多模型对比", intro, table, fig)
