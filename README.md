# TVC Downloader

Giao diện web tiếng Việt cho điện thoại và PC, chạy tải video trên Ubuntu. Hỗ trợ URL Douyin, TikTok, Facebook, YouTube. F2 dùng cho tải cả kênh Douyin/TikTok; yt-dlp dùng cho link lẻ và kênh Facebook/YouTube. Danh sách xem trước lấy từ yt-dlp, tùy nền tảng và cookie có thể không quét được. Không có trình duyệt đăng nhập tích hợp.

## Cài trên Ubuntu

Cần Docker Engine và Docker Compose plugin. Giải nén, vào thư mục `tvc-downloader`, rồi:

```bash
cp .env.example .env
nano .env                     # đổi TVC_PASSWORD thành mật khẩu dài, riêng
mkdir -p data
sudo docker compose up -d --build
```

Mở `http://IP-MAY-CHU:8080` nếu bạn đổi dòng ports trong `compose.yaml` thành `8080:8080` để dùng trong mạng LAN. Mặc định ứng dụng chỉ nghe `127.0.0.1:8080` trên máy chủ để tránh lộ ra Internet. Để truy cập từ xa, đặt sau HTTPS reverse proxy hoặc VPN và giữ Basic Auth. Ví dụ với Caddy đã có trên máy: cấu hình tên miền riêng trỏ về `127.0.0.1:8080`, kiểm tra cổng Caddy thực tế và chứng chỉ trước khi dùng. Không trỏ công khai cổng 8080 dạng HTTP.

Nếu muốn xem qua SSH từ PC: `ssh -L 8080:127.0.0.1:8080 user@IP-MAY-CHU`, rồi vào `http://localhost:8080`.

## Đưa dự án lên GitHub và cập nhật bằng Git

Đặt thư mục `tvc-downloader` thành một repo GitHub riêng (ưu tiên **private** nếu sau này thêm cấu hình riêng). `data/`, `.env` và `.updates/` đã nằm trong `.gitignore`; đừng ép đưa chúng lên Git. Có thể tạo repo trống trên GitHub rồi chạy trên máy chứa mã nguồn:

```bash
git init
git add .
git commit -m "Initial TVC Downloader"
git branch -M main
git remote add origin GIT_URL_CUA_BAN
git push -u origin main
```

Trên Ubuntu, cài từ repo bằng `git clone GIT_URL_CUA_BAN`, `cd tvc-downloader`, `cp .env.example .env`, sửa mật khẩu rồi `docker compose up -d --build`. Mỗi khi GitHub có bản mới, trong thư mục đó chạy:

```bash
./update-git.sh
```

Script dùng `git pull --ff-only`, gọi `sudo docker compose` để build lại container và giữ nguyên `data/`, `.env`. Nếu build lỗi, nó trả mã nguồn về commit trước. Nó từ chối cập nhật khi mã nguồn trên Ubuntu đã sửa để không ghi đè thay đổi của bồ. Không chạy `git add -f data/` hay đưa `.env` lên GitHub.

## Cập nhật bằng ZIP mà không mất video

Khi có bản cập nhật, tải **gói ZIP mới** (chỉ khoảng vài chục KB mã nguồn), chép vào Ubuntu rồi chạy trong thư mục dự án:

```bash
./update.sh /đường/dẫn/TVC_Downloader_Ubuntu_Web.zip
```

Script kiểm tra gói, sao lưu mã nguồn cũ trong `.updates/`, thay mã, chạy `docker compose up -d --build`. Docker dùng cache cho những lớp không thay đổi; `data/` và `.env` không bị xóa hoặc ghi đè. Nếu build không thành công, script tự phục hồi mã nguồn cũ. Video và hàng đợi vẫn lưu nguyên; tác vụ đang tải được xếp lại khi ứng dụng khởi động. Không dùng `docker compose down -v` vì lệnh đó xóa volume do Docker quản lý.

## Dùng

1. Dán URL kênh, bấm **Quét kênh** để xem tối đa 30–200 video và chọn video tải. Hoặc bấm **Tải cả kênh** để tải toàn bộ theo bộ tải tương ứng.
2. Với URL video riêng, bấm **+ Thêm URL tải**.
3. Đặt **Thư mục lưu** trước khi thêm tác vụ. File ở `data/downloads/<Nền tảng>/<Thư mục>` trên Ubuntu. Mỗi kênh nên đặt tên thư mục riêng.
4. Hàng đợi vẫn chạy khi đóng trang; khởi động lại container thì tác vụ đang chạy được xếp lại. Các tác vụ hoàn tất lưu dấu qua `data/archive.txt` đối với yt-dlp. F2 quản lý file trùng theo cơ chế riêng của F2.
5. **Tạm dừng** tác vụ đang tải sẽ ngắt tiến trình. **Tiếp tục** sẽ gọi lại bộ tải; yt-dlp dùng file `.part` để tiếp tục khi nguồn hỗ trợ. F2 có thể phải kiểm tra lại danh sách của kênh.

Kiểm tra: `sudo docker compose logs -f --tail=80`. Cập nhật yt-dlp/F2: `sudo docker compose build --pull --no-cache && sudo docker compose up -d`. Sao lưu cả thư mục `data` để giữ video, hàng đợi và dấu chống trùng.

## Lưu ý

- Một số kênh Douyin/TikTok yêu cầu cookie đăng nhập. Nếu TikTok/Douyin yêu cầu xác thực, đặt cookie dạng Netscape tại `data/cookies/tiktok.txt` hoặc `data/cookies/douyin.txt`. Ứng dụng tự đưa file đó vào yt-dlp khi quét/tải, và chuyển cookie tương ứng cho F2 khi tải kênh. Cookie là phiên đăng nhập: không gửi trong chat, không đưa lên GitHub, chỉ dùng trên máy chủ tin cậy. Xuất cookie bằng yt-dlp trên PC đã đăng nhập (xem phần dưới).
- Các trang thay đổi thường xuyên; lỗi quét/tải do xác thực hay hạn chế nền tảng hiện ở hàng đợi. Không có bảo đảm quét hết video nếu nền tảng giới hạn phân trang.
- Chỉ tải nội dung bạn có quyền lưu và sử dụng.

## Khi TikTok báo cần đăng nhập

Trên PC đã đăng nhập TikTok bằng Chrome, có thể cài yt-dlp và chạy `yt-dlp --cookies-from-browser chrome --cookies tiktok.txt` để xuất cookie theo định dạng Netscape. Nếu dùng Edge, thay `chrome` bằng `edge`. Chuyển file sang Ubuntu (thay IP nếu máy thay đổi):

```bash
mkdir -p ~/TVC-Studio/data/cookies
# Chạy trên PC với scp: scp tiktok.txt cuong@192.168.1.13:~/TVC-Studio/data/cookies/tiktok.txt
chmod 600 ~/TVC-Studio/data/cookies/tiktok.txt
```

File phải bắt đầu `# Netscape HTTP Cookie File` hoặc `# HTTP Cookie File`. Không cần rebuild khi thay cookie; quét lại link trên web. Nếu vẫn bị chặn, phiên cookie có thể hết hạn hoặc nền tảng hạn chế chính video đó. Không dán nội dung cookie vào GitHub/chat.
