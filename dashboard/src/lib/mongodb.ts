export interface DetectionEvent {
  _id: string;
  timestamp: Date | string;
  image_url: string;
  s3_bucket: string;
  s3_key: string;
  device_id?: string;
  detection: {
    type: "known" | "stranger" | "no_face";
    person_id?: string;
    external_id?: string;
    confidence: number;
  };
  processed_at: Date | string;
}

export interface KnownPerson {
  _id: string;
  name: string;
  face_id: string;
  s3_key: string;
  image_url?: string;
  registered_at: Date | string;
}

export interface DeviceStatus {
  _id: string;
  device_id: string;
  status: "online" | "degraded";
  capture_interval_sec?: number;
  camera_device?: string;
  last_capture_at?: Date | string | null;
  last_upload_ok_at?: Date | string | null;
  last_error?: string | null;
  last_seen: Date | string;
  updated_at?: Date | string;
  created_at?: Date | string;
  is_online?: boolean;
}
