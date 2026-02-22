# AI Analysis Pipeline — Per-Ticket Processing

## Overview

Each ticket passes through a **3-phase pipeline** that extracts structured intelligence from unstructured customer text. The entire pipeline runs **asynchronously** and completes in **~1–3 seconds per ticket**.

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TICKET INPUT                                     │
│  ticket_id · description (text) · segment · attachments · address       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 0 — IMAGE ENRICHMENT                           │
│                        (conditional)                                    │
│                                                                         │
│   ┌─ attachments present? ──────────────────────────────────────────┐   │
│   │                                                                 │   │
│   │  YES ──► gpt-4o-mini (multimodal) ──► image description (text) │   │
│   │          ┌──────────────────────────────────────┐               │   │
│   │          │ "На изображении видно: квитанция об   │               │   │
│   │          │  оплате на сумму 150,000 KZT..."      │               │   │
│   │          └──────────────────────────────────────┘               │   │
│   │          │                                                      │   │
│   │          ▼                                                      │   │
│   │  description = IMAGE_CONTEXT + original_description             │   │
│   │  (enriched text used for ALL Phase 1 tasks)                     │   │
│   │                                                                 │   │
│   │  NO ───► description unchanged, proceed to Phase 1              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                PHASE 1 — PARALLEL TASK EXECUTION                        │
│                    asyncio.gather (6 tasks)                              │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Request Type  │  │  Sentiment   │  │   Urgency    │                   │
│  │              │  │              │  │              │                   │
│  │  LLM call    │  │  LLM call    │  │  LLM call    │                   │
│  │  gpt-4o-mini │  │  gpt-4o-mini │  │  gpt-4o-mini │                   │
│  │              │  │              │  │              │                   │
│  │  ──────────  │  │  ──────────  │  │  ──────────  │                   │
│  │  7 categories│  │  3 classes   │  │  Score 1-10  │                   │
│  │  • Консульт. │  │  • Позитивн. │  │  1 = low     │                   │
│  │  • Жалоба    │  │  • Нейтральн.│  │  10 = critical│                  │
│  │  • Изм.данных│  │  • Негативн. │  │              │                   │
│  │  • Техн.подд.│  │              │  │              │                   │
│  │  • Фин.вопрос│  │              │  │              │                   │
│  │  • Мошенн.   │  │              │  │              │                   │
│  │  • Другое    │  │              │  │              │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
│         │                 │                 │                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │   Language    │  │   Summary    │  │   Geocoding  │                   │
│  │              │  │              │  │              │                   │
│  │  LLM call    │  │  LLM call    │  │  Google Maps  │                   │
│  │  gpt-4o-mini │  │  gpt-4o-mini │  │  Geocode API │                   │
│  │              │  │              │  │              │                   │
│  │  ──────────  │  │  ──────────  │  │  ──────────  │                   │
│  │  3 languages │  │  2-3 sentence│  │  lat, lon    │                   │
│  │  • KZ        │  │  summary +   │  │  formatted   │                   │
│  │  • RU        │  │  recommend-  │  │  address     │                   │
│  │  • ENG       │  │  ation       │  │  status      │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
│         │                 │                 │                            │
└─────────┴────────────┬────┴─────────────────┴───────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              RESILIENCE LAYER (per-task, built into each)                │
│                                                                         │
│  Each of the 6 tasks wraps its call with:                               │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                                                                 │    │
│  │  1. retry_with_timeout(max_retries=3, timeout=30s)              │    │
│  │     │                                                           │    │
│  │     ├── Attempt 1 ──► LLM / API call                           │    │
│  │     │   └── Success? ──► normalize & validate                   │    │
│  │     │                    ├── Valid ──► return result ✓           │    │
│  │     │                    └── Invalid ──► retry                  │    │
│  │     │                                                           │    │
│  │     ├── Attempt 2 ──► exponential backoff (base × 2)            │    │
│  │     │   └── Same validation logic                               │    │
│  │     │                                                           │    │
│  │     ├── Attempt 3 ──► last chance                               │    │
│  │     │   └── Same validation logic                               │    │
│  │     │                                                           │    │
│  │     └── All failed / timeout ──► SAFE FALLBACK                  │    │
│  │                                                                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Safe Fallback Values:                                                  │
│  ┌──────────────────┬─────────────────────┐                             │
│  │ Task             │ Fallback            │                             │
│  ├──────────────────┼─────────────────────┤                             │
│  │ Request Type     │ "Другое"            │                             │
│  │ Sentiment        │ "Нейтральный"       │                             │
│  │ Urgency          │ 5 (medium)          │                             │
│  │ Language         │ "RU"                │                             │
│  │ Summary          │ original text[:200] │                             │
│  │ Geocoding        │ (0.0, 0.0, "", ⚠)  │                             │
│  │ Image Describe   │ "" (empty)          │                             │
│  └──────────────────┴─────────────────────┘                             │
│                                                                         │
│  Key property: ONE FAILED TASK NEVER CRASHES THE ENTIRE REQUEST         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 2 — ASSEMBLY & OUTPUT                          │
│                                                                         │
│  All 6 task results are collected and assembled into:                   │
│                                                                         │
│  ┌────────────────── AnalysisResult ──────────────────────────────┐     │
│  │                                                                │     │
│  │  request_type:    "Жалоба"                                     │     │
│  │  sentiment:       "Негативный"                                 │     │
│  │  urgency_score:   8                                            │     │
│  │  language:        "RU"                                         │     │
│  │  summary:         "Клиент жалуется на... Рекомендация: ..."    │     │
│  │  geo:             { lat: 51.12, lon: 71.43, addr: "...", ✓ }  │     │
│  │  image_enriched:  true / false                                 │     │
│  │                                                                │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                         │
│  ┌────────────────── AnalysisMeta (observability) ────────────────┐     │
│  │                                                                │     │
│  │  model:              "gpt-4o-mini"                             │     │
│  │  task_latencies_ms:  { request_type: 420, sentiment: 380, ... }│     │
│  │  retries_used:       { request_type: 0, urgency: 1, ... }     │     │
│  │  fallbacks_used:     ["geo"]                                   │     │
│  │  total_processing_ms: 1840                                     │     │
│  │                                                                │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                         │
│              ──► Persisted to PostgreSQL via Backend API                 │
│              ──► Displayed on React Dashboard                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Prompt Engineering

