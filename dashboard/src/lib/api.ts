export interface PresignedPostData {
  url: string;
  fields: Record<string, string>;
  key: string;
}

export async function getPresignedUrl(
  fileType: string,
  useCase: "register" | "simulate"
): Promise<PresignedPostData> {
  // Use internal API route instead of public Lambda URL to avoid CORS/Auth issues
  const res = await fetch(
    `/api/upload-url?file_type=${encodeURIComponent(
      fileType
    )}&use_case=${useCase}`
  );
  
  if (!res.ok) throw new Error("Failed to get upload URL");
  return res.json();
}

export async function uploadToS3(presignedData: PresignedPostData, file: File | Blob) {
  const formData = new FormData();
  Object.entries(presignedData.fields).forEach(([key, value]) => {
    formData.append(key, value);
  });
  formData.append("file", file);

  const res = await fetch(presignedData.url, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorText = await res.text();
    console.error("S3 Upload Error:", errorText);
    throw new Error(`Upload failed: ${res.status} ${res.statusText} - ${errorText}`);
  }
  return presignedData.key;
}
