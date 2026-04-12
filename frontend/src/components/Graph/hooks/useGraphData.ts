import { useState, useEffect, useCallback, useRef } from "react";
import { getGraphVisualization } from "@/lib/api";
import type { GraphNode, GraphEdge, LensType } from "../types";

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeCount: number;
  edgeCount: number;
}

interface UseGraphDataResult {
  graphData: GraphData | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useGraphData(limit: number = 150, activeLens: LensType = "none"): UseGraphDataResult {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(false);
  const lensDataFetchedRef = useRef(false);

  const fetchData = useCallback(async () => {
    const needsLensData = activeLens !== "none";
    // If we already have base data and now need lens data, re-fetch with lens flag
    if (graphData && needsLensData && !lensDataFetchedRef.current) {
      setLoading(true);
      try {
        const data = await getGraphVisualization(limit, true);
        const nodes: GraphNode[] = data.nodes;
        const edges: GraphEdge[] = data.edges;
        const connectionCounts = new Map<string, number>();
        for (const edge of edges) {
          const src = typeof edge.source === "string" ? edge.source : edge.source.id;
          const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
          connectionCounts.set(src, (connectionCounts.get(src) || 0) + 1);
          connectionCounts.set(tgt, (connectionCounts.get(tgt) || 0) + 1);
        }
        for (const node of nodes) {
          node.connection_count = connectionCounts.get(node.id) || 0;
        }
        setGraphData({ nodes, edges, nodeCount: nodes.length, edgeCount: edges.length });
        lensDataFetchedRef.current = true;
      } catch (err) {
        console.error("Lens data fetch error:", err);
      } finally {
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await getGraphVisualization(limit, needsLensData);
      if (needsLensData) lensDataFetchedRef.current = true;
      const nodes: GraphNode[] = data.nodes;
      const edges: GraphEdge[] = data.edges;

      // Compute connection_count for each node
      const connectionCounts = new Map<string, number>();
      for (const edge of edges) {
        const src = typeof edge.source === "string" ? edge.source : edge.source.id;
        const tgt = typeof edge.target === "string" ? edge.target : edge.target.id;
        connectionCounts.set(src, (connectionCounts.get(src) || 0) + 1);
        connectionCounts.set(tgt, (connectionCounts.get(tgt) || 0) + 1);
      }
      for (const node of nodes) {
        node.connection_count = connectionCounts.get(node.id) || 0;
      }

      setGraphData({
        nodes,
        edges,
        nodeCount: nodes.length,
        edgeCount: edges.length,
      });
    } catch (err) {
      console.error("Graph data fetch error:", err);
      setError("Failed to load graph data");
    } finally {
      setLoading(false);
    }
  }, [limit, activeLens, graphData]);

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchData();
    }
  }, [fetchData]);

  // Re-fetch with lens data when lens is activated for the first time
  useEffect(() => {
    if (activeLens !== "none" && graphData && !lensDataFetchedRef.current) {
      fetchData();
    }
  }, [activeLens, graphData, fetchData]);

  return { graphData, loading, error, refetch: fetchData };
}
