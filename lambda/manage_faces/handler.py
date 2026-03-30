"""Lambda: Manage Faces and device upload/heartbeat APIs."""

import base64
from datetime import datetime, timezone
import json
import os
import re
import uuid

import boto3
from botocore.exceptions import ClientError
from pymongo import MongoClient


REKOGNITION_COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "home-security-faces")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "iot-face-recognition-bucket")
MONGODB_URI = os.environ.get("MONGODB_URI")

rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")
mongo_client = MongoClient(MONGODB_URI) if MONGODB_URI else None


def get_db():
    if not mongo_client:
        raise ValueError("MONGODB_URI is not configured")
    return mongo_client["home_security"]


def get_known_persons_collection():
    return get_db()["known_persons"]


def get_device_status_collection():
    collection = get_db()["device_status"]
    collection.create_index("device_id", unique=True)
    return collection


def parse_json_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def sanitize_device_id(device_id):
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (device_id or "").strip()).strip("-")
    return cleaned or "unknown"


def file_extension_from_type(file_type):
    ext = file_type.split("/")[-1].lower()
    return "jpg" if ext == "jpeg" else ext


def build_device_capture_key(device_id, file_type):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_device_id = sanitize_device_id(device_id)
    return f"captures/{safe_device_id}/{timestamp}.{file_extension_from_type(file_type)}"


def ensure_collection_exists():
    """Create Rekognition collection if it doesn't exist."""
    try:
        rekognition.create_collection(CollectionId=REKOGNITION_COLLECTION_ID)
        print(f"Created collection: {REKOGNITION_COLLECTION_ID}")
    except rekognition.exceptions.ResourceAlreadyExistsException:
        pass


def index_face(s3_key, person_name):
    """Index a face from S3 image."""
    ensure_collection_exists()

    response = rekognition.index_faces(
        CollectionId=REKOGNITION_COLLECTION_ID,
        Image={"S3Object": {"Bucket": S3_BUCKET_NAME, "Name": s3_key}},
        ExternalImageId=person_name,
        DetectionAttributes=["ALL"],
        MaxFaces=1,
    )

    if not response.get("FaceRecords"):
        return {"error": "No face detected in image"}

    face_record = response["FaceRecords"][0]
    face_id = face_record["Face"]["FaceId"]

    collection = get_known_persons_collection()
    person_doc = {
        "name": person_name,
        "face_id": face_id,
        "s3_key": s3_key,
        "registered_at": datetime.utcnow(),
    }
    collection.insert_one(person_doc)

    return {"face_id": face_id, "name": person_name}


def list_faces():
    """List all faces in collection."""
    try:
        response = rekognition.list_faces(CollectionId=REKOGNITION_COLLECTION_ID, MaxResults=100)
        faces = []
        for face in response.get("Faces", []):
            faces.append(
                {
                    "face_id": face["FaceId"],
                    "external_id": face.get("ExternalImageId", "Unknown"),
                }
            )
        return faces
    except rekognition.exceptions.ResourceNotFoundException:
        return []


def delete_face(face_id):
    """Delete a face from collection."""
    try:
        rekognition.delete_faces(CollectionId=REKOGNITION_COLLECTION_ID, FaceIds=[face_id])
        collection = get_known_persons_collection()
        collection.delete_one({"face_id": face_id})
        return {"deleted": face_id}
    except Exception as e:
        return {"error": str(e)}


def generate_presigned_url(file_type, prefix="faces", object_name=None):
    """Generate S3 presigned URL for upload."""
    if object_name:
        key = object_name
    else:
        key = f"{prefix}/{uuid.uuid4().hex}.{file_extension_from_type(file_type)}"

    conditions = [
        {"bucket": S3_BUCKET_NAME},
        {"Content-Type": file_type},
    ]

    if object_name:
        conditions.append({"key": key})
    else:
        conditions.append(["starts-with", "$key", prefix])

    try:
        response = s3.generate_presigned_post(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Fields={
                "Content-Type": file_type,
            },
            Conditions=conditions,
            ExpiresIn=600,
        )
        return {"url": response["url"], "fields": response["fields"], "key": key}
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None


def upsert_device_status(payload):
    device_id = sanitize_device_id(payload.get("device_id"))
    status = payload.get("status") or "degraded"
    now = datetime.utcnow()

    update_doc = {
        "$set": {
            "device_id": device_id,
            "status": status,
            "capture_interval_sec": payload.get("capture_interval_sec"),
            "camera_device": payload.get("camera_device"),
            "last_capture_at": parse_datetime(payload.get("last_capture_at")),
            "last_upload_ok_at": parse_datetime(payload.get("last_upload_ok_at")),
            "last_error": payload.get("last_error"),
            "last_seen": now,
            "updated_at": now,
        },
        "$setOnInsert": {
            "created_at": now,
        },
    }

    collection = get_device_status_collection()
    collection.update_one({"device_id": device_id}, update_doc, upsert=True)
    return {"ok": True, "device_id": device_id, "last_seen": now.isoformat()}


def handler(event, context):
    """Lambda handler for API Gateway / Lambda Function URL."""
    print(f"Event: {json.dumps(event)}")

    http_method = event.get("httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "GET"))
    path = event.get("path", event.get("rawPath", "/faces"))
    query_params = event.get("queryStringParameters", {}) or {}
    action = query_params.get("action")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Content-Type": "application/json",
    }

    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    try:
        if http_method == "POST":
            body = parse_json_body(event)

            if action == "heartbeat":
                if not body.get("device_id"):
                    return {
                        "statusCode": 400,
                        "headers": headers,
                        "body": json.dumps({"error": "device_id is required"}),
                    }

                result = upsert_device_status(body)
                return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

            s3_key = body.get("s3_key")
            person_name = body.get("name")

            if not s3_key or not person_name:
                return {
                    "statusCode": 400,
                    "headers": headers,
                    "body": json.dumps({"error": "s3_key and name are required"}),
                }

            result = index_face(s3_key, person_name)
            return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

        if http_method == "GET":
            if action == "upload_url":
                file_type = query_params.get("file_type", "image/jpeg")
                use_case = query_params.get("use_case", "register")

                if use_case == "device":
                    device_id = query_params.get("device_id")
                    if not device_id:
                        return {
                            "statusCode": 400,
                            "headers": headers,
                            "body": json.dumps({"error": "device_id is required for device uploads"}),
                        }

                    object_name = build_device_capture_key(device_id, file_type)
                    result = generate_presigned_url(file_type, prefix="captures", object_name=object_name)
                else:
                    prefix = "captures/web-simulator" if use_case == "simulate" else "faces"
                    result = generate_presigned_url(file_type, prefix=prefix)

                if result:
                    return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

                return {
                    "statusCode": 500,
                    "headers": headers,
                    "body": json.dumps({"error": "Failed to generate URL"}),
                }

            faces = list_faces()
            return {"statusCode": 200, "headers": headers, "body": json.dumps({"faces": faces})}

        if http_method == "DELETE":
            path_parts = path.split("/")
            face_id = path_parts[-1] if len(path_parts) > 2 else None

            if not face_id:
                return {
                    "statusCode": 400,
                    "headers": headers,
                    "body": json.dumps({"error": "face_id is required"}),
                }

            result = delete_face(face_id)
            return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

        return {
            "statusCode": 405,
            "headers": headers,
            "body": json.dumps({"error": "Method not allowed"}),
        }
    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": str(e)})}
