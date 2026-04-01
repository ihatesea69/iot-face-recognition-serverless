import { NextResponse } from "next/server";

const lambdaUrl = process.env.NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL;

export async function GET(request: Request) {
  if (!lambdaUrl) {
    return NextResponse.json({ error: "ManageFaces URL is not configured" }, { status: 500 });
  }

  try {
    const { searchParams } = new URL(request.url);
    const proxyUrl = new URL(lambdaUrl);
    proxyUrl.searchParams.set("action", "upload_url");

    for (const [key, value] of searchParams.entries()) {
      proxyUrl.searchParams.set(key, value);
    }

    const response = await fetch(proxyUrl.toString(), {
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
    console.error("Upload URL proxy error:", error);
    return NextResponse.json({ error: "Failed to generate URL" }, { status: 500 });
  }
}
