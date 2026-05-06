from __future__ import annotations

import io
import json
import uuid
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update

from analysis import (
    MAIN_DIMENSIONS,
    METRIC_FORMULAS,
    AnalysisConfig,
    format_percentage,
    get_dates,
    get_dimension_values,
    perform_mix_analysis,
)
from data_sources import parse_uploaded_file


app = Dash(__name__, title="Ads Revenue Mix Analysis Dashboard v5")
server = app.server

DATASETS: dict[str, pd.DataFrame] = {}
RESULTS: dict[str, dict[str, Any]] = {}

METRIC_OPTIONS = [{"label": key, "value": key} for key in METRIC_FORMULAS]
DIM_OPTIONS = [{"label": "None", "value": ""}] + [
    {"label": item["name"], "value": item["column"]} for item in MAIN_DIMENSIONS
]


def dropdown_options(values: list[str], include_total: bool = False) -> list[dict[str, str]]:
    options = [{"label": value, "value": value} for value in values]
    if include_total:
        return [{"label": "Total (All)", "value": "Total"}] + options
    return options


def section_title(text: str) -> html.Div:
    return html.Div(text, className="section-title")


def form_group(label: str, component: Any) -> html.Div:
    return html.Div([html.Label(label), component], className="form-group")


def app_layout() -> html.Div:
    return html.Div(
        className="container",
        children=[
            dcc.Store(id="dataset-token"),
            dcc.Store(id="analysis-token"),
            dcc.Download(id="download-excel"),
            dcc.Download(id="download-report"),
            dcc.Download(id="download-dashboard"),
            html.Div(
                className="header",
                children=[
                    html.H1("📊 Ads Revenue Mix Analysis Dashboard v5"),
                    html.P("Enhanced with eBay Live Tag, Item Price Tranche, and PLG Credit Ratio"),
                ],
            ),
            html.Div(
                className="content",
                children=[
                    html.Div(
                        className="collapsible-section",
                        children=[
                            html.Button([html.Span("▼", className="arrow"), html.Span("Data Input & Preview")], className="collapse-toggle"),
                            html.Div(
                                className="section",
                                children=[
                                    section_title("📁 Data Input"),
                                    dcc.Upload(
                                        id="file-upload",
                                        className="upload-area",
                                        multiple=False,
                                        children=html.Div(
                                            [
                                                html.Div("📂", className="upload-icon"),
                                                html.H3("Click to upload or drag and drop"),
                                                html.P("Supports CSV and Excel files (.csv, .xlsx, .xls)"),
                                                html.Button("Select File", className="btn"),
                                            ]
                                        ),
                                    ),
                                    html.Div(id="upload-status"),
                                    html.Div(id="data-preview"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        id="config-sections",
                        children=[
                            html.Div(
                                className="section",
                                children=[
                                    section_title("📅 Session 1: Time Period Selection"),
                                    html.Div(
                                        className="form-row",
                                        children=[
                                            form_group("Per Time Period - From Date", dcc.Dropdown(id="per-date-from", clearable=False)),
                                            form_group("Per Time Period - To Date", dcc.Dropdown(id="per-date-to", clearable=False)),
                                            form_group("Post Time Period - From Date", dcc.Dropdown(id="post-date-from", clearable=False)),
                                            form_group("Post Time Period - To Date", dcc.Dropdown(id="post-date-to", clearable=False)),
                                        ],
                                    ),
                                    html.Div(id="period-info", className="info-box"),
                                ],
                            ),
                            html.Div(
                                className="section",
                                children=[
                                    section_title("🎯 Session 2: Dimension Selection"),
                                    html.H4("Part 1: Must Select Dimensions", style={"marginBottom": "15px", "color": "#2c3e50"}),
                                    html.Div(
                                        className="form-row",
                                        children=[
                                            form_group("B2C_C2C (Hold Ctrl/Cmd for multiple)", dcc.Dropdown(id="b2c-c2c-select", multi=True, value=["Total"])),
                                            form_group("Seller_Cntry (Hold Ctrl/Cmd for multiple)", dcc.Dropdown(id="seller-cntry-select", multi=True, value=["Total"])),
                                            form_group("Focus_Category (Hold Ctrl/Cmd for multiple)", dcc.Dropdown(id="focus-category-select", multi=True, value=["Total"])),
                                            form_group("eBay_Live_Tag (Hold Ctrl/Cmd for multiple)", dcc.Dropdown(id="ebay-live-tag-select", multi=True, value=["Total"])),
                                            form_group("Item_Price_Tranche (Hold Ctrl/Cmd for multiple)", dcc.Dropdown(id="item-price-tranche-select", multi=True, value=["Total"])),
                                        ],
                                    ),
                                    html.H4("Part 2: Optional DIY Dimension", style={"margin": "25px 0 15px", "color": "#2c3e50"}),
                                    html.Div(
                                        className="form-row",
                                        children=[
                                            form_group("1st Dimension (Optional)", dcc.Dropdown(id="diy-dim-1", options=DIM_OPTIONS, value="", clearable=False)),
                                            form_group("2nd Dimension (Optional)", dcc.Dropdown(id="diy-dim-2", options=DIM_OPTIONS, value="", clearable=False)),
                                        ],
                                    ),
                                    html.Div("💡 Select two different dimensions to create a combined analysis", className="info-box"),
                                ],
                            ),
                            html.Div(
                                className="section",
                                children=[
                                    section_title("📈 Session 3: Key Metrics Selection"),
                                    html.Div(
                                        className="form-row",
                                        children=[
                                            form_group("Select Key Metric", dcc.Dropdown(id="key-metric-select", options=METRIC_OPTIONS, value="Ads_Rev_Pen", clearable=False)),
                                        ],
                                    ),
                                    html.Div(id="metric-formula", className="metric-formula"),
                                ],
                            ),
                            html.Div(
                                style={"textAlign": "center"},
                                children=html.Button("🚀 Run Mix Analysis", id="run-analysis", className="btn btn-success", style={"fontSize": "1.2rem", "padding": "15px 50px"}),
                            ),
                        ],
                    ),
                    html.Div(id="results-section"),
                    html.Div(id="chart-container"),
                ],
            ),
        ],
    )


app.layout = app_layout


@app.callback(
    Output("dataset-token", "data"),
    Output("upload-status", "children"),
    Output("data-preview", "children"),
    Output("per-date-from", "options"),
    Output("per-date-to", "options"),
    Output("post-date-from", "options"),
    Output("post-date-to", "options"),
    Output("per-date-from", "value"),
    Output("per-date-to", "value"),
    Output("post-date-from", "value"),
    Output("post-date-to", "value"),
    Output("b2c-c2c-select", "options"),
    Output("seller-cntry-select", "options"),
    Output("focus-category-select", "options"),
    Output("ebay-live-tag-select", "options"),
    Output("item-price-tranche-select", "options"),
    Input("file-upload", "contents"),
    State("file-upload", "filename"),
    prevent_initial_call=True,
)
def load_uploaded_file(contents: str | None, filename: str | None):
    if not contents or not filename:
        return [no_update] * 16
    try:
        df = parse_uploaded_file(contents, filename)
        token = str(uuid.uuid4())
        DATASETS[token] = df
        dates = get_dates(df)
        if not dates:
            raise ValueError("No valid RTL_WEEK_BEG_DT values found.")
        date_options = dropdown_options(dates)
        preview = build_preview(df.head(10))
        status = html.Div(f"✅ Data loaded successfully! {len(df)} rows loaded.", className="success-box")
        return (
            token,
            status,
            preview,
            date_options,
            date_options,
            date_options,
            date_options,
            dates[min(12, len(dates) - 1)],
            dates[min(8, len(dates) - 1)],
            dates[0],
            dates[0],
            dropdown_options(get_dimension_values(df, "B2C_C2C_FLAG"), include_total=True),
            dropdown_options(get_dimension_values(df, "SELLER_CNTRY_GROUP"), include_total=True),
            dropdown_options(get_dimension_values(df, "FOCUS_CATEGORY"), include_total=True),
            dropdown_options(get_dimension_values(df, "EBAY_LIVE_TAG"), include_total=True),
            dropdown_options(get_dimension_values(df, "ITEM_PRICE_TRANCHE"), include_total=True),
        )
    except Exception as exc:
        return (
            no_update,
            html.Div(f"❌ {exc}", className="error-box"),
            no_update,
            *[no_update] * 13,
        )


def build_preview(df: pd.DataFrame) -> html.Div:
    return html.Div(
        className="data-preview",
        children=[
            html.H4("Data Preview (first 10 rows)", style={"marginBottom": "10px"}),
            html.Table(
                className="preview-table",
                children=[
                    html.Thead(html.Tr([html.Th(col) for col in df.columns])),
                    html.Tbody(
                        [
                            html.Tr([html.Td("" if pd.isna(row[col]) else str(row[col])) for col in df.columns])
                            for _, row in df.iterrows()
                        ]
                    ),
                ],
            ),
        ],
    )


@app.callback(Output("metric-formula", "children"), Input("key-metric-select", "value"))
def update_metric_formula(metric: str):
    return [html.Strong("Formula:"), f" {metric} = {METRIC_FORMULAS.get(metric, '')}"]


@app.callback(
    Output("period-info", "children"),
    Input("per-date-from", "value"),
    Input("per-date-to", "value"),
    Input("post-date-from", "value"),
    Input("post-date-to", "value"),
)
def update_period_info(per_from: str, per_to: str, post_from: str, post_to: str):
    if not all([per_from, per_to, post_from, post_to]):
        return ""
    per_text = f"Single date ({per_to})" if per_from == per_to else f"Average from {per_from} to {per_to}"
    post_text = f"Single date ({post_to})" if post_from == post_to else f"Average from {post_from} to {post_to}"
    return [html.Strong("Per Period:"), f" {per_text}", html.Br(), html.Strong("Post Period:"), f" {post_text}"]


@app.callback(
    Output("results-section", "children"),
    Output("analysis-token", "data"),
    Output("chart-container", "children", allow_duplicate=True),
    Input("run-analysis", "n_clicks"),
    State("dataset-token", "data"),
    State("per-date-from", "value"),
    State("per-date-to", "value"),
    State("post-date-from", "value"),
    State("post-date-to", "value"),
    State("b2c-c2c-select", "value"),
    State("seller-cntry-select", "value"),
    State("focus-category-select", "value"),
    State("ebay-live-tag-select", "value"),
    State("item-price-tranche-select", "value"),
    State("diy-dim-1", "value"),
    State("diy-dim-2", "value"),
    State("key-metric-select", "value"),
    prevent_initial_call=True,
)
def run_analysis(
    n_clicks,
    dataset_token,
    per_from,
    per_to,
    post_from,
    post_to,
    b2c_c2c,
    seller_cntry,
    focus_category,
    ebay_live_tag,
    item_price_tranche,
    diy_dim1,
    diy_dim2,
    key_metric,
):
    if not n_clicks:
        return no_update, no_update, no_update
    if not dataset_token or dataset_token not in DATASETS:
        return html.Div("❌ Please upload data first.", className="error-box"), no_update, no_update
    try:
        config = AnalysisConfig(
            per_from=per_from,
            per_to=per_to,
            post_from=post_from,
            post_to=post_to,
            b2c_c2c=b2c_c2c or ["Total"],
            seller_cntry=seller_cntry or ["Total"],
            focus_category=focus_category or ["Total"],
            ebay_live_tag=ebay_live_tag or ["Total"],
            item_price_tranche=item_price_tranche or ["Total"],
            diy_dim1=diy_dim1 or None,
            diy_dim2=diy_dim2 or None,
            key_metric=key_metric,
        )
        results = perform_mix_analysis(DATASETS[dataset_token], config)
        analysis_token = str(uuid.uuid4())
        RESULTS[analysis_token] = results
        return build_results(results), analysis_token, ""
    except Exception as exc:
        return html.Div(f"❌ Error during analysis: {exc}", className="error-box"), no_update, no_update


def build_results(results: dict[str, Any]) -> html.Div:
    summary = results["summary"]
    config = results["config"]
    delta = summary["metricPost"] - summary["metricPer"]
    t4w_diff = None if summary["metricT4w"] is None else summary["metricPost"] - summary["metricT4w"]
    ly_diff = None if summary["metricLy"] is None else summary["metricPost"] - summary["metricLy"]
    dimension_options = [{"label": dim["name"], "value": dim["name"]} for dim in results["dimensions"]]
    return html.Div(
        className="section",
        children=[
            section_title("📊 Mix Analysis Results"),
            html.Div(
                className="summary-cards",
                children=[
                    summary_card(f"Per Period {config['key_metric']}", format_percentage(summary["metricPer"])),
                    summary_card(f"Post Period {config['key_metric']}", format_percentage(summary["metricPost"]), delta),
                    summary_card("Total Change", signed_percentage(delta), delta),
                    summary_card("vs. T4 Weeks", signed_percentage(t4w_diff), t4w_diff),
                    summary_card("vs. Previous Year", signed_percentage(ly_diff), ly_diff),
                ],
            ),
            html.Div(
                id="dimension-results",
                children=[html.H3("Detailed Results by Dimension", style={"margin": "30px 0 20px", "color": "#2c3e50"})]
                + [build_dimension_section(dim, config["key_metric"], index) for index, dim in enumerate(results["dimensions"])],
            ),
            html.Div(
                className="button-group",
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "10px"},
                        children=[
                            html.Label("Walk Dimension:", style={"fontWeight": 600, "color": "#111820", "fontSize": "0.95rem"}),
                            dcc.Dropdown(id="walk-dimension-select", options=dimension_options, value=dimension_options[0]["value"] if dimension_options else None, clearable=False, style={"minWidth": "220px"}),
                        ],
                    ),
                    html.Button("📊 Create Walk Chart", id="create-walk-chart", className="btn"),
                    html.Button("📥 Export to Excel", id="export-excel", className="btn btn-export"),
                    html.Button("💾 Download Report", id="download-report-button", className="btn btn-success"),
                    html.Button("💾 Save Dashboard", id="save-dashboard-button", className="btn", style={"background": "linear-gradient(135deg, #9333ea 0%, #7c3aed 100%)", "color": "white"}),
                ],
            ),
        ],
    )


def summary_card(title: str, value: str, delta: float | None = None) -> html.Div:
    cls = ""
    if delta is not None:
        cls = "positive" if delta >= 0 else "negative"
    children = [html.H3(title), html.Div(value, className=f"value {cls}")]
    if title.startswith("Post Period") and delta is not None:
        children.append(html.Div(signed_percentage(delta), className=f"delta {cls}"))
    return html.Div(children, className="summary-card")


def signed_percentage(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{format_percentage(value)}"


def build_dimension_section(dimension: dict[str, Any], key_metric: str, index: int) -> html.Div:
    threshold = 0.00015 if index == 0 else 0.0001
    totals = calculate_totals(dimension["results"])
    rows = [build_result_row(row, threshold) for row in dimension["results"]]
    rows.append(build_total_row(totals, threshold))
    return html.Div(
        className="dimension-section",
        children=[
            html.Div(
                className="dimension-header",
                children=[html.H3(f"{dimension['name']} ({len(dimension['results'])} values)"), html.Span("▼", className="dimension-toggle")],
            ),
            html.Div(
                className="dimension-content",
                children=html.Table(
                    className="results-table",
                    children=[
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Dimension Value"),
                                    html.Th(f"Per {key_metric}"),
                                    html.Th(f"Post {key_metric}"),
                                    html.Th("Metric Change"),
                                    html.Th("Per Share"),
                                    html.Th("Post Share"),
                                    html.Th("Performance Effect to Overall"),
                                    html.Th("Mix Effect to Overall"),
                                    html.Th("Total Effect to Overall"),
                                ]
                            )
                        ),
                        html.Tbody(rows),
                    ],
                ),
            ),
        ],
    )


