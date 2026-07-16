"""ITR analysis: recompute a filed return, spot where it went wrong, and say
what it exposes the filer to.

A new top-level capability package alongside query/, computation/, rag/ and
ingestion/. It does not fit any of them: reconciliation is part pure
computation and part retrieval, and splitting it across three packages would
scatter one feature. See "Deliberate taxonomy extensions" in the plan.

The layering inside is the same as everywhere else in this codebase:

    itr_extractor   -- document -> declared facts (with source spans)
    reconciler      -- recompute from declared inputs, diff, emit discrepancies
                       (PURE: no DB, no LLM, no network)
    penalty_mapper  -- discrepancy -> statutory penalty (Neo4j lookup ONLY)
    ai_score        -- discrepancies -> accuracy + risk (PURE, deterministic)

The LLM appears nowhere in this package. It never decides whether a return is
wrong, never picks the penalty, and never computes the score -- those are
arithmetic and graph lookups. It only narrates the result, upstream in
orchestration.
"""
