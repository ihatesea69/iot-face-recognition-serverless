import { NextResponse } from "next/server";

const lambdaUrl = process.env.NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL;

export async function POST(request: Request) {
  if (!lambdaUrl) {
    return NextResponse.json({ error: "ManageFaces URL is not configured" }, { status: 500 });
  }

  try {
    const payload = await request.text();
    const response = await fetch(lambdaUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: payload,
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
    console.error("Registration proxy error:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
