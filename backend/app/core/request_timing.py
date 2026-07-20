"""Per-request timing: where the wall-clock time of a request actually went.

A query here can take four seconds, and the useful question is never "was it
slow" but "which service was slow" -- Pinecone, the embedding call, the chat
completion, or the graph. So spans name the external service rather than
splitting framework-vs-application, which would only ever say "the handler".

Spans are collected in a ContextVar. asyncio copies the context into each task,
so a span opened inside `asyncio.gather` still lands on the right request
without threading an argument through every call signature between the
middleware and the Pinecone client.

INTERVALS, NOT DURATIONS -- the subtle part. `hybrid_retriever.hybrid_search`
runs the Pinecone and Neo4j legs concurrently, so those two spans overlap in
wall-clock time. Summing durations would exceed the request total and make the
leftover "app" figure negative. Recording (start, end) and merging overlapping
intervals gives the true time the request spent waiting on external services,
so the reported numbers always add up. Per-service figures stay raw: "pinecone
took 340ms" is true even while Neo4j ran alongside it.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

# Set per request by RequestTimingMiddleware. The default is None rather than
# an empty list so that a span opened outside a request (a startup seed query,
# a test calling a service directly) is silently ignored instead of
# accumulating into a list nobody ever drains.
_SPANS: ContextVar[list["Span"] | None] = ContextVar("request_spans", default=None)


@dataclass(frozen=True)
class Span:
    name: str
    start: float
    end: float

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000


def start_request() -> list[Span]:
    """Begin collecting spans for one request. Returns the list to read later."""
    spans: list[Span] = []
    _SPANS.set(spans)
    return spans


def clear_request() -> None:
    _SPANS.set(None)


@asynccontextmanager
async def record_span(name: str):
    """Time an external call and attribute it to the current request.

    A no-op when there is no active request, so services stay callable from
    tests, scripts and startup without special-casing.
    """
    spans = _SPANS.get()
    if spans is None:
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        # Recorded in `finally` so a failed call still shows its cost: a
        # request slow because Neo4j timed out must not look instant.
        spans.append(Span(name=name, start=start, end=time.perf_counter()))


def record_elapsed(name: str, elapsed_ms: float) -> None:
    """Attribute an already-measured duration to the current request.

    For calls that time themselves: the LLM providers compute `latency_ms` on
    every response, so re-measuring around them would be duplicate work.
    The interval is back-dated from now, which is accurate enough for a leg
    whose own clock we trust.
    """
    spans = _SPANS.get()
    if spans is None:
        return
    end = time.perf_counter()
    spans.append(Span(name=name, start=end - (elapsed_ms / 1000), end=end))


def _merged_external_ms(spans: list[Span]) -> float:
    """Wall-clock time spent inside external calls, counting overlap once."""
    if not spans:
        return 0.0

    merged: list[list[float]] = []
    for span in sorted(spans, key=lambda s: s.start):
        if merged and span.start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span.end)
        else:
            merged.append([span.start, span.end])
    return sum(end - start for start, end in merged) * 1000


def format_timings(spans: list[Span], total_ms: float, framework_ms: float) -> str:
    """The parenthesised breakdown, e.g.
    "framework: 12ms, pinecone: 340ms, openai-chat: 3180ms, app: 406ms".

    Same-named spans are summed and counted: three graph reads read as
    "neo4j: 95ms (x3)", which distinguishes one slow query from many quick ones.
    """
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for span in spans:
        totals[span.name] = totals.get(span.name, 0.0) + span.duration_ms
        counts[span.name] = counts.get(span.name, 0) + 1

    parts = [f"framework: {framework_ms:.0f}ms"]
    for name, ms in sorted(totals.items(), key=lambda kv: -kv[1]):
        suffix = f" (x{counts[name]})" if counts[name] > 1 else ""
        parts.append(f"{name}: {ms:.0f}ms{suffix}")

    # Whatever is left after the framework and the external waits: our own
    # Python -- parsing, computation, serialisation -- plus any I/O not
    # instrumented (Postgres and Redis have no single chokepoint to hook).
    # Clamped at zero: clock jitter on a sub-millisecond request should never
    # print a negative.
    app_ms = max(0.0, total_ms - framework_ms - _merged_external_ms(spans))
    parts.append(f"app: {app_ms:.0f}ms")
    return ", ".join(parts)
