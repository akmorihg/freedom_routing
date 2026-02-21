import os
import re
import math
import logging
from collections import defaultdict, deque
from datetime import date, datetime, time
from decimal import Decimal
from html import escape
from typing import Any, Tuple
from uuid import UUID, uuid4

from backend.core.dependency_injection import app_container
from backend.core.dependency_injection.repository_container import RepositoryContainer
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from typing_extensions import TypedDict

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required to run NL2SQL agent.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
NL2SQL_MAX_ROWS = int(os.getenv("NL2SQL_MAX_ROWS", "100"))
NL2SQL_ANALYTICS_MAX_ROWS = int(os.getenv("NL2SQL_ANALYTICS_MAX_ROWS", "500"))
NL2SQL_MAX_CHART_POINTS = int(os.getenv("NL2SQL_MAX_CHART_POINTS", "30"))
NL2SQL_CHART_BUCKET = os.getenv("NL2SQL_CHART_BUCKET")
NL2SQL_CHART_KEY_PREFIX = os.getenv("NL2SQL_CHART_KEY_PREFIX", "nl2sql/charts")
NL2SQL_CHART_URL_EXPIRES_IN = int(os.getenv("NL2SQL_CHART_URL_EXPIRES_IN", "86400"))

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


class GraphState(TypedDict, total=False):
    messages: list[Any]


def _strip_sql_fences(sql: str) -> str:
    value = sql.strip()
    if value.startswith("```"):
        value = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", value)
        value = re.sub(r"\n?```$", "", value)
    return value.strip()


def _extract_tool_call_ids(message: Any) -> list[str]:
    tool_calls: list[Any] = []

    if isinstance(message, AIMessage):
        tool_calls = getattr(message, "tool_calls", []) or []
    elif isinstance(message, dict):
        direct_tool_calls = message.get("tool_calls")
        if isinstance(direct_tool_calls, list):
            tool_calls = direct_tool_calls
        else:
            additional_kwargs = message.get("additional_kwargs")
            if isinstance(additional_kwargs, dict):
                kw_tool_calls = additional_kwargs.get("tool_calls")
                if isinstance(kw_tool_calls, list):
                    tool_calls = kw_tool_calls

    ids: list[str] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            tool_call_id = tool_call.get("id")
            if isinstance(tool_call_id, str) and tool_call_id:
                ids.append(tool_call_id)
    return ids


def _is_ai_message(message: Any) -> bool:
    if isinstance(message, AIMessage):
        return True
    if isinstance(message, dict):
        role = message.get("role")
        msg_type = message.get("type")
        return role == "assistant" or msg_type == "ai"
    return False


def _is_tool_message(message: Any) -> bool:
    if isinstance(message, ToolMessage):
        return True
    if isinstance(message, dict):
        role = message.get("role")
        msg_type = message.get("type")
        return role == "tool" or msg_type == "tool"
    return False


def _get_tool_message_id(message: Any) -> str | None:
    if isinstance(message, ToolMessage):
        tool_call_id = getattr(message, "tool_call_id", None)
        return tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None
    if isinstance(message, dict):
        tool_call_id = message.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id:
            return tool_call_id
    return None


def _sanitize_tool_message_sequence(messages: list[Any]) -> tuple[list[Any], int]:
    sanitized_messages: list[Any] = []
    pending_tool_call_ids: set[str] = set()
    dropped_tool_messages = 0

    for message in messages:
        if _is_ai_message(message):
            sanitized_messages.append(message)
            pending_tool_call_ids = set(_extract_tool_call_ids(message))
            continue

        if _is_tool_message(message):
            tool_call_id = _get_tool_message_id(message)
            if tool_call_id and tool_call_id in pending_tool_call_ids:
                sanitized_messages.append(message)
                pending_tool_call_ids.discard(tool_call_id)
            else:
                dropped_tool_messages += 1
            continue

        sanitized_messages.append(message)
        pending_tool_call_ids = set()

    return sanitized_messages, dropped_tool_messages


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


def _normalize_qualified_table_name(table_name: str) -> str:
    schema_name, table = _parse_table_name(table_name)
    return f"{schema_name}.{table}"


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        if math.isfinite(number):
            return number
    return None


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


