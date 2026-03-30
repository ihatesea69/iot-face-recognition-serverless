import { NextResponse } from "next/server";
import { connectToDatabase, DeviceStatus } from "@/lib/mongodb";

const OFFLINE_THRESHOLD_MS = 90 * 1000;

export async function GET() {
  try {
    const { db } = await connectToDatabase();
    const collection = db.collection<DeviceStatus>("device_status");

    const devices = await collection.find({}).sort({ last_seen: -1 }).toArray();
    const now = Date.now();

    const serializedDevices = devices.map((device) => {
      const lastSeen = device.last_seen ? new Date(device.last_seen) : null;
      const isOnline = lastSeen ? now - lastSeen.getTime() <= OFFLINE_THRESHOLD_MS : false;

      return {
        ...device,
        _id: device._id.toString(),
        last_seen: device.last_seen,
        last_capture_at: device.last_capture_at ?? null,
        last_upload_ok_at: device.last_upload_ok_at ?? null,
        updated_at: device.updated_at ?? null,
        is_online: isOnline,
      };
    });

    return NextResponse.json({ devices: serializedDevices });
  } catch (error) {
    console.error("Device status error:", error);
    return NextResponse.json({ error: "Device status error" }, { status: 500 });
  }
}
