"use client";

import { useState, useRef, KeyboardEvent, FormEvent } from "react";
import { Compass } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { t } = useLocaleStore();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 150) + "px";
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-3 p-4 border-t border-border bg-background"
    >
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            handleInput();
          }}
          onKeyDown={handleKeyDown}
          placeholder={t.inputPlaceholder}
          disabled={disabled}
          rows={1}
          className="w-full px-4 py-3 bg-surface border border-border rounded-xl text-foreground text-sm resize-none
            placeholder:text-text-secondary
            focus:outline-none focus:border-accent-gold/50 focus:ring-1 focus:ring-accent-gold/20
            disabled:opacity-40 transition-all duration-200"
        />
      </div>
      <button
        type="submit"
        disabled={disabled || !input.trim()}
        className="flex items-center justify-center w-11 h-11 rounded-xl
          bg-accent-gold text-background font-medium
          hover:bg-accent-gold/90
          disabled:opacity-30 disabled:cursor-not-allowed
          transition-all duration-200"
      >
        <Compass size={18} />
      </button>
    </form>
  );
}
