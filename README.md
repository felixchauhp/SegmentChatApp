_Dự án được phát triển bằng ngôn ngữ Python 3, sử dụng các thư viện tiêu chuẩn như socket,
threading, tkinter, và Flask để xây dựng giao diện người dùng và API. Kiến trúc hệ thống
bao gồm các thành phần chính: tracker server, peer client, API REST, và các module hỗ trợ như
đồng bộ, ghi log, và quản lý kết nối P2P._

**HƯỚNG DẪN SỬ DỤNG**
_**1. Yêu cầu môi trường**_
Trước khi sử dụng hệ thống Segment Chat, người dùng cần đảm bảo môi trường máy tính
đã được cấu hình như sau:
• Hệ điều hành: Windows / Linux / macOS
• Python: Phiên bản 3.10 trở lên
• Thư viện cần cài đặt:
    – Flask
    – tkinter (có sẵn với Python trên Windows, cần cài thêm trên Linux)
• Cài đặt thư viện:
    pip install flask
_**2 Khởi động hệ thống**_
_Bước 1: Khởi động tracker server_
  Mở một terminal và chạy lệnh sau trong thư mục chứa mã nguồn:
    python server.py
  Lệnh này sẽ khởi tạo:
    • Một server TCP (port 5000) tiếp nhận kết nối từ peer.
    • Một API server (Flask, chạy trên port 5001) cung cấp REST API.
_Bước 2: Khởi động peer client_
  Mỗi peer là một tiến trình riêng. Mở một terminal mới và chạy:
    python client.py
  Sau khi giao diện xuất hiện, người dùng có thể:
    • Nhập tên và chọn “Login as User” để đăng nhập.
    • Bỏ trống tên và chọn “Join as Visitor” để vào chế độ khách.
_Bước 3: Kết nối nhiều peer_
  Để kiểm thử P2P, mở nhiều terminal và chạy nhiều phiên bản client.py đồng thời. Mỗi
peer sẽ:
    • Tự động gửi thông tin lên server.
    • Nhận danh sách peer và thiết lập kết nối P2P.
