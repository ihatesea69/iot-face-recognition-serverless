# 🚀 Infrastructure Deployment Guide

Hướng dẫn triển khai AWS infrastructure cho hệ thống IoT Face Recognition.

## 📁 Cấu trúc

```
infrastructure/
├── cloudformation.yaml    # SAM Template - Định nghĩa TẤT CẢ AWS resources
├── README.md              # Hướng dẫn này
├── SETUP_MONGODB.md       # Hướng dẫn cấu hình MongoDB Atlas
└── [deprecated]/          # Các file cũ (có thể xóa)
    ├── setup_aws.py       # Thay bằng CloudFormation
    ├── deploy_backend.py  # Thay bằng CloudFormation
    └── cleanup_aws.py     # Thay bằng `sam delete`
```

## 🛠️ Yêu cầu

1. **AWS CLI** đã cấu hình với credentials
2. **AWS SAM CLI** - [Cài đặt](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
3. **MongoDB Atlas** connection string

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
- **MongoDBUri**: `mongodb+srv://...` (connection string từ Atlas)
- **Environment**: `dev` hoặc `prod`

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
| `DashboardEnvConfig` | Copy vào `dashboard/.env.local` |

**Ví dụ output:**
```
ManageFacesFunctionUrl: https://abc123.lambda-url.ap-southeast-1.on.aws/
```

## 🔧 Cấu hình Dashboard

Copy output `DashboardEnvConfig` vào file `dashboard/.env.local`:

```env
NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL=https://abc123.lambda-url.ap-southeast-1.on.aws/
NEXT_PUBLIC_S3_BUCKET_URL=https://your-bucket.s3.ap-southeast-1.amazonaws.com
MONGODB_URI=mongodb+srv://...
```

## 🗑️ Cleanup (Xóa tất cả)

```bash
# Xóa toàn bộ stack (S3, Lambda, IAM Role, Rekognition Collection)
sam delete --stack-name iot-face-recognition
```

⚠️ **Lưu ý**: S3 bucket phải empty trước khi xóa. SAM sẽ tự động xóa nếu bucket trống.

## 📊 Resources được tạo

CloudFormation template sẽ tạo:

| Resource | Type | Mô tả |
|----------|------|-------|
| `FaceDataBucket` | S3 Bucket | Lưu ảnh captured |
| `BucketPolicy` | S3 Policy | Public read |
| `FaceCollection` | Rekognition Collection | Face embeddings |
| `LambdaExecutionRole` | IAM Role | Permissions cho Lambda |
| `ProcessImageFunction` | Lambda | Xử lý ảnh, gọi Rekognition |
| `ManageFacesFunction` | Lambda + URL | API quản lý faces |

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
