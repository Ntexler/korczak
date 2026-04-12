"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  FileText,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  CloudUpload,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { uploadPaper, getUploadStatus } from "@/lib/api";

interface PaperUploadProps {
  userId?: string;
  onUploadComplete?: () => void;
}

type UploadPhase =
  | "idle"
  | "uploading"
  | "pending"
  | "processing"
  | "approved"
  | "quarantined"
  | "rejected"
  | "duplicate"
  | "error";

interface QualityBreakdown {
  methodology?: number;
  claims?: number;
  writing?: number;
  rigor?: number;
}

interface UploadResult {
  upload_id: string;
  status: string;
  quality_score?: number;
  quality_breakdown?: QualityBreakdown;
  concerns?: string[];
  rejection_reason?: string;
}

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export default function PaperUpload({ userId, onUploadComplete }: PaperUploadProps) {
  const { t, isRtl } = useLocaleStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const resetUpload = () => {
    setPhase("idle");
    setDragOver(false);
    setUploadProgress(0);
    setFileName("");
    setResult(null);
    setErrorMsg("");
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const handleFile = useCallback(
    async (file: File) => {
      // Validate
      if (file.type !== "application/pdf") {
        setErrorMsg(t.pdfOnly);
        setPhase("error");
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setErrorMsg(t.pdfOnly);
        setPhase("error");
        return;
      }

      setFileName(file.name);
      setPhase("uploading");
      setUploadProgress(0);

      // Simulate progress during upload
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + Math.random() * 15;
        });
      }, 200);

      try {
        const res = await uploadPaper(file, userId);
        clearInterval(progressInterval);
        setUploadProgress(100);
        setResult(res);

        const status = res.status as UploadPhase;
        if (["approved", "quarantined", "rejected", "duplicate"].includes(status)) {
          setPhase(status);
          if (status === "approved") onUploadComplete?.();
        } else {
          // Start polling
          setPhase(res.status === "processing" ? "processing" : "pending");
          startPolling(res.upload_id);
        }
      } catch (err: any) {
        clearInterval(progressInterval);
        setErrorMsg(err?.message || "Upload failed");
        setPhase("error");
      }
    },
    [userId, onUploadComplete, t]
  );

  const startPolling = (uploadId: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const status = await getUploadStatus(uploadId);
        setResult(status);
        const phase = status.status as UploadPhase;

        if (["approved", "quarantined", "rejected", "duplicate"].includes(phase)) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setPhase(phase);
          if (phase === "approved") onUploadComplete?.();
        } else if (phase === "processing") {
          setPhase("processing");
        }
      } catch {
        // Keep polling on transient errors
      }
    }, 2000);
  };

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const renderScoreBar = (label: string, score: number) => (
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-secondary w-28 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-sunken rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${score * 100}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={`h-full rounded-full ${
            score >= 0.7
              ? "bg-accent-green"
              : score >= 0.4
              ? "bg-accent-amber"
              : "bg-accent-red"
          }`}
        />
      </div>
      <span className="text-xs text-text-tertiary w-10 text-right">
        {Math.round(score * 100)}%
      </span>
    </div>
  );

  const renderStatus = () => {
    switch (phase) {
      case "uploading":
        return (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-3"
          >
            <div className="flex items-center gap-2">
              <Loader2 size={16} className="animate-spin text-accent-gold" />
              <span className="text-sm text-foreground">{t.uploading}</span>
            </div>
            <div className="h-1.5 bg-surface-sunken rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-accent-gold rounded-full"
                animate={{ width: `${uploadProgress}%` }}
                transition={{ duration: 0.2 }}
              />
            </div>
            <p className="text-xs text-text-tertiary truncate">{fileName}</p>
          </motion.div>
        );

      case "pending":
        return (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2"
          >
            <Loader2 size={16} className="animate-spin text-accent-blue" />
            <span className="text-sm text-text-secondary">
              {isRtl ? "ממתין בתור..." : "Waiting in queue..."}
            </span>
          </motion.div>
        );

      case "processing":
        return (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2"
          >
            <Loader2 size={16} className="animate-spin text-accent-purple" />
            <span className="text-sm text-text-secondary">{t.analyzing}</span>
          </motion.div>
        );

      case "approved":
        return (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-2">
              <CheckCircle2 size={18} className="text-accent-green" />
              <span className="text-sm font-medium text-accent-green">{t.paperApproved}</span>
            </div>
            {result?.quality_breakdown && renderQualityBreakdown()}
          </motion.div>
        );

      case "quarantined":
        return (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-accent-amber" />
              <span className="text-sm font-medium text-accent-amber">{t.paperQuarantined}</span>
            </div>
            {result?.concerns && result.concerns.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-text-secondary">{t.concerns}:</p>
                <ul className="space-y-1">
                  {result.concerns.map((c, i) => (
                    <li key={i} className="text-xs text-text-tertiary flex items-start gap-1.5">
                      <span className="text-accent-amber mt-0.5">-</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result?.quality_breakdown && renderQualityBreakdown()}
          </motion.div>
        );

      case "rejected":
        return (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-2">
              <XCircle size={18} className="text-accent-red" />
              <span className="text-sm font-medium text-accent-red">{t.paperRejected}</span>
            </div>
            {result?.rejection_reason && (
              <p className="text-xs text-text-tertiary bg-surface-sunken rounded-lg px-3 py-2">
                {result.rejection_reason}
              </p>
            )}
            {result?.quality_breakdown && renderQualityBreakdown()}
          </motion.div>
        );

      case "duplicate":
        return (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-2"
          >
            <Info size={18} className="text-accent-blue" />
            <span className="text-sm text-accent-blue">{t.paperDuplicate}</span>
          </motion.div>
        );

      case "error":
        return (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-2"
          >
            <XCircle size={18} className="text-accent-red" />
            <span className="text-sm text-accent-red">{errorMsg}</span>
          </motion.div>
        );

      default:
        return null;
    }
  };

  const renderQualityBreakdown = () => {
    const bd = result?.quality_breakdown;
    if (!bd) return null;

    return (
      <div className="bg-surface-sunken rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-text-secondary">{t.qualityScore}</span>
          {result?.quality_score != null && (
            <span
              className={`text-sm font-bold ${
                result.quality_score >= 0.7
                  ? "text-accent-green"
                  : result.quality_score >= 0.4
                  ? "text-accent-amber"
                  : "text-accent-red"
              }`}
            >
              {Math.round(result.quality_score * 100)}%
            </span>
          )}
        </div>
        <div className="space-y-2.5">
          {bd.methodology != null && renderScoreBar(t.methodology, bd.methodology)}
          {bd.writing != null && renderScoreBar(t.writingQuality, bd.writing)}
          {bd.rigor != null && renderScoreBar(t.academicRigor, bd.rigor)}
        </div>
      </div>
    );
  };

  const isTerminal = ["approved", "quarantined", "rejected", "duplicate", "error"].includes(phase);

  return (
    <div dir={isRtl ? "rtl" : "ltr"} className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Upload size={16} className="text-accent-gold" />
        <h3 className="text-sm font-semibold text-foreground">{t.uploadPaper}</h3>
      </div>

      {/* Drop zone */}
      <AnimatePresence mode="wait">
        {phase === "idle" ? (
          <motion.div
            key="dropzone"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`
              relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-200
              flex flex-col items-center justify-center gap-3 py-10 px-6
              ${
                dragOver
                  ? "border-accent-gold bg-accent-gold/5 scale-[1.01]"
                  : "border-border hover:border-text-tertiary hover:bg-surface/60"
              }
            `}
          >
            <motion.div
              animate={dragOver ? { y: -4, scale: 1.1 } : { y: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 300 }}
            >
              <CloudUpload
                size={36}
                className={dragOver ? "text-accent-gold" : "text-text-tertiary"}
              />
            </motion.div>
            <p className="text-sm text-text-secondary text-center">{t.dragDropHint}</p>
            <p className="text-xs text-text-tertiary">{t.pdfOnly}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={onFileSelect}
              className="hidden"
            />
          </motion.div>
        ) : (
          <motion.div
            key="status"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl border border-border bg-surface p-5 space-y-4"
          >
            {/* File name badge */}
            {fileName && (
              <div className="flex items-center gap-2 text-xs text-text-tertiary">
                <FileText size={14} />
                <span className="truncate">{fileName}</span>
              </div>
            )}

            {renderStatus()}

            {/* Reset button for terminal states */}
            {isTerminal && (
              <button
                onClick={resetUpload}
                className="mt-2 px-4 py-1.5 text-xs font-medium rounded-lg
                  bg-surface-hover hover:bg-surface-elevated text-text-secondary
                  hover:text-foreground transition-colors"
              >
                {t.uploadPaper}
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
