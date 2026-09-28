# TVC Downloader

Giao diện web tiếng Việt cho điện thoại và PC, chạy tải video trên Ubuntu. Hỗ trợ URL Douyin, TikTok, Facebook, YouTube. F2 dùng cho video lẻ và kênh Douyin, kênh TikTok; yt-dlp dùng cho video lẻ TikTok và Facebook/YouTube. Danh sách xem trước lấy từ yt-dlp, tùy nền tảng và cookie có thể không quét được. Không có trình duyệt đăng nhập tích hợp.

Bản 0.5.2: các ô Hoạt động mở hàng đợi theo trạng thái; ô URL có mẫu link kênh và tự tách URL từ đoạn chia sẻ Douyin; video lẻ Douyin tải bằng F2. Nếu một tác vụ cũ đã báo lỗi, thêm lại link video để tạo tác vụ mới. Nếu F2 vẫn báo lỗi xác thực, xem thông báo ở **Cần kiểm tra** và thiết lập cookie Douyin trên Ubuntu.

Bản 0.5.3: quét tab Reels Facebook theo link dạng `https://www.facebook.com/profile.php?id=61589782348979&sk=reels_tab` hoặc `https://www.facebook.com/TenTrang/reels/`. Trình quét Chrome chạy ẩn trong container, đọc cookie Netscape từ `data/cookies/facebook.txt`, cuộn trang và đưa các link Reel tìm thấy vào bộ tải yt-dlp. Với Reels Facebook, cần cookie còn hạn để thấy các trang tiếp theo. Không gửi cookie vào chat/GitHub; chỉ chép vào Ubuntu. Việc cuộn có thể mất vài phút, tối đa 2.000 Reel cho một lượt **Tải cả kênh**; nếu Trang giới hạn nội dung, danh sách có thể không đầy đủ. Chrome làm bản Docker đầu tiên của phiên bản này lớn hơn.

Bản 0.5.4: giao diện co giãn cho PC/điện thoại; kết quả quét có số thứ tự, ảnh thu nhỏ khi nguồn cung cấp và Chọn tất cả. Trình xem thử phát ngay sau khi bấm Xem nếu trình duyệt cho phép. Hàng đợi hiển thị số thứ tự, ngày giờ hoàn tất và file của từng tác vụ kèm Xem/Tải về; file cũ chưa gắn tác vụ cũng nằm ở cuối Hàng đợi. Nút Chọn tất cả ở Hàng đợi cho phép tải nhiều file về thiết bị (trình duyệt có thể hỏi quyền tải nhiều file). Trình quét Reels Facebook lấy ảnh từ lưới Reels khi trang trả ảnh.

Bản 0.5.5: khi dán link Facebook `/share/r/…` hoặc `/share/v/…`, bấm **Giải mã link Facebook** để xem link gốc; nút **+ Thêm URL tải** tự giải mã trước khi xếp hàng. Tác vụ cũ mang link chia sẻ cũng tự giải mã lúc chạy. Nếu yt-dlp báo lỗi với Reel đã giải mã và có cookie Facebook, ứng dụng thử lại một lần bằng chế độ giả lập Chrome. Bản này cài thêm phần hỗ trợ `curl-cffi` cho yt-dlp. Facebook có thể vẫn hạn chế Reel cụ thể, kể cả khi link gốc và cookie hợp lệ; lỗi cuối cùng hiện trong Hàng đợi.

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

1. Bấm mẫu link Douyin/TikTok/Facebook để điền đầu link kênh, thêm tên/ID, rồi bấm **Quét kênh** để xem tối đa 30–200 video. Hoặc bấm **Tải cả kênh**. Với Facebook, dùng URL tab Reels của Trang; link `/share/r/…` là một video: bấm **Giải mã link Facebook** hoặc **+ Thêm URL tải**. Có thể dán nguyên đoạn chia sẻ Douyin: ứng dụng tự tách link. Quét Douyin vẫn phụ thuộc khả năng yt-dlp và cookie; nếu không quét được, dùng **Tải cả kênh** với F2.
2. Với URL video riêng, bấm **+ Thêm URL tải**.
3. Đặt **Thư mục lưu** trước khi thêm tác vụ. File ở `data/downloads/<Nền tảng>/<Thư mục>` trên Ubuntu. Mỗi kênh nên đặt tên thư mục riêng.
4. Hàng đợi vẫn chạy khi đóng trang; khởi động lại container thì tác vụ đang chạy được xếp lại. Các tác vụ hoàn tất lưu dấu qua `data/archive.txt` đối với yt-dlp. F2 quản lý file trùng theo cơ chế riêng của F2.
5. **Tạm dừng** tác vụ đang tải sẽ ngắt tiến trình. **Tiếp tục** sẽ gọi lại bộ tải; yt-dlp dùng file `.part` để tiếp tục khi nguồn hỗ trợ. F2 có thể phải kiểm tra lại danh sách của kênh.
6. Bấm số **Đang chờ**, **Đang tải**, **Hoàn tất** hoặc **Cần kiểm tra** để mở danh sách tác vụ tương ứng. Bấm **Xem tất cả** để bỏ lọc.