All prompts are written in **Russian** (matching the majority of ticket text) and stored in a centralized **Prompt Registry**. Each task uses a `(SYSTEM, USER)` pair:

| Task | System Prompt (key instruction) | Output Contract |
|---|---|---|
| **Request Type** | "Классифицируй обращение клиента в одну из 7 категорий" | Exact string from allowed set |
| **Sentiment** | "Определи тональность: Позитивный, Нейтральный, Негативный" | One of 3 values |
| **Urgency** | "Оцени срочность от 1 до 10. Только число." | Integer `[1–10]` |
| **Language** | "Определи язык: KZ, RU, или ENG" | One of 3 codes |
| **Summary** | "Кратко опиши суть + дай рекомендацию для менеджера" | 2–3 sentence text |
| **Image Describe** | "Опиши что изображено на картинке" | Free-form description |

Each prompt uses `{description}` as the ticket text placeholder.

---

## Validation & Normalization

Every LLM response passes through a **task-specific normalizer** before acceptance:

```
             LLM raw output
                  │
                  ▼
        ┌─────────────────┐
        │   normalize_*() │
        │                 │
        │  • strip()      │
        │  • lower()      │
        │  • fuzzy match  │      e.g., "жалобa" → "Жалоба"
        │  • range check  │      e.g., urgency 0 → reject
        │  • type coerce  │      e.g., "8" → int(8)
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        │                 │
     Valid             Invalid
        │                 │
   Return result     Retry or Fallback
```

**Example normalizers:**
- `normalize_request_type()` — fuzzy-matches against 7 allowed Russian category names
- `normalize_sentiment()` — maps variations ("негатив", "negative", "плохо") → "Негативный"
- `normalize_urgency()` — extracts first integer, clamps to `[1, 10]`
- `normalize_language()` — maps ("казахский", "kazakh", "kz") → "KZ"

---

## Concurrency Model

```
Time ────────────────────────────────────────────────────────────────►

Phase 0    ║ image_describe ║  (only if attachments exist)
           ║   ~800ms       ║
                             │
Phase 1                      ▼
           ┌─────────── asyncio.gather ────────────────┐
           │                                            │
    T+0ms  │  request_type ═══════╗     ~400ms          │
           │  sentiment    ═══════╣     ~380ms          │
           │  urgency      ═══════╣     ~350ms          │
           │  language     ═══════╣     ~300ms          │
           │  summary      ═══════╣     ~500ms          │  ← slowest
           │  geocoding    ═══════╝     ~200ms          │
           │                                            │
           └─── all complete when SLOWEST finishes ─────┘
                             │
                          ~500ms total (not 2130ms sequential!)
                             │
Phase 2                      ▼
           ║ validate + assemble ║  ~5ms
           ║                     ║

Total:     ~500ms (no images) / ~1300ms (with images)
           vs. ~2100ms+ if tasks ran sequentially
```

**Speed-up factor: ~4× from parallelism alone.**

---

## Batch Processing

For the full dataset of **31 tickets**, the AI service exposes a batch endpoint:

```
POST /ai/analyze-batch

  ┌──────────┐
  │ Ticket 1 │──► analyze() ──┐
  │ Ticket 2 │──► analyze() ──┤
  │ Ticket 3 │──► analyze() ──┤   asyncio.gather
  │   ...    │       ...      │   (all tickets in parallel)
  │ Ticket 31│──► analyze() ──┘
  └──────────┘                │
                              ▼
                    31 AnalysisResults
                    Total: ~3-5 seconds
                    (not 31 × 1.5s = 46s sequential)
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Russian prompts** | 90%+ of ticket text is Russian; reduces translation ambiguity |
| **Phase 0 before Phase 1** | Image context enriches ALL subsequent tasks, not just one |
| **`asyncio.gather` parallelism** | 5 independent LLM calls have no data dependencies → run simultaneously |
| **Per-task retry + fallback** | Partial failure is acceptable; a missing sentiment shouldn't block urgency |
| **Normalized validators** | LLM outputs are non-deterministic; normalization ensures type-safe structured data |
| **Observability metadata** | Per-task latency, retry count, and fallback flags enable debugging in production |
| **gpt-4o-mini** | Best cost/speed/quality ratio for classification tasks; supports multimodal |
