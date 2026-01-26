import { NextResponse } from "next/server";
import { connectToDatabase, DetectionEvent } from "@/lib/mongodb";

export async function GET() {
  try {
    const { db } = await connectToDatabase();
    const collection = db.collection<DetectionEvent>("detection_events");

    const events = await collection
      .find({})
      .sort({ timestamp: -1 })
      .limit(50)
      .toArray();

    // Convert ObjectId to string for JSON serialization
    const serializedEvents = events.map((event) => ({
      ...event,
      _id: event._id.toString(),
      timestamp: event.timestamp,
      processed_at: event.processed_at,
    }));

    return NextResponse.json({ events: serializedEvents });
  } catch (error) {
    console.error("Database error:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
