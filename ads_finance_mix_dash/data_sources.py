from __future__ import annotations

import base64
import io
import os
from typing import Any

import pandas as pd

from analysis import normalize_data


def parse_uploaded_file(contents: str, filename: str) -> pd.DataFrame:
    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(decoded))
    elif lower_name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(decoded), sheet_name=0)
    else:
        raise ValueError("Unsupported file format. Please upload CSV or Excel file.")
    return normalize_data(df)


def query_hadoop(config: dict[str, Any]) -> pd.DataFrame:
    engine = os.getenv("HADOOP_ENGINE", "").lower()
    if engine == "trino":
        return query_trino(config)
    if engine in {"impyla", "impala", "hive"}:
        return query_impyla(config)
    raise RuntimeError("Set HADOOP_ENGINE=trino or HADOOP_ENGINE=impyla before using the Hadoop data source.")


def query_trino(config: dict[str, Any]) -> pd.DataFrame:
    import trino

    conn = trino.dbapi.connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.getenv("TRINO_PORT", "443")),
        user=os.environ["TRINO_USER"],
        catalog=os.getenv("TRINO_CATALOG", "hive"),
        schema=os.environ["TRINO_SCHEMA"],
        http_scheme=os.getenv("TRINO_HTTP_SCHEME", "https"),
    )
    sql = build_source_sql(config)
    return normalize_data(pd.read_sql(sql, conn))


def query_impyla(config: dict[str, Any]) -> pd.DataFrame:
    from impala.dbapi import connect

    conn = connect(
        host=os.environ["IMPALA_HOST"],
        port=int(os.getenv("IMPALA_PORT", "21050")),
        user=os.getenv("IMPALA_USER"),
        auth_mechanism=os.getenv("IMPALA_AUTH_MECHANISM", "GSSAPI"),
        use_ssl=os.getenv("IMPALA_USE_SSL", "true").lower() == "true",
        database=os.environ["IMPALA_DATABASE"],
    )
    sql = build_source_sql(config)
    return normalize_data(pd.read_sql(sql, conn))


def build_source_sql(config: dict[str, Any]) -> str:
    table = os.environ["HADOOP_TABLE"]
    # Keep the first Hadoop version conservative: fetch only required columns and date range.
    # Metric and dimension filtering still happen through the audited Python logic.
    date_min = min(config["per_from"], config["post_from"])
    date_max = max(config["per_to"], config["post_to"])
    columns = [
        "RTL_WEEK_BEG_DT",
        "B2C_C2C_FLAG",
        "SELLER_CNTRY_GROUP",
        "FOCUS_CATEGORY",
        "EBAY_LIVE_TAG",
        "ITEM_PRICE_TRANCHE",
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
    return f"""
        SELECT {", ".join(columns)}
        FROM {table}
        WHERE RTL_WEEK_BEG_DT BETWEEN DATE '{date_min}' AND DATE '{date_max}'
    """
