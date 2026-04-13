"use client";

import { useState, useRef } from "react";
import {
  Upload,
  FileArchive,
  Loader2,
  CheckCircle2,
  AlertCircle,
  X,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { importVault } from "@/lib/api";

interface VaultUploadProps {
  onAnalysisComplete: (result: any) => void;
  field?: string;
}

export default function VaultUpload({ onAnalysisComplete, field }: VaultUploadProps) {
  const { locale, fonts: f } = useLocaleStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith(".zip")) {
      setError(locale === "he" ? "יש להעלות קובץ ZIP של כספת Obsidian" : "Please upload a .zip file of your Obsidian vault");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError(locale === "he" ? "הקובץ גדול מדי (מקסימום 50MB)" : "File too large (max 50MB)");
      return;
    }

    setFileName(file.name);
    setError(null);
    setUploading(true);

    try {
      const result = await importVault(file, "mock-user", field);
      onAnalysisComplete(result);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 p-6 rounded-xl border-2 border-dashed
          cursor-pointer transition-all duration-200
          ${dragging
            ? "border-accent-gold bg-accent-gold/5"
            : "border-border hover:border-accent-gold/40 hover:bg-surface-hover/50"
          }
          ${uploading ? "pointer-events-none opacity-60" : ""}
        `}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".zip"
          onChange={onFileSelect}
          className="hidden"
        />

        {uploading ? (
          <>
            <Loader2 size={28} className="text-accent-gold animate-spin" />
            <div className="text-center">
              <p className="text-sm text-foreground font-medium">
                {locale === "he" ? "מנתח את הכספת שלך..." : "Analyzing your vault..."}
              </p>
              <p className="text-xs text-text-tertiary mt-1">
                {locale === "he"
                  ? "ממפה פתקים למושגים, מחפש פערים וקשרים נסתרים"
                  : "Mapping notes to concepts, finding gaps & hidden connections"}
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="w-12 h-12 rounded-full bg-accent-gold/10 flex items-center justify-center">
              <FileArchive size={22} className="text-accent-gold" />
            </div>
            <div className="text-center">
              <p className="text-sm text-foreground font-medium">
                {locale === "he" ? "העלה את כספת ה-Obsidian שלך" : "Upload your Obsidian vault"}
              </p>
              <p className="text-xs text-text-tertiary mt-1">
                {locale === "he"
                  ? "גרור קובץ ZIP לכאן או לחץ לבחירה"
                  : "Drag a .zip file here or click to browse"}
              </p>
            </div>
          </>
        )}

        {fileName && !uploading && (
          <p className="text-[10px] text-text-tertiary">{fileName}</p>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-accent-red/10 text-accent-red text-xs">
          <AlertCircle size={14} />
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto">
            <X size={12} />
          </button>
        </div>
      )}

      {/* What we do with it */}
      <div className="px-1">
        <p className="text-[10px] text-text-tertiary leading-relaxed">
          {locale === "he"
            ? "קורצאק ינתח את הפתקים שלך, ימפה אותם למושגים אקדמיים, יזהה פערים בידע וימצא קשרים נסתרים. שום דירוג לא ישתנה — רק תובנות אישיות."
            : "Korczak will analyze your notes, map them to academic concepts, detect knowledge gaps, and find hidden connections. No global scores change — only personal insights."}
        </p>
      </div>
    </div>
  );
}
