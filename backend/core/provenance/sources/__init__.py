"""Candidate-passage sources for claim provenance extraction.

Each source exposes `async def fetch(ctx) -> SourceResult` and does its own
network I/O. Sources are called in parallel by the extractor.
"""
