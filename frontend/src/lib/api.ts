const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function sendMessage(
  message: string,
  conversationId?: string,
  mode: string = "navigator"
) {
  const res = await fetch(`${API_BASE}/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      mode,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export async function getConversationHistory(conversationId: string) {
  const res = await fetch(`${API_BASE}/chat/history/${conversationId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getGraphStats() {
  const res = await fetch(`${API_BASE}/graph/stats`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function searchConcepts(query: string) {
  const res = await fetch(
    `${API_BASE}/graph/concepts?search=${encodeURIComponent(query)}`
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getConceptDetail(id: string) {
  const res = await fetch(`${API_BASE}/graph/concepts/${id}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getConceptNeighbors(id: string, depth: number = 1) {
  const res = await fetch(
    `${API_BASE}/graph/concepts/${id}/neighbors?depth=${depth}`
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function healthCheck() {
  const res = await fetch(`${API_BASE}/health`);
  return res.ok;
}

export async function getDetailedHealth() {
  const res = await fetch(`${API_BASE}/health/detailed`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Features API ---

export async function getControversies(limit: number = 10) {
  const res = await fetch(`${API_BASE}/features/controversies?limit=${limit}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getDebateLandscape(keyword: string) {
  const res = await fetch(`${API_BASE}/features/debates?keyword=${encodeURIComponent(keyword)}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getResearchGaps(keyword?: string, limit: number = 20) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (keyword) params.set("keyword", keyword);
  const res = await fetch(`${API_BASE}/features/gaps?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getRisingStars(days: number = 90, limit: number = 10) {
  const res = await fetch(`${API_BASE}/features/rising?days=${days}&limit=${limit}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getBriefing(briefingType: string = "daily", userId?: string) {
  const params = new URLSearchParams({ briefing_type: briefingType });
  if (userId) params.set("user_id", userId);
  const res = await fetch(`${API_BASE}/features/briefing?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getBriefingTopics(userId?: string) {
  const params = userId ? `?user_id=${userId}` : "";
  const res = await fetch(`${API_BASE}/features/briefing/topics${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getGraphVisualization(limit: number = 100) {
  const res = await fetch(`${API_BASE}/features/visualization/graph?limit=${limit}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
