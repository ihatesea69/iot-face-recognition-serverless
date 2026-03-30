# Raspberry Pi Setup

Tài liệu này mô tả cách bật hệ thống giám sát trên Raspberry Pi cho project này.

## Thư mục chạy trên Pi

```bash
/home/pi/iot-face-recognition
```

## 1. Cài dependency

```bash
cd /home/pi/iot-face-recognition
python3 -m venv .venv
. .venv/bin/activate
pip install -r src/rpi_client/requirements.txt
```

## 2. Cấu hình `.env`

Tạo hoặc cập nhật:

```bash
cd /home/pi/iot-face-recognition
cp src/rpi_client/.env.example .env
```

Điền các giá trị:

```env
DEVICE_ID=pi-main
CAPTURE_INTERVAL_SEC=5
HEARTBEAT_INTERVAL_SEC=30
UPLOAD_API_URL=https://<manage-faces-function-url>.lambda-url.ap-southeast-1.on.aws/
CAMERA_DEVICE=/dev/v4l/by-id/usb-046d_C270_HD_WEBCAM_FECCE640-video-index0
CAMERA_INPUT_FORMAT=mjpeg
CAMERA_RESOLUTION=640x480
CAMERA_FRAMERATE=30
CAMERA_WARMUP_FRAMES=30
CAPTURE_RETRY_ATTEMPTS=3
CAPTURE_RETRY_DELAY_SEC=1.0
REQUEST_TIMEOUT_SEC=15
```

## 3. Test thủ công

```bash
cd /home/pi/iot-face-recognition
. .venv/bin/activate
python -m src.rpi_client.main --capture
```

Nếu thành công:
- ảnh sẽ được upload vào `captures/<device_id>/...`
- Lambda `ProcessImage` sẽ xử lý ảnh
- dashboard sẽ hiện detection mới
- collection `device_status` sẽ có heartbeat của Pi

## 4. Bật service tự khởi động

```bash
sudo cp /home/pi/iot-face-recognition/src/rpi_client/iot-face-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now iot-face-client.service
```

## 5. Vận hành

Xem trạng thái:

```bash
systemctl status iot-face-client.service
```

Xem log:

```bash
journalctl -u iot-face-client.service -f
```

Khởi động lại:

```bash
sudo systemctl restart iot-face-client.service
```

Dừng:

```bash
sudo systemctl disable --now iot-face-client.service
```

## 6. Kiểm tra camera

```bash
v4l2-ctl --list-devices
```

```bash
ffmpeg -hide_banner -loglevel error -y \
  -f v4l2 -input_format mjpeg -video_size 640x480 -framerate 30 \
  -i /dev/video0 \
  -vf "select='gte(n,30)'" -frames:v 1 /tmp/test.jpg
```

## 7. Các lỗi thường gặp

- `Device or resource busy`
  Một app khác đang giữ camera. Thoát preview desktop hoặc process webcam cũ.

- Ảnh đen
  Camera chưa warmup đủ. Client đã bỏ qua 30 frame đầu; nếu vẫn tối, tăng `CAMERA_WARMUP_FRAMES`.

- Dashboard báo `offline`
  Kiểm tra `journalctl -u iot-face-client.service -f`, mạng outbound của Pi, và `UPLOAD_API_URL`.

- Log báo `/dev/video0` không tồn tại
  Webcam đang bị USB reset/disconnect. Ưu tiên dùng `/dev/v4l/by-id/...` và kiểm tra lại nguồn Pi.
