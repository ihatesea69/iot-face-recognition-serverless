"""
Raspberry Pi Edge Client - Main Application

This script runs on the Raspberry Pi controls the camera and PIR sensor.
When motion is detected:
1. Captures an image
2. Uploads to AWS S3
3. Cooldown to prevent spamming
"""

import argparse
import sys
import time
import uuid
import threading
from datetime import datetime
import cv2
import boto3
from botocore.exceptions import ClientError

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    S3_BUCKET_NAME,
    PIR_PIN,
    CAMERA_INDEX,
    MOTION_COOLDOWN,
    SIMULATE_GPIO,
)

# Setup GPIO
try:
    if not SIMULATE_GPIO:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIR_PIN, GPIO.IN)
        print(f"[INIT] GPIO setup complete. PIR Sensor on Pin {PIR_PIN}")
    else:
        print("[INIT] Running in SIMULATION mode (Mock GPIO)")
except ImportError:
    print("[WARN] RPi.GPIO not found. Forcing SIMULATION mode.")
    SIMULATE_GPIO = True


class RPiEdgeClient:
    def __init__(self):
        # Configure AWS client with optional credentials
        aws_args = {"region_name": AWS_REGION}
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            aws_args["aws_access_key_id"] = AWS_ACCESS_KEY_ID
            aws_args["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
            
        self.s3_client = boto3.client("s3", **aws_args)
        
        self.device_id = f"rpi-{uuid.uuid4().hex[:8]}"
        self.last_capture_time = 0
        self.is_processing = False
        print(f"[INIT] Device ID: {self.device_id}")

    def capture_image(self) -> bytes | None:
        """Capture image from camera using OpenCV."""
        if SIMULATE_GPIO:
             print("[SIM] Generating synthetic image (Simulation Mode)...")
             # Create a black image with timestamp
             import numpy as np
             img = np.zeros((720, 1280, 3), np.uint8)
             
             # Add text
             font = cv2.FONT_HERSHEY_SIMPLEX
             cv2.putText(img, f'SIMULATION {datetime.now()}', (50, 50), font, 1, (255, 255, 255), 2, cv2.LINE_AA)
             
             # Draw a fake "face" (circle) to limit confusion
             cv2.circle(img, (640, 360), 100, (255, 255, 255), -1)
             
             _, buffer = cv2.imencode(".jpg", img)
             return buffer.tobytes()

        print("[CAMERA] Capturing frame...")
        cap = cv2.VideoCapture(CAMERA_INDEX)
        
        # Warmup camera
        if not cap.isOpened():
            print("[ERROR] Cannot open camera")
            return None

        # Allow camera to adjust light levels
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret:
            print("[ERROR] Failed to capture frame")
            return None

        # Resize for faster upload (optional, e.g., to 720p)
        # frame = cv2.resize(frame, (1280, 720))

        _, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes()

    def upload_to_s3(self, image_data: bytes) -> str | None:
        """Upload image to S3 bucket."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_key = f"captures/{self.device_id}/{timestamp}.jpg"

        try:
            print(f"[UPLOAD] Uploading to S3: {object_key}...")
            self.s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=object_key,
                Body=image_data,
                ContentType="image/jpeg",
            )

            image_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{object_key}"
            print(f"[SUCCESS] Upload complete: {image_url}")
            return image_url

        except ClientError as e:
            print(f"[ERROR] S3 upload failed: {e}")
            return None

    def handle_motion(self):
        """Handle motion detection event."""
        current_time = time.time()
        
        # Check cooldown and processing flag
        if self.is_processing or (current_time - self.last_capture_time < MOTION_COOLDOWN):
            return

        print("\n[MOTION] Movement detected!")
        self.is_processing = True
        
        try:
            image_data = self.capture_image()
            if image_data:
                self.upload_to_s3(image_data)
                self.last_capture_time = time.time()
        except Exception as e:
            print(f"[ERROR] Processing exception: {e}")
        finally:
            self.is_processing = False
            print("[WAIT] Ready for next motion...")

    def run(self, auto_mode: bool = False, interval: int = 5):
        """Main loop."""
        print(f"[START] Monitoring for motion... (Press Ctrl+C to stop)")
        
        try:
            if SIMULATE_GPIO:
                if auto_mode:
                    print(f"[AUTO] Running in auto-simulation mode. Triggering every {interval}s.")
                    while True:
                        self.handle_motion()
                        time.sleep(interval)
                else:
                    # Interactive simulation
                    while True:
                        input("Press Enter to simulate motion (or Ctrl+C to exit)...")
                        self.handle_motion()
            else:
                # Real GPIO loop
                # Basic Polling (can be upgraded to Interrupts)
                while True:
                    if GPIO.input(PIR_PIN):
                        self.handle_motion()
                    time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n[STOP] Stopping...")
        finally:
            if not SIMULATE_GPIO:
                try:
                    GPIO.cleanup()
                except:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raspberry Pi Edge Client")
    parser.add_argument("--auto", action="store_true", help="Auto simulation mode (no manual input required)")
    parser.add_argument("--capture", action="store_true", help="Capture single image and exit (for testing)")
    parser.add_argument("--interval", type=int, default=5, help="Interval for auto simulation (seconds)")
    args = parser.parse_args()

    client = RPiEdgeClient()
    
    if args.capture:
        print("[TEST] performing single capture...")
        client.handle_motion()
    else:
        client.run(auto_mode=args.auto, interval=args.interval)