async def _get_schema_catalog() -> dict[str, Any]:
    tables_stmt = text(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
        """
    )

    columns_stmt = text(
        """
        SELECT
            c.table_schema,
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.ordinal_position
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE t.table_type = 'BASE TABLE'
          AND c.table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """
    )

    pk_stmt = text(
        """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
        """
    )

    fk_stmt = text(
        """
        SELECT
            tc.table_schema AS from_schema,
            tc.table_name AS from_table,
            kcu.column_name AS from_column,
            ccu.table_schema AS to_schema,
            ccu.table_name AS to_table,
            ccu.column_name AS to_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND ccu.table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY from_schema, from_table, from_column
        """
    )

    try:
        async with engine.connect() as conn:
            table_rows = (await conn.execute(tables_stmt)).mappings().all()
            column_rows = (await conn.execute(columns_stmt)).mappings().all()
            pk_rows = (await conn.execute(pk_stmt)).mappings().all()
            fk_rows = (await conn.execute(fk_stmt)).mappings().all()
    except SQLAlchemyError as exc:
        return {"error": f"Failed to load schema catalog: {exc}"}

    table_map: dict[str, dict[str, Any]] = {}
    for row in table_rows:
        qualified_table = f"{row['table_schema']}.{row['table_name']}"
        table_map[qualified_table] = {
            "table": qualified_table,
            "columns": [],
            "primary_key": [],
            "foreign_keys": [],
        }

    for row in column_rows:
        qualified_table = f"{row['table_schema']}.{row['table_name']}"
        table_map.setdefault(
            qualified_table,
            {"table": qualified_table, "columns": [], "primary_key": [], "foreign_keys": []},
        )
        table_map[qualified_table]["columns"].append(
            {
                "name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"],
                "default": row["column_default"],
            }
        )

    for row in pk_rows:
        qualified_table = f"{row['table_schema']}.{row['table_name']}"
        if qualified_table in table_map:
            table_map[qualified_table]["primary_key"].append(row["column_name"])

    relationships: list[dict[str, Any]] = []
    for row in fk_rows:
        from_table = f"{row['from_schema']}.{row['from_table']}"
        to_table = f"{row['to_schema']}.{row['to_table']}"
        relationship = {
            "from_table": from_table,
            "from_column": row["from_column"],
            "to_table": to_table,
            "to_column": row["to_column"],
            "join_condition": f"{from_table}.{row['from_column']} = {to_table}.{row['to_column']}",
        }
        relationships.append(relationship)

        if from_table in table_map:
            table_map[from_table]["foreign_keys"].append(
                {
                    "column": row["from_column"],
                    "references_table": to_table,
                    "references_column": row["to_column"],
                }
            )

    tables = sorted(table_map.values(), key=lambda item: item["table"])
    relationships = sorted(
        relationships,
        key=lambda rel: (rel["from_table"], rel["to_table"], rel["from_column"], rel["to_column"]),
    )
    table_names = [table["table"] for table in tables]

    return {
        "table_count": len(tables),
        "relationship_count": len(relationships),
        "table_names": table_names,
        "tables": tables,
        "relationships": relationships,
    }


def _resolve_requested_tables(
    requested_tables: list[str],
    available_tables: list[str],
) -> tuple[list[str], list[str]]:
    by_lower = {table.lower(): table for table in available_tables}
    by_name: dict[str, list[str]] = defaultdict(list)
    for table in available_tables:
        by_name[table.split(".", 1)[1].lower()].append(table)

    resolved: list[str] = []
    unresolved: list[str] = []
    for raw_table in requested_tables:
        candidate = raw_table.strip().strip('"')
        if not candidate:
            continue

        normalized = _normalize_qualified_table_name(candidate)
        resolved_table = by_lower.get(normalized.lower())
        if resolved_table is None and "." not in candidate:
            public_variant = f"public.{candidate}"
            resolved_table = by_lower.get(public_variant.lower())
        if resolved_table is None and "." not in candidate:
            matches = by_name.get(candidate.lower(), [])
            if len(matches) == 1:
                resolved_table = matches[0]

        if resolved_table is None:
            unresolved.append(candidate)
        elif resolved_table not in resolved:
            resolved.append(resolved_table)

    return resolved, unresolved


def _find_join_path(
    source_table: str,
    target_table: str,
    adjacency: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]] | None:
    if source_table == target_table:
        return []

    queue = deque([source_table])
    visited = {source_table}
    parent: dict[str, tuple[str, dict[str, str]]] = {}

    while queue:
        current = queue.popleft()
        for edge in adjacency.get(current, []):
            next_table = edge["to_table"]
            if next_table in visited:
                continue

            visited.add(next_table)
            parent[next_table] = (current, edge)
            if next_table == target_table:
                queue.clear()
                break
            queue.append(next_table)

    if target_table not in visited:
        return None

    path: list[dict[str, str]] = []
    cursor = target_table
    while cursor != source_table:
        previous_table, edge = parent[cursor]
        path.append(edge)
        cursor = previous_table
    path.reverse()
    return path


def _sanitize_file_stem(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower())
    return cleaned.strip("_") or "chart"


@app_container.inject(params=["session", "external_session", "global_external_session"])
async def _upload_chart_image_via_repo(
    repository_container: RepositoryContainer,
    bucket: str,
    object_key: str,
    data: bytes,
    content_type: str,
    url_expires_in: int,
) -> dict[str, Any]:
    repo = repository_container.static_file_repo_
    return await repo.create(
        bucket=bucket,
        key=object_key,
        data=data,
        content_type=content_type,
        include_url=True,
        url_expires_in=url_expires_in,
    )


@tool
async def get_schema_relationships() -> dict[str, Any]:
    """
    Return full DB schema context: all tables, columns, PKs, FKs, and relationship graph.
    Use this before writing SQL.
    """
    return await _get_schema_catalog()


@tool
async def suggest_joins(tables: str) -> dict[str, Any]:
    """
    Suggest JOIN paths from foreign-key relationships.
    Input format: comma-separated table names, e.g. "tickets, ticket_analysis, addresses".
    """
    requested_tables = [part.strip() for part in tables.split(",") if part.strip()]
    if len(requested_tables) < 2:
        return {"error": "Provide at least two tables in comma-separated format."}

    schema_catalog = await _get_schema_catalog()
    if "error" in schema_catalog:
        return schema_catalog

    available_tables: list[str] = schema_catalog["table_names"]
    resolved_tables, unresolved_tables = _resolve_requested_tables(
        requested_tables=requested_tables,
        available_tables=available_tables,
    )
    if len(resolved_tables) < 2:
        return {
            "error": "Could not resolve enough valid tables for join suggestion.",
            "requested_tables": requested_tables,
            "resolved_tables": resolved_tables,
            "unresolved_tables": unresolved_tables,
        }

    relationships: list[dict[str, Any]] = schema_catalog["relationships"]
    adjacency: dict[str, list[dict[str, str]]] = defaultdict(list)
    for relationship in relationships:
        from_edge = {
            "from_table": relationship["from_table"],
            "to_table": relationship["to_table"],
            "from_column": relationship["from_column"],
            "to_column": relationship["to_column"],
        }
        adjacency[from_edge["from_table"]].append(from_edge)

        reverse_edge = {
            "from_table": relationship["to_table"],
            "to_table": relationship["from_table"],
            "from_column": relationship["to_column"],
            "to_column": relationship["from_column"],
        }
        adjacency[reverse_edge["from_table"]].append(reverse_edge)

    anchor_table = resolved_tables[0]
    join_paths: list[dict[str, Any]] = []
    disconnected_tables: list[str] = []

    for target_table in resolved_tables[1:]:
        path = _find_join_path(
            source_table=anchor_table,
            target_table=target_table,
            adjacency=adjacency,
        )
        if path is None:
            disconnected_tables.append(target_table)
            continue

        steps = []
        sql_lines = [f"FROM {path[0]['from_table']}"]
        for edge in path:
            on_clause = (
                f"{edge['from_table']}.{edge['from_column']} = "
                f"{edge['to_table']}.{edge['to_column']}"
            )
            steps.append(
                {
                    "from_table": edge["from_table"],
                    "to_table": edge["to_table"],
                    "on": on_clause,
                }
            )
            sql_lines.append(f"JOIN {edge['to_table']} ON {on_clause}")

        join_paths.append(
            {
                "from": anchor_table,
                "to": target_table,
                "steps": steps,
                "suggested_join_sql": "\n".join(sql_lines),
            }
        )

    return {
        "requested_tables": requested_tables,
        "resolved_tables": resolved_tables,
        "unresolved_tables": unresolved_tables,
        "disconnected_tables": disconnected_tables,
        "join_paths": join_paths,
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
    Generate a chart image (SVG), upload it to MinIO, and return a chat-safe URL.
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

    file_stem = _sanitize_file_stem(safe_title)
    object_key = (
        f"{NL2SQL_CHART_KEY_PREFIX.rstrip('/')}/"
        f"{datetime.utcnow().strftime('%Y/%m/%d')}/"
        f"{file_stem}_{uuid4().hex[:12]}.svg"
    )

    settings = app_container.global_vars_map.get("settings")
    default_bucket = getattr(settings, "S3_BUCKET", "static") if settings is not None else "static"
    bucket = NL2SQL_CHART_BUCKET or default_bucket

    try:
        upload_result = await _upload_chart_image_via_repo(
            bucket=bucket,
            object_key=object_key,
            data=svg.encode("utf-8"),
            content_type="image/svg+xml",
            url_expires_in=NL2SQL_CHART_URL_EXPIRES_IN,
        )
    except Exception as exc:
        logger.exception("Failed to upload chart image to MinIO")
        return {
            "query": result["query"],
            "chart_type": normalized_type,
            "error": f"Chart generated but upload failed: {exc}",
        }

    image_url = upload_result.get("url")
    if not image_url:
        return {
            "query": result["query"],
            "chart_type": normalized_type,
            "error": "Chart uploaded but no URL was returned by storage repository.",
        }

    return {
        "query": result["query"],
        "chart_type": normalized_type,
        "x_column": x_column,
        "y_column": y_column,
        "points_used": len(points),
        "dropped_rows_non_numeric_y": dropped_rows,
        "image_mime_type": "image/svg+xml",
        "bucket": bucket,
        "object_key": object_key,
        "image_url": image_url,
        "image_markdown": f"![{safe_title}]({image_url})",
    }


SYSTEM_PROMPT = (
    "You are an NL2SQL assistant for the Freedom Routing backend. "
    "Use tools to inspect schema and run read-only SQL. "
    "Before generating SQL, always call get_schema_relationships to load all schemas and relationships. "
    "For multi-table queries, call suggest_joins with relevant tables and use those join conditions. "
    "Workflow for data questions: get_schema_relationships -> suggest_joins (if multi-table) -> run_sql_query -> answer. "
    "Workflow for analytics requests: analytics_summary -> explanation. "
    "Workflow for chart/image requests: get_schema_relationships -> analytics_summary (optional) -> generate_chart_image -> return image_markdown and short explanation. "
    "Never invent columns/tables. "
    "Prefer explicit INNER/LEFT JOIN syntax over subqueries when data spans multiple models. "
    "Never use implicit comma joins. "
    "Use explicit column names with table qualifiers. "
    "If no rows are returned, state that clearly. "
    "Do not attempt INSERT/UPDATE/DELETE/DDL."
)

llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

nl2sql_agent_graph = create_agent(
    model=llm,
    tools=[
        get_schema_relationships,
        suggest_joins,
        list_tables,
        describe_table,
        run_sql_query,
        analytics_summary,
        generate_chart_image,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def sanitize_messages_node(state: GraphState) -> dict[str, Any]:
    raw_messages = state.get("messages", [])
    if not isinstance(raw_messages, list):
        return {}

    sanitized_messages, dropped_count = _sanitize_tool_message_sequence(raw_messages)
    if dropped_count > 0:
        logger.warning(
            "Dropped %s orphan tool message(s) before model call to avoid OpenAI role validation error.",
            dropped_count,
        )
    return {"messages": sanitized_messages}


async def run_agent_node(state: GraphState) -> dict[str, Any]:
    return await nl2sql_agent_graph.ainvoke(state)


builder = StateGraph(GraphState)
builder.add_node("sanitize_messages", sanitize_messages_node)
builder.add_node("agent", run_agent_node)
builder.set_entry_point("sanitize_messages")
builder.add_edge("sanitize_messages", "agent")
builder.add_edge("agent", END)

graph = builder.compile()
