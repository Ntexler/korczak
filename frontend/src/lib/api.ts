const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function sendMessage(
  message: string,
  conversationId?: string,
  mode: string = "navigator",
  locale: string = "en"
) {
  const res = await fetch(`${API_BASE}/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      mode,
      locale,
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

// --- Library API ---

export async function savePaperToLibrary(userId: string, paperId: string, saveContext: string = "browsing") {
  const res = await fetch(`${API_BASE}/library/papers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, paper_id: paperId, save_context: saveContext }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getLibraryPapers(userId: string, status?: string, limit: number = 50) {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/library/papers?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function updatePaperInLibrary(paperId: string, userId: string, data: Record<string, any>) {
  const res = await fetch(`${API_BASE}/library/papers/${paperId}?user_id=${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function removePaperFromLibrary(paperId: string, userId: string) {
  const res = await fetch(`${API_BASE}/library/papers/${paperId}?user_id=${userId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getPaperLibraryStatus(paperId: string, userId: string) {
  const res = await fetch(`${API_BASE}/library/papers/${paperId}/status?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getLibraryRecommendations(userId: string, limit: number = 10) {
  const res = await fetch(`${API_BASE}/library/recommendations?user_id=${userId}&limit=${limit}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getReadingLists(userId: string) {
  const res = await fetch(`${API_BASE}/library/lists?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function createReadingList(userId: string, title: string, description?: string, color?: string) {
  const res = await fetch(`${API_BASE}/library/lists`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title, description, color }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getReadingListDetail(listId: string) {
  const res = await fetch(`${API_BASE}/library/lists/${listId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteReadingList(listId: string) {
  const res = await fetch(`${API_BASE}/library/lists/${listId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Highlights API ---

export async function createHighlight(data: Record<string, any>) {
  const res = await fetch(`${API_BASE}/highlights/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getHighlights(userId: string, sourceType?: string, sourceId?: string) {
  const params = new URLSearchParams({ user_id: userId });
  if (sourceType) params.set("source_type", sourceType);
  if (sourceId) params.set("source_id", sourceId);
  const res = await fetch(`${API_BASE}/highlights/?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteHighlight(highlightId: string) {
  const res = await fetch(`${API_BASE}/highlights/${highlightId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getLearningPaths(userId: string) {
  const res = await fetch(`${API_BASE}/highlights/paths?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function createLearningPath(userId: string, title: string) {
  const res = await fetch(`${API_BASE}/highlights/paths`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getLearningPathDetail(pathId: string) {
  const res = await fetch(`${API_BASE}/highlights/paths/${pathId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteLearningPath(pathId: string) {
  const res = await fetch(`${API_BASE}/highlights/paths/${pathId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Reading API ---

export async function startReadingSession(userId: string, paperId: string) {
  const res = await fetch(`${API_BASE}/reading/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, paper_id: paperId }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function updateReadingSession(sessionId: string, data: Record<string, any>) {
  const res = await fetch(`${API_BASE}/reading/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function endReadingSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/reading/sessions/${sessionId}/end`, { method: "POST" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getReadingAnalytics(userId: string) {
  const res = await fetch(`${API_BASE}/reading/analytics?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getPaperSections(paperId: string) {
  const res = await fetch(`${API_BASE}/reading/papers/${paperId}/sections`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Syllabus API ---

export async function getSyllabi(search?: string, department?: string, source?: string) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (department) params.set("department", department);
  if (source) params.set("source", source);
  const res = await fetch(`${API_BASE}/syllabus/?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getSyllabusDetail(syllabusId: string) {
  const res = await fetch(`${API_BASE}/syllabus/${syllabusId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getSyllabusConcepts(syllabusId: string) {
  const res = await fetch(`${API_BASE}/syllabus/${syllabusId}/concepts`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getSyllabusProgress(syllabusId: string, userId: string) {
  const res = await fetch(`${API_BASE}/syllabus/${syllabusId}/progress?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function forkSyllabus(syllabusId: string, userId: string) {
  const res = await fetch(`${API_BASE}/syllabus/${syllabusId}/fork`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getUserSyllabi(userId: string) {
  const res = await fetch(`${API_BASE}/syllabus/user/list?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function createCustomSyllabus(userId: string, title: string, department?: string) {
  const res = await fetch(`${API_BASE}/syllabus/user/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title, department }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Community API ---

export async function getComments(paperId: string) {
  const res = await fetch(`${API_BASE}/community/comments?paper_id=${paperId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function createComment(paperId: string, userId: string, content: string, parentId?: string) {
  const res = await fetch(`${API_BASE}/community/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId, user_id: userId, content, parent_id: parentId }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function communityVote(userId: string, targetType: string, targetId: string, voteType: string) {
  const res = await fetch(`${API_BASE}/community/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, target_type: targetType, target_id: targetId, vote_type: voteType }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getPublicHighlights(sourceType: string, sourceId: string) {
  const res = await fetch(`${API_BASE}/community/highlights/public?source_type=${sourceType}&source_id=${sourceId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Knowledge Tree API ---

export async function getKnowledgeTree(userId: string, domain?: string) {
  const params = new URLSearchParams({ user_id: userId });
  if (domain) params.set("domain", domain);
  const res = await fetch(`${API_BASE}/features/tree?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getTreeBranches(conceptId: string, userId: string) {
  const res = await fetch(`${API_BASE}/features/tree/branches?concept_id=${conceptId}&user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function chooseTreeBranch(userId: string, branchPointId: string, chosenConceptId: string) {
  const res = await fetch(
    `${API_BASE}/features/tree/choose?user_id=${userId}&branch_point_id=${branchPointId}&chosen_concept_id=${chosenConceptId}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getTreeProgress(userId: string) {
  const res = await fetch(`${API_BASE}/features/tree/progress?user_id=${userId}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// --- Connection Feedback API ---

export async function submitConnectionFeedback(
  relationshipId: string,
  feedbackType: string,
  comment?: string,
  userId?: string
) {
  const params = userId ? `?user_id=${userId}` : "";
  const res = await fetch(`${API_BASE}/connections/${relationshipId}/feedback${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback_type: feedbackType, comment }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getConnectionFeedback(relationshipId: string) {
  const res = await fetch(`${API_BASE}/connections/${relationshipId}/feedback`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function proposeConnection(
  sourceConceptId: string,
  targetConceptId: string,
  relationshipType: string,
  explanation: string,
  userId?: string
) {
  const params = userId ? `?user_id=${userId}` : "";
  const res = await fetch(`${API_BASE}/connections/propose${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_concept_id: sourceConceptId,
      target_concept_id: targetConceptId,
      relationship_type: relationshipType,
      explanation,
    }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getProposedConnections(status: string = "pending") {
  const res = await fetch(`${API_BASE}/connections/proposals?status=${status}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function voteProposal(proposalId: string, vote: "up" | "down") {
  const res = await fetch(`${API_BASE}/connections/proposals/${proposalId}/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vote }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