def calculate_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals = {
        "metricPer": 0.0,
        "metricPost": 0.0,
        "metricChange": 0.0,
        "sharePer": sum(row["sharePer"] for row in rows),
        "sharePost": sum(row["sharePost"] for row in rows),
        "performanceEffect": sum(row["performanceEffect"] for row in rows),
        "mixEffect": sum(row["mixEffect"] for row in rows),
        "totalEffect": sum(row["totalEffect"] for row in rows),
    }
    if totals["sharePer"] > 0:
        totals["metricPer"] = sum(row["metricPer"] * (row["sharePer"] / totals["sharePer"]) for row in rows)
    if totals["sharePost"] > 0:
        totals["metricPost"] = sum(row["metricPost"] * (row["sharePost"] / totals["sharePost"]) for row in rows)
    totals["metricChange"] = totals["metricPost"] - totals["metricPer"]
    return totals


def build_result_row(row: dict[str, Any], threshold: float) -> html.Tr:
    return html.Tr(
        [
            html.Td(html.Strong(row["value"])),
            pct_td(row["metricPer"]),
            pct_td(row["metricPost"]),
            pct_td(row["metricChange"], effect=True),
            pct_td(row["sharePer"]),
            pct_td(row["sharePost"]),
            pct_td(row["performanceEffect"], threshold=threshold),
            pct_td(row["mixEffect"], threshold=threshold),
            pct_td(row["totalEffect"], threshold=threshold),
        ]
    )


