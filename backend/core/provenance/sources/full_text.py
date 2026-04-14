"""Full-text source — uses the paper's cached `full_text` column.

When the paper already has `full_text`, we pass the whole document (or a
relevant-looking slice) to the aggregator. The aggregator then produces a
verbatim quote via Claude. No network I/O here.
"""

from backend.core.provenance.types import ExtractionContext, SourceResult


# Keep the payload modest so the aggregator's Claude call stays cheap.
_MAX_FULL_TEXT_CHARS = 40_000


async def fetch(ctx: ExtractionContext) -> SourceResult:
    if not ctx.full_text:
        return SourceResult(source="full_text", status="miss", error="no full_text on paper")

    text = ctx.full_text
    if len(text) > _MAX_FULL_TEXT_CHARS:
        # Keep beginning + end — typically Intro + Results/Discussion — so the
        # aggregator has both framing and conclusions to ground quotes in.
        head = text[: _MAX_FULL_TEXT_CHARS // 2]
        tail = text[-_MAX_FULL_TEXT_CHARS // 2 :]
        text = head + "\n\n[... middle truncated ...]\n\n" + tail

    return SourceResult(
        source="full_text",
        status="hit",
        passages=[text],
        location_hints=["in-paper"],
        extra={"source_label": ctx.full_text_source or "cached"},
    )
