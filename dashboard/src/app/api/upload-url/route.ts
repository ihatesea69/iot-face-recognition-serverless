import { S3Client, type S3ClientConfig } from "@aws-sdk/client-s3";
import { createPresignedPost } from "@aws-sdk/s3-presigned-post";
import { NextResponse } from "next/server";
import { v4 as uuidv4 } from "uuid";

function getAwsRegion() {
  return process.env.APP_AWS_REGION || process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "ap-southeast-1";
}

// Create S3 client on demand to ensure env vars are read correctly
function getS3Client() {
  const region = getAwsRegion();
  console.log("Creating S3 client with region:", region);
  
  const clientConfig: S3ClientConfig = { region };

  if (process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY) {
    clientConfig.credentials = {
      accessKeyId: process.env.AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
    };
  }

  return new S3Client(clientConfig);
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const fileType = searchParams.get("file_type") || "image/jpeg";
  const useCase = searchParams.get("use_case") || "register";
  
  const prefix = useCase === "simulate" ? "captures/web-simulator" : "faces";
  const ext = fileType.split("/")[1] === "jpeg" ? "jpg" : fileType.split("/")[1];
  const key = `${prefix}/${uuidv4()}.${ext}`;
  const bucketName = process.env.S3_BUCKET_NAME || "nghi-iot-face-bucket-2026";
  
  console.log("Using bucket:", bucketName, "region:", getAwsRegion());

  try {
    const s3Client = getS3Client();
    const { url, fields } = await createPresignedPost(s3Client, {
      Bucket: bucketName,
      Key: key,
      Conditions: [
        ["starts-with", "$key", prefix],
        { "Content-Type": fileType }, // Fixed: Use object for exact match
      ],
      Fields: {
        "Content-Type": fileType,
      },
      Expires: 600, // 10 minutes
    });

    return NextResponse.json({ url, fields, key });
  } catch (error) {
    console.error("Error generating presigned URL:", error);
    return NextResponse.json({ error: "Failed to generate URL" }, { status: 500 });
  }
}
