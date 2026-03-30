# Raspberry Pi Client

Pi client này chụp ảnh bằng `ffmpeg`, upload lên S3 bằng presigned POST, và gửi
heartbeat lên Lambda để dashboard hiển thị trạng thái `online/offline`.

## Chuẩn bị

Project trên Pi đang được đặt tại:

```bash
/home/pi/iot-face-recognition
```

Tạo virtualenv và cài dependency:

```bash
cd /home/pi/iot-face-recognition
python3 -m venv .venv
. .venv/bin/activate
pip install -r src/rpi_client/requirements.txt
```

Tạo file cấu hình từ mẫu:

```bash
cp src/rpi_client/.env.example .env
```

Giá trị quan trọng trong `.env`:

```env
DEVICE_ID=pi-main
CAPTURE_INTERVAL_SEC=5
HEARTBEAT_INTERVAL_SEC=30
UPLOAD_API_URL=https://<manage-faces-function-url>.lambda-url.ap-southeast-1.on.aws/
CAMERA_DEVICE=/dev/video0
CAMERA_INPUT_FORMAT=mjpeg
CAMERA_RESOLUTION=640x480
CAMERA_FRAMERATE=30
CAMERA_WARMUP_FRAMES=30
CAPTURE_RETRY_ATTEMPTS=3
CAPTURE_RETRY_DELAY_SEC=1.0
```

Nếu có symlink ổn định trong `/dev/v4l/by-id/`, ưu tiên dùng path đó thay vì
`/dev/video0`.

## Chạy tay để test

Chụp một ảnh và upload một lần:

```bash
cd /home/pi/iot-face-recognition
. .venv/bin/activate
python -m src.rpi_client.main --capture
```

Chạy vòng lặp liên tục, mỗi 5 giây chụp một ảnh:

```bash
cd /home/pi/iot-face-recognition
. .venv/bin/activate
python -m src.rpi_client.main
```

## Chạy cùng systemd

Copy service file:

```bash
sudo cp /home/pi/iot-face-recognition/src/rpi_client/iot-face-client.service /etc/systemd/system/
```

Reload systemd và bật tự khởi động:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iot-face-client.service
```

Kiểm tra trạng thái:

```bash
systemctl status iot-face-client.service
```

Xem log realtime:

```bash
journalctl -u iot-face-client.service -f
```

Restart sau khi sửa code hoặc `.env`:

```bash
sudo systemctl restart iot-face-client.service
```

Tắt service:

```bash
sudo systemctl disable --now iot-face-client.service
```

## Kiểm tra nhanh phần cứng

Liệt kê camera:

```bash
v4l2-ctl --list-devices
```

Chụp thử trực tiếp bằng ffmpeg:

```bash
ffmpeg -hide_banner -loglevel error -y \
  -f v4l2 -input_format mjpeg -video_size 640x480 -framerate 30 \
  -i /dev/video0 \
  -vf "select='gte(n,30)'" -frames:v 1 /tmp/test.jpg
```

## Ghi chú

- Camera đã xác nhận hoạt động trên `/dev/video0`.
- Ổn định hơn nếu dùng `/dev/v4l/by-id/...-video-index0` khi webcam hỗ trợ.
- Client sẽ retry ngắn khi camera báo `busy` hoặc biến mất tạm thời khỏi `/dev/video*`.
- Pi không cần AWS access key; xác thực upload dùng presigned URL từ Lambda.
- Dashboard sẽ hiện `offline` nếu quá khoảng 90 giây không nhận heartbeat mới.
