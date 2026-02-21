import os
import re
import math
import base64
from datetime import date, datetime, time
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any, Tuple
from uuid import UUID, uuid4

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required to run NL2SQL agent.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
NL2SQL_MAX_ROWS = int(os.getenv("NL2SQL_MAX_ROWS", "100"))
NL2SQL_ANALYTICS_MAX_ROWS = int(os.getenv("NL2SQL_ANALYTICS_MAX_ROWS", "500"))
NL2SQL_MAX_CHART_POINTS = int(os.getenv("NL2SQL_MAX_CHART_POINTS", "30"))
NL2SQL_CHARTS_DIR = os.getenv("NL2SQL_CHARTS_DIR", "generated_charts")

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

LEADING_ALLOWED_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|"
    r"comment|copy|vacuum|analyze|merge|call|do)\b",
    re.IGNORECASE,
)
LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)


def _strip_sql_fences(sql: str) -> str:
    value = sql.strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", value)
        value = re.sub(r"\n?```$", "", value)
    return value.strip()


def _enforce_read_only(sql: str, max_rows: int | None = None) -> Tuple[bool, str]:
    value = _strip_sql_fences(sql).rstrip(";").strip()
    row_limit = max_rows if max_rows is not None else NL2SQL_MAX_ROWS
    row_limit = max(1, row_limit)

    if not value:
        return False, "Query is empty."
    if ";" in value:
        return False, "Only one SQL statement is allowed."
    if not LEADING_ALLOWED_RE.search(value):
        return False, "Only SELECT queries are allowed."
    if FORBIDDEN_SQL_RE.search(value):
        return False, "Only read-only SQL is allowed."

    limit_match = LIMIT_RE.search(value)
    if limit_match:
        current_limit = int(limit_match.group(1))
        if current_limit > row_limit:
            value = LIMIT_RE.sub(f"LIMIT {row_limit}", value, count=1)
    else:
        value = f"{value}\nLIMIT {row_limit}"

    return True, value


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _parse_table_name(table_name: str) -> Tuple[str, str]:
    value = table_name.strip()
    if "." in value:
        schema_name, table = value.split(".", 1)
    else:
        schema_name, table = "public", value
    return schema_name.strip('"'), table.strip('"')


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        if math.isfinite(number):
            return number
    return None


def _sanitize_file_stem(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower())
    return cleaned.strip("_") or "chart"


def _build_chart_svg(
    points: list[tuple[str, float]],
    chart_type: str,
    title: str,
    x_label: str,
    y_label: str,
) -> str:
    width = 960
    height = 560
    left = 80
    right = 30
    top = 70
    bottom = 120
    plot_w = width - left - right
    plot_h = height - top - bottom

    y_values = [value for _, value in points]
    y_min = min(0.0, min(y_values))
    y_max = max(0.0, max(y_values))
    if math.isclose(y_max, y_min):
        y_max = y_min + 1.0

    def x_for_index(index: int, count: int) -> float:
        if count == 1:
            return left + plot_w / 2
        return left + (index / (count - 1)) * plot_w

    def y_for_value(value: float) -> float:
        return top + plot_h - ((value - y_min) / (y_max - y_min)) * plot_h

    zero_y = y_for_value(0.0)
    y_ticks = 5
    tick_rows = []
    for i in range(y_ticks + 1):
        value = y_min + ((y_max - y_min) * i / y_ticks)
        y_pos = y_for_value(value)
        tick_rows.append(
            (
                f'<line x1="{left}" y1="{y_pos:.2f}" x2="{left + plot_w}" y2="{y_pos:.2f}" '
                f'stroke="#e5e7eb" stroke-width="1"/>'
                f'<text x="{left - 10}" y="{y_pos + 4:.2f}" text-anchor="end" '
                f'font-size="11" fill="#4b5563">{value:.2f}</text>'
            )
        )

    count = len(points)
    x_step = plot_w / max(count, 1)
    label_step = max(1, count // 12)
    x_labels = []
    for idx, (label, _) in enumerate(points):
        if idx % label_step != 0 and idx != count - 1:
            continue
        x_pos = left + (idx + 0.5) * x_step if chart_type == "bar" else x_for_index(idx, count)
        x_labels.append(
            f'<text x="{x_pos:.2f}" y="{top + plot_h + 20}" text-anchor="middle" '
            f'font-size="10" fill="#4b5563" transform="rotate(25 {x_pos:.2f},{top + plot_h + 20})">'
            f"{escape(label[:20])}</text>"
        )

    chart_shapes: list[str] = []
    if chart_type == "bar":
        bar_w = max(8.0, x_step * 0.7)
        for idx, (_, value) in enumerate(points):
            x = left + idx * x_step + (x_step - bar_w) / 2
            y = min(y_for_value(value), zero_y)
            h = abs(zero_y - y_for_value(value))
            chart_shapes.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{h:.2f}" '
                f'fill="#2563eb" opacity="0.9"/>'
            )
    else:
        series_points = []
        for idx, (_, value) in enumerate(points):
            x = x_for_index(idx, count)
            y = y_for_value(value)
            series_points.append((x, y))

        if chart_type == "line":
            polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in series_points)
            chart_shapes.append(
                f'<polyline fill="none" stroke="#2563eb" stroke-width="3" points="{polyline}"/>'
            )

        for x, y in series_points:
            chart_shapes.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#2563eb" stroke="#ffffff" stroke-width="1.5"/>'
            )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>
