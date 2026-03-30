"use client";

import useSWR from "swr";
import DetectionCard from "@/components/DetectionCard";
import { DetectionEvent, DeviceStatus } from "@/lib/mongodb";
import { useEffect, useRef } from "react";

const fetcher = (url: string) => fetch(url).then((res) => res.json());
const formatTime = (value?: Date | string | null) =>
  value
    ? new Date(value).toLocaleString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";

export default function Home() {
  const { data, error, isLoading } = useSWR<{ events: DetectionEvent[] }>(
    "/api/detections",
    fetcher,
    { refreshInterval: 3000 } // Poll every 3 seconds for real-time updates
  );
  const { data: devicesData } = useSWR<{ devices: DeviceStatus[] }>(
    "/api/devices",
    fetcher,
    { refreshInterval: 5000 }
  );

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastEventRef = useRef<string | null>(null);

  // Play alert sound when new stranger detected
  useEffect(() => {
    if (data?.events && data.events.length > 0) {
      const latestEvent = data.events[0];
      const latestId = latestEvent._id;

      if (
        lastEventRef.current &&
        lastEventRef.current !== latestId &&
        latestEvent.detection.type === "stranger"
      ) {
        // New stranger detected - play sound
        audioRef.current?.play();
      }

      lastEventRef.current = latestId;
    }
  }, [data]);

  const strangerCount =
    data?.events?.filter((e) => e.detection.type === "stranger").length ?? 0;
  const knownCount =
    data?.events?.filter((e) => e.detection.type === "known").length ?? 0;
  const onlineDeviceCount =
    devicesData?.devices?.filter((device) => device.is_online).length ?? 0;
  const devices = devicesData?.devices ?? [];

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Alert Sound */}
      <audio ref={audioRef} preload="auto">
        <source
          src="data:audio/wav;base64,UklGRl9vT19teleXample"
          type="audio/wav"
        />
      </audio>

      {/* Header */}
      <header className="bg-black/30 backdrop-blur-sm border-b border-white/10 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 flex items-center justify-center">
                <span className="text-xl">🏠</span>
              </div>
              <div>
                <h1 className="text-xl font-bold">Home Security</h1>
                <p className="text-sm text-gray-400">
                  Hệ thống nhận diện khuôn mặt
                </p>
              </div>
            </div>

            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
                <span className="text-sm text-gray-300">Đang hoạt động</span>
              </div>
              <a
                href="/simulate"
                className="px-4 py-2 rounded-lg bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition-colors border border-purple-500/50"
              >
                🎮 Simulator
              </a>
              <a
                href="/faces"
                className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
              >
                Quản lý khuôn mặt
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10">
            <div className="text-4xl font-bold text-cyan-400">
              {data?.events?.length ?? 0}
            </div>
            <div className="text-gray-400 mt-1">Tổng phát hiện</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10">
            <div className="text-4xl font-bold text-green-400">{knownCount}</div>
            <div className="text-gray-400 mt-1">Người quen</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10">
            <div className="text-4xl font-bold text-red-400">
              {strangerCount}
            </div>
            <div className="text-gray-400 mt-1">Người lạ</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10">
            <div className="text-4xl font-bold text-amber-400">
              {onlineDeviceCount}
            </div>
            <div className="text-gray-400 mt-1">Thiết bị online</div>
          </div>
        </div>

        <section className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold">Thiết bị giám sát</h2>
            <span className="text-sm text-gray-400">
              Trạng thái cập nhật từ heartbeat Pi
            </span>
          </div>

          {devices.length === 0 ? (
            <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-dashed border-white/10 text-gray-400">
              Chưa có Pi nào gửi heartbeat.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {devices.map((device) => (
                <div
                  key={device._id}
                  className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-lg font-semibold">{device.device_id}</div>
                      <div className="text-sm text-gray-400 font-mono">
                        {device.camera_device || "/dev/video0"}
                      </div>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        device.is_online
                          ? "bg-green-500/20 text-green-300"
                          : "bg-red-500/20 text-red-300"
                      }`}
                    >
                      {device.is_online ? "ONLINE" : "OFFLINE"}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm">
                    <div>
                      <div className="text-gray-400">Last seen</div>
                      <div>{formatTime(device.last_seen)}</div>
                    </div>
                    <div>
                      <div className="text-gray-400">Last upload</div>
                      <div>{formatTime(device.last_upload_ok_at)}</div>
                    </div>
                    <div>
                      <div className="text-gray-400">Interval</div>
                      <div>{device.capture_interval_sec ?? 5}s</div>
                    </div>
                    <div>
                      <div className="text-gray-400">Status</div>
                      <div className="capitalize">{device.status}</div>
                    </div>
                  </div>

                  {device.last_error && (
                    <div className="mt-4 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-200">
                      {device.last_error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Detection Feed */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold">Phát hiện gần đây</h2>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <div className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></div>
            Cập nhật mỗi 3 giây
          </div>
        </div>

        {isLoading && (
          <div className="text-center py-20">
            <div className="inline-block w-10 h-10 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="mt-4 text-gray-400">Đang tải...</p>
          </div>
        )}

        {error && (
          <div className="text-center py-20 text-red-400">
            <p>Lỗi kết nối database</p>
            <p className="text-sm mt-2">{String(error)}</p>
          </div>
        )}

        {data?.events?.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-6xl mb-4">📷</p>
            <p>Chưa có phát hiện nào</p>
            <p className="text-sm mt-2">
              Bật simulator hoặc Pi client để bắt đầu capture
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data?.events?.map((event) => (
            <DetectionCard key={event._id} event={event} />
          ))}
        </div>
      </div>
    </main>
  );
}
