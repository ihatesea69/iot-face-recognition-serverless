# Hướng dẫn Setup MongoDB Atlas (Miễn phí)

## 1. Tạo Tài khoản & Cluster

1. Truy cập [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register).
2. Đăng ký tài khoản và đăng nhập.
3. Tạo **Shared Cluster** (FREE).
4. Chọn Cloud Provider (AWS) và Region (Singapore hoặc gần nhất).
5. Nhấn **Create Cluster**.

## 2. Tạo Database User

1. Vào tab **Database Access** (cột bên trái).
2. Nhấn **Add New Database User**.
3. Authentication Method: **Password**.
4. Nhập Username (VD: `admin`) và Password (lưu lại mật khẩu này).
5. Built-in Roles: Chọn `Atlas Admin` hoặc `Read and write to any database`.
6. Nhấn **Add User**.

## 3. Cấu hình Network Access

1. Vào tab **Network Access**.
2. Nhấn **Add IP Address**.
3. Chọn **Allow Access From Anywhere** (`0.0.0.0/0`) để đơn giản hóa việc kết nối từ Vercel và Máy cá nhân.
4. Nhấn **Confirm**.

## 4. Lấy Connection String

1. Vào tab **Database** -> Nhấn nút **Connect** ở Cluster của bạn.
2. Chọn **Drivers** (Python, Node.js, etc).
3. Copy chuỗi kết nối (Connection String).
   - Dạng: `mongodb+srv://admin:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
4. Thay thế `<password>` bằng mật khẩu bạn đã tạo ở bước 2.

## 5. Cập nhật vào dự án

1. Mở file `.env` trong thư mục gốc dự án.
2. Dán chuỗi kết nối vào biến `MONGODB_URI`.

```env
MONGODB_URI=mongodb+srv://admin:matkhau@cluster0.xxxxx.mongodb.net/home_security?retryWrites=true&w=majority
```
