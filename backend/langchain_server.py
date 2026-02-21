import asyncio
import json
import os
import re
import math
import logging
from collections import defaultdict, deque
from copy import deepcopy
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
from pydantic import BaseModel, Field
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
NL2SQL_CANDIDATE_TOP_K = int(os.getenv("NL2SQL_CANDIDATE_TOP_K", "4"))
NL2SQL_CANDIDATE_MAX_K = int(os.getenv("NL2SQL_CANDIDATE_MAX_K", "8"))
NL2SQL_CANDIDATE_RESULT_PREVIEW_ROWS = int(
    os.getenv("NL2SQL_CANDIDATE_RESULT_PREVIEW_ROWS", "25")
)
NL2SQL_CHART_BUCKET = os.getenv("NL2SQL_CHART_BUCKET")
NL2SQL_CHART_KEY_PREFIX = os.getenv("NL2SQL_CHART_KEY_PREFIX", "nl2sql/charts")
NL2SQL_CHART_URL_EXPIRES_IN = int(os.getenv("NL2SQL_CHART_URL_EXPIRES_IN", "86400"))

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_timeout=30,
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


class SQLCandidate(BaseModel):
    sql: str = Field(description="Read-only PostgreSQL query using only the provided schema")
    rationale: str = Field(description="Why this candidate can answer the user question")


class SQLCandidateSet(BaseModel):
    candidates: list[SQLCandidate] = Field(default_factory=list)


class SQLCandidateSelection(BaseModel):
    best_candidate_index: int = Field(
        description="Zero-based index of the strongest candidate from the provided list",
        ge=0,
    )
    reason: str = Field(default="")


class StringTranslationVariants(BaseModel):
    variants: list[str] = Field(default_factory=list)


