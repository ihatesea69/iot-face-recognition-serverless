"use client";

import { useRef, useState, useEffect } from "react";
import { getPresignedUrl, uploadToS3 } from "@/lib/api";
import DetectionCard from "@/components/DetectionCard";
import useSWR from "swr";
import { DetectionEvent } from "@/lib/mongodb";
import Link from "next/link";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function SimulatorPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState("Sẵn sàng");

  // Real-time updates for simulation result
  const { data } = useSWR<{ events: DetectionEvent[] }>(
    "/api/detections",
    fetcher,
    { refreshInterval: 1000 }
  );
  
  const latestEvent = data?.events?.[0];

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, []);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setIsStreaming(true);
      }
    } catch (err) {
      console.error("Camera error:", err);
      setStatus("Không thể truy cập Camera");
    }
  };

  const stopCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
      setIsStreaming(false);
    }
  };

  const captureAndSimulate = async () => {
    if (!videoRef.current || !canvasRef.current || isProcessing) return;
    
    setIsProcessing(true);
    setStatus("Đang chụp...");

    try {
      // 1. Capture Frame
      const context = canvasRef.current.getContext("2d");
      if (!context) return;
      
      canvasRef.current.width = videoRef.current.videoWidth;
      canvasRef.current.height = videoRef.current.videoHeight;
      context.drawImage(videoRef.current, 0, 0);
      
      // Convert to Blob
      const blob = await new Promise<Blob | null>((resolve) => 
        canvasRef.current?.toBlob(resolve, "image/jpeg", 0.9)
      );
      
      if (!blob) throw new Error("Capture failed");

      // 2. Get Upload URL
      setStatus("Đang tải lên Cloud...");
      const presigned = await getPresignedUrl("image/jpeg", "simulate");
      
      // 3. Upload
      await uploadToS3(presigned, blob);
      setStatus("Đã gửi! Đang chờ kết quả...");
      
      // Reset status after delay
      setTimeout(() => setStatus("Sẵn sàng"), 3000);

    } catch (err) {
      console.error(err);
      setStatus("Lỗi xử lý");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-900 text-white p-6">
      <header className="max-w-4xl mx-auto mb-8 flex justify-between items-center">
        <div>
           <h1 className="text-2xl font-bold">Web Simulator</h1>
           <p className="text-gray-400">Giả lập IoT Device ngay trên trình duyệt</p>
        </div>
        <Link href="/" className="px-4 py-2 bg-white/10 rounded-lg hover:bg-white/20">
          Quay lại Dashboard
        </Link>
      </header>
      
      <div className="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Camera Feed */}
        <div className="bg-black rounded-xl overflow-hidden relative shadow-2xl border border-white/10">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
          />
          <canvas ref={canvasRef} className="hidden" />
          
          <div className="absolute bottom-4 left-0 right-0 flex justify-center">
            <button
              onClick={captureAndSimulate}
              disabled={isProcessing || !isStreaming}
              className={`w-16 h-16 rounded-full border-4 border-white flex items-center justify-center transition-all ${
                isProcessing ? "bg-gray-500 scale-90" : "bg-red-500 hover:scale-110"
              }`}
            >
              <div className="w-14 h-14 rounded-full border-2 border-black/20" />
            </button>
          </div>
          
          <div className="absolute top-4 left-4 bg-black/50 px-3 py-1 rounded-full text-sm font-mono">
            {status}
          </div>
        </div>
        
        {/* Result Feed */}
        <div>
           <h2 className="text-xl font-bold mb-4">Kết Quả Gần Nhất</h2>
           {latestEvent ? (
              <DetectionCard event={latestEvent} />
           ) : (
              <div className="h-64 bg-white/5 rounded-xl flex items-center justify-center text-gray-500 border border-white/10">
                Chưa có dữ liệu
              </div>
           )}
           
           <div className="mt-8 bg-cyan-900/20 p-4 rounded-xl border border-cyan-500/30">
              <h3 className="font-bold text-cyan-400 mb-2">Cách hoạt động</h3>
              <ul className="list-disc list-inside text-sm text-cyan-200 space-y-1">
                 <li>Nhấn nút chụp để gửi ảnh hiện tại.</li>
                 <li>Browser sẽ upload trực tiếp lên S3 (giống IoT Device).</li>
                 <li>AWS Lambda sẽ xử lý và trả về kết quả Realtime.</li>
              </ul>
           </div>
        </div>
      </div>
    </main>
  );
}
