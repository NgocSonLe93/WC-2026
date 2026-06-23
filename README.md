# World Cup 2026 Dashboard — NGOC SON LE

Website tĩnh tối ưu cho điện thoại, gồm:

- Kết quả và lịch thi đấu theo từng ngày.
- Bảng xếp hạng 12 bảng A–L.
- Bảng chung các đội đứng thứ ba: **STT – đội/bảng – điểm – hệ số**.
- Quy tắc sắp xếp theo yêu cầu: **điểm → hiệu số → tên đội A–Z**.
- Thống kê tổng bàn, trung bình bàn/trận, tỷ trọng bàn thắng theo ngày và biểu đồ.
- Dữ liệu được GitHub Actions cập nhật mỗi ngày vào khoảng **12:00 trưa Việt Nam**.
- Nút cập nhật trên web chỉ đọc lại file dữ liệu cùng website, không gọi API trực tiếp từ iPhone.

## Cách đưa web lên GitHub Pages

1. Tạo repository mới, ví dụ `world-cup-2026` và chọn **Public**.
2. Giải nén gói ZIP này.
3. Trong repository, chọn **Add file → Upload files** rồi tải lên toàn bộ nội dung đã giải nén, gồm cả thư mục `.github`, `data`, `scripts`.
4. Bấm **Commit changes** vào nhánh `main`.
5. Vào **Settings → Pages**.
6. Ở **Build and deployment → Source**, chọn **GitHub Actions**.
7. Vào tab **Actions**, mở workflow **Cập nhật & triển khai World Cup 2026**. Nếu workflow chưa tự chạy, bấm **Run workflow**.
8. Chờ dấu tích xanh. Đường link online thường có dạng:

   `https://TEN-TAI-KHOAN.github.io/world-cup-2026/`

## Mở trên iPhone

Mở đường link GitHub Pages bằng Safari. Có thể bấm **Chia sẻ → Thêm vào Màn hình chính** để dùng như một ứng dụng.

## Nguồn dữ liệu

Workflow ưu tiên API mở `worldcup26.ir`; nếu nguồn này lỗi, hệ thống dùng dữ liệu công khai từ `openfootball/worldcup.json`. Khi cả hai nguồn lỗi, file dữ liệu hiện có được giữ nguyên.

## API token tùy chọn

Nếu nguồn chính yêu cầu token, tạo secret tại **Settings → Secrets and variables → Actions → New repository secret** với tên `WORLD_CUP_API_TOKEN`. Không đưa token vào `index.html`.

## Bản quyền

**COPYRIGHT © 2026: NGOC SON LE**
