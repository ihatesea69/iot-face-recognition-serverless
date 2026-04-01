from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib import error


REPO_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def temporary_sys_path(path: Path):
    path_str = str(path)
    sys.path.insert(0, path_str)
    try:
        yield
    finally:
        try:
            sys.path.remove(path_str)
        except ValueError:
            pass


def load_module(unique_name: str, relative_path: str, env: dict[str, str] | None = None):
    module_path = REPO_ROOT / relative_path
    sys.modules.pop(unique_name, None)
    sys.modules.pop("telegram_notify", None)

    with (
        patch.dict(os.environ, env or {}, clear=False),
        patch("boto3.client", return_value=MagicMock()),
        patch("boto3.resource", return_value=MagicMock()),
        temporary_sys_path(module_path.parent),
    ):
        spec = importlib.util.spec_from_file_location(unique_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


class FakeDeviceStatusTable:
    def __init__(self, existing_item=None):
        self.existing_item = existing_item or {}
        self.put_calls = []

    def get_item(self, Key):
        return {"Item": self.existing_item}

    def put_item(self, Item):
        self.put_calls.append(Item)
        self.existing_item = Item


class TelegramNotifyTests(unittest.TestCase):
    def test_send_telegram_message_success(self):
        module = load_module(
            "process_image_telegram_notify_success",
            "lambda/process_image/telegram_notify.py",
            env={"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "12345"},
        )

        response = MagicMock()
        response.read.return_value = b'{"ok": true, "result": {"message_id": 1}}'
        context_manager = MagicMock()
        context_manager.__enter__.return_value = response
        context_manager.__exit__.return_value = False

        with patch.object(module.request, "urlopen", return_value=context_manager) as urlopen_mock:
            sent = module.send_telegram_message("hello")

        self.assertTrue(sent)
        self.assertEqual(urlopen_mock.call_count, 1)

    def test_send_telegram_message_http_error(self):
        module = load_module(
            "process_image_telegram_notify_error",
            "lambda/process_image/telegram_notify.py",
            env={"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "12345"},
        )

        http_error = error.HTTPError(
            url="https://api.telegram.org",
            code=500,
            msg="boom",
            hdrs=None,
            fp=BytesIO(b'{"ok": false}'),
        )

        with patch.object(module.request, "urlopen", side_effect=http_error):
            sent = module.send_telegram_message("hello")

        self.assertFalse(sent)


class ProcessImageNotificationTests(unittest.TestCase):
    def test_stranger_detection_sends_telegram_alert(self):
        module = load_module("process_image_handler_stranger", "lambda/process_image/handler.py")
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "demo-bucket"},
                        "object": {"key": "captures/pi-main/frame.jpg"},
                    }
                }
            ]
        }

        with (
            patch.object(module, "search_face", return_value={"FaceMatches": []}),
            patch.object(module, "store_detection_event", return_value="evt-123"),
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            response = module.handler(s3_event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(send_mock.call_count, 1)
        self.assertIn("evt-123", send_mock.call_args.args[0])

    def test_known_and_no_face_do_not_send_telegram_alert(self):
        module = load_module("process_image_handler_non_stranger", "lambda/process_image/handler.py")
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "demo-bucket"},
                        "object": {"key": "captures/pi-main/frame.jpg"},
                    }
                }
            ]
        }

        cases = [
            {"FaceMatches": [{"Face": {"FaceId": "face-1", "ExternalImageId": "Alice"}, "Similarity": 98.2}]},
            {"FaceMatches": [], "Error": "NoFaceDetected"},
        ]

        for result in cases:
            with self.subTest(result=result):
                with (
                    patch.object(module, "search_face", return_value=result),
                    patch.object(module, "store_detection_event", return_value="evt-123"),
                    patch.object(module, "send_telegram_message", return_value=True) as send_mock,
                ):
                    response = module.handler(s3_event, None)

                self.assertEqual(response["statusCode"], 200)
                send_mock.assert_not_called()

    def test_telegram_failure_does_not_fail_handler(self):
        module = load_module("process_image_handler_telegram_failure", "lambda/process_image/handler.py")
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "demo-bucket"},
                        "object": {"key": "captures/pi-main/frame.jpg"},
                    }
                }
            ]
        }

        with (
            patch.object(module, "search_face", return_value={"FaceMatches": []}),
            patch.object(module, "store_detection_event", return_value="evt-123"),
            patch.object(module, "send_telegram_message", side_effect=RuntimeError("telegram down")),
        ):
            response = module.handler(s3_event, None)

        self.assertEqual(response["statusCode"], 200)


