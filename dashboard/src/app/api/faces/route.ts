import { NextResponse } from "next/server";
import { connectToDatabase, KnownPerson } from "@/lib/mongodb";

export async function GET() {
  try {
    const { db } = await connectToDatabase();
    const collection = db.collection<KnownPerson>("known_persons");

    const persons = await collection
      .find({})
      .sort({ registered_at: -1 })
      .toArray();

    const serializedPersons = persons.map((person) => ({
      ...person,
      _id: person._id.toString(),
    }));

    return NextResponse.json({ persons: serializedPersons });
  } catch (error) {
    console.error("Database error:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