def build_total_row(totals: dict[str, float], threshold: float) -> html.Tr:
    return html.Tr(
        className="total-row",
        children=[
            html.Td(html.Strong("TOTAL")),
            pct_td(totals["metricPer"]),
            pct_td(totals["metricPost"]),
            pct_td(totals["metricChange"], effect=True),
            pct_td(totals["sharePer"]),
            pct_td(totals["sharePost"]),
            pct_td(totals["performanceEffect"], threshold=threshold),
            pct_td(totals["mixEffect"], threshold=threshold),
            pct_td(totals["totalEffect"], threshold=threshold),
        ],
    )


def pct_td(value: float, effect: bool = False, threshold: float | None = None) -> html.Td:
    cls = "percentage"
    if threshold is not None:
        if value > threshold:
            cls += " positive-effect-strong"
        elif value < -threshold:
            cls += " negative-effect-strong"
    elif effect:
        if value > 0:
            cls += " positive-effect"
        elif value < 0:
            cls += " negative-effect"
    return html.Td(format_percentage(value), className=cls)


@app.callback(
    Output("chart-container", "children", allow_duplicate=True),
    Input("create-walk-chart", "n_clicks"),
    State("analysis-token", "data"),
    State("walk-dimension-select", "value"),
    prevent_initial_call=True,
)
def create_walk_chart(n_clicks, analysis_token, selected_dimension):
    if not n_clicks or not analysis_token or analysis_token not in RESULTS:
        return no_update
    results = RESULTS[analysis_token]
    figure = build_waterfall_figure(results, selected_dimension)
    return html.Div(
        className="chart-container",
        children=[
            html.H2("🌊 Mix Impact Waterfall Chart", style={"marginBottom": "20px", "color": "#2c3e50"}),
            html.Div(className="chart-wrapper", children=dcc.Graph(figure=figure, config={"displayModeBar": True}, className="dash-graph")),
        ],
    )


