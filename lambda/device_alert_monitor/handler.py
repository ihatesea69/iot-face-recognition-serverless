"""Scheduled Lambda for offline device alerting."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os

import boto3

from telegram_notify import send_telegram_message


DYNAMODB_DEVICE_STATUS_TABLE = os.environ.get(
    "DYNAMODB_DEVICE_STATUS_TABLE", "home-security-device-status-prod"
)
DEVICE_OFFLINE_THRESHOLD_SEC = int(os.environ.get("DEVICE_OFFLINE_THRESHOLD_SEC", "90"))

dynamodb = boto3.resource("dynamodb")


def get_device_status_table():
    return dynamodb.Table(DYNAMODB_DEVICE_STATUS_TABLE)


def parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def iso_utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_offline_alert_message(device):
    lines = [
        "THIET BI MAT KET NOI",
        f"Thiet bi: {device['device_id']}",
        "Trang thai: offline",
        f"Last seen (UTC): {device.get('last_seen') or 'unknown'}",
    ]
    if device.get("last_error"):
        lines.append(f"Loi gan nhat: {device['last_error']}")
    return "\n".join(lines)


def iter_devices():
    table = get_device_status_table()
    scan_kwargs = {}

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            yield item

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key


def mark_device_offline(device_id, now_iso):
    get_device_status_table().update_item(
        Key={"device_id": device_id},
        UpdateExpression=(
            "SET alert_state = :alert_state, last_alert_at = :last_alert_at, "
            "last_alert_error_key = :last_alert_error_key"
        ),
        ExpressionAttributeValues={
            ":alert_state": "offline",
            ":last_alert_at": now_iso,
            ":last_alert_error_key": "offline",
        },
    )


def handler(event, context):
    """Scheduled monitor entrypoint."""
    print(f"Event: {json.dumps(event)}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    now_iso = iso_utc_now()
    alerts_sent = 0

    for device in iter_devices():
        last_seen_raw = device.get("last_seen")
        last_seen = parse_datetime(last_seen_raw)
        if not last_seen:
            continue

        elapsed = (now - last_seen).total_seconds()
        if elapsed <= DEVICE_OFFLINE_THRESHOLD_SEC:
            continue

        if device.get("alert_state") == "offline":
            continue

        message = build_offline_alert_message(device)
        try:
            if send_telegram_message(message):
                alerts_sent += 1
                print(f"Sent offline alert for {device['device_id']}")
            else:
                print(f"Telegram offline alert skipped or failed for {device['device_id']}")
        except Exception as exc:  # pragma: no cover - defensive logging path
            print(f"Telegram offline alert error for {device['device_id']}: {exc}")

        mark_device_offline(device["device_id"], now_iso)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Device alert monitor completed", "alerts_sent": alerts_sent}),
    }
