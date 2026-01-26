import { RekognitionClient, IndexFacesCommand } from "@aws-sdk/client-rekognition";
import { connectToDatabase } from "@/lib/mongodb";
import { NextResponse } from "next/server";

// Initialize Rekognition Client
// Configure Rekognition Client
const clientConfig: any = {
  region: process.env.AWS_REGION || "us-east-1",
};

if (process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY) {
  clientConfig.credentials = {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  };
}

const rekognition = new RekognitionClient(clientConfig);

const COLLECTION_ID = process.env.REKOGNITION_COLLECTION_ID || "home-security-faces";
const BUCKET_NAME = process.env.S3_BUCKET_NAME || "nghi-face-recognition-bucket";

export async function POST(request: Request) {
  try {
    const { name, s3_key } = await request.json();

    if (!name || !s3_key) {
      return NextResponse.json({ error: "Missing name or s3_key" }, { status: 400 });
    }

    console.log(`Indexing face for ${name} from ${s3_key}`);

    // 1. Index Face in Rekognition
    const command = new IndexFacesCommand({
      CollectionId: COLLECTION_ID,
      Image: {
        S3Object: {
          Bucket: BUCKET_NAME,
          Name: s3_key,
        },
      },
      ExternalImageId: name.replace(/\s+/g, "_"), // Simple sanitation
      DetectionAttributes: ["ALL"],
      MaxFaces: 1,
      QualityFilter: "AUTO",
    });

    const response = await rekognition.send(command);

    if (!response.FaceRecords || response.FaceRecords.length === 0) {
      return NextResponse.json({ error: "No face detected in the image" }, { status: 400 });
    }

    const faceRecord = response.FaceRecords[0];
    const faceId = faceRecord.Face?.FaceId;

    if (!faceId) {
       return NextResponse.json({ error: "Failed to get FaceId" }, { status: 500 });
    }

    // 2. Save to MongoDB
    const { db } = await connectToDatabase();
    const collection = db.collection("known_persons");

    await collection.updateOne(
      { face_id: faceId },
      {
        $set: {
          name: name,
          face_id: faceId,
          image_url: `https://${BUCKET_NAME}.s3.amazonaws.com/${s3_key}`,
          registered_at: new Date(),
        },
      },
      { upsert: true }
    );

    return NextResponse.json({ 
        success: true, 
        message: `Registered ${name}`, 
        faceId 
    });

  } catch (error) {
    console.error("Registration error:", error);
    return NextResponse.json({ 
      error: error instanceof Error ? error.message : "Internal Server Error",
      details: String(error)
    }, { status: 500 });
  }
}
