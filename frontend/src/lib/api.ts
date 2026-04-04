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
