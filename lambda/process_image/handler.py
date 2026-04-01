"""
Lambda: Process Image
Triggered by S3 PutObject event when the system uploads an image.
Stores detection results in DynamoDB.
"""

import json
import os
from datetime import datetime
from decimal import Decimal
import uuid

import boto3

# Environment variables
REKOGNITION_COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "home-security-faces")
DYNAMODB_DETECTIONS_TABLE = os.environ.get(
    "DYNAMODB_DETECTIONS_TABLE", "home-security-detections-prod"
)
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "80"))

# Initialize clients
rekognition = boto3.client("rekognition")
dynamodb = boto3.resource("dynamodb")


def get_detections_table():
    return dynamodb.Table(DYNAMODB_DETECTIONS_TABLE)


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
        return {"FaceMatches": [], "Error": "NoFaceDetected"}
    except rekognition.exceptions.ResourceNotFoundException:
        return {"FaceMatches": [], "Error": "CollectionNotFound"}
    except Exception as e:
        return {"FaceMatches": [], "Error": str(e)}


def extract_device_id(s3_key: str) -> str:
    """Extract the logical device ID from captures/<device_id>/... keys."""
    parts = s3_key.split("/")
    if len(parts) >= 3 and parts[0] == "captures" and parts[1]:
        return parts[1]
    return "unknown"


def build_detection_result(result: dict) -> dict:
    face_matches = result.get("FaceMatches", [])
    if face_matches:
        match = face_matches[0]
        return {
            "type": "known",
            "person_id": match["Face"]["FaceId"],
            "external_id": match["Face"].get("ExternalImageId", "Unknown"),
            "confidence": float(match["Similarity"]),
        }

    error = result.get("Error")
    if error == "NoFaceDetected":
        return {"type": "no_face", "confidence": 0.0}
    return {"type": "stranger", "confidence": 0.0}


def store_detection_event(bucket: str, key: str, image_url: str, detection_result: dict):
    timestamp = datetime.utcnow().isoformat() + "Z"
    event_id = uuid.uuid4().hex
    item = {
        "pk": "FEED",
        "sk": f"{timestamp}#{event_id}",
        "event_id": event_id,
        "timestamp": timestamp,
        "processed_at": timestamp,
        "image_url": image_url,
        "s3_bucket": bucket,
        "s3_key": key,
        "device_id": extract_device_id(key),
        "detection_type": detection_result["type"],
        "person_id": detection_result.get("person_id"),
        "external_id": detection_result.get("external_id"),
        "confidence": Decimal(str(detection_result.get("confidence", 0.0))),
    }
    get_detections_table().put_item(Item=item)
    return event_id


def handler(event, context):
    """Lambda handler for S3 trigger."""
    print(f"Event: {json.dumps(event)}")

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    image_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    print(f"Processing image: {image_url}")

    result = search_face(bucket, key)
    detection_result = build_detection_result(result)

    event_id = None
    try:
        event_id = store_detection_event(bucket, key, image_url, detection_result)
        print(f"Stored detection event: {event_id}")
    except Exception as e:
        print(f"DynamoDB error: {e}")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Image processed",
                "event_id": event_id,
                "detection": detection_result,
                "image_url": image_url,
            },
            default=str,
        ),
    }
