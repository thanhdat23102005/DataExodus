# DataExodus Box: Raspberry Pi 5

Cập nhật 27/10/2026 (bản 0.5, tập trung vào sản phẩm). Raspberry Pi 5 trở thành một **thiết bị đo và bảo vệ riêng**. Laptop chỉ duyệt web; những việc rủi ro hoặc chạy lâu được giao cho Pi. Muốn cho thầy thử bằng điện thoại qua Wi‑Fi của Pi: cài theo tài liệu này đến hết mục 5, rồi làm tiếp [HOTSPOT_VI.md](HOTSPOT_VI.md).

| Vai trò của Pi | Làm gì | Vì sao có giá trị cho đồ án |
| --- | --- | --- |
| **Kiểm tra link + Safe Browse** (`dataexodus-guard`) | Mở link đáng ngờ trong Chromium headless **trên Pi**, chấm điểm 0–100 kèm lý do (form mật khẩu gửi sang site khác, ép tải file, ghi clipboard, xin quyền thông báo, tên miền giả thương hiệu, tracker, máy chủ ở nước ngoài…), chụp ảnh, trả link sạch. Safe Browse: dùng trang đó bằng cách chạm vào ảnh của nó. | Sandbox thật sự: một máy khác, một tài khoản riêng, bị tường lửa chặn truy cập mạng LAN. |
| **Wi‑Fi + cổng web cho khách** (`dataexodus-portal`, tuỳ chọn `--hotspot`) | Pi phát Wi‑Fi; điện thoại vào là trang chào tự mở: kiểm tra link, Safe Browse, "My device". | Thầy thử ngay bằng điện thoại của mình. Xem [HOTSPOT_VI.md](HOTSPOT_VI.md). |
| **DNS watch** (`dataexodus-dnswatch`) | Ghi lại tên miền mà thiết bị tra cứu (khách trên Wi‑Fi chỉ khi họ đồng ý), gắn nhãn tracker, công ty, quốc gia. Có chế độ chặn, kể cả chặn riêng từng thiết bị. | Đo được luồng dữ liệu của **mọi ứng dụng**, không chỉ trình duyệt. Góc nhìn APP 8. |
| **Nghiên cứu theo lịch** (`dataexodus-study.timer`, tuỳ chọn `--study`) | Mỗi Chủ nhật 03:00 crawl danh sách 50 site, tạo báo cáo và audit **so với tuần trước**. | Phần nghiên cứu cũ; không cần cho demo sản phẩm. |
| **Dashboard** (`dataexodus-box`) | Trạng thái dịch vụ, Wi‑Fi, DNS, **thẻ QR in ra cho thầy** (`/card`), dữ liệu tham chiếu, nhiệt độ CPU. | Dễ trình bày khi demo. |

Dịch vụ web quản trị trên Pi **chỉ nghe ở 127.0.0.1**. Laptop kết nối tới chúng qua **SSH tunnel**: có mã hoá, có xác thực, không mở thêm cổng nào ra mạng. Guard vẫn gọi `127.0.0.1:8010` như cũ. Chỉ hai dịch vụ nghe trên mạng: DNS watch (cổng 53, chỉ trả lời các dải mạng được phép) và cổng web cho khách (cổng 80 trên địa chỉ Wi‑Fi `10.42.0.1`, chỉ trả lời thiết bị trong Wi‑Fi đó, chỉ khi đã bật `--hotspot`).

> **Trung thực khi báo cáo:** các script cho Pi đã được kiểm thử tự động trên Windows: DNS watch chạy với socket thật, test unit file, kiểm tra cú pháp bash, thử các phép thay thế trong installer. Nhưng **chưa chạy trên một Raspberry Pi thật** trong môi trường phát triển. Hãy chạy các bước bên dưới trên Pi của bạn, rồi lưu kết quả phần "Kiểm chứng" làm bằng chứng.

## 1. Chuẩn bị