<text x="{width/2:.2f}" y="34" text-anchor="middle" font-size="20" fill="#111827" font-weight="600">{escape(title)}</text>
<line x1="{left}" y1="{top + plot_h:.2f}" x2="{left + plot_w}" y2="{top + plot_h:.2f}" stroke="#111827" stroke-width="1.5"/>
<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h:.2f}" stroke="#111827" stroke-width="1.5"/>
{''.join(tick_rows)}
<line x1="{left}" y1="{zero_y:.2f}" x2="{left + plot_w}" y2="{zero_y:.2f}" stroke="#9ca3af" stroke-width="1"/>
{''.join(chart_shapes)}
{''.join(x_labels)}
<text x="{width/2:.2f}" y="{height - 20}" text-anchor="middle" font-size="12" fill="#374151">{escape(x_label)}</text>
<text x="20" y="{top + plot_h/2:.2f}" text-anchor="middle" font-size="12" fill="#374151" transform="rotate(-90 20,{top + plot_h/2:.2f})">{escape(y_label)}</text>
</svg>"""
    return svg


async def _execute_query(query: str, max_rows: int) -> dict[str, Any]:
    is_safe, validated_or_error = _enforce_read_only(query, max_rows=max_rows)
    if not is_safe:
        return {"error": validated_or_error}

    sql = validated_or_error

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql))
            column_names = list(result.keys())
            rows = result.mappings().all()
    except SQLAlchemyError as exc:
        return {"query": sql, "error": f"SQL execution failed: {exc}"}

    data = [{k: _json_safe(v) for k, v in row.items()} for row in rows]
    return {
        "query": sql,
        "columns": column_names,
        "row_count": len(data),
        "rows": data,
    }


@tool
async def list_tables() -> dict[str, Any]:
    """List all user-facing tables available in the database."""
    stmt = text(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
        """
    )

    try:
        async with engine.connect() as conn:
            result = await conn.execute(stmt)
            rows = result.mappings().all()
    except SQLAlchemyError as exc:
        return {"error": f"Failed to list tables: {exc}"}

    tables = [f"{row['table_schema']}.{row['table_name']}" for row in rows]
    return {"count": len(tables), "tables": tables}


@tool
async def describe_table(table_name: str) -> dict[str, Any]:
    """Describe columns and key relations for one table (input: 'table' or 'schema.table')."""
    schema_name, table = _parse_table_name(table_name)

    columns_stmt = text(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = :schema_name
          AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )

    pk_stmt = text(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = :schema_name
          AND tc.table_name = :table_name
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
    )

    fk_stmt = text(
        """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = :schema_name
          AND tc.table_name = :table_name
        ORDER BY kcu.column_name
        """
    )

    try:
        async with engine.connect() as conn:
            columns_result = await conn.execute(
                columns_stmt,
                {"schema_name": schema_name, "table_name": table},
            )
            columns = [dict(row) for row in columns_result.mappings().all()]

            if not columns:
                return {
                    "error": f"Table '{schema_name}.{table}' not found or has no columns."
                }

            pk_result = await conn.execute(
                pk_stmt,
                {"schema_name": schema_name, "table_name": table},
            )
            primary_key = [row["column_name"] for row in pk_result.mappings().all()]

            fk_result = await conn.execute(
                fk_stmt,
                {"schema_name": schema_name, "table_name": table},
            )
            foreign_keys = [dict(row) for row in fk_result.mappings().all()]
    except SQLAlchemyError as exc:
        return {"error": f"Failed to describe table '{schema_name}.{table}': {exc}"}

    return {
        "table": f"{schema_name}.{table}",
        "columns": columns,
        "primary_key": primary_key,
        "foreign_keys": foreign_keys,
    }


