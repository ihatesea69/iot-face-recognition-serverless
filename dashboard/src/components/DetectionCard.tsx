"use client";

import { DetectionEvent } from "@/lib/mongodb";

interface DetectionCardProps {
  event: DetectionEvent;
}

export default function DetectionCard({ event }: DetectionCardProps) {
  const isStranger = event.detection.type === "stranger";
  const isKnown = event.detection.type === "known";
  const noFace = event.detection.type === "no_face";

  const formatTime = (date: Date | string) => {
    return new Date(date).toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div
      className={`rounded-xl overflow-hidden shadow-lg transition-all hover:shadow-xl ${
        isStranger
          ? "border-2 border-red-500 bg-red-50"
          : isKnown
          ? "border-2 border-green-500 bg-green-50"
          : "border border-gray-200 bg-gray-50"
      }`}
    >
      <div className="relative">
        <img
          src={event.image_url}
          alt="Detection"
          className="w-full h-48 object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = "/placeholder.svg";
          }}
        />
        <div
          className={`absolute top-2 right-2 px-3 py-1 rounded-full text-sm font-semibold ${
            isStranger
              ? "bg-red-500 text-white"
              : isKnown
              ? "bg-green-500 text-white"
              : "bg-gray-500 text-white"
          }`}
        >
          {isStranger ? "NGƯỜI LẠ" : isKnown ? "NGƯỜI QUEN" : "KHÔNG CÓ MẶT"}
        </div>
      </div>

      <div className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">
            {formatTime(event.timestamp)}
          </span>
          {event.detection.confidence > 0 && (
            <span className="text-sm font-medium text-gray-700">
              {event.detection.confidence.toFixed(1)}%
            </span>
          )}
        </div>

        {isKnown && event.detection.external_id && (
          <div className="mt-2 p-2 bg-green-100 rounded-lg">
            <span className="text-green-800 font-medium">
              👤 {event.detection.external_id}
            </span>
          </div>
        )}

        {isStranger && (
          <div className="mt-2 p-2 bg-red-100 rounded-lg">
            <span className="text-red-800 font-medium">
              ⚠️ Phát hiện người lạ!
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