Kiểm tra: `sudo docker compose logs -f --tail=80`. Cập nhật yt-dlp/F2: `sudo docker compose build --pull --no-cache && sudo docker compose up -d`. Sao lưu cả thư mục `data` để giữ video, hàng đợi và dấu chống trùng.

## Lưu ý

- Một số kênh Douyin/TikTok yêu cầu cookie đăng nhập. Nếu TikTok/Douyin yêu cầu xác thực, đặt cookie dạng Netscape tại `data/cookies/tiktok.txt` hoặc `data/cookies/douyin.txt`. Ứng dụng tự đưa file đó vào yt-dlp khi quét/tải, và chuyển cookie tương ứng cho F2 khi tải kênh. Cookie là phiên đăng nhập: không gửi trong chat, không đưa lên GitHub, chỉ dùng trên máy chủ tin cậy. Xuất cookie bằng yt-dlp trên PC đã đăng nhập (xem phần dưới).
- Để quét toàn bộ Reels Facebook, xuất cookie Netscape từ trình duyệt PC đã đăng nhập Facebook rồi chép thành `~/TVC-Studio/data/cookies/facebook.txt`. Có thể dùng `yt-dlp --cookies-from-browser chrome --cookies facebook.txt` trên PC, sau đó dùng `scp` chuyển file vào Ubuntu; `chmod 600` file ở Ubuntu. Không cần đưa mật khẩu Facebook vào TVC. Cookie hết hạn thì xuất lại. Link Trang riêng tư chỉ hiển thị nội dung mà tài khoản cookie được phép xem.
- Các trang thay đổi thường xuyên; lỗi quét/tải do xác thực hay hạn chế nền tảng hiện ở hàng đợi. Không có bảo đảm quét hết video nếu nền tảng giới hạn phân trang.
- Chỉ tải nội dung bạn có quyền lưu và sử dụng.

## Xem và tải về PC/điện thoại

Ở danh sách quét kênh, bấm **Xem** để xem thử video hoặc ảnh khi nền tảng cung cấp đường dẫn phát trực tiếp. Trình xem tự phát nếu trình duyệt cho phép; nếu bị chặn sẽ thử phát tắt tiếng, hoặc bạn bấm ▶. Video xem trước ưu tiên MP4 khoảng 720p; nguồn có thể hết hạn hoặc không cho phát từ trình duyệt.

Trong **Hàng đợi**, mỗi tác vụ hoàn tất có file và nút **Xem**/**Tải về**. File tải từ phiên bản cũ nằm cùng trang dưới nhãn “File đã tải trước bản này”. Ngày giờ trên file lấy từ thời điểm file được lưu, theo múi giờ của thiết bị đang xem. Nơi lưu bản sao do trình duyệt và cài đặt thiết bị quyết định (trên iPhone thường là ứng dụng Tệp/Downloads). File gốc vẫn nằm ở `data/downloads/` trên Ubuntu. MP4/MOV/JPG/PNG/WEBP thường xem được; MKV hoặc codec lạ có thể cần tải về rồi mở bằng ứng dụng phù hợp.

## Khi TikTok báo cần đăng nhập

Trên PC đã đăng nhập TikTok bằng Chrome, có thể cài yt-dlp và chạy `yt-dlp --cookies-from-browser chrome --cookies tiktok.txt` để xuất cookie theo định dạng Netscape. Nếu dùng Edge, thay `chrome` bằng `edge`. Chuyển file sang Ubuntu (thay IP nếu máy thay đổi):

```bash
mkdir -p ~/TVC-Studio/data/cookies
# Chạy trên PC với scp: scp tiktok.txt cuong@192.168.1.13:~/TVC-Studio/data/cookies/tiktok.txt
chmod 600 ~/TVC-Studio/data/cookies/tiktok.txt
```

File phải bắt đầu `# Netscape HTTP Cookie File` hoặc `# HTTP Cookie File`. Không cần rebuild khi thay cookie; quét lại link trên web. Nếu vẫn bị chặn, phiên cookie có thể hết hạn hoặc nền tảng hạn chế chính video đó. Không dán nội dung cookie vào GitHub/chat.
