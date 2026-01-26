"""
Raspberry Pi Edge Client - Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")

# S3 Configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "iot-face-recognition-bucket")

# Hardware Configuration
PIR_PIN = int(os.getenv("PIR_PIN", "17"))  # GPIO Pin for PIR Sensor (BCM mode)
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))  # 0 for default camera
MOTION_COOLDOWN = int(os.getenv("MOTION_COOLDOWN", "5"))  # Seconds between captures

# Simulator Mode (for testing on PC without GPIO)
SIMULATE_GPIO = os.getenv("SIMULATE_GPIO", "false").lower() == "true"
