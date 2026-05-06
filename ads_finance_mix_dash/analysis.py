from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd


METRIC_FORMULAS = {
    "PLG_Rev_Pen": "PLG_REV_NET / GMV",
    "PLP_Rev_Pen": "PLP_REV_NET / GMV",
    "PO_Rev_Pen": "PO_REV_NET / GMV",
    "PS_Rev_Pen": "PS_REV_NET / GMV",
    "Ads_Rev_Pen": "(PLG_REV_NET + PLP_REV_NET + PO_REV_NET + PS_REV_NET) / GMV",
    "PLG_Adoption": "PLG_ENABLED_GMV / GMV",
    "PLP_Adoption": "PLP_ENABLED_GMV / GMV",
    "PLG_Credit_Ratio": "PLG_CREDIT / PLG_REV_GROSS",
}

NUMERIC_COLUMNS = [
    "PLG_REV_NET",
    "PLP_REV_NET",
    "PO_REV_NET",
    "PS_REV_NET",
    "GMV",
    "PLG_ENABLED_GMV",
    "PLP_ENABLED_GMV",
    "PLG_CREDIT",
    "PLG_REV_GROSS",
]

MAIN_DIMENSIONS = [
    {"name": "B2C_C2C", "column": "B2C_C2C_FLAG"},
    {"name": "Seller_Cntry", "column": "SELLER_CNTRY_GROUP"},
    {"name": "Focus_Category", "column": "FOCUS_CATEGORY"},
    {"name": "eBay_Live_Tag", "column": "EBAY_LIVE_TAG"},
    {"name": "Item_Price_Tranche", "column": "ITEM_PRICE_TRANCHE"},
]

DIMENSION_LABELS = {
    "B2C_C2C_FLAG": "B2C_C2C",
    "SELLER_CNTRY_GROUP": "Seller_Cntry",
    "FOCUS_CATEGORY": "Focus_Category",
    "EBAY_LIVE_TAG": "eBay_Live_Tag",
    "ITEM_PRICE_TRANCHE": "Item_Price_Tranche",
}


@dataclass(frozen=True)
class AnalysisConfig:
    per_from: str
    per_to: str
    post_from: str
    post_to: str
    b2c_c2c: list[str]
    seller_cntry: list[str]
    focus_category: list[str]
    ebay_live_tag: list[str]
    item_price_tranche: list[str]
    diy_dim1: str | None
    diy_dim2: str | None
    key_metric: str

    @property
    def dimension_filters(self) -> list[dict[str, Any]]:
        return [
            {"name": "B2C_C2C", "column": "B2C_C2C_FLAG", "values": self.b2c_c2c},
            {"name": "Seller_Cntry", "column": "SELLER_CNTRY_GROUP", "values": self.seller_cntry},
            {"name": "Focus_Category", "column": "FOCUS_CATEGORY", "values": self.focus_category},
            {"name": "eBay_Live_Tag", "column": "EBAY_LIVE_TAG", "values": self.ebay_live_tag},
            {"name": "Item_Price_Tranche", "column": "ITEM_PRICE_TRANCHE", "values": self.item_price_tranche},
        ]


