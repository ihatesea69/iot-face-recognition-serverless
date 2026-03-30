"""
Lambda: Process Image
Triggered by S3 PutObject event when IoT simulator uploads an image.

Flow:
1. Get image from S3
2. Call Rekognition search_faces_by_image
3. Determine stranger/known person
4. Store result in MongoDB Atlas
"""

import json
import os
from datetime import datetime

import boto3
from pymongo import MongoClient

# Environment variables
REKOGNITION_COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "home-security-faces")
MONGODB_URI = os.environ.get("MONGODB_URI")
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "80"))

# Initialize clients
rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")


def get_mongo_collection():
    """Get MongoDB collection for detection events."""
    client = MongoClient(MONGODB_URI)
    db = client["home_security"]
    return db["detection_events"]


def search_face(bucket: str, key: str) -> dict:
    """Search for face in Rekognition collection."""
    try:
        response = rekognition.search_faces_by_image(
            CollectionId=REKOGNITION_COLLECTION_ID,
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            MaxFaces=1,
            FaceMatchThreshold=CONFIDENCE_THRESHOLD,
        )
        return response
    except rekognition.exceptions.InvalidParameterException:
        # No face detected in image
        return {"FaceMatches": [], "Error": "NoFaceDetected"}
    except rekognition.exceptions.ResourceNotFoundException:
        # Collection doesn't exist yet
        return {"FaceMatches": [], "Error": "CollectionNotFound"}
    except Exception as e:
        return {"FaceMatches": [], "Error": str(e)}


def extract_device_id(s3_key: str) -> str:
    """Extract the logical device ID from captures/<device_id>/... keys."""
    parts = s3_key.split("/")
    if len(parts) >= 3 and parts[0] == "captures" and parts[1]:
        return parts[1]
    return "unknown"


def handler(event, context):
    """Lambda handler for S3 trigger."""
    print(f"Event: {json.dumps(event)}")

    # Parse S3 event
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    # Build public image URL
    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    image_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    print(f"Processing image: {image_url}")

    # Search face in collection
    result = search_face(bucket, key)

    # Determine detection result
    face_matches = result.get("FaceMatches", [])

    if face_matches:
        # Known person found
        match = face_matches[0]
        detection_result = {
            "type": "known",
            "person_id": match["Face"]["FaceId"],
            "external_id": match["Face"].get("ExternalImageId", "Unknown"),
            "confidence": match["Similarity"],
        }
    else:
        # Stranger or no face
        error = result.get("Error")
        if error == "NoFaceDetected":
            detection_result = {"type": "no_face", "confidence": 0}
        else:
            detection_result = {"type": "stranger", "confidence": 0}

    # Build detection event document
    detection_event = {
        "timestamp": datetime.utcnow(),
        "image_url": image_url,
        "s3_bucket": bucket,
        "s3_key": key,
        "device_id": extract_device_id(key),
        "detection": detection_result,
        "processed_at": datetime.utcnow(),
    }

    # Store in MongoDB
    try:
        collection = get_mongo_collection()
        insert_result = collection.insert_one(detection_event)
        detection_event["_id"] = str(insert_result.inserted_id)
        print(f"Stored detection event: {detection_event['_id']}")
    except Exception as e:
        print(f"MongoDB error: {e}")
        detection_event["_id"] = None

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Image processed",
                "detection": detection_result,
                "image_url": image_url,
            },
            default=str,
        ),
    }
