"""Configuration for the Raspberry Pi edge client."""

from pathlib import Path
import os
import glob

from dotenv import load_dotenv


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]

# Load root-level env first, then an optional Pi-local env beside this module.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(MODULE_DIR / ".env", override=True)


DEVICE_ID = os.getenv("DEVICE_ID", "pi-main")
CAPTURE_INTERVAL_SEC = int(os.getenv("CAPTURE_INTERVAL_SEC", "5"))
HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "30"))
UPLOAD_API_URL = os.getenv("UPLOAD_API_URL", "").rstrip("/")

DEFAULT_CAMERA_DEVICE = "/dev/video0"
CAMERA_INPUT_FORMAT = os.getenv("CAMERA_INPUT_FORMAT", "mjpeg")
CAMERA_RESOLUTION = os.getenv("CAMERA_RESOLUTION", "640x480")
CAMERA_FRAMERATE = int(os.getenv("CAMERA_FRAMERATE", "30"))
CAMERA_WARMUP_FRAMES = int(os.getenv("CAMERA_WARMUP_FRAMES", "30"))
CAPTURE_RETRY_ATTEMPTS = int(os.getenv("CAPTURE_RETRY_ATTEMPTS", "3"))
CAPTURE_RETRY_DELAY_SEC = float(os.getenv("CAPTURE_RETRY_DELAY_SEC", "1.0"))

REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "15"))
HEALTH_OFFLINE_THRESHOLD_SEC = int(os.getenv("HEALTH_OFFLINE_THRESHOLD_SEC", "90"))


def resolve_camera_device() -> str:
    """Resolve a stable video device path if possible."""
    configured = os.getenv("CAMERA_DEVICE")
    if configured:
        return configured

    by_id_matches = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    if by_id_matches:
        return by_id_matches[0]

    return DEFAULT_CAMERA_DEVICE


CAMERA_DEVICE = resolve_camera_device()
