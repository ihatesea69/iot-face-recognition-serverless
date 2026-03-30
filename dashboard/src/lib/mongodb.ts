import { MongoClient, Db } from "mongodb";

let cachedClient: MongoClient | null = null;
let cachedDb: Db | null = null;

export async function connectToDatabase(): Promise<{ client: MongoClient; db: Db }> {
  const MONGODB_URI = process.env.MONGODB_URI;

  if (!MONGODB_URI) {
    throw new Error("Please define MONGODB_URI environment variable");
  }

  if (cachedClient && cachedDb) {
    return { client: cachedClient, db: cachedDb };
  }

  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db("home_security");

  cachedClient = client;
  cachedDb = db;

  return { client, db };
}

export interface DetectionEvent {
  _id: string;
  timestamp: Date;
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
  processed_at: Date;
}

export interface KnownPerson {
  _id: string;
  name: string;
  face_id: string;
  s3_key: string;
  registered_at: Date;
}

export interface DeviceStatus {
  _id: string;
  device_id: string;
  status: "online" | "degraded";
  capture_interval_sec?: number;
  camera_device?: string;
  last_capture_at?: Date | null;
  last_upload_ok_at?: Date | null;
  last_error?: string | null;
  last_seen: Date;
  updated_at?: Date;
  is_online?: boolean;
}
