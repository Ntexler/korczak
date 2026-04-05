"use client";

import { Highlight } from "@/stores/highlightStore";

interface HighlightOverlayProps {
  text: string;
  highlights: Highlight[];
}

/**
 * Renders text with highlight spans overlaid.
 * Uses start_offset and end_offset when available, otherwise does text matching.
 */
export default function HighlightOverlay({ text, highlights }: HighlightOverlayProps) {
  if (!highlights.length) {
    return <span>{text}</span>;
  }

  // Build ranges from highlights
  const ranges: { start: number; end: number; color: string; annotation: string | null }[] = [];

  for (const h of highlights) {
    if (h.start_offset != null && h.end_offset != null) {
      ranges.push({
        start: h.start_offset,
        end: h.end_offset,
        color: h.color,
        annotation: h.annotation,
      });
    } else {
      // Fallback: find text within the content
      const idx = text.indexOf(h.highlighted_text);
      if (idx >= 0) {
        ranges.push({
          start: idx,
          end: idx + h.highlighted_text.length,
          color: h.color,
          annotation: h.annotation,
        });
      }
    }
  }

  if (!ranges.length) {
    return <span>{text}</span>;
  }

  // Sort by start position
  ranges.sort((a, b) => a.start - b.start);

  // Build segments
  const segments: React.ReactNode[] = [];
  let pos = 0;

  for (const range of ranges) {
    // Text before this highlight
    if (range.start > pos) {
      segments.push(<span key={`t-${pos}`}>{text.slice(pos, range.start)}</span>);
    }

    // Highlighted text
    segments.push(
      <mark
        key={`h-${range.start}`}
        className="rounded px-0.5 cursor-help"
        style={{ backgroundColor: `${range.color}30`, borderBottom: `2px solid ${range.color}` }}
        title={range.annotation || undefined}
      >
        {text.slice(range.start, range.end)}
      </mark>
    );

    pos = range.end;
  }

  // Remaining text
  if (pos < text.length) {
    segments.push(<span key={`t-${pos}`}>{text.slice(pos)}</span>);
  }

  return <>{segments}</>;
}
