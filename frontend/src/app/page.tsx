"use client";

import { useChatStore } from "@/stores/chatStore";
import { sendMessage } from "@/lib/api";
import ChatMessage from "@/components/Chat/ChatMessage";
import ChatInput from "@/components/Chat/ChatInput";

export default function Home() {
  const {
    messages,
    isLoading,
    conversationId,
    addMessage,
    setLoading,
    setConversationId,
  } = useChatStore();

  const handleSend = async (text: string) => {
    addMessage({ role: "user", content: text });
    setLoading(true);
    try {
      const res = await sendMessage(text, conversationId ?? undefined);
      if (res.conversation_id) setConversationId(res.conversation_id);
      addMessage({
        role: "assistant",
        content: res.response,
        conceptsReferenced: res.concepts_referenced,
        insight: res.insight,
      });
    } catch {
      addMessage({
        role: "assistant",
        content: "Sorry, something went wrong. Please try again.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white dark:bg-gray-950">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            Korczak
          </h1>
          <p className="text-sm text-gray-500">
            Knowledge Navigator
          </p>
        </div>
        <span className="px-3 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded-full">
          Navigator
        </span>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <p className="text-lg font-medium mb-2">Welcome to Korczak</p>
            <p className="text-sm">
              Ask me anything about anthropology. I&apos;ll navigate the knowledge for you.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            insight={msg.insight}
          />
        ))}
        {isLoading && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-100 rounded-2xl px-4 py-3 rounded-bl-sm">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
