"use client";

import useSWR from "swr";
import { KnownPerson } from "@/lib/mongodb";
import { useState } from "react";
import { getPresignedUrl, uploadToS3 } from "@/lib/api";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function FacesPage() {
  const { data, error, isLoading, mutate } = useSWR<{ persons: KnownPerson[] }>(
    "/api/faces",
    fetcher
  );

  const [showAddForm, setShowAddForm] = useState(false);
  const [newPersonName, setNewPersonName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAddFace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !newPersonName) return;
    
    setIsSubmitting(true);

    try {
      // 1. Get Presigned URL
      const presigned = await getPresignedUrl(selectedFile.type, "register");
      
      // 2. Upload to S3
      await uploadToS3(presigned, selectedFile);
      
      // 3. Register Face
      const res = await fetch("/api/register-face", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newPersonName,
          s3_key: presigned.key
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Failed to register face");
      }
      mutate();
      setNewPersonName("");
      setSelectedFile(null);
      setShowAddForm(false);
    } catch (err: any) {
      console.error("Failed to add face:", err);
      alert(`Lỗi: ${err.message || "Vui lòng thử lại"}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteFace = async (faceId: string) => {
    if (!confirm("Bạn có chắc muốn xóa khuôn mặt này?")) return;

    try {
      const lambdaUrl = process.env.NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL;
      if (lambdaUrl) {
        await fetch(`${lambdaUrl}/faces/${faceId}`, { method: "DELETE" });
      }
      mutate();
    } catch (err) {
      console.error("Failed to delete face:", err);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="bg-black/30 backdrop-blur-sm border-b border-white/10 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <a href="/" className="text-gray-400 hover:text-white transition-colors">
                ← Quay lại
              </a>
              <h1 className="text-xl font-bold">Quản lý người quen</h1>
            </div>
            <button
              onClick={() => setShowAddForm(true)}
              className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-600 transition-colors font-medium"
            >
              + Thêm người mới
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Add Form Modal */}
        {showAddForm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md border border-white/10">
              <h2 className="text-xl font-bold mb-4">Thêm người quen mới</h2>
              <form onSubmit={handleAddFace}>
                <div className="mb-4">
                  <label className="block text-sm text-gray-400 mb-2">
                    Tên người
                  </label>
                  <input
                    type="text"
                    value={newPersonName}
                    onChange={(e) => setNewPersonName(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 focus:border-cyan-500 focus:outline-none"
                    required
                  />
                </div>
                <div className="mb-6">
                  <label className="block text-sm text-gray-400 mb-2">
                    Ảnh khuôn mặt
                  </label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                    className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 focus:border-cyan-500 focus:outline-none"
                    required
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    className="flex-1 px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                  >
                    Hủy
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex-1 px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-600 transition-colors disabled:opacity-50"
                  >
                    {isSubmitting ? "Đang xử lý..." : "Thêm"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Info */}
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-4 mb-8">
          <p className="text-cyan-300">
            💡 Để thêm người quen, upload ảnh khuôn mặt lên S3 rồi nhập S3 key vào form.
            Hệ thống sẽ index khuôn mặt vào Rekognition Collection.
          </p>
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

        {/* Empty */}
        {data?.persons?.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-6xl mb-4">👤</p>
            <p>Chưa có người quen nào được đăng ký</p>
          </div>
        )}

        {/* Persons Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data?.persons?.map((person) => (
            <div
              key={person._id}
              className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10 hover:border-white/20 transition-colors"
            >
              <div className="flex items-center gap-4 mb-4">
                <div className="w-14 h-14 rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 flex items-center justify-center text-2xl">
                  👤
                </div>
                <div>
                  <h3 className="text-lg font-bold">{person.name}</h3>
                  <p className="text-sm text-gray-400">
                    {new Date(person.registered_at).toLocaleDateString("vi-VN")}
                  </p>
                </div>
              </div>
              <div className="text-xs text-gray-500 mb-4 font-mono truncate">
                {person.face_id}
              </div>
              <button
                onClick={() => handleDeleteFace(person.face_id)}
                className="w-full px-4 py-2 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors text-sm"
              >
                Xóa
              </button>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