HARD_CODED_TABLES: list[dict[str, Any]] = [
    {
        "table": "public.addresses",
        "description": "Normalized street address used by tickets and location entities.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "Address ID."},
            {"name": "country_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to country dimension."},
            {"name": "region_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to region dimension."},
            {"name": "city_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to city dimension."},
            {"name": "street", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Street name."},
            {"name": "home_number", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Building number."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "country_id", "references_table": "public.countries", "references_column": "id"},
            {"column": "region_id", "references_table": "public.regions", "references_column": "id"},
            {"column": "city_id", "references_table": "public.cities", "references_column": "id"},
        ],
    },
    {
        "table": "public.attachment_types",
        "description": "Dictionary of attachment file/media types.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Attachment type ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Human-readable type name."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.attachments",
        "description": "Stored files attached to tickets.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Attachment ID."},
            {"name": "type", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to attachment type."},
            {"name": "key", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Object storage key/path."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "type", "references_table": "public.attachment_types", "references_column": "id"},
        ],
    },
    {
        "table": "public.cities",
        "description": "City dictionary dimension.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "City ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "City name."},
            {"name": "region_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to region dimension."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "region_id", "references_table": "public.regions", "references_column": "id"},
        ],
    },
    {
        "table": "public.client_segments",
        "description": "Client segmentation metadata for routing priority.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Segment ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Segment name."},
            {"name": "priority", "data_type": "integer", "is_nullable": "NO", "default": "0", "description": "Relative routing/service priority."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.countries",
        "description": "Country dictionary dimension.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Country ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Country name."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.genders",
        "description": "Gender dictionary for ticket submitter demographics.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "Gender ID."},
            {"name": "name", "data_type": "string", "is_nullable": "YES", "default": None, "description": "Gender label."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.manager_positions",
        "description": "Hierarchy positions used by managers.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Manager position ID."},
            {"name": "name", "data_type": "string", "is_nullable": "YES", "default": None, "description": "Position name."},
            {"name": "hierarchy_level", "data_type": "integer", "is_nullable": "NO", "default": "0", "description": "Lower/upper hierarchy order value."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.manager_skills",
        "description": "M2M table linking managers to skills.",
        "columns": [
            {"name": "manager_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to manager."},
            {"name": "skill_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to skill."},
        ],
        "primary_key": ["manager_id", "skill_id"],
        "foreign_keys": [
            {"column": "manager_id", "references_table": "public.managers", "references_column": "id"},
            {"column": "skill_id", "references_table": "public.skills", "references_column": "id"},
        ],
    },
    {
        "table": "public.managers",
        "description": "Routing managers/operators who can be assigned to tickets.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Manager ID."},
            {"name": "position_id", "data_type": "integer", "is_nullable": "YES", "default": None, "description": "FK to manager position."},
            {"name": "city_id", "data_type": "integer", "is_nullable": "YES", "default": None, "description": "FK to city of responsibility."},
            {"name": "in_progress_requests", "data_type": "integer", "is_nullable": "NO", "default": "0", "description": "Current active workload count."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "position_id", "references_table": "public.manager_positions", "references_column": "id"},
            {"column": "city_id", "references_table": "public.cities", "references_column": "id"},
        ],
    },
    {
        "table": "public.offices",
        "description": "Physical office locations.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Office ID."},
            {"name": "city_id", "data_type": "integer", "is_nullable": "YES", "default": None, "description": "FK to city where office is located."},
            {"name": "address", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Office street address text."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "city_id", "references_table": "public.cities", "references_column": "id"},
        ],
    },
    {
        "table": "public.regions",
        "description": "Region/state dimension.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Region ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Region name."},
            {"name": "country_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to country dimension."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "country_id", "references_table": "public.countries", "references_column": "id"},
        ],
    },
    {
        "table": "public.skills",
        "description": "Skill dictionary for manager capabilities.",
        "columns": [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": "autoincrement", "description": "Skill ID."},
            {"name": "name", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Skill name."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [],
    },
    {
        "table": "public.ticket_analysis",
        "description": "AI-enriched analysis output per ticket.",
        "columns": [
            {"name": "ticket_id", "data_type": "uuid", "is_nullable": "NO", "default": None, "description": "Ticket FK and PK."},
            {"name": "request_type", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Predicted request category/type."},
            {"name": "sentiment", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Sentiment label."},
            {"name": "urgency_score", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "Urgency score from analysis."},
            {"name": "language", "data_type": "string", "is_nullable": "NO", "default": None, "description": "Detected language code/name."},
            {"name": "summary", "data_type": "text", "is_nullable": "NO", "default": None, "description": "Short AI summary of ticket content."},
            {"name": "image_enriched", "data_type": "boolean", "is_nullable": "NO", "default": "false", "description": "Whether image context was used."},
            {"name": "latitude", "data_type": "float", "is_nullable": "YES", "default": None, "description": "Optional extracted geo latitude."},
            {"name": "longitude", "data_type": "float", "is_nullable": "YES", "default": None, "description": "Optional extracted geo longitude."},
            {"name": "formatted_address", "data_type": "string", "is_nullable": "NO", "default": "''", "description": "Normalized address text from analysis."},
        ],
        "primary_key": ["ticket_id"],
        "foreign_keys": [
            {"column": "ticket_id", "references_table": "public.tickets", "references_column": "id"},
        ],
    },
    {
        "table": "public.ticket_assignments",
        "description": "Ticket-to-manager assignment bridge.",
        "columns": [
            {"name": "ticket_id", "data_type": "uuid", "is_nullable": "NO", "default": None, "description": "FK to ticket."},
            {"name": "manager_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to manager."},
        ],
        "primary_key": ["ticket_id", "manager_id"],
        "foreign_keys": [
            {"column": "ticket_id", "references_table": "public.tickets", "references_column": "id"},
            {"column": "manager_id", "references_table": "public.managers", "references_column": "id"},
        ],
    },
    {
        "table": "public.ticket_attachments",
        "description": "Many-to-many mapping between tickets and attachments.",
        "columns": [
            {"name": "ticket_id", "data_type": "uuid", "is_nullable": "NO", "default": None, "description": "FK to ticket."},
            {"name": "attachment_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to attachment."},
        ],
        "primary_key": ["ticket_id", "attachment_id"],
        "foreign_keys": [
            {"column": "ticket_id", "references_table": "public.tickets", "references_column": "id"},
            {"column": "attachment_id", "references_table": "public.attachments", "references_column": "id"},
        ],
    },
    {
        "table": "public.tickets",
        "description": "Primary ticket entity submitted by clients/users.",
        "columns": [
            {"name": "id", "data_type": "uuid", "is_nullable": "NO", "default": None, "description": "Ticket ID."},
            {"name": "gender_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to gender dimension."},
            {"name": "date_of_birth", "data_type": "date", "is_nullable": "NO", "default": None, "description": "Client birth date."},
            {"name": "description", "data_type": "string", "is_nullable": "NO", "default": "''", "description": "Raw client request text."},
            {"name": "segment_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to client segment."},
            {"name": "address_id", "data_type": "integer", "is_nullable": "NO", "default": None, "description": "FK to normalized address."},
        ],
        "primary_key": ["id"],
        "foreign_keys": [
            {"column": "gender_id", "references_table": "public.genders", "references_column": "id"},
            {"column": "segment_id", "references_table": "public.client_segments", "references_column": "id"},
            {"column": "address_id", "references_table": "public.addresses", "references_column": "id"},
        ],
    },
]


HARD_CODED_RELATIONSHIPS: list[dict[str, str]] = [
    {"from_table": "public.addresses", "from_column": "country_id", "to_table": "public.countries", "to_column": "id"},
    {"from_table": "public.addresses", "from_column": "region_id", "to_table": "public.regions", "to_column": "id"},
    {"from_table": "public.addresses", "from_column": "city_id", "to_table": "public.cities", "to_column": "id"},
    {"from_table": "public.attachments", "from_column": "type", "to_table": "public.attachment_types", "to_column": "id"},
    {"from_table": "public.cities", "from_column": "region_id", "to_table": "public.regions", "to_column": "id"},
    {"from_table": "public.manager_skills", "from_column": "manager_id", "to_table": "public.managers", "to_column": "id"},
    {"from_table": "public.manager_skills", "from_column": "skill_id", "to_table": "public.skills", "to_column": "id"},
    {"from_table": "public.managers", "from_column": "position_id", "to_table": "public.manager_positions", "to_column": "id"},
    {"from_table": "public.managers", "from_column": "city_id", "to_table": "public.cities", "to_column": "id"},
    {"from_table": "public.offices", "from_column": "city_id", "to_table": "public.cities", "to_column": "id"},
    {"from_table": "public.regions", "from_column": "country_id", "to_table": "public.countries", "to_column": "id"},
    {"from_table": "public.ticket_analysis", "from_column": "ticket_id", "to_table": "public.tickets", "to_column": "id"},
    {"from_table": "public.ticket_assignments", "from_column": "ticket_id", "to_table": "public.tickets", "to_column": "id"},
    {"from_table": "public.ticket_assignments", "from_column": "manager_id", "to_table": "public.managers", "to_column": "id"},
    {"from_table": "public.ticket_attachments", "from_column": "ticket_id", "to_table": "public.tickets", "to_column": "id"},
    {"from_table": "public.ticket_attachments", "from_column": "attachment_id", "to_table": "public.attachments", "to_column": "id"},
    {"from_table": "public.tickets", "from_column": "gender_id", "to_table": "public.genders", "to_column": "id"},
    {"from_table": "public.tickets", "from_column": "segment_id", "to_table": "public.client_segments", "to_column": "id"},
    {"from_table": "public.tickets", "from_column": "address_id", "to_table": "public.addresses", "to_column": "id"},
]


def _build_hard_coded_schema_catalog() -> dict[str, Any]:
    relationships: list[dict[str, Any]] = []
    for rel in HARD_CODED_RELATIONSHIPS:
        relation = dict(rel)
        relation["join_condition"] = (
            f"{relation['from_table']}.{relation['from_column']} = "
            f"{relation['to_table']}.{relation['to_column']}"
        )
        relationships.append(relation)

    tables = sorted(deepcopy(HARD_CODED_TABLES), key=lambda item: item["table"])
    relationships = sorted(
        relationships,
        key=lambda rel: (rel["from_table"], rel["to_table"], rel["from_column"], rel["to_column"]),
    )

    return {
        "source": "hardcoded_from_backend/infrastructure/db/models",
        "table_count": len(tables),
        "relationship_count": len(relationships),
        "table_names": [table["table"] for table in tables],
        "tables": tables,
        "relationships": relationships,
    }


HARD_CODED_SCHEMA_CATALOG = _build_hard_coded_schema_catalog()


SQL_CANDIDATE_SYSTEM_PROMPT = (
    "You generate PostgreSQL NL2SQL candidates. "
    "Return distinct candidate queries that could answer the user question. "
    "Strict rules: one SELECT/CTE statement per candidate, no DML/DDL, no invented tables/columns, "
    "use JOINs only when required to retrieve requested data, and qualify columns with table aliases. "
    "All string filters must be case-insensitive. "
    "For every string comparison, build the WHERE predicate from original+translated lowercase variants. "
    "For exact matching use LOWER(column) IN (...lowered translated variants...). "
    "For contains matching use LOWER(column) LIKE ANY(ARRAY[...lowered translated variants with wildcards...]). "
    "For language filters (RU/KZ/EN), include aliases and translations in the same variant array."
)


SQL_CANDIDATE_SELECTION_SYSTEM_PROMPT = (
    "You choose the best SQL candidate based on execution summaries. "
    "Pick the candidate that best answers the original question with correct semantics and useful rows. "
    "Prefer successful candidates with relevant columns and non-empty results."
)


TRANSLATION_VARIANTS_SYSTEM_PROMPT = (
    "You expand one filter string into equivalent translations for SQL filtering. "
    "Return only direct equivalents of the same concept in RU, KZ, and EN. "
    "No explanations, no morphology lists, no unrelated synonyms."
)


LANGUAGE_ALIASES: dict[str, list[str]] = {
    "ru": [
        "ru",
        "rus",
        "russian",
        "russkiy",
        "рус",
        "русский",
        "русский язык",
    ],
    "kz": [
        "kz",
        "kaz",
        "kazakh",
        "kazakh language",
        "қаз",
        "қазақ",
        "қазақша",
        "каз",
        "казах",
        "казахский",
    ],
    "en": [
        "en",
        "eng",
        "english",
        "англ",
        "английский",
        "английский язык",
    ],
}


def _normalize_string(value: str) -> str:
    return value.strip().lower()


def _unique_non_empty(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_string(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(normalized)
    return unique_values


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _resolve_language_aliases(value: str) -> dict[str, Any]:
    normalized = _normalize_string(value)
    for canonical, aliases in LANGUAGE_ALIASES.items():
        normalized_aliases = {_normalize_string(alias) for alias in aliases}
        if normalized in normalized_aliases:
            values = sorted(normalized_aliases)
            return {
                "canonical": canonical,
                "aliases": values,
                "matched": True,
            }

    return {
        "canonical": normalized,
        "aliases": [normalized],
        "matched": False,
    }


async def _translate_filter_variants(value: str) -> list[str]:
    base = _normalize_string(value)
    if not base:
        return []

    payload = {
        "value": value,
        "target_languages": ["ru", "kz", "en"],
        "max_variants": 12,
    }
    translated_values: list[str] = []

    try:
        translator = llm.with_structured_output(StringTranslationVariants)
        response = await translator.ainvoke(
            [
                ("system", TRANSLATION_VARIANTS_SYSTEM_PROMPT),
                ("human", json.dumps(payload, ensure_ascii=False)),
            ]
        )
        translated_values = response.variants
    except Exception:
        logger.exception("Failed to expand translated string variants; using original filter only")

    variants = _unique_non_empty([base, *translated_values])
    expanded_variants: list[str] = []
    for variant in variants:
        language_resolved = _resolve_language_aliases(variant)
        if language_resolved["matched"]:
            expanded_variants.extend(language_resolved["aliases"])
        else:
            expanded_variants.append(variant)

    return _unique_non_empty(expanded_variants)


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


async def _build_ci_string_predicate(
    column: str,
    value: str,
    mode: str = "contains",
    language_aware: bool = False,
) -> dict[str, Any]:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"exact", "contains"}:
        normalized_mode = "contains"

    translated_variants = await _translate_filter_variants(value)
    if not translated_variants:
        translated_variants = [_normalize_string(value)]

    resolved_language = _resolve_language_aliases(value)
    if language_aware and resolved_language["matched"]:
        translated_variants = _unique_non_empty(
            [*translated_variants, *resolved_language["aliases"]]
        )

    escaped_variants = [_escape_sql_literal(item) for item in translated_variants]
    if normalized_mode == "exact" or language_aware:
        sql_values = ", ".join(f"'{item}'" for item in escaped_variants)
        predicate = f"LOWER({column}) IN ({sql_values})"
    else:
        like_array = ", ".join(f"'%{item}%'" for item in escaped_variants)
        predicate = f"LOWER({column}) LIKE ANY (ARRAY[{like_array}])"

    return {
        "mode": "exact" if language_aware else normalized_mode,
        "language_aware": language_aware,
        "canonical_language": resolved_language["canonical"] if language_aware else None,
        "values_used": translated_variants,
        "predicate": predicate,
    }


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
    return deepcopy(HARD_CODED_SCHEMA_CATALOG)


def _schema_catalog_to_text(schema_catalog: dict[str, Any]) -> str:
    lines: list[str] = []
    for table in schema_catalog["tables"]:
        lines.append(f"Table {table['table']}: {table.get('description', '')}")

        primary_keys = set(table.get("primary_key", []))
        fk_targets = {
            fk["column"]: f"{fk['references_table']}.{fk['references_column']}"
            for fk in table.get("foreign_keys", [])
        }
        for column in table.get("columns", []):
            markers: list[str] = []
            column_name = column["name"]
            if column_name in primary_keys:
                markers.append("PK")
            if column_name in fk_targets:
                markers.append(f"FK->{fk_targets[column_name]}")
            marker_suffix = f" [{', '.join(markers)}]" if markers else ""
            description = column.get("description", "")
            lines.append(
                f"  - {column_name} ({column.get('data_type', 'unknown')})"
                f"{marker_suffix}: {description}"
            )

    lines.append("Relationships:")
    for relationship in schema_catalog["relationships"]:
        lines.append(f"  - {relationship['join_condition']}")

    return "\n".join(lines)


def _normalize_sql_for_dedup(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


async def _generate_sql_candidates(
    question: str,
    top_k: int,
    max_rows: int,
) -> dict[str, Any]:
    clamped_top_k = max(1, min(int(top_k), NL2SQL_CANDIDATE_MAX_K))
    schema_catalog = await _get_schema_catalog()
    schema_text = _schema_catalog_to_text(schema_catalog)

    payload = {
        "question": question.strip(),
        "top_k": clamped_top_k,
        "max_rows": max_rows,
        "schema_text": schema_text,
        "string_filter_policy": {
            "case_insensitive": True,
            "default_mode": "contains",
            "exact_mode_template": "LOWER(column) IN (...lowered translated variants...)",
            "contains_mode_template": (
                "LOWER(column) LIKE ANY(ARRAY['%...lowered translated variant...%', ...])"
            ),
            "language_field_rule": (
                "For string language filters, include RU/KZ/EN alias+translation variants"
            ),
        },
        "language_aliases": LANGUAGE_ALIASES,
    }

    try:
        generator = llm.with_structured_output(SQLCandidateSet)
        candidate_set = await generator.ainvoke(
            [
                ("system", SQL_CANDIDATE_SYSTEM_PROMPT),
                ("human", json.dumps(payload, ensure_ascii=True)),
            ]
        )
    except Exception as exc:
        return {"error": f"Failed to generate SQL candidates: {exc}"}

    candidates: list[dict[str, str]] = []
    seen_sql: set[str] = set()
    for candidate in candidate_set.candidates:
        is_safe, validated_or_error = _enforce_read_only(candidate.sql, max_rows=max_rows)
        if not is_safe:
            continue

        normalized_sql = _normalize_sql_for_dedup(validated_or_error)
        if normalized_sql in seen_sql:
            continue
        seen_sql.add(normalized_sql)

        candidates.append(
            {
                "sql": validated_or_error,
                "rationale": candidate.rationale.strip(),
            }
        )
        if len(candidates) >= clamped_top_k:
            break

    if not candidates:
        return {"error": "No valid SQL candidates were generated."}

    return {
        "question": question,
        "top_k_requested": top_k,
        "top_k_used": clamped_top_k,
        "candidates": candidates,
    }


async def _select_best_candidate_with_llm(
    question: str,
    candidate_summaries: list[dict[str, Any]],
) -> tuple[int, str] | None:
    payload = {
        "question": question,
        "candidates": candidate_summaries,
    }
    try:
        selector = llm.with_structured_output(SQLCandidateSelection)
        selection = await selector.ainvoke(
            [
                ("system", SQL_CANDIDATE_SELECTION_SYSTEM_PROMPT),
                ("human", json.dumps(payload, ensure_ascii=True)),
            ]
        )
    except Exception:
        logger.exception("Failed to select best SQL candidate with LLM; falling back to heuristic")
        return None

    candidate_index = int(selection.best_candidate_index)
    if candidate_index < 0 or candidate_index >= len(candidate_summaries):
        return None
    return candidate_index, selection.reason.strip()


def _heuristic_candidate_score(question: str, sql: str, result: dict[str, Any]) -> int:
    if "error" in result:
        return -10_000

    score = 0
    lower_question = question.lower()
    lower_sql = sql.lower()
    row_count = int(result.get("row_count", 0))

    if row_count > 0:
        score += 40
    if " group by " in lower_sql:
        score += 4

    if any(token in lower_question for token in ("count", "how many", "number of", "total")):
        if "count(" in lower_sql:
            score += 20
        if row_count == 1:
            score += 8

    if any(token in lower_question for token in ("average", "avg", "mean")) and "avg(" in lower_sql:
        score += 18
    if any(token in lower_question for token in ("sum", "total")) and "sum(" in lower_sql:
        score += 14
    if any(token in lower_question for token in ("top", "highest", "lowest", "most", "least")):
        if " order by " in lower_sql:
            score += 12

    if row_count == 0:
        score -= 12

    return score


def _select_best_candidate_with_heuristic(
    question: str,
    candidate_results: list[dict[str, Any]],
) -> tuple[int, str]:
    best_index = 0
    best_score = -10_001

    for index, candidate in enumerate(candidate_results):
        score = _heuristic_candidate_score(
            question=question,
            sql=candidate["sql"],
            result=candidate["result"],
        )
        if score > best_score:
            best_index = index
            best_score = score

    return best_index, f"heuristic_score={best_score}"


def _format_markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not columns:
        return ""

    def _sanitize(value: Any) -> str:
        text = "" if value is None else str(value)
        text = text.replace("\n", " ").replace("|", "\\|")
        return text

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, separator]
    for row in rows:
        line = "| " + " | ".join(_sanitize(row.get(column)) for column in columns) + " |"
        lines.append(line)
    return "\n".join(lines)


def _find_table_definition(
    schema_catalog: dict[str, Any],
    table_name: str,
) -> dict[str, Any] | None:
    normalized = _normalize_qualified_table_name(table_name)
    normalized_lower = normalized.lower()

    for table in schema_catalog["tables"]:
        qualified = table["table"]
        if qualified.lower() == normalized_lower:
            return table

    if "." not in table_name:
        short_name = table_name.strip().strip('"').lower()
        matches = [table for table in schema_catalog["tables"] if table["table"].split(".", 1)[1].lower() == short_name]
        if len(matches) == 1:
            return matches[0]

    return None


async def _run_and_select_best_sql_candidate(
    question: str,
    top_k: int,
    max_rows: int,
) -> dict[str, Any]:
    clamped_max_rows = max(1, min(int(max_rows), NL2SQL_MAX_ROWS))
    generated = await _generate_sql_candidates(
        question=question,
        top_k=top_k,
        max_rows=clamped_max_rows,
    )
    if "error" in generated:
        return generated

    candidates: list[dict[str, str]] = generated["candidates"]
    execution_tasks = [
        _execute_query(query=candidate["sql"], max_rows=clamped_max_rows)
        for candidate in candidates
    ]
    execution_results = await asyncio.gather(*execution_tasks)

    candidate_results: list[dict[str, Any]] = []
    candidate_summaries: list[dict[str, Any]] = []
    for index, (candidate, result) in enumerate(zip(candidates, execution_results), start=1):
        candidate_results.append(
            {
                "index": index - 1,
                "rank": index,
                "sql": candidate["sql"],
                "rationale": candidate["rationale"],
                "result": result,
            }
        )
        candidate_summaries.append(
            {
                "index": index - 1,
                "rank": index,
                "sql": candidate["sql"],
                "error": result.get("error"),
                "row_count": result.get("row_count"),
                "columns": result.get("columns", []),
                "rows_preview": (result.get("rows") or [])[:5],
            }
        )

    if not candidate_results:
        return {"error": "No SQL candidates were available for execution."}

    successful_candidates = [candidate for candidate in candidate_results if "error" not in candidate["result"]]
    if not successful_candidates:
        first_failed = candidate_results[0]
        return {
            "error": "All SQL candidates failed to execute.",
            "selected_sql": first_failed["sql"],
            "query_error": first_failed["result"].get("error", "Unknown SQL execution error."),
        }

    llm_choice = await _select_best_candidate_with_llm(
        question=question,
        candidate_summaries=candidate_summaries,
    )
    if llm_choice is None:
        selected_index, _ = _select_best_candidate_with_heuristic(
            question=question,
            candidate_results=candidate_results,
        )
    else:
        selected_index, _ = llm_choice

    selected_candidate = candidate_results[selected_index]
    selected_result = selected_candidate["result"]
    if "error" in selected_result:
        selected_candidate = successful_candidates[0]
        selected_result = selected_candidate["result"]

    selected_rows = selected_result.get("rows", [])
    selected_columns = selected_result.get("columns", [])
    rows_preview = selected_rows[:NL2SQL_CANDIDATE_RESULT_PREVIEW_ROWS]
    table_markdown = _format_markdown_table(selected_columns, rows_preview)

    return {
        "selected_sql": selected_candidate["sql"],
        "row_count": selected_result.get("row_count", 0),
        "columns": selected_columns,
        "rows": rows_preview,
        "rows_truncated": len(selected_rows) > len(rows_preview),
        "table_markdown": table_markdown,
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
    Return hardcoded schema context from infrastructure/db/models:
    tables, column descriptions, PKs, FKs, and relationship graph.
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
    """List all user-facing tables from the hardcoded model schema catalog."""
    schema_catalog = await _get_schema_catalog()
    return {
        "count": schema_catalog["table_count"],
        "tables": schema_catalog["table_names"],
        "source": schema_catalog["source"],
    }


@tool
async def describe_table(table_name: str) -> dict[str, Any]:
    """Describe one table using hardcoded metadata (input: 'table' or 'schema.table')."""
    schema_catalog = await _get_schema_catalog()
    table = _find_table_definition(schema_catalog=schema_catalog, table_name=table_name)
    if table is None:
        normalized = _normalize_qualified_table_name(table_name)
        return {"error": f"Table '{normalized}' not found in hardcoded schema catalog."}

    return {
        "table": table["table"],
        "description": table.get("description"),
        "columns": table.get("columns", []),
        "primary_key": table.get("primary_key", []),
        "foreign_keys": table.get("foreign_keys", []),
        "source": schema_catalog["source"],
    }


@tool
async def build_string_filter_predicate(
    column: str,
    value: str,
    mode: str = "contains",
    language_aware: bool = False,
) -> dict[str, Any]:
    """
    Build a case-insensitive SQL predicate for string filtering.
    Always includes lowered translated variants of the original value (RU/KZ/EN).
    exact -> LOWER(column) IN (...)
    contains -> LOWER(column) LIKE ANY (ARRAY['%...%'])
    If language_aware=true, forces exact IN semantics over alias+translation variants.
    """
    column_name = column.strip()
    if not column_name:
        return {"error": "column is required"}

    raw_value = value.strip()
    if not raw_value:
        return {"error": "value is required"}

    return await _build_ci_string_predicate(
        column=column_name,
        value=raw_value,
        mode=mode,
        language_aware=_to_bool(language_aware),
    )


@tool
async def build_sql_candidates(
    question: str,
    top_k: int = NL2SQL_CANDIDATE_TOP_K,
    max_rows: int = NL2SQL_MAX_ROWS,
) -> dict[str, Any]:
    """
    Build top-k SQL candidate queries for a natural-language question using hardcoded schema.
    """
    generated = await _generate_sql_candidates(
        question=question,
        top_k=top_k,
        max_rows=max(1, min(int(max_rows), NL2SQL_MAX_ROWS)),
    )
    if "error" in generated:
        return generated

    candidates = [
        {
            "rank": index,
            "sql": candidate["sql"],
        }
        for index, candidate in enumerate(generated["candidates"], start=1)
    ]
    return {
        "question": generated["question"],
        "top_k_used": generated["top_k_used"],
        "candidates": candidates,
    }


@tool
async def run_sql_candidates_and_select_best(
    question: str,
    top_k: int = NL2SQL_CANDIDATE_TOP_K,
    max_rows: int = NL2SQL_MAX_ROWS,
) -> dict[str, Any]:
    """
    End-to-end NL2SQL: build top-k SQL candidates, run all, and return only the best result as table_markdown.
    """
    return await _run_and_select_best_sql_candidate(
        question=question,
        top_k=top_k,
        max_rows=max_rows,
    )


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
    "Before generating SQL, always call get_schema_relationships to load all tables/columns/relationships. "
    "Primary workflow for data questions: get_schema_relationships -> run_sql_candidates_and_select_best -> respond from tool output. "
    "If needed, you can inspect alternatives via build_sql_candidates and run_sql_query manually. "
    "Use suggest_joins only when the question requires data from multiple related tables. "
    "Workflow for analytics requests: run_sql_candidates_and_select_best or analytics_summary, then explain concisely. "
    "Workflow for chart/image requests: get_schema_relationships -> run_sql_candidates_and_select_best -> generate_chart_image (using selected_sql) -> return image_markdown and a short explanation. "
    "Do not output intermediate reasoning, candidate comparisons, or tool traces. "
    "For SQL answers, output the final result table from table_markdown and a short direct statement only. "
    "For string filtering, always use case-insensitive predicates with lowered translated variants of the filter value. "
    "Use build_string_filter_predicate for every WHERE clause string comparison. "
    "For language filters, support RU/KZ/EN aliases and translations using lowercase IN semantics. "
    "Never invent columns/tables. "
    "Do not force JOIN usage; use JOIN only when needed to acquire required data. "
    "If JOIN is needed, use explicit INNER/LEFT JOIN syntax and never implicit comma joins. "
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
        build_string_filter_predicate,
        build_sql_candidates,
        run_sql_candidates_and_select_best,
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