def build_waterfall_figure(results: dict[str, Any], selected_dimension: str) -> go.Figure:
    dimension = next((dim for dim in results["dimensions"] if dim["name"] == selected_dimension), None)
    if not dimension:
        return go.Figure()
    labels = ["Per Period"]
    values = [results["summary"]["metricPer"] * 100]
    measures = ["absolute"]
    for row in dimension["results"]:
        total_effect = row["totalEffect"] * 100
        if abs(total_effect) > 0.0001:
            labels.append(row["value"])
            values.append(total_effect)
            measures.append("relative")
    labels.append("Post Period")
    values.append(results["summary"]["metricPost"] * 100)
    measures.append("total")
    fig = go.Figure(
        go.Waterfall(
            name=results["config"]["key_metric"],
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{value:+.2f}%" if measure == "relative" else f"{value:.2f}%" for value, measure in zip(values, measures)],
            textposition="outside",
            connector={"line": {"color": "rgba(44,62,80,0.4)"}},
            increasing={"marker": {"color": "rgba(134, 184, 23, 0.85)"}},
            decreasing={"marker": {"color": "rgba(229, 50, 56, 0.85)"}},
            totals={"marker": {"color": "rgba(0, 100, 210, 0.9)"}},
        )
    )
    fig.update_layout(
        title=f"Mix Impact Walk: {results['config']['key_metric']} by {selected_dimension}",
        yaxis_title=results["config"]["key_metric"],
        xaxis_title="Mix Impact Components",
        height=500,
        margin={"l": 60, "r": 30, "t": 80, "b": 120},
        showlegend=False,
        plot_bgcolor="white",
    )
    fig.update_yaxes(ticksuffix="%")
    return fig


