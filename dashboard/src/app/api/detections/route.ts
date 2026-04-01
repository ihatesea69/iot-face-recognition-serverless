import { NextResponse } from "next/server";

const lambdaUrl = process.env.NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL;

export async function GET() {
  if (!lambdaUrl) {
    return NextResponse.json({ error: "ManageFaces URL is not configured" }, { status: 500 });
  }

  try {
    const response = await fetch(`${lambdaUrl}?action=detections`, {
      cache: "no-store",
    });
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
      },
    });
  } catch (error) {
    console.error("Detections proxy error:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
