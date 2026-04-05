"use client";

import { motion } from "framer-motion";
import { GitFork, ChevronRight, BookOpen, X } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface Branch {
  concept_id: string;
  name: string;
  type: string;
  definition: string;
  paper_count: number;
  downstream_count: number;
  is_chosen: boolean;
}

interface BranchChoiceModalProps {
  branchPointName: string;
  branches: Branch[];
  onChoose: (conceptId: string) => void;
  onClose: () => void;
}

export default function BranchChoiceModal({
  branchPointName,
  branches,
  onChoose,
  onClose,
}: BranchChoiceModalProps) {
  const { t } = useLocaleStore();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-60 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        className="bg-surface border border-border rounded-2xl shadow-2xl max-w-lg w-full max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-accent-gold/20 flex items-center justify-center">
                <GitFork size={18} className="text-accent-gold" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">{t.choosePath}</h3>
                <p className="text-[11px] text-text-secondary">
                  {t.foundations}: {branchPointName}
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-surface-hover text-text-tertiary">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Branch cards */}
        <div className="px-6 py-4 space-y-3 overflow-y-auto max-h-[50vh]">
          {branches.map((branch, i) => (
            <motion.button
              key={branch.concept_id}
              initial={{ opacity: 0, x: i % 2 === 0 ? -10 : 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1 }}
              onClick={() => onChoose(branch.concept_id)}
              className={`w-full text-left p-4 rounded-xl border transition-all group ${
                branch.is_chosen
                  ? "border-accent-gold bg-accent-gold/10"
                  : "border-border-subtle hover:border-accent-gold/40 hover:bg-surface-hover"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-foreground group-hover:text-accent-gold transition-colors">
                    {branch.name}
                  </h4>
                  {branch.definition && (
                    <p className="text-xs text-text-secondary mt-1 line-clamp-2">
                      {branch.definition}
                    </p>
                  )}
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-[10px] text-text-tertiary">
                      {branch.downstream_count} {t.concepts}
                    </span>
                    <span className="text-[10px] text-text-tertiary flex items-center gap-0.5">
                      <BookOpen size={9} />
                      {branch.paper_count} {t.papers}
                    </span>
                  </div>
                </div>
                <ChevronRight
                  size={16}
                  className="text-text-tertiary group-hover:text-accent-gold transition-colors mt-1"
                />
              </div>
              {branch.is_chosen && (
                <span className="inline-block mt-2 text-[9px] bg-accent-gold/20 text-accent-gold px-2 py-0.5 rounded-full font-medium">
                  {t.chosen}
                </span>
              )}
            </motion.button>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border bg-surface-sunken/50">
          <button
            onClick={onClose}
            className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            {t.exploreBoth}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
