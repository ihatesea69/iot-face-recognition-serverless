"""Scheduled Lambda placeholder for offline device alerting."""

from __future__ import annotations

import json


def handler(event, context):
    """Scheduled monitor entrypoint."""
    print(f"Event: {json.dumps(event)}")
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Device alert monitor is configured"}),
    }
