"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Flag } from "lucide-react";
import { communityVote } from "@/lib/api";

interface VoteButtonProps {
  targetType: string;
  targetId: string;
  userId?: string;
  upvotes?: number;
  downvotes?: number;
  size?: number;
}

export default function VoteButton({
  targetType,
  targetId,
  userId,
  upvotes = 0,
  downvotes = 0,
  size = 12,
}: VoteButtonProps) {
  const [ups, setUps] = useState(upvotes);
  const [downs, setDowns] = useState(downvotes);
  const [myVote, setMyVote] = useState<string | null>(null);

  const handleVote = async (voteType: string) => {
    if (!userId) return;
    try {
      const res = await communityVote(userId, targetType, targetId, voteType);
      if (res.status === "removed" || res.action === "toggle_off") {
        if (voteType === "upvote") setUps((u) => Math.max(0, u - 1));
        if (voteType === "downvote") setDowns((d) => Math.max(0, d - 1));
        setMyVote(null);
      } else {
        if (myVote === "upvote" && voteType !== "upvote") setUps((u) => Math.max(0, u - 1));
        if (myVote === "downvote" && voteType !== "downvote") setDowns((d) => Math.max(0, d - 1));
        if (voteType === "upvote") setUps((u) => u + 1);
        if (voteType === "downvote") setDowns((d) => d + 1);
        setMyVote(voteType);
      }
    } catch {
      // Silently fail
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => handleVote("upvote")}
        className={`flex items-center gap-0.5 p-0.5 rounded transition-colors ${
          myVote === "upvote" ? "text-green-400" : "text-text-tertiary hover:text-green-400"
        }`}
      >
        <ThumbsUp size={size} />
        {ups > 0 && <span className="text-[10px]">{ups}</span>}
      </button>
      <button
        onClick={() => handleVote("downvote")}
        className={`flex items-center gap-0.5 p-0.5 rounded transition-colors ${
          myVote === "downvote" ? "text-red-400" : "text-text-tertiary hover:text-red-400"
        }`}
      >
        <ThumbsDown size={size} />
        {downs > 0 && <span className="text-[10px]">{downs}</span>}
      </button>
      <button
        onClick={() => handleVote("flag")}
        className="p-0.5 rounded text-text-tertiary hover:text-orange-400 transition-colors"
        title="Flag"
      >
        <Flag size={size - 2} />
      </button>
    </div>
  );
}
