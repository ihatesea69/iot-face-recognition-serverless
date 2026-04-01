"""Lambda: Manage Faces and device upload/heartbeat APIs backed by DynamoDB."""

import base64
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import re
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from telegram_notify import send_telegram_message


REKOGNITION_COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "home-security-faces")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "iot-face-recognition-bucket")
DYNAMODB_KNOWN_PERSONS_TABLE = os.environ.get(
    "DYNAMODB_KNOWN_PERSONS_TABLE", "home-security-known-persons-prod"
)
DYNAMODB_DEVICE_STATUS_TABLE = os.environ.get(
    "DYNAMODB_DEVICE_STATUS_TABLE", "home-security-device-status-prod"
)
DYNAMODB_DETECTIONS_TABLE = os.environ.get(
    "DYNAMODB_DETECTIONS_TABLE", "home-security-detections-prod"
)
DEVICE_OFFLINE_THRESHOLD_SEC = int(os.environ.get("DEVICE_OFFLINE_THRESHOLD_SEC", "90"))

rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


def get_known_persons_table():
    return dynamodb.Table(DYNAMODB_KNOWN_PERSONS_TABLE)


def get_device_status_table():
    return dynamodb.Table(DYNAMODB_DEVICE_STATUS_TABLE)


def get_detections_table():
    return dynamodb.Table(DYNAMODB_DETECTIONS_TABLE)


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


def iso_or_none(value):
    parsed = parse_datetime(value)
    return parsed.isoformat() + "Z" if parsed else None


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


