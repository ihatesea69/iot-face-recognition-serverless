# 🚀 Infrastructure Deployment Guide

Hướng dẫn triển khai AWS production stack cho hệ thống IoT Face Recognition với
S3, Rekognition, Lambda Function URL, DynamoDB và frontend host trên AWS Amplify.

## 📁 Cấu trúc

```
infrastructure/
├── cloudformation.yaml    # SAM Template - Định nghĩa TẤT CẢ AWS resources
├── README.md              # Hướng dẫn này
├── vercel-iam-policy.json # IAM policy mẫu cũ cho Vercel (rollback/reference)
├── SETUP_MONGODB.md       # Hướng dẫn cấu hình MongoDB Atlas
├── scripts/               # Scripts backup / migrate dữ liệu Mongo -> DynamoDB
└── [deprecated]/          # Các file cũ (có thể xóa)
    ├── setup_aws.py       # Thay bằng CloudFormation
    ├── deploy_backend.py  # Thay bằng CloudFormation
    └── cleanup_aws.py     # Thay bằng `sam delete`
```

## 🛠️ Yêu cầu

1. **AWS CLI** đã cấu hình với credentials
2. **AWS SAM CLI** - [Cài đặt](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
3. Nếu migrate dữ liệu cũ: MongoDB Atlas connection string

```bash
# Kiểm tra AWS CLI
aws sts get-caller-identity

# Cài đặt SAM CLI (Windows)
winget install Amazon.SAM-CLI

# Hoặc với Chocolatey
choco install aws-sam-cli
```

## 🚀 Deploy (Triển khai)

### Bước 1: Build

```bash
cd infrastructure
sam build
```

### Bước 2: Deploy lần đầu (guided)

```bash
sam deploy --guided
```

Nhập các thông số khi được hỏi:
- **Stack Name**: `iot-face-recognition` (hoặc tên tùy chọn)
- **AWS Region**: `ap-southeast-1` (hoặc region của bạn)
- **S3BucketName**: `your-unique-bucket-name` (phải unique toàn cầu)
- **RekognitionCollectionId**: `home-security-faces`
- **Environment**: `dev` hoặc `prod`
- **TelegramBotToken**: bot token từ `@BotFather` (để trống nếu chưa bật notifications)
- **TelegramChatId**: chat ID hoặc group ID nhận cảnh báo
- **DeviceOfflineThresholdSec**: ngưỡng heartbeat để coi thiết bị offline

### Bước 3: Deploy các lần sau

```bash
sam deploy
```

## 📋 Outputs

Sau khi deploy thành công, bạn sẽ nhận được:

| Output | Mô tả |
|--------|-------|
| `S3BucketName` | Tên S3 bucket |
| `S3BucketUrl` | URL public của bucket |
| `ManageFacesFunctionUrl` | **API URL** - dùng cho dashboard |
| `DetectionsTableName` | Bảng DynamoDB cho detection events |
| `KnownPersonsTableName` | Bảng DynamoDB cho known persons |
| `DeviceStatusTableName` | Bảng DynamoDB cho device status |
| `DashboardEnvConfig` | Copy vào `dashboard/.env.local` |

**Ví dụ output:**
```
ManageFacesFunctionUrl: https://abc123.lambda-url.ap-southeast-1.on.aws/
```

## 🔧 Cấu hình Dashboard

Copy output `DashboardEnvConfig` vào file `dashboard/.env.local` hoặc AWS Amplify env:

```env
APP_AWS_REGION=ap-southeast-1
AWS_REGION=ap-southeast-1
NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL=https://abc123.lambda-url.ap-southeast-1.on.aws/
NEXT_PUBLIC_S3_BUCKET_URL=https://your-bucket.s3.ap-southeast-1.amazonaws.com
S3_BUCKET_NAME=your-bucket
REKOGNITION_COLLECTION_ID=home-security-faces
DYNAMODB_DETECTIONS_TABLE=home-security-detections-prod
DYNAMODB_KNOWN_PERSONS_TABLE=home-security-known-persons-prod
DYNAMODB_DEVICE_STATUS_TABLE=home-security-device-status-prod
```

`TelegramBotToken` và `TelegramChatId` là backend config/secrets, không được đưa vào `dashboard/.env.local` dưới dạng `NEXT_PUBLIC_*`.

## 🌐 Deploy Frontend lên AWS Amplify

1. Tạo Amplify app mới, ví dụ `iot-face-recognition-dashboard-aws`
2. Kết nối repo GitHub hiện tại
3. Chọn branch `main`
4. Chọn **App root** là `dashboard`
5. Amplify sẽ dùng file `dashboard/amplify.yml`
6. Gắn env vars:
   - `APP_AWS_REGION`
   - `S3_BUCKET_NAME`
   - `REKOGNITION_COLLECTION_ID`
   - `DYNAMODB_DETECTIONS_TABLE`
   - `DYNAMODB_KNOWN_PERSONS_TABLE`
   - `DYNAMODB_DEVICE_STATUS_TABLE`
   - `NEXT_PUBLIC_S3_BUCKET_URL`
   - `NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL`
7. Gắn **SSR Compute role** với quyền tối thiểu cho:
   - 3 bảng DynamoDB production
   - `s3:PutObject` trên bucket production
   - Rekognition collection `home-security-faces`

## 🗑️ Cleanup (Xóa tất cả)

```bash
# Xóa toàn bộ stack (S3, Lambda, IAM Role, DynamoDB tables)
sam delete --stack-name iot-face-recognition
```

⚠️ **Lưu ý**: S3 bucket phải empty trước khi xóa. SAM sẽ tự động xóa nếu bucket trống.

## 📊 Resources được tạo

CloudFormation template sẽ tạo:

| Resource | Type | Mô tả |
|----------|------|-------|
| `FaceDataBucket` | S3 Bucket | Lưu ảnh captured |
| `BucketPolicy` | S3 Policy | Public read |
| `DetectionEventsTable` | DynamoDB | Feed detection events |
| `KnownPersonsTable` | DynamoDB | Danh sách người quen |
| `DeviceStatusTable` | DynamoDB | Trạng thái thiết bị |
| `LambdaExecutionRole` | IAM Role | Permissions cho Lambda |
| `ProcessImageFunction` | Lambda | Xử lý ảnh, gọi Rekognition |
| `ManageFacesFunction` | Lambda + URL | API quản lý faces |
| `DeviceAlertMonitorFunction` | Lambda + Schedule | Quét heartbeat để phát hiện offline và gửi Telegram alert |

## 🔄 Migration từ MongoDB

Backup và migrate dữ liệu cũ sang DynamoDB:

```bash
node infrastructure/scripts/migrate-mongodb-to-dynamodb.mjs
```

Script sẽ:
- backup `known_persons`, `detection_events`, `device_status` ra JSON
- backfill sang các bảng DynamoDB
- đối chiếu số lượng bản ghi sau migration

## ✅ Serverless / managed components

- **AWS Lambda**: serverless
- **Amazon S3**: fully managed object storage
- **Amazon DynamoDB**: serverless NoSQL
- **Amazon Rekognition**: fully managed AI service
- **AWS Amplify Hosting compute**: managed frontend hosting cho SSR

## 🔄 So sánh với Python scripts (cũ)

| Tính năng | Python Scripts | CloudFormation/SAM |
|-----------|---------------|-------------------|
| Quản lý state | ❌ Không có | ✅ AWS quản lý |
| Rollback | ❌ Thủ công | ✅ Tự động |
| Drift detection | ❌ Không | ✅ Có |
| Reproducible | ⚠️ Có thể lỗi | ✅ Luôn giống nhau |
| Team collaboration | ❌ Khó | ✅ Version control |

**Khuyến nghị**: Dùng CloudFormation/SAM cho production.

## 🐛 Troubleshooting

### Lỗi "Bucket already exists"
Bucket name phải unique toàn cầu. Thử tên khác.

### Lỗi "Role already exists"
Stack cũ chưa xóa sạch. Chạy `sam delete` trước.

### Lambda không có quyền
Kiểm tra IAM Role đã attach đúng policies chưa trong CloudWatch Logs.

---

📚 **Tài liệu tham khảo:**
- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [CloudFormation Resource Types](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)