@app.callback(
    Output("download-excel", "data"),
    Input("export-excel", "n_clicks"),
    State("analysis-token", "data"),
    prevent_initial_call=True,
)
def export_excel(n_clicks, analysis_token):
    if not n_clicks or not analysis_token or analysis_token not in RESULTS:
        return no_update
    results = RESULTS[analysis_token]
    export_rows = flatten_export_rows(results)
    output = io.BytesIO()
    pd.DataFrame(export_rows).to_excel(output, sheet_name="Mix Analysis", index=False, engine="xlsxwriter")
    output.seek(0)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"mix_analysis_{results['config']['key_metric']}_{timestamp}.xlsx"
    return dcc.send_bytes(output.getvalue(), filename)


@app.callback(
    Output("download-report", "data"),
    Input("download-report-button", "n_clicks"),
    State("analysis-token", "data"),
    prevent_initial_call=True,
)
def download_report(n_clicks, analysis_token):
    if not n_clicks or not analysis_token or analysis_token not in RESULTS:
        return no_update
    results = RESULTS[analysis_token]
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"Mix_Analysis_Report_{results['config']['key_metric']}_{timestamp}.html"
    return {"content": generate_html_report(results), "filename": filename, "type": "text/html"}


@app.callback(
    Output("download-dashboard", "data"),
    Input("save-dashboard-button", "n_clicks"),
    State("analysis-token", "data"),
    prevent_initial_call=True,
)
def save_dashboard(n_clicks, analysis_token):
    if not n_clicks or not analysis_token or analysis_token not in RESULTS:
        return no_update
    results = RESULTS[analysis_token]
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"ads_mix_dashboard_v5_results_{timestamp}.json"
    return {"content": json.dumps(results, indent=2), "filename": filename, "type": "application/json"}