def to_date(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed:
        return parsed
    return None


def normalize_number(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def iso_utc_now():
    return datetime.utcnow().isoformat() + "Z"


def build_alert_error_key(status, last_error):
    value = (last_error or status or "unknown").strip()
    return value[:500]


def build_device_alert_message(
    *,
    title,
    device_id,
    status,
    updated_at,
    last_seen=None,
    last_error=None,
):
    lines = [
        title,
        f"Thiet bi: {device_id}",
        f"Trang thai: {status}",
        f"Cap nhat luc (UTC): {updated_at}",
    ]
    if last_seen:
        lines.append(f"Last seen (UTC): {last_seen}")
    if last_error:
        lines.append(f"Loi gan nhat: {last_error}")
    return "\n".join(lines)


def evaluate_heartbeat_alert(existing, item, now_iso):
    alert_state = existing.get("alert_state") or "online"
    last_alert_at = existing.get("last_alert_at")
    last_alert_error_key = existing.get("last_alert_error_key")

    next_status = item["status"]
    next_error_key = build_alert_error_key(next_status, item.get("last_error"))
    notification_message = None

    if next_status == "online":
        next_alert_state = "online"
        next_alert_error_key = None
        next_last_alert_at = last_alert_at

        if alert_state in ("degraded", "offline"):
            next_last_alert_at = now_iso
            notification_message = build_device_alert_message(
                title="THIET BI PHUC HOI",
                device_id=item["device_id"],
                status="online",
                updated_at=now_iso,
                last_seen=item.get("last_seen"),
            )
    else:
        next_alert_state = "degraded"
        next_alert_error_key = next_error_key
        next_last_alert_at = last_alert_at

        if alert_state != "degraded" or last_alert_error_key != next_error_key:
            next_last_alert_at = now_iso
            notification_message = build_device_alert_message(
                title="CANH BAO THIET BI",
                device_id=item["device_id"],
                status="degraded",
                updated_at=now_iso,
                last_seen=item.get("last_seen"),
                last_error=item.get("last_error"),
            )

    return (
        {
            "alert_state": next_alert_state,
            "last_alert_at": next_last_alert_at,
            "last_alert_error_key": next_alert_error_key,
        },
        notification_message,
    )


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

    image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
    get_known_persons_table().put_item(
        Item={
            "face_id": face_id,
            "name": person_name,
            "s3_key": s3_key,
            "image_url": image_url,
            "registered_at": datetime.utcnow().isoformat() + "Z",
        }
    )

    return {"face_id": face_id, "name": person_name}


def list_faces():
    """List all known persons from DynamoDB."""
    response = get_known_persons_table().scan()
    persons = response.get("Items", [])
    persons.sort(key=lambda item: item.get("registered_at", ""), reverse=True)
    return {
        "persons": [
            {
                "_id": item["face_id"],
                "face_id": item["face_id"],
                "name": item.get("name", "Unknown"),
                "s3_key": item.get("s3_key", ""),
                "image_url": item.get("image_url"),
                "registered_at": item.get("registered_at"),
            }
            for item in persons
        ]
    }


def list_detections(limit=50):
    response = get_detections_table().query(
        KeyConditionExpression=Key("pk").eq("FEED"),
        ScanIndexForward=False,
        Limit=limit,
    )
    events = []
    for item in response.get("Items", []):
        events.append(
            {
                "_id": item["event_id"],
                "timestamp": item["timestamp"],
                "processed_at": item.get("processed_at", item["timestamp"]),
                "image_url": item["image_url"],
                "s3_bucket": item["s3_bucket"],
                "s3_key": item["s3_key"],
                "device_id": item.get("device_id", "unknown"),
                "detection": {
                    "type": item.get("detection_type", "stranger"),
                    "person_id": item.get("person_id"),
                    "external_id": item.get("external_id"),
                    "confidence": float(item.get("confidence", 0)),
                },
            }
        )
    return {"events": events}


def list_devices():
    now = datetime.utcnow()
    response = get_device_status_table().scan()
    devices = response.get("Items", [])
    devices.sort(key=lambda item: item.get("last_seen", ""), reverse=True)
    payload = []
    for item in devices:
        last_seen = to_date(item.get("last_seen"))
        is_online = bool(
            last_seen and (now - last_seen).total_seconds() <= DEVICE_OFFLINE_THRESHOLD_SEC
        )
        alert_state = item.get("alert_state")
        if not alert_state:
            alert_state = "offline" if not is_online else item.get("status", "degraded")
        payload.append(
            {
                "_id": item["device_id"],
                "device_id": item["device_id"],
                "status": item.get("status", "degraded"),
                "alert_state": alert_state,
                "capture_interval_sec": normalize_number(item.get("capture_interval_sec")),
                "camera_device": item.get("camera_device"),
                "last_capture_at": item.get("last_capture_at"),
                "last_upload_ok_at": item.get("last_upload_ok_at"),
                "last_error": item.get("last_error"),
                "last_seen": item.get("last_seen"),
                "updated_at": item.get("updated_at"),
                "created_at": item.get("created_at"),
                "is_online": is_online,
            }
        )
    return {"devices": payload}


def delete_face(face_id):
    """Delete a face from collection and DynamoDB."""
    try:
        rekognition.delete_faces(CollectionId=REKOGNITION_COLLECTION_ID, FaceIds=[face_id])
        get_known_persons_table().delete_item(Key={"face_id": face_id})
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
    now_iso = iso_utc_now()
    table = get_device_status_table()

    existing = table.get_item(Key={"device_id": device_id}).get("Item", {})
    item = {
        "device_id": device_id,
        "status": payload.get("status") or "degraded",
        "capture_interval_sec": payload.get("capture_interval_sec"),
        "camera_device": payload.get("camera_device"),
        "last_capture_at": iso_or_none(payload.get("last_capture_at")),
        "last_upload_ok_at": iso_or_none(payload.get("last_upload_ok_at")),
        "last_error": payload.get("last_error"),
        "last_seen": now_iso,
        "updated_at": now_iso,
        "created_at": existing.get("created_at", now_iso),
    }

    alert_update, notification_message = evaluate_heartbeat_alert(existing, item, now_iso)
    item.update(alert_update)
    table.put_item(Item=item)

    if notification_message:
        try:
            if send_telegram_message(notification_message):
                print(f"Sent Telegram device alert for {device_id}")
            else:
                print(f"Telegram device alert skipped or failed for {device_id}")
        except Exception as exc:  # pragma: no cover - defensive logging path
            print(f"Telegram device alert error for {device_id}: {exc}")

    return {
        "ok": True,
        "device_id": device_id,
        "last_seen": now_iso,
        "alert_state": item.get("alert_state"),
    }


def handler(event, context):
    """Lambda handler for API Gateway / Lambda Function URL."""
    print(f"Event: {json.dumps(event)}")

    http_method = event.get(
        "httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "GET")
    )
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

            if action == "detections":
                result = list_detections()
                return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

            if action == "devices":
                result = list_devices()
                return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

            if action == "faces":
                result = list_faces()
                return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

            result = list_faces()
            return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}

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