@tool
async def run_sql_query(query: str) -> dict[str, Any]:
    """
    Execute one read-only SQL query (SELECT/CTE only).
    Automatically enforces a max row limit.
    """
    return await _execute_query(query=query, max_rows=NL2SQL_MAX_ROWS)


@tool
async def analytics_summary(query: str, max_rows: int = 200) -> dict[str, Any]:
    """
    Run an analytics query and return computed numeric statistics.
    Use for analytical summaries before generating charts.
    """
    clamped_max_rows = max(1, min(int(max_rows), NL2SQL_ANALYTICS_MAX_ROWS))
    result = await _execute_query(query=query, max_rows=clamped_max_rows)
    if "error" in result:
        return result

    rows: list[dict[str, Any]] = result["rows"]
    columns: list[str] = result["columns"]

    numeric_summary: dict[str, Any] = {}
    for column in columns:
        values: list[float] = []
        for row in rows:
            number = _to_float(row.get(column))
            if number is not None:
                values.append(number)

        if values:
            numeric_summary[column] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "sum": sum(values),
            }

    return {
        "query": result["query"],
        "columns": columns,
        "row_count": result["row_count"],
        "preview_rows": rows[:20],
        "numeric_summary": numeric_summary,
    }


@tool
async def generate_chart_image(
    query: str,
    x_column: str,
    y_column: str,
    chart_type: str = "bar",
    title: str = "Analytics Chart",
    max_points: int = 20,
) -> dict[str, Any]:
    """
    Generate a chart image (SVG + data URI) from a read-only SQL query result.
    Supported chart_type: bar, line, scatter.
    """
    normalized_type = chart_type.strip().lower()
    if normalized_type not in {"bar", "line", "scatter"}:
        return {"error": "chart_type must be one of: bar, line, scatter"}

    clamped_max_points = max(2, min(int(max_points), NL2SQL_MAX_CHART_POINTS))
    result = await _execute_query(query=query, max_rows=clamped_max_points)
    if "error" in result:
        return result

    columns: list[str] = result["columns"]
    rows: list[dict[str, Any]] = result["rows"]
    if not rows:
        return {"query": result["query"], "error": "No rows returned for chart generation."}
    if x_column not in columns:
        return {"query": result["query"], "error": f"x_column '{x_column}' not found in query result."}
    if y_column not in columns:
        return {"query": result["query"], "error": f"y_column '{y_column}' not found in query result."}

    points: list[tuple[str, float]] = []
    dropped_rows = 0
    for row in rows:
        y_value = _to_float(row.get(y_column))
        if y_value is None:
            dropped_rows += 1
            continue
        x_value = row.get(x_column)
        points.append((str(x_value), y_value))

    if not points:
        return {
            "query": result["query"],
            "error": f"No numeric values found in y_column '{y_column}'.",
        }

    safe_title = title.strip() or "Analytics Chart"
    svg = _build_chart_svg(
        points=points,
        chart_type=normalized_type,
        title=safe_title,
        x_label=x_column,
        y_label=y_column,
    )

    chart_dir = Path(__file__).resolve().parent / NL2SQL_CHARTS_DIR
    chart_dir.mkdir(parents=True, exist_ok=True)
    file_stem = _sanitize_file_stem(safe_title)
    file_name = f"{file_stem}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}.svg"
    chart_path = chart_dir / file_name
    chart_path.write_text(svg, encoding="utf-8")

    data_uri = f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('ascii')}"

    return {
        "query": result["query"],
        "chart_type": normalized_type,
        "x_column": x_column,
        "y_column": y_column,
        "points_used": len(points),
        "dropped_rows_non_numeric_y": dropped_rows,
        "image_mime_type": "image/svg+xml",
        "image_path": str(chart_path),
        "image_data_uri": data_uri,
        "image_markdown": f"![{safe_title}]({data_uri})",
    }


SYSTEM_PROMPT = (
    "You are an NL2SQL assistant for the Freedom Routing backend. "
    "Use tools to inspect schema and run read-only SQL. "
    "Workflow for data questions: list_tables -> describe_table (for relevant tables) -> run_sql_query -> answer. "
    "Workflow for analytics requests: analytics_summary -> explanation. "
    "Workflow for chart/image requests: analytics_summary (optional) -> generate_chart_image -> return image_markdown and short explanation. "
    "Never invent columns/tables. "
    "Use explicit joins and explicit column names. "
    "If no rows are returned, state that clearly. "
    "Do not attempt INSERT/UPDATE/DELETE/DDL."
)

llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

graph = create_agent(
    model=llm,
    tools=[
        list_tables,
        describe_table,
        run_sql_query,
        analytics_summary,
        generate_chart_image,
    ],
    system_prompt=SYSTEM_PROMPT,
)
