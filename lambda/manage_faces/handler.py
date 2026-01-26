"""
Lambda: Manage Faces
API Gateway handler for managing known faces in Rekognition collection.

Endpoints:
- POST /faces - Index a new face
- GET /faces - List all faces
- DELETE /faces/{faceId} - Remove a face
"""

import json
import os
from datetime import datetime

import boto3
import uuid
from pymongo import MongoClient

REKOGNITION_COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "home-security-faces")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "iot-face-recognition-bucket")
MONGODB_URI = os.environ.get("MONGODB_URI")

rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")


def get_mongo_collection():
    """Get MongoDB collection for known persons."""
    client = MongoClient(MONGODB_URI)
    db = client["home_security"]
    return db["known_persons"]


def ensure_collection_exists():
    """Create Rekognition collection if it doesn't exist."""
    try:
        rekognition.create_collection(CollectionId=REKOGNITION_COLLECTION_ID)
        print(f"Created collection: {REKOGNITION_COLLECTION_ID}")
    except rekognition.exceptions.ResourceAlreadyExistsException:
        pass


def index_face(s3_key: str, person_name: str) -> dict:
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

    # Store in MongoDB
    collection = get_mongo_collection()
    person_doc = {
        "name": person_name,
        "face_id": face_id,
        "s3_key": s3_key,
        "registered_at": datetime.utcnow(),
    }
    collection.insert_one(person_doc)

    return {"face_id": face_id, "name": person_name}


def list_faces() -> list:
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


def delete_face(face_id: str) -> dict:
    """Delete a face from collection."""
    try:
        rekognition.delete_faces(CollectionId=REKOGNITION_COLLECTION_ID, FaceIds=[face_id])

        # Remove from MongoDB
        collection = get_mongo_collection()
        collection.delete_one({"face_id": face_id})

        return {"deleted": face_id}
    except Exception as e:
        return {"error": str(e)}


def generate_presigned_url(file_type: str, prefix: str = "faces") -> dict:
    """Generate S3 presigned URL for upload."""
    object_name = f"{prefix}/{uuid.uuid4().hex}.{file_type.split('/')[-1]}"
    
    try:
        response = s3.generate_presigned_post(
            Bucket=S3_BUCKET_NAME,
            Key=object_name,
            Fields={"Content-Type": file_type},
            Conditions=[
                {"bucket": S3_BUCKET_NAME},
                ["starts-with", "$key", prefix],
            ],
            ExpiresIn=3600
        )
        return {"url": response["url"], "fields": response["fields"], "key": object_name}
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None

def handler(event, context):
    """Lambda handler for API Gateway."""
    print(f"Event: {json.dumps(event)}")

    http_method = event.get("httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "GET"))
    path = event.get("path", event.get("rawPath", "/faces"))
    
    # Handle query parameters
    query_params = event.get("queryStringParameters", {}) or {}

    # CORS headers
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
            body = json.loads(event.get("body", "{}"))
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

        elif http_method == "GET":
            action = query_params.get("action")
            
            if action == "upload_url":
                file_type = query_params.get("file_type", "image/jpeg")
                use_case = query_params.get("use_case", "register") # register or simulate
                prefix = "captures/web-simulator" if use_case == "simulate" else "faces"
                
                result = generate_presigned_url(file_type, prefix)
                if result:
                     return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}
                else:
                     return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": "Failed to generate URL"})}

            faces = list_faces()
            return {"statusCode": 200, "headers": headers, "body": json.dumps({"faces": faces})}

        elif http_method == "DELETE":
            # Extract face_id from path
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

        else:
            return {
                "statusCode": 405,
                "headers": headers,
                "body": json.dumps({"error": "Method not allowed"}),
            }

    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": str(e)})}