- Raspberry Pi 5 (4 GB là đủ, 8 GB thoải mái hơn), thẻ microSD 32 GB trở lên (SSD NVMe thì càng tốt), nguồn chính hãng 27 W, nên dùng dây mạng.
- Trên laptop Windows: [Raspberry Pi Imager](https://www.raspberrypi.com/software/) và OpenSSH Client (Windows 11 có sẵn; nếu thiếu thì vào Settings → System → Optional features).
- Thư mục dự án `E:\claude\DataExodus_Final`.

**Tạo SSH key trên laptop** (khuyên dùng thay cho mật khẩu). Chạy trong PowerShell:

```powershell
ssh-keygen -t ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

## 2. Cài Raspberry Pi OS

Trong Raspberry Pi Imager:

1. Device: **Raspberry Pi 5**. OS: **Raspberry Pi OS Lite (64-bit)**.
2. Mở phần tuỳ chỉnh (OS customisation):
   - Hostname: `dataexodus`
   - Username: ví dụ `student`, kèm mật khẩu
   - Wi-Fi: chỉ điền nếu không dùng dây mạng. Nếu định bật Wi‑Fi cho khách (HOTSPOT_VI.md), hãy dùng dây mạng: lúc đó Wi‑Fi của Pi sẽ thành điểm phát.
   - Locale: múi giờ `Australia/Sydney`
   - Tab Services: bật **SSH**, chọn *Allow public-key authentication only*, rồi dán nội dung `id_ed25519.pub` vừa in ra.
3. Ghi ra thẻ, cắm thẻ vào Pi và cấp nguồn. Chờ khoảng 1–2 phút.

Từ laptop:

```powershell
ssh student@dataexodus.local
```

Nếu `dataexodus.local` không phân giải được, xem IP của Pi trong trang quản trị router rồi dùng IP đó. Trên Pi:

```bash
sudo apt update && sudo apt full-upgrade -y
```

## 3. Chép dự án sang Pi

Cách gọn nhất là chép file zip, vì thư mục trên laptop có thể đã chứa `.venv` của Windows (nặng và vô dụng trên Pi). Chạy các lệnh dưới đây trong **PowerShell trên laptop** (dấu nhắc `PS C:\...>`), **không** chạy trong cửa sổ SSH của Pi (dấu nhắc `user@host:~ $`): đường dẫn `E:\...` chỉ có trên laptop. Thay `student@dataexodus.local` bằng tên đăng nhập và tên máy (hoặc IP) Pi của bạn, ví dụ `admin@Lab.local` hoặc `admin@192.168.0.83`; trên Pi, lệnh `hostname -I` in ra IP.

```powershell
scp E:\claude\DataExodus_Final.zip student@dataexodus.local:~/
ssh student@dataexodus.local "python3 -m zipfile -e DataExodus_Final.zip ."
# Dùng lại danh sách tham chiếu và file GeoLite2 đã tải trên laptop
# (không phải tải lại 100 MB, không cần nhập key MaxMind trên Pi):
scp -r E:\claude\DataExodus\data\blocklists student@dataexodus.local:~/DataExodus_Final/data/
```

(Nếu file zip được lưu ở chỗ khác, ví dụ thư mục Downloads, hãy sửa lại đường dẫn trong lệnh `scp` đầu tiên.)

Không chép `data/identities.local.yaml` có thông tin thật của bạn. Nếu cần một định danh thử cho nghiên cứu, hãy tạo file đó trên Pi với dữ liệu giả (xem mục 8).

## 4. Chạy installer

Trên Pi:

```bash
cd ~/DataExodus_Final
sudo bash pi/install.sh              # thêm --hotspot để bật luôn Wi-Fi cho khách, --study cho phần nghiên cứu
```

Mất khoảng 10–15 phút. Script làm các việc sau:

1. Cài `python3-venv`, `chromium`, `nftables`, `iw`.
2. Tạo tài khoản hệ thống `dataexodus` (không có shell đăng nhập).
3. Chép code vào `/opt/dataexodus`; dữ liệu nằm ở `/var/lib/dataexodus`.
4. Tạo file cài đặt `/etc/dataexodus/dataexodus.env`, chứa **token Guard mới** sinh ngẫu nhiên. File có quyền 640.
5. Nạp tường lửa nftables: tài khoản `dataexodus` được ra Internet nhưng **không được vào mạng LAN**, kể cả router và mọi điện thoại trên Wi‑Fi của Pi.
6. Tải EasyPrivacy, Tracker Radar và URLhaus (bỏ qua những file đã chép sang).
7. Bật các dịch vụ rồi tự kiểm tra. Timer nghiên cứu chỉ bật khi có `--study`; Wi‑Fi cho khách chỉ bật khi có `--hotspot` (chạy `pi/hotspot.sh`).

Kết quả mong đợi ở cuối:

```
Guard service:        ok
Dashboard:            ok
Firewall:             service account cannot reach 192.168.1.1 (as intended)
Internet:             ok
```

Sau đó **đăng xuất rồi SSH vào lại một lần**, để tài khoản của bạn đọc được token.

## 5. Kết nối laptop với Pi

Trên laptop, trong thư mục dự án:

```powershell
cd E:\claude\DataExodus_Final
powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost dataexodus.local -User student -CopyToken
```

- `-CopyToken` chép token vào clipboard. Mở Guard Settings → **Local service token**, dán vào, rồi **Save and apply rules**.
- **Để cửa sổ này mở** trong suốt thời gian dùng; Ctrl+C sẽ đóng tunnel.
- Nếu laptop đang chạy dịch vụ Guard cục bộ ở cổng 8010, hãy tắt nó trước. Script sẽ báo nếu cổng đang bận.

Dashboard: mở `http://127.0.0.1:8020` trên laptop.

### Thử sandbox trên Pi

1. Trong Guard Settings, bật **Route ad clicks…** và lưu.
2. Tìm kiếm trên Google hoặc Bing, rồi nhấn một **kết quả được tài trợ** (Sponsored).
3. Guard giữ cú nhấp lại trong trang **Quarantine**: trình duyệt của bạn chưa hề liên lạc với mạng quảng cáo.
4. Nhấn **Preview in isolated sandbox**. Pi mở link và trả về chuỗi chuyển hướng, tracker, ảnh chụp, cùng dòng *Opened on: dataexodus* (máy đã mở link).
5. Nhấn **Open clean destination** để mở trang của nhà quảng cáo mà không mang `gclid`/`utm_*`.

Lưu ý: phòng lab `examples.guard_lab` chạy trên **loopback của laptop** (127.0.0.x), nên sandbox trên Pi không thấy được nó; tường lửa của Pi cũng cố ý chặn. Để xem trước quảng cáo của lab, hãy đóng tunnel rồi chạy dịch vụ ngay trên laptop như trong `GUARD_QUICKSTART_VI.md`. Kịch bản acceptance tự làm việc này.

## 6. DNS watch: điện thoại của bạn gửi dữ liệu đi đâu

Chỉ làm với thiết bị **của bạn**: các lượt tra cứu DNS của người khác là thông tin cá nhân của họ.

1. Lấy IP của Pi bằng lệnh `hostname -I` (ví dụ `192.168.1.50`).
2. Trên điện thoại, đặt DNS của Wi-Fi về IP đó:
   - **Android:** Wi-Fi → mạng đang dùng → IP settings: *Static* → DNS 1 = IP của Pi. **Tắt Private DNS.**
   - **iPhone:** Wi-Fi → (i) → Configure DNS → Manual → chỉ giữ IP của Pi.
3. Dùng vài ứng dụng như bình thường trong khoảng 5 phút: tin tức, mua sắm, mạng xã hội.
4. Mở `http://127.0.0.1:8020/dns`. Trang hiển thị số lượt tra cứu, tỉ lệ tới tracker, công ty đứng sau, quốc gia của địa chỉ, và từng thiết bị.

Chế độ chặn: sửa `/etc/dataexodus/dataexodus.env` thành `DNSWATCH_MODE=block`, rồi chạy `sudo systemctl restart dataexodus-dnswatch`. Ở chế độ này, các tên miền nằm trong danh sách được trả về `0.0.0.0`. Danh sách gồm các rule EasyPrivacy chặn cả domain, URLhaus, và file của riêng bạn `/var/lib/dataexodus/data/blocklists/custom.txt` (mỗi dòng một domain). Nếu một ứng dụng bị hỏng, thêm domain đó vào `DNSWATCH_NEVER_BLOCK`.

Cần nói rõ khi trình bày:

- Một lượt tra cứu DNS cho biết thiết bị *sắp kết nối* tới đâu, **không** cho biết nó đã gửi gì.
- Quốc gia là ước tính GeoIP của địa chỉ trả lời, không phải nơi lưu trữ dữ liệu, và tự nó chưa chứng minh có vi phạm APP 8.
- Ứng dụng nào dùng DNS-over-HTTPS (Private DNS, hoặc DoH bật sẵn trong trình duyệt) sẽ không đi qua DNS watch.

## 7. Nghiên cứu theo lịch (tuỳ chọn)

Từ bản 0.5, phần này không bật mặc định. Muốn dùng: `sudo bash pi/install.sh --study` (hoặc `sudo systemctl enable --now dataexodus-study.timer`). Timer chạy mỗi Chủ nhật lúc 03:00 theo giờ của Pi. Pi tắt vào giờ đó thì lần chạy dời sang lần khởi động kế tiếp. Muốn chạy ngay:

```bash
sudo systemctl start dataexodus-study      # ~15–25 phút cho 50 site
journalctl -u dataexodus-study -f          # xem tiến độ
```

Kết quả nằm ở `/var/lib/dataexodus/runs/<giờ UTC>/` và được liệt kê trên dashboard, kèm link tới `audit.html` và `report.md`. Từ lần thứ hai trở đi, audit tự so sánh với lần chạy thành công trước đó. Nếu reference list hoặc protocol thay đổi giữa hai lần, kết quả so sánh sẽ ghi *inconclusive* thay vì báo "đã cải thiện". Pi giữ 8 lần chạy gần nhất (đổi bằng `STUDY_KEEP_RUNS`).

Danh sách 50 site là danh sách đã đóng băng của đề tài: không sửa giữa chừng nếu chưa ghi một protocol amendment.

## 8. Định danh thử cho nghiên cứu (tuỳ chọn)

Crawler không điền form, nên định danh chỉ có ích với site mà bạn **được phép** thử. Nếu cần, tạo file trên Pi bằng dữ liệu giả:

```bash
sudo -u dataexodus tee /var/lib/dataexodus/data/identities.local.yaml >/dev/null <<'EOF'
email: [student.demo@example.com]
phone: ["0491 570 006"]
EOF
```

(`example.com` là domain dành riêng theo RFC 2606; 0491 570 006 là số giả do ACMA dành riêng.)

## 9. Kiểm chứng: bằng chứng cho thầy

Chạy trên Pi, chụp màn hình kết quả:

```bash
systemctl --no-pager status dataexodus-guard dataexodus-box dataexodus-dnswatch
sudo ss -tulpn | grep -E ':(22|53|80|8010|8020|8030)\b'   # 8010/8020 chỉ ở 127.0.0.1; 80 chỉ ở 10.42.0.1; 8030 ở 127.0.0.49-58
sudo nft list table inet dataexodus               # rule tường lửa và counter
sudo -u dataexodus curl -m 3 http://$(ip -4 route show default | awk '{print $3}')/ ; echo "exit=$?"   # exit=28: bị chặn
sudo -u dataexodus curl -s -o /dev/null -w '%{http_code}\n' https://example.com/           # 200: Internet vẫn được
systemd-analyze security dataexodus-guard dataexodus-dnswatch dataexodus-box | tail -n 5
```

Trên laptop, có thể đo thêm độ trễ của sandbox: chạy một lần preview và ghi lại thời gian từ lúc nhấn đến lúc có ảnh chụp.

## 10. Gỡ lỗi

| Triệu chứng | Cách xử lý |
| --- | --- |
| `connect-pi.ps1`: không đọc được token | Đăng xuất, SSH vào Pi lại một lần. Hoặc chạy `sudo grep TOKEN /etc/dataexodus/dataexodus.env` trên Pi. |
| Preview báo *Sandbox browser failed to start* | `journalctl -u dataexodus-guard -n 50`. Nếu lỗi liên quan đến sandbox của Chromium, đặt `DATAEXODUS_CHROMIUM_SANDBOX=0` trong file env rồi `sudo systemctl restart dataexodus-guard`. Tường lửa vẫn giữ tài khoản này ngoài mạng LAN. |
| Preview báo *Only public http(s) URLs…* với quảng cáo thật | DNS của router hoặc nhà mạng đang trả domain quảng cáo về một địa chỉ nội bộ (ví dụ 10.10.10.1). Sandbox từ chối là đúng. Muốn xem trước, cho Pi dùng DNS công cộng: `sudo nmcli con mod "<tên kết nối>" ipv4.dns 1.1.1.1 ipv4.ignore-auto-dns yes`, sau đó khởi động lại kết nối. |
| DNS watch không chạy | Có chương trình khác đang chiếm cổng 53: `sudo ss -lunp 'sport = :53'`. |
| Điện thoại không ra mạng khi trỏ DNS về Pi | IP của điện thoại phải nằm trong `DNSWATCH_ALLOW`. Kiểm tra `journalctl -u dataexodus-dnswatch`. |
| Dashboard chỉ báo "Guard: token mismatch" | Token trong file env đã đổi mà chưa restart: `sudo systemctl restart dataexodus-guard dataexodus-box`. |
| Muốn đổi nhà cung cấp DNS phía trên | Sửa `DNSWATCH_UPSTREAM` (mặc định `auto`: DNS của mạng mà Pi đang dùng, đọc từ `/etc/resolv.conf`, nếu không có thì 1.1.1.1), rồi restart `dataexodus-dnswatch`. |

## 11. Cập nhật và gỡ cài đặt

Cập nhật: chép thư mục dự án mới sang Pi, rồi chạy lại `sudo bash pi/install.sh`. File cài đặt, token, dữ liệu và các lần chạy được giữ nguyên.

Gỡ cài đặt:

```bash
sudo bash pi/hotspot.sh --off      # nếu đã bật Wi-Fi cho khách
sudo systemctl disable --now dataexodus-guard dataexodus-box dataexodus-dnswatch dataexodus-study.timer dataexodus-firewall
sudo rm /etc/systemd/system/dataexodus-*.service /etc/systemd/system/dataexodus-study.timer
sudo systemctl daemon-reload
sudo rm -rf /opt/dataexodus /etc/dataexodus      # thêm /var/lib/dataexodus nếu muốn xoá cả dữ liệu
sudo userdel dataexodus
```

## 12. Giới hạn cần nói khi bảo vệ

- Sandbox chỉ cho biết trang **đã làm gì trong một lần mở ẩn danh**. Kết quả "sạch" không chứng minh trang an toàn; trang có thể cư xử khác với trình duyệt có đăng nhập.
- Lớp chặn SSRF trong ứng dụng kiểm tra địa chỉ trước mỗi request. Tường lửa nftables là lớp thứ hai, phòng trường hợp DNS rebinding. Cả hai đều không thay thế được một VM riêng cho mã độc thật.
- DNS watch không thấy nội dung, không thấy truy vấn DoH/DoT, và đếm lượt tra cứu chứ không đếm lượt truyền dữ liệu.
- Chưa có thử nghiệm với người dùng khác ngoài dự án, chưa đo hiệu năng trên phần cứng thật, và không có cam kết bảo vệ 100%.
