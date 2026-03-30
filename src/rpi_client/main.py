"""Raspberry Pi edge client using FFmpeg capture and presigned uploads."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

try:
    from .config import (
        CAMERA_DEVICE,
        CAMERA_FRAMERATE,
        CAMERA_INPUT_FORMAT,
        CAMERA_RESOLUTION,
        CAPTURE_RETRY_ATTEMPTS,
        CAPTURE_RETRY_DELAY_SEC,
        CAMERA_WARMUP_FRAMES,
        CAPTURE_INTERVAL_SEC,
        DEVICE_ID,
        HEARTBEAT_INTERVAL_SEC,
        REQUEST_TIMEOUT_SEC,
        UPLOAD_API_URL,
    )
except ImportError:
    from config import (  # type: ignore
        CAMERA_DEVICE,
        CAMERA_FRAMERATE,
        CAMERA_INPUT_FORMAT,
        CAMERA_RESOLUTION,
        CAPTURE_RETRY_ATTEMPTS,
        CAPTURE_RETRY_DELAY_SEC,
        CAMERA_WARMUP_FRAMES,
        CAPTURE_INTERVAL_SEC,
        DEVICE_ID,
        HEARTBEAT_INTERVAL_SEC,
        REQUEST_TIMEOUT_SEC,
        UPLOAD_API_URL,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


@dataclass
class HeartbeatState:
    status: str = "online"
    last_capture_at: str | None = None
    last_upload_ok_at: str | None = None
    last_error: str | None = None
    last_heartbeat_sent_at: float = 0.0


class PiEdgeClient:
    def __init__(self, device_id: str, capture_interval_sec: int, heartbeat_interval_sec: int):
        if not UPLOAD_API_URL:
            raise ValueError("UPLOAD_API_URL must be configured in .env")

        self.device_id = device_id
        self.capture_interval_sec = capture_interval_sec
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.session = requests.Session()
        self.heartbeat = HeartbeatState()
        self.last_reported_status = "online"

        print(f"[INIT] Device ID: {self.device_id}")
        print(f"[INIT] Upload API: {UPLOAD_API_URL}")
        print(f"[INIT] Capture interval: {self.capture_interval_sec}s")
        print(f"[INIT] Heartbeat interval: {self.heartbeat_interval_sec}s")
        print(f"[INIT] Camera: {CAMERA_DEVICE} ({CAMERA_INPUT_FORMAT} {CAMERA_RESOLUTION}@{CAMERA_FRAMERATE})")

    def get_presigned_upload(self) -> dict:
        response = self.session.get(
            UPLOAD_API_URL,
            params={
                "action": "upload_url",
                "use_case": "device",
                "device_id": self.device_id,
                "file_type": "image/jpeg",
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json()
        for field in ("url", "fields", "key"):
            if field not in payload:
                raise ValueError(f"Missing '{field}' in presigned upload response")
        return payload

    def capture_image(self) -> bytes:
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(1, CAPTURE_RETRY_ATTEMPTS + 1):
            try:
                return self._capture_image_once()
            except subprocess.CalledProcessError as exc:
                last_error = exc
                stderr = (exc.stderr or "").strip()
                is_transient = "No such file or directory" in stderr or "Device or resource busy" in stderr
                if attempt >= CAPTURE_RETRY_ATTEMPTS or not is_transient:
                    raise
                print(
                    f"[CAMERA] transient failure on attempt {attempt}/{CAPTURE_RETRY_ATTEMPTS}, retrying in {CAPTURE_RETRY_DELAY_SEC}s"
                )
                time.sleep(CAPTURE_RETRY_DELAY_SEC)

        if last_error:
            raise last_error
        raise RuntimeError("capture_image exhausted without a result")

    def _capture_image_once(self) -> bytes:
        with tempfile.TemporaryDirectory(prefix="iot-face-") as tmp_dir:
            output_path = Path(tmp_dir) / "capture.jpg"
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "v4l2",
                "-input_format",
                CAMERA_INPUT_FORMAT,
                "-video_size",
                CAMERA_RESOLUTION,
                "-framerate",
                str(CAMERA_FRAMERATE),
                "-i",
                CAMERA_DEVICE,
            ]

            if CAMERA_WARMUP_FRAMES > 0:
                command.extend(["-vf", f"select=gte(n\\,{CAMERA_WARMUP_FRAMES})"])

            command.extend(["-frames:v", "1", str(output_path)])

            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )

            image_data = output_path.read_bytes()
            if not image_data:
                raise RuntimeError("FFmpeg produced an empty image")
            return image_data

    def upload_image(self, image_data: bytes, presigned: dict) -> None:
        files = {
            "file": ("capture.jpg", image_data, "image/jpeg"),
        }
        response = self.session.post(
            presigned["url"],
            data=presigned["fields"],
            files=files,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()

    def send_heartbeat(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.heartbeat.last_heartbeat_sent_at < self.heartbeat_interval_sec:
            return

        payload = {
            "device_id": self.device_id,
            "status": self.heartbeat.status,
            "capture_interval_sec": self.capture_interval_sec,
            "camera_device": CAMERA_DEVICE,
            "last_capture_at": self.heartbeat.last_capture_at,
            "last_upload_ok_at": self.heartbeat.last_upload_ok_at,
            "last_error": self.heartbeat.last_error,
        }
        try:
            response = self.session.post(
                UPLOAD_API_URL,
                params={"action": "heartbeat"},
                json=payload,
                timeout=REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
            self.heartbeat.last_heartbeat_sent_at = now
            self.last_reported_status = self.heartbeat.status
            print(f"[HEARTBEAT] status={self.heartbeat.status}")
        except requests.RequestException as exc:
            print(f"[HEARTBEAT] failed: {exc}")

    def run_once(self) -> None:
        capture_started_at = utc_now_iso()
        print("[CAPTURE] Requesting presigned upload URL...")
        presigned = self.get_presigned_upload()

        print("[CAPTURE] Capturing frame via FFmpeg...")
        image_data = self.capture_image()
        self.heartbeat.last_capture_at = capture_started_at

        print(f"[UPLOAD] Uploading to {presigned['key']}...")
        self.upload_image(image_data, presigned)

        self.heartbeat.status = "online"
        self.heartbeat.last_error = None
        self.heartbeat.last_upload_ok_at = utc_now_iso()
        print("[SUCCESS] Capture and upload complete")
        if self.last_reported_status != "online":
            self.send_heartbeat(force=True)

    def loop(self) -> None:
        print("[START] Running interval capture loop (Ctrl+C to stop)")
        while True:
            cycle_started_at = time.time()
            try:
                self.run_once()
                self.send_heartbeat()
            except requests.RequestException as exc:
                self.heartbeat.status = "degraded"
                self.heartbeat.last_error = f"{type(exc).__name__}: {exc}"
                print(f"[ERROR] Network error: {exc}")
                self.send_heartbeat(force=True)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                self.heartbeat.status = "degraded"
                self.heartbeat.last_error = stderr or f"FFmpeg exited with code {exc.returncode}"
                print(f"[ERROR] FFmpeg capture failed: {self.heartbeat.last_error}")
                self.send_heartbeat(force=True)
            except Exception as exc:  # pragma: no cover - defensive path
                self.heartbeat.status = "degraded"
                self.heartbeat.last_error = f"{type(exc).__name__}: {exc}"
                print(f"[ERROR] Unexpected error: {exc}")
                self.send_heartbeat(force=True)

            elapsed = time.time() - cycle_started_at
            sleep_for = max(0.0, self.capture_interval_sec - elapsed)
            if sleep_for:
                time.sleep(sleep_for)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raspberry Pi edge capture client")
    parser.add_argument("--device-id", default=DEVICE_ID, help="Logical device identifier")
    parser.add_argument(
        "--interval",
        type=int,
        default=CAPTURE_INTERVAL_SEC,
        help="Capture interval in seconds",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=HEARTBEAT_INTERVAL_SEC,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--capture",
        "--once",
        action="store_true",
        dest="capture_once",
        help="Capture and upload a single image, then exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        client = PiEdgeClient(
            device_id=args.device_id,
            capture_interval_sec=args.interval,
            heartbeat_interval_sec=args.heartbeat_interval,
        )

        if args.capture_once:
            client.run_once()
            client.send_heartbeat(force=True)
            return 0

        client.loop()
        return 0
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
        return 0
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
