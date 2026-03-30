"use client";

import useSWR from "swr";
import { DetectionEvent } from "@/lib/mongodb";
import { useState } from "react";
import Link from "next/link";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function AlertsPage() {
  const { data, error, isLoading } = useSWR<{ events: DetectionEvent[] }>(
    "/api/detections",
    fetcher
  );

  const [filter, setFilter] = useState<"all" | "stranger" | "known">("all");

  const filteredEvents = data?.events?.filter((event) => {
    if (filter === "all") return true;
    return event.detection.type === filter;
  });

  const exportToCSV = () => {
    if (!data?.events) return;

    const headers = ["Timestamp", "Type", "Person", "Confidence", "Image URL"];
    const rows = data.events.map((event) => [
      new Date(event.timestamp).toISOString(),
      event.detection.type,
      event.detection.external_id || "N/A",
      event.detection.confidence.toFixed(2),
      event.image_url,
    ]);

    const csvContent = [headers, ...rows].map((row) => row.join(",")).join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute(
      "download",
      `detection_history_${new Date().toISOString().split("T")[0]}.csv`
    );
    link.click();
    URL.revokeObjectURL(url);
  };

  const formatTime = (date: Date | string) => {
    return new Date(date).toLocaleString("vi-VN");
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="bg-black/30 backdrop-blur-sm border-b border-white/10 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-400 hover:text-white transition-colors">
                ← Quay lại
              </Link>
              <h1 className="text-xl font-bold">Lịch sử phát hiện</h1>
            </div>
            <button
              onClick={exportToCSV}
              className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-600 transition-colors font-medium"
            >
              📥 Export CSV
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Filter Tabs */}
        <div className="flex gap-2 mb-8">
          {(["all", "stranger", "known"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-lg transition-colors ${
                filter === f
                  ? "bg-cyan-500 text-white"
                  : "bg-white/10 text-gray-300 hover:bg-white/20"
              }`}
            >
              {f === "all" ? "Tất cả" : f === "stranger" ? "Người lạ" : "Người quen"}
            </button>
          ))}
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="text-center py-20">
            <div className="inline-block w-10 h-10 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="text-center py-20 text-red-400">
            <p>Lỗi tải dữ liệu</p>
          </div>
        )}

        {/* Table */}
        {filteredEvents && filteredEvents.length > 0 && (
          <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
            <table className="w-full">
              <thead className="bg-white/5">
                <tr>
                  <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">
                    Ảnh
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">
                    Thời gian
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">
                    Loại
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">
                    Người
                  </th>
                  <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">
                    Độ tin cậy
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredEvents.map((event) => (
                  <tr key={event._id} className="hover:bg-white/5 transition-colors">
                    <td className="px-6 py-4">
                      <img
                        src={event.image_url}
                        alt="Detection"
                        className="w-16 h-12 object-cover rounded-lg"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = "/placeholder.svg";
                        }}
                      />
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {formatTime(event.timestamp)}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${
                          event.detection.type === "stranger"
                            ? "bg-red-500/20 text-red-400"
                            : event.detection.type === "known"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-gray-500/20 text-gray-400"
                        }`}
                      >
                        {event.detection.type === "stranger"
                          ? "Người lạ"
                          : event.detection.type === "known"
                          ? "Người quen"
                          : "Không có mặt"}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {event.detection.external_id || "—"}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {event.detection.confidence > 0
                        ? `${event.detection.confidence.toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty */}
        {filteredEvents?.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p>Không có dữ liệu</p>
          </div>
        )}
      </div>
    </main>
  );
}