def flatten_export_rows(results: dict[str, Any]) -> list[dict[str, str]]:
    export_rows: list[dict[str, str]] = []
    for dim in results["dimensions"]:
        for row in dim["results"]:
            export_rows.append(export_row(dim["name"], row["value"], row))
        export_rows.append(export_row(dim["name"], "TOTAL", calculate_totals(dim["results"])))
    return export_rows


def export_row(dimension: str, value: str, row: dict[str, float]) -> dict[str, str]:
    return {
        "Dimension": dimension,
        "Value": value,
        "Per Metric (%)": f"{row['metricPer'] * 100:.4f}",
        "Post Metric (%)": f"{row['metricPost'] * 100:.4f}",
        "Metric Change (%)": f"{row['metricChange'] * 100:.4f}",
        "Per Share (%)": f"{row['sharePer'] * 100:.4f}",
        "Post Share (%)": f"{row['sharePost'] * 100:.4f}",
        "Performance Effect to Overall (%)": f"{row['performanceEffect'] * 100:.4f}",
        "Mix Effect to Overall (%)": f"{row['mixEffect'] * 100:.4f}",
        "Total Effect to Overall (%)": f"{row['totalEffect'] * 100:.4f}",
    }


def generate_html_report(results: dict[str, Any]) -> str:
    config = results["config"]
    summary = results["summary"]
    rows = flatten_export_rows(results)
    table_rows = "\n".join(
        "<tr>" + "".join(f"<td>{value}</td>" for value in row.values()) + "</tr>"
        for row in rows
    )
    headers = "".join(f"<th>{header}</th>" for header in rows[0].keys()) if rows else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Mix Analysis Report - {config['key_metric']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #0064D2 0%, #0654BA 100%); color: white; padding: 40px 30px; text-align: center; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 30px; padding: 20px; border: 1px solid #e5e5e5; border-left: 4px solid #0064D2; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
        th {{ background: #0064D2; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #e5e5e5; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Ads Revenue Mix Analysis Report v5</h1>
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class="content">
            <div class="section">
                <h2>Summary Results</h2>
                <p><strong>Metric:</strong> {config['key_metric']}</p>
                <p><strong>Per Period:</strong> {config['per_from']} to {config['per_to']} - {format_percentage(summary['metricPer'])}</p>
                <p><strong>Post Period:</strong> {config['post_from']} to {config['post_to']} - {format_percentage(summary['metricPost'])}</p>
                <p><strong>Total Change:</strong> {signed_percentage(summary['metricPost'] - summary['metricPer'])}</p>
                <p><strong>Total Performance Effect:</strong> {format_percentage(summary['totalPerformanceEffect'])}</p>
                <p><strong>Total Mix Effect:</strong> {format_percentage(summary['totalMixEffect'])}</p>
            </div>
            <div class="section">
                <h2>Detailed Breakdown by Dimension</h2>
                <table><thead><tr>{headers}</tr></thead><tbody>{table_rows}</tbody></table>
            </div>
        </div>
    </div>
</body>
</html>"""


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