def normalize_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "RTL_WEEK_BEG_DT" in df.columns:
        df["RTL_WEEK_BEG_DT"] = pd.to_datetime(df["RTL_WEEK_BEG_DT"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def get_dates(df: pd.DataFrame) -> list[str]:
    dates = df["RTL_WEEK_BEG_DT"].dropna().astype(str).unique().tolist()
    return sorted(dates, reverse=True)


def get_dimension_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str)
    return sorted(v for v in values.unique().tolist() if v)


def calculate_metric(row: dict[str, float] | pd.Series, metric: str) -> float:
    gmv = float(row.get("GMV", 0) or 0)
    if gmv == 0 and metric != "PLG_Credit_Ratio":
        return 0
    if metric == "PLG_Rev_Pen":
        return float(row.get("PLG_REV_NET", 0) or 0) / gmv
    if metric == "PLP_Rev_Pen":
        return float(row.get("PLP_REV_NET", 0) or 0) / gmv
    if metric == "PO_Rev_Pen":
        return float(row.get("PO_REV_NET", 0) or 0) / gmv
    if metric == "PS_Rev_Pen":
        return float(row.get("PS_REV_NET", 0) or 0) / gmv
    if metric == "Ads_Rev_Pen":
        numerator = sum(float(row.get(col, 0) or 0) for col in ["PLG_REV_NET", "PLP_REV_NET", "PO_REV_NET", "PS_REV_NET"])
        return numerator / gmv
    if metric == "PLG_Adoption":
        return float(row.get("PLG_ENABLED_GMV", 0) or 0) / gmv
    if metric == "PLP_Adoption":
        return float(row.get("PLP_ENABLED_GMV", 0) or 0) / gmv
    if metric == "PLG_Credit_Ratio":
        gross = float(row.get("PLG_REV_GROSS", 0) or 0)
        return 0 if gross == 0 else float(row.get("PLG_CREDIT", 0) or 0) / gross
    return 0


def filter_by_time_period(df: pd.DataFrame, date_from: str, date_to: str) -> pd.DataFrame:
    dates = df["RTL_WEEK_BEG_DT"].astype(str)
    return df[(dates >= date_from) & (dates <= date_to)]


def apply_dimension_filters(df: pd.DataFrame, dimensions: list[dict[str, Any]]) -> pd.DataFrame:
    filtered = df
    for dim in dimensions:
        values = dim.get("values") or ["Total"]
        if "Total" not in values and dim["column"] in filtered.columns:
            filtered = filtered[filtered[dim["column"]].astype(str).isin(values)]
    return filtered


def aggregate_data(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {col: 0.0 for col in NUMERIC_COLUMNS}
    return {col: float(df[col].sum()) for col in NUMERIC_COLUMNS}


def calculate_t4w_average(df: pd.DataFrame, post_from: str, key_metric: str, dimensions: list[dict[str, Any]]) -> float | None:
    post_start = pd.to_datetime(post_from)
    t4w_end = post_start - timedelta(days=1)
    t4w_start = post_start - timedelta(days=28)
    t4w_data = filter_by_time_period(df, t4w_start.strftime("%Y-%m-%d"), t4w_end.strftime("%Y-%m-%d"))
    if t4w_data.empty:
        return None
    filtered = apply_dimension_filters(t4w_data, dimensions)
    if filtered.empty:
        return None
    return calculate_metric(aggregate_data(filtered), key_metric)


def calculate_previous_year_metric(
    df: pd.DataFrame,
    post_from: str,
    post_to: str,
    key_metric: str,
    dimensions: list[dict[str, Any]],
) -> float | None:
    post_start = pd.to_datetime(post_from)
    post_end = pd.to_datetime(post_to)
    duration_days = round((post_end - post_start).days)
    ly_start = post_start - timedelta(days=364)
    ly_end = ly_start + timedelta(days=duration_days)
    ly_data = filter_by_time_period(df, ly_start.strftime("%Y-%m-%d"), ly_end.strftime("%Y-%m-%d"))
    if ly_data.empty:
        return None
    filtered = apply_dimension_filters(ly_data, dimensions)
    if filtered.empty:
        return None
    return calculate_metric(aggregate_data(filtered), key_metric)


def analyze_dimension(
    raw_df: pd.DataFrame,
    per_df: pd.DataFrame,
    post_df: pd.DataFrame,
    dimension: dict[str, Any],
    key_metric: str,
    total_gmv_per: float,
    total_gmv_post: float,
) -> list[dict[str, Any]]:
    column = dimension["column"]
    values = get_dimension_values(raw_df, column)
    rows: list[dict[str, Any]] = []
    for value in values:
        per_filtered = per_df[per_df[column].astype(str) == value]
        post_filtered = post_df[post_df[column].astype(str) == value]
        if per_filtered.empty and post_filtered.empty:
            continue
        agg_per = aggregate_data(per_filtered)
        agg_post = aggregate_data(post_filtered)
        metric_per = calculate_metric(agg_per, key_metric)
        metric_post = calculate_metric(agg_post, key_metric)
        share_per = agg_per["GMV"] / total_gmv_per if total_gmv_per > 0 else 0
        share_post = agg_post["GMV"] / total_gmv_post if total_gmv_post > 0 else 0
        performance_effect = ((share_per + share_post) / 2) * (metric_post - metric_per)
        mix_effect = ((metric_per + metric_post) / 2) * (share_post - share_per)
        rows.append(
            {
                "value": value,
                "metricPer": metric_per,
                "metricPost": metric_post,
                "metricChange": metric_post - metric_per,
                "sharePer": share_per,
                "sharePost": share_post,
                "performanceEffect": performance_effect,
                "mixEffect": mix_effect,
                "totalEffect": performance_effect + mix_effect,
            }
        )
    return sorted(rows, key=lambda row: row["sharePer"], reverse=True)


def analyze_diy_dimension(
    raw_df: pd.DataFrame,
    per_df: pd.DataFrame,
    post_df: pd.DataFrame,
    dim1: str,
    dim2: str,
    key_metric: str,
    total_gmv_per: float,
    total_gmv_post: float,
) -> list[dict[str, Any]]:
    combos = raw_df[[dim1, dim2]].dropna().astype(str).drop_duplicates()
    rows: list[dict[str, Any]] = []
    for _, combo_row in combos.iterrows():
        val1 = combo_row[dim1]
        val2 = combo_row[dim2]
        per_filtered = per_df[(per_df[dim1].astype(str) == val1) & (per_df[dim2].astype(str) == val2)]
        post_filtered = post_df[(post_df[dim1].astype(str) == val1) & (post_df[dim2].astype(str) == val2)]
        if per_filtered.empty and post_filtered.empty:
            continue
        agg_per = aggregate_data(per_filtered)
        agg_post = aggregate_data(post_filtered)
        metric_per = calculate_metric(agg_per, key_metric)
        metric_post = calculate_metric(agg_post, key_metric)
        share_per = agg_per["GMV"] / total_gmv_per if total_gmv_per > 0 else 0
        share_post = agg_post["GMV"] / total_gmv_post if total_gmv_post > 0 else 0
        performance_effect = ((share_per + share_post) / 2) * (metric_post - metric_per)
        mix_effect = ((metric_per + metric_post) / 2) * (share_post - share_per)
        rows.append(
            {
                "value": f"{val1} | {val2}",
                "metricPer": metric_per,
                "metricPost": metric_post,
                "metricChange": metric_post - metric_per,
                "sharePer": share_per,
                "sharePost": share_post,
                "performanceEffect": performance_effect,
                "mixEffect": mix_effect,
                "totalEffect": performance_effect + mix_effect,
            }
        )
    return sorted(rows, key=lambda row: row["sharePer"], reverse=True)


def perform_mix_analysis(df: pd.DataFrame, config: AnalysisConfig) -> dict[str, Any]:
    dimensions = config.dimension_filters
    per_data = filter_by_time_period(df, config.per_from, config.per_to)
    post_data = filter_by_time_period(df, config.post_from, config.post_to)
    filtered_per_data = apply_dimension_filters(per_data, dimensions)
    filtered_post_data = apply_dimension_filters(post_data, dimensions)

    total_gmv_per = float(filtered_per_data["GMV"].sum()) if not filtered_per_data.empty else 0
    total_gmv_post = float(filtered_post_data["GMV"].sum()) if not filtered_post_data.empty else 0
    agg_per = aggregate_data(filtered_per_data)
    agg_post = aggregate_data(filtered_post_data)

    results: dict[str, Any] = {
        "config": config.__dict__,
        "dimensions": [],
        "summary": {
            "metricPer": calculate_metric(agg_per, config.key_metric),
            "metricPost": calculate_metric(agg_post, config.key_metric),
            "metricT4w": calculate_t4w_average(df, config.post_from, config.key_metric, dimensions),
            "metricLy": calculate_previous_year_metric(df, config.post_from, config.post_to, config.key_metric, dimensions),
            "totalPerformanceEffect": 0,
            "totalMixEffect": 0,
        },
    }

    for dim in dimensions:
        dim_results = analyze_dimension(df, filtered_per_data, filtered_post_data, dim, config.key_metric, total_gmv_per, total_gmv_post)
        if dim_results:
            results["dimensions"].append({"name": dim["name"], "results": dim_results})

    if config.diy_dim1 and config.diy_dim2 and config.diy_dim1 != config.diy_dim2:
        diy_results = analyze_diy_dimension(
            df,
            filtered_per_data,
            filtered_post_data,
            config.diy_dim1,
            config.diy_dim2,
            config.key_metric,
            total_gmv_per,
            total_gmv_post,
        )
        if diy_results:
            results["dimensions"].append(
                {
                    "name": f"DIY: {DIMENSION_LABELS.get(config.diy_dim1, config.diy_dim1)} x {DIMENSION_LABELS.get(config.diy_dim2, config.diy_dim2)}",
                    "results": diy_results,
                }
            )

    if results["dimensions"]:
        for row in results["dimensions"][0]["results"]:
            results["summary"]["totalPerformanceEffect"] += row["performanceEffect"]
            results["summary"]["totalMixEffect"] += row["mixEffect"]

    return results


def format_percentage(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.4f}%"
