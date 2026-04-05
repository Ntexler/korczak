"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { X, TreePine, Loader2, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import * as d3 from "d3";
import { useLocaleStore } from "@/stores/localeStore";
import { getKnowledgeTree, getTreeBranches, chooseTreeBranch } from "@/lib/api";
import BranchChoiceModal from "./BranchChoiceModal";
import TreeProgress from "./TreeProgress";

interface KnowledgeTreeProps {
  userId: string;
  onClose: () => void;
}

interface TreeNode {
  concept_id: string;
  name: string;
  type: string;
  depth: number;
  status: string;
  centrality: number;
  is_branch_point: boolean;
  parent_id: string | null;
  child_count: number;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "#3FB950",
  in_progress: "#E8B931",
  available: "#E8EAED",
  locked: "#3A3F47",
};

const STATUS_GLOW: Record<string, string> = {
  completed: "0 0 12px #3FB950",
  in_progress: "0 0 8px #E8B931",
  available: "none",
  locked: "none",
};

export default function KnowledgeTree({ userId, onClose }: KnowledgeTreeProps) {
  const { t } = useLocaleStore();
  const svgRef = useRef<SVGSVGElement>(null);
  const [loading, setLoading] = useState(true);
  const [treeData, setTreeData] = useState<{ nodes: TreeNode[]; edges: any[]; stats: any } | null>(null);
  const [branchModal, setBranchModal] = useState<{ conceptId: string; name: string } | null>(null);
  const [branches, setBranches] = useState<any[]>([]);

  useEffect(() => {
    loadTree();
  }, [userId]);

  const loadTree = async () => {
    setLoading(true);
    try {
      const res = await getKnowledgeTree(userId);
      setTreeData(res);
    } catch {
      setTreeData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!treeData || !svgRef.current) return;
    renderTree(treeData);
  }, [treeData]);

  const renderTree = useCallback((data: typeof treeData) => {
    if (!data || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const margin = { top: 40, right: 40, bottom: 60, left: 40 };

    // Build hierarchy from flat nodes
    const nodeMap = new Map(data.nodes.map((n) => [n.concept_id, { ...n, children: [] as any[] }]));
    const roots: any[] = [];

    for (const node of data.nodes) {
      const mapped = nodeMap.get(node.concept_id)!;
      if (node.parent_id && nodeMap.has(node.parent_id)) {
        nodeMap.get(node.parent_id)!.children.push(mapped);
      } else {
        roots.push(mapped);
      }
    }

    // Create a virtual root if multiple roots
    const virtualRoot = roots.length === 1 ? roots[0] : { name: "Knowledge", children: roots, concept_id: "root", status: "completed", depth: -1, is_branch_point: false, centrality: 1 };

    // Create d3 hierarchy
    const hierarchy = d3.hierarchy(virtualRoot);
    const treeLayout = d3.tree().size([
      width - margin.left - margin.right,
      height - margin.top - margin.bottom,
    ]);

    const root = treeLayout(hierarchy as any);

    // Zoom behavior
    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Center initially
    const initialTransform = d3.zoomIdentity
      .translate(margin.left, height - margin.bottom)
      .scale(1);
    svg.call(zoom.transform, initialTransform);

    // Draw links (branches)
    g.selectAll(".link")
      .data(root.links())
      .enter()
      .append("path")
      .attr("class", "link")
      .attr("d", (d: any) => {
        // Vertical tree growing upward
        return `M${d.source.x},${-d.source.y}
                C${d.source.x},${-(d.source.y + d.target.y) / 2}
                 ${d.target.x},${-(d.source.y + d.target.y) / 2}
                 ${d.target.x},${-d.target.y}`;
      })
      .attr("fill", "none")
      .attr("stroke", (d: any) => {
        const status = d.target.data.status;
        return status === "locked" ? "#2A2E35" : "#4A4F57";
      })
      .attr("stroke-width", (d: any) => {
        return Math.max(1, 3 - d.target.depth * 0.5);
      })
      .attr("stroke-opacity", (d: any) => {
        return d.target.data.status === "locked" ? 0.2 : 0.6;
      });

    // Draw nodes
    const nodeGroup = g.selectAll(".node")
      .data(root.descendants().filter((d: any) => d.data.concept_id !== "root"))
      .enter()
      .append("g")
      .attr("class", "node")
      .attr("transform", (d: any) => `translate(${d.x},${-d.y})`)
      .style("cursor", "pointer")
      .on("click", (_: any, d: any) => {
        if (d.data.is_branch_point && d.data.status !== "locked") {
          handleBranchClick(d.data.concept_id, d.data.name);
        }
      });

    // Node circles
    nodeGroup.append("circle")
      .attr("r", (d: any) => {
        if (d.data.is_branch_point) return 10;
        return Math.max(4, 8 - d.depth);
      })
      .attr("fill", (d: any) => STATUS_COLORS[d.data.status] || "#3A3F47")
      .attr("stroke", (d: any) => {
        if (d.data.is_branch_point) return "#E8B931";
        return "none";
      })
      .attr("stroke-width", (d: any) => d.data.is_branch_point ? 2 : 0)
      .attr("opacity", (d: any) => d.data.status === "locked" ? 0.3 : 1)
      .style("filter", (d: any) => {
        // Glow effect for completed/in-progress
        if (d.data.status === "completed") return "drop-shadow(0 0 6px #3FB950)";
        if (d.data.status === "in_progress") return "drop-shadow(0 0 4px #E8B931)";
        return "none";
      });

    // Branch point fork icon
    nodeGroup.filter((d: any) => d.data.is_branch_point)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", "10px")
      .attr("fill", "#0F1419")
      .text("⑂");

    // Labels
    nodeGroup.append("text")
      .attr("x", (d: any) => d.children ? -12 : 12)
      .attr("dy", "0.3em")
      .attr("text-anchor", (d: any) => d.children ? "end" : "start")
      .attr("font-size", (d: any) => d.data.is_branch_point ? "10px" : "9px")
      .attr("fill", (d: any) => d.data.status === "locked" ? "#4A4F57" : "#B8BCC4")
      .attr("opacity", (d: any) => d.data.status === "locked" ? 0.4 : 0.8)
      .text((d: any) => {
        const name = d.data.name;
        return name.length > 20 ? name.slice(0, 18) + "..." : name;
      });

    // Fog of war gradient for locked branches
    const defs = svg.append("defs");
    const fogGradient = defs.append("radialGradient")
      .attr("id", "fog-gradient");
    fogGradient.append("stop").attr("offset", "0%").attr("stop-color", "#0F1419").attr("stop-opacity", 0);
    fogGradient.append("stop").attr("offset", "100%").attr("stop-color", "#0F1419").attr("stop-opacity", 0.8);

  }, []);

  const handleBranchClick = async (conceptId: string, name: string) => {
    try {
      const res = await getTreeBranches(conceptId, userId);
      setBranches(res.branches || []);
      setBranchModal({ conceptId, name });
    } catch {
      // Handle
    }
  };

  const handleBranchChoice = async (branchPointId: string, chosenId: string) => {
    try {
      await chooseTreeBranch(userId, branchPointId, chosenId);
      setBranchModal(null);
      loadTree(); // Rebuild tree
    } catch {
      // Handle
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-background flex flex-col"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface/30 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <TreePine size={18} className="text-accent-gold" />
          <div>
            <h2 className="text-sm font-semibold text-foreground">{t.knowledgeTree}</h2>
            <span className="text-[10px] text-text-tertiary">{t.yourTree}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {treeData?.stats && <TreeProgress stats={treeData.stats} />}
          <button
            onClick={loadTree}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary"
            title="Refresh"
          >
            <RotateCcw size={14} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Tree canvas */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Loader2 size={24} className="animate-spin text-accent-gold mx-auto mb-2" />
            <p className="text-sm text-text-tertiary">{t.buildingTree}</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <svg
            ref={svgRef}
            className="w-full h-full"
            style={{ background: "#0F1419" }}
          />
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 px-6 py-2 border-t border-border bg-surface/20">
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <div key={status} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-text-tertiary">{t[status] || status}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full border border-accent-gold bg-transparent" />
          <span className="text-[10px] text-text-tertiary">{t.branchPoint}</span>
        </div>
      </div>

      {/* Branch choice modal */}
      {branchModal && (
        <BranchChoiceModal
          branchPointName={branchModal.name}
          branches={branches}
          onChoose={(chosenId) => handleBranchChoice(branchModal.conceptId, chosenId)}
          onClose={() => setBranchModal(null)}
        />
      )}
    </motion.div>
  );
}
