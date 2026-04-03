"use client";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  insight?: { type: string; content: string } | null;
}

export default function ChatMessage({ role, content, insight }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] px-4 py-3 rounded-2xl ${
          isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-gray-100 text-gray-900 rounded-bl-sm"
        }`}
      >
        <p className="whitespace-pre-wrap">{content}</p>
        {insight && (
          <div className="mt-3 pt-3 border-t border-gray-300/30">
            <p className="text-xs font-semibold opacity-70 mb-1">
              Insight: {insight.type}
            </p>
            <p className="text-sm">{insight.content}</p>
          </div>
        )}
      </div>
    </div>
  );
}