class ManageFacesAlertTests(unittest.TestCase):
    def test_upsert_degraded_sends_new_error_alert(self):
        module = load_module("manage_faces_handler_degraded", "lambda/manage_faces/handler.py")
        table = FakeDeviceStatusTable(existing_item={"device_id": "pi-main", "created_at": "2026-01-01T00:00:00Z"})

        with (
            patch.object(module, "get_device_status_table", return_value=table),
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            result = module.upsert_device_status(
                {
                    "device_id": "pi-main",
                    "status": "degraded",
                    "capture_interval_sec": 5,
                    "camera_device": "/dev/video0",
                    "last_error": "Camera busy",
                }
            )

        self.assertEqual(result["alert_state"], "degraded")
        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(table.put_calls[-1]["alert_state"], "degraded")
        self.assertEqual(table.put_calls[-1]["last_alert_error_key"], "Camera busy")

    def test_upsert_same_degraded_error_does_not_resend(self):
        module = load_module("manage_faces_handler_duplicate_error", "lambda/manage_faces/handler.py")
        table = FakeDeviceStatusTable(
            existing_item={
                "device_id": "pi-main",
                "created_at": "2026-01-01T00:00:00Z",
                "alert_state": "degraded",
                "last_alert_at": "2026-04-01T00:00:00Z",
                "last_alert_error_key": "Camera busy",
            }
        )

        with (
            patch.object(module, "get_device_status_table", return_value=table),
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            result = module.upsert_device_status(
                {
                    "device_id": "pi-main",
                    "status": "degraded",
                    "capture_interval_sec": 5,
                    "camera_device": "/dev/video0",
                    "last_error": "Camera busy",
                }
            )

        self.assertEqual(result["alert_state"], "degraded")
        send_mock.assert_not_called()

    def test_upsert_online_after_offline_sends_recovery(self):
        module = load_module("manage_faces_handler_recovery", "lambda/manage_faces/handler.py")
        table = FakeDeviceStatusTable(
            existing_item={
                "device_id": "pi-main",
                "created_at": "2026-01-01T00:00:00Z",
                "alert_state": "offline",
                "last_alert_at": "2026-04-01T00:00:00Z",
                "last_alert_error_key": "offline",
            }
        )

        with (
            patch.object(module, "get_device_status_table", return_value=table),
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            result = module.upsert_device_status(
                {
                    "device_id": "pi-main",
                    "status": "online",
                    "capture_interval_sec": 5,
                    "camera_device": "/dev/video0",
                }
            )

        self.assertEqual(result["alert_state"], "online")
        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(table.put_calls[-1]["last_alert_error_key"], None)


class DeviceAlertMonitorTests(unittest.TestCase):
    def test_monitor_sends_offline_alert_once(self):
        module = load_module("device_alert_monitor_handler", "lambda/device_alert_monitor/handler.py")
        offline_device = {
            "device_id": "pi-main",
            "last_seen": "2026-04-01T00:00:00Z",
            "alert_state": "online",
            "last_error": "Network timeout",
        }

        with (
            patch.object(module, "iter_devices", return_value=[offline_device]),
            patch.object(module, "mark_device_offline") as mark_mock,
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            response = module.handler({}, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(mark_mock.call_count, 1)

    def test_monitor_skips_devices_already_marked_offline(self):
        module = load_module("device_alert_monitor_skip", "lambda/device_alert_monitor/handler.py")
        offline_device = {
            "device_id": "pi-main",
            "last_seen": "2026-04-01T00:00:00Z",
            "alert_state": "offline",
        }

        with (
            patch.object(module, "iter_devices", return_value=[offline_device]),
            patch.object(module, "mark_device_offline") as mark_mock,
            patch.object(module, "send_telegram_message", return_value=True) as send_mock,
        ):
            response = module.handler({}, None)

        self.assertEqual(response["statusCode"], 200)
        send_mock.assert_not_called()
        mark_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
