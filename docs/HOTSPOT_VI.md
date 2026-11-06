# DataExodus Box: Wi‑Fi để thầy thử bằng điện thoại

Cập nhật 27/10/2026 (bản 0.5). Raspberry Pi 5 phát một mạng Wi‑Fi riêng tên **DataExodus-Box**. Thầy quét mã QR để vào mạng, điện thoại tự mở trang chào (captive portal, giống Wi‑Fi khách sạn), rồi thầy dùng ba chức năng:

| Chức năng | Thầy thấy gì |
| --- | --- |
| **Check a link** | Dán một link, hoặc cả tin nhắn lừa đảo có chứa link. Pi mở link trong Chromium cách ly, rồi trả về điểm 0–100 kèm từng lý do, chuỗi chuyển hướng, ảnh chụp, tracker và công ty, quốc gia của máy chủ. **Điện thoại không hề mở trang đó.** |
| **Safe Browse** | Dùng trang đáng ngờ bằng cách chạm vào ảnh của nó: cuộn, gõ chữ, quay lại. Trang chạy trên Pi, điện thoại chỉ nhận ảnh JPEG. |
| **My device** (chỉ khi thầy đồng ý) | Các app trên điện thoại liên lạc với công ty nào, máy chủ ở nước nào. Có công tắc chặn tracker riêng cho máy của thầy, và nút **Forget this device** để xoá hết. |

Kèm theo có **4 link mẫu** do chính Pi phục vụ, đều là site hư cấu và vô hại: một bài báo bình thường, một quảng cáo, một trang ngân hàng giả, một CAPTCHA giả. Nhờ vậy demo chạy được cả khi không có Internet, và không phải mở trang lừa đảo thật.

> **Trung thực khi báo cáo:** toàn bộ luồng của khách (cổng web, sandbox, Safe Browse, DNS watch với quyền đồng ý và chặn theo thiết bị, link mẫu) đã chạy thật trên Chromium, trên Windows, qua địa chỉ loopback: đạt 19/19 bước (`docs/evidence/box-v05-acceptance.json`, kèm ảnh trong `docs/evidence/box-v05/`). Trên **Pi 5 thật** (27/10/2026) đã kiểm chứng được: bộ cài, các dịch vụ, tường lửa, chấm điểm trong sandbox (điểm giống hệt trên Windows, 3,6–5,3 giây mỗi link) và Safe Browse (`docs/evidence/pi-hardware-verification.txt`). **Phần sóng Wi‑Fi, cổng web ở 10.42.0.1 và cửa sổ đăng nhập tự bật trên iPhone/Android thật thì chưa chạy**, vì lúc đó Pi chưa có dây mạng. Hãy làm mục 3 khi có dây mạng, rồi lưu kết quả làm bằng chứng.

## 0. Cần chuẩn bị gì

- Pi 5 đã cài theo `docs/RASPBERRY_PI_VI.md`, mục 1–5.
- **Một đường Internet cho Pi mà không phải Wi‑Fi**, vì Wi‑Fi của Pi sẽ thành điểm phát. Chọn một trong các cách:
  1. **Dây mạng cắm vào router.** Dễ nhất, dùng khi ở nhà.
  2. **Dây mạng nối với laptop Windows**, rồi chia sẻ Wi‑Fi của laptop qua cổng Ethernet: Control Panel → Network Connections → chuột phải vào Wi‑Fi → Properties → Sharing → tick *Allow other network users to connect…* → chọn cổng Ethernet. Pi sẽ nhận địa chỉ 192.168.137.x.
  3. **Điện thoại Android cắm USB vào Pi**, rồi bật Settings → Hotspot & tethering → *USB tethering*. Pi tự nhận mạng `usb0`.
  - **Không có Internet:** cổng web và 4 link mẫu vẫn chạy. Link thật, và mục "My device" với app thật, thì cần Internet.
- **Khi chạy lệnh bật Wi‑Fi, hãy SSH vào Pi qua dây mạng** (`ip -4 addr show eth0` cho biết IP của cổng dây), không qua Wi‑Fi. Lệnh sẽ chuyển `wlan0` sang chế độ phát nên kết nối Wi‑Fi cũ sẽ mất. Nếu phiên SSH của bạn đi qua `wlan0`, script sẽ báo trước rằng phiên sắp rớt, rồi tự chạy tiếp ở chế độ nền. Chờ khoảng 1 phút, kết nối lại (qua dây mạng, hoặc vào Wi‑Fi DataExodus rồi SSH tới `10.42.0.1`), và đọc log bằng `sudo tail -n 40 /var/log/dataexodus-hotspot.log`.

## 1. Bật Wi‑Fi DataExodus

Có ba chế độ:

| Lệnh (trong thư mục `~/DataExodus` trên Pi) | Tác dụng |
| --- | --- |
| `sudo bash pi/hotspot.sh --prepare` | Cài sẵn mọi thứ. Pi vẫn dùng Wi‑Fi hiện tại. |
| `sudo bash pi/hotspot.sh --on` | Chế độ demo: Wi‑Fi của Pi thành `DataExodus-Box`, ngay lập tức và sau mỗi lần khởi động. |
| `sudo bash pi/hotspot.sh --home` | Quay về Wi‑Fi nhà. Phần cài đặt được giữ lại cho lần `--on` sau. |

Nếu lệnh làm rớt phiên SSH của bạn (khi bạn đang SSH qua chính Wi‑Fi đó), script sẽ báo trước rồi **tự chạy tiếp ở chế độ nền**, log ghi vào `/var/log/dataexodus-hotspot.log`. Hướng dẫn từng bước cho buổi demo ở TAFE bằng 4G của điện thoại: `docs/TAFE_DEMO_VI.md`.

Cách làm một lần cho tất cả: chép bản mới nhất sang Pi (`docs/RASPBERRY_PI_VI.md`, mục 3), rồi trên Pi chạy:

```bash
cd ~/DataExodus
sudo bash pi/install.sh --hotspot
```

Nếu Pi đã cài sẵn từ trước, chỉ cần chạy lại lệnh trên: settings, token và dữ liệu được giữ nguyên. Cuối cùng script in ra:

```
The DataExodus Wi-Fi is on.
  Network:  DataExodus-Box
  Password: xxxx-xxxx-xxxx        (ngẫu nhiên, lưu trong /etc/dataexodus/dataexodus.env)
  Portal:   http://10.42.0.1  (or http://dataexodus.home.arpa)
Scan this with a phone camera to join:
█▀▀▀▀▀█ ...                       (mã QR ngay trong terminal)
```

Muốn tự đặt tên hoặc mật khẩu (mật khẩu ít nhất 8 ký tự):

```bash
sudo HOTSPOT_SSID="DataExodus-Demo" HOTSPOT_PSK="matkhau-cua-ban" bash pi/hotspot.sh
```

Các việc script đã làm:

- Tạo điểm phát WPA2 trên `wlan0`, địa chỉ `10.42.0.1/24`, bật **cách ly thiết bị** (điện thoại của thầy không nhìn thấy được laptop của bạn).
- NetworkManager cấp địa chỉ IP (DHCP). Phần DNS do **DNS watch** của DataExodus trả lời.
- Bật `dataexodus-portal` (cổng web ở `http://10.42.0.1`) và `dataexodus-samples` (link mẫu ở `127.0.0.49–58:8030`, chỉ sandbox mở được).
- Đặt `DNSWATCH_UPSTREAM=auto`, để DNS chạy được dù Pi đang ở nhà, ở TAFE hay qua điện thoại.

Tắt Wi‑Fi và trả `wlan0` về như cũ: `sudo bash pi/hotspot.sh --off`.

## 2. In thẻ QR cho thầy

Trên laptop, mở tunnel như mục 5 của `RASPBERRY_PI_VI.md`, rồi vào **http://127.0.0.1:8020/card** và bấm Ctrl+P. Thẻ có 2 mã QR: một mã để vào Wi‑Fi, một mã để mở cổng web. Kèm theo là 4 bước hướng dẫn bằng tiếng Anh.

Laptop cũng có thể vào Wi‑Fi DataExodus và SSH tới `10.42.0.1`:

```powershell
cd C:\DataExodus
powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost 10.42.0.1 -User student -CopyToken
```

## 3. Tự thử trước khi gặp thầy (checklist, nhớ chụp màn hình)

1. **Vào Wi‑Fi:** dùng điện thoại của bạn quét mã QR. Android sẽ hiện thông báo *Sign in to network*, iPhone tự bật một cửa sổ. Nếu không thấy gì, mở `http://10.42.0.1`.
2. **Trang chào:** để nguyên ô *Show my device's connections*, bấm **Join and continue**. Thấy dòng "You're online" là xong. Lúc này điện thoại coi mạng là có Internet.
3. **Check a link → Try a sample**, chạy lần lượt 4 mẫu. Kết quả đúng:

   | Mẫu | Kết quả mong đợi |
   | --- | --- |
   | Local news article | **Low risk**, 0 điểm |
   | Sponsored deal (an ad click) | **Be careful**, khoảng 35: quảng cáo, click-ID `gclid`, xin quyền thông báo, chuyển hướng qua site khác |
   | "Verify your account" text message | **Dangerous**, khoảng 60: form mật khẩu + thẻ gửi sang site khác, lời lẽ lừa đảo |
   | Fake "I'm not a robot" check | **Dangerous**, khoảng 85: ghi lệnh vào clipboard, ép tải `browser_update.exe` |

4. **Dán cả một tin nhắn**, ví dụ `KoalaBank: unusual sign-in. Verify: http://127.0.0.55:8030/s/kb7Q`. Pi tự lấy link trong tin nhắn ra để kiểm tra.
5. **Safe Browse:** trong kết quả của trang ngân hàng giả, bấm **Open in Safe Browse**. Chạm vào ô *Password* trong ảnh, gõ một chữ bất kỳ ở ô bên dưới, bấm **Type**, rồi bấm **Enter ↵**. Trang hiện *"The form was sent to another site"*: thứ bạn gõ đã bị gửi đi, nhưng là trên Pi chứ không phải trên điện thoại.
6. **My device:** mở vài app (YouTube, Facebook, một trang báo), rồi quay lại trang này. Bạn sẽ thấy tên miền, công ty và quốc gia. Tick **Block known trackers** → **Save**, mở lại app, sẽ thấy nhãn *blocked*.
7. **Forget this device:** dữ liệu của máy bị xoá, trang chào hiện lại.
8. **Link thật** (khi Pi có Internet): thử một link quảng cáo hoặc link bất kỳ. Kết quả có thêm tracker thật, công ty thật và quốc gia của máy chủ.

Kiểm chứng trên Pi (chạy rồi chụp màn hình):

```bash
nmcli -f NAME,DEVICE,TYPE connection show --active             # có DataExodus-AP trên wlan0
systemctl --no-pager status dataexodus-portal dataexodus-samples dataexodus-dnswatch
sudo ss -tlnp | grep -E ':(80|8030)\b'                         # 80 chỉ ở 10.42.0.1; 8030 chỉ ở 127.0.0.x
cat /var/lib/NetworkManager/dnsmasq-wlan0.leases               # các thiết bị đã vào Wi-Fi
sudo -u dataexodus curl -m 3 http://10.42.0.23/ ; echo "exit=$?"   # thay bằng IP một điện thoại: exit=28 (sandbox không chạm được tới điện thoại)
sudo nft list table inet dataexodus                            # có dòng 127.0.0.48/28 tcp dport 8030 accept
```

Từ laptop đang vào Wi‑Fi DataExodus: `nslookup connectivitycheck.gstatic.com 10.42.0.1` sẽ trả về `10.42.0.1`. Đây chính là cơ chế làm cửa sổ đăng nhập tự bật.

## 4. Kịch bản demo sản phẩm (khoảng 7 phút)

| Thời gian | Làm gì | Nói gì |
| --- | --- | --- |
| 0:00–0:45 | Đưa thầy thẻ QR. Thầy quét, trang chào tự mở. | "Đây là Wi‑Fi của một Raspberry Pi 5. Không có gì bị ghi lại nếu thầy không đồng ý; nếu đồng ý thì chỉ 24 giờ, và chỉ máy thầy xem được." |
| 0:45–2:30 | Check a link: mẫu ngân hàng giả, rồi CAPTCHA giả. | "Pi mở link trong một trình duyệt dùng một lần, không cookie, bị tường lửa chặn khỏi mạng nội bộ. Mỗi điểm số đều có lý do cụ thể, không có mô hình bí ẩn nào." |
| 2:30–3:30 | Thầy tự dán một link hoặc tin nhắn lừa đảo thật mà thầy từng nhận. | "Điện thoại của thầy không tải trang đó. Chỉ có Pi tải." |
| 3:30–4:45 | Safe Browse: chạm vào form của ngân hàng giả, gõ, Enter. | "Thầy dùng được trang lừa đảo mà không trang nào chạy trên máy thầy. Thứ bị gửi đi là trên Pi." |
| 4:45–6:00 | My device: thầy mở vài app, xem công ty và quốc gia, bật chặn. | "Hashing is not anonymisation: email đã băm vẫn là định danh. Ở đây ta thấy dữ liệu của app đi đâu, nhiều nơi ở ngoài Úc (APP 8). Quốc gia chỉ là ước tính." |
| 6:00–7:00 | Laptop: Guard giữ một cú nhấp quảng cáo → *Preview in isolated sandbox* → điểm số từ Pi. | "Cùng một sandbox, giờ dùng từ tiện ích trình duyệt trên laptop." |
| Cuối | Thầy bấm **Forget this device**, rồi quên mạng Wi‑Fi. | "Xoá ngay, không cần tin lời ai." |

## 5. Gỡ lỗi

| Triệu chứng | Cách xử lý |
| --- | --- |
| `the Pi reaches the internet through wlan0 itself` | Cắm dây mạng hoặc USB tethering trước, rồi chạy lại. Nếu chỉ demo offline: `sudo HOTSPOT_FORCE=1 bash pi/hotspot.sh`. |
| Không thấy mạng DataExodus-Box | `nmcli connection up DataExodus-AP`, `journalctl -u NetworkManager -n 50`, `rfkill list`. Kiểm tra quốc gia Wi‑Fi: `sudo raspi-config` → Localisation → WLAN Country → AU. |
| Báo *client isolation* rồi tự chạy lại không có nó | Driver Wi‑Fi không hỗ trợ cách ly thiết bị. Wi‑Fi vẫn chạy được, nhưng các thiết bị khách nhìn thấy nhau. Khi demo, đừng để laptop có thư mục chia sẻ. |
| Trang chào không tự bật | Mở `http://10.42.0.1`. Một số máy bỏ qua bước kiểm tra này: có VPN, Private DNS đặt tên riêng (Android), iCloud Private Relay. |
| My device không có dữ liệu | Thiết bị đang dùng DNS riêng: Android *Private DNS* (đặt về Automatic hoặc Off), VPN, hoặc *Secure DNS* của Chrome. Khi đó DNS watch không thấy gì; đây cũng là một giới hạn cần nói khi trình bày. |
| Link thật báo *could not open* | Pi không có Internet: kiểm tra `ip route` (cần dòng `default via … dev eth0` hoặc `usb0`). |
| *Safe Browse is busy* | Mỗi lần chỉ một người dùng Safe Browse (`SANDBOX_BROWSE_SESSIONS=1`). Phiên tự đóng sau 2 phút không chạm. Pi 5 8 GB có thể đặt thành 2 rồi `sudo systemctl restart dataexodus-guard`. |
| Cổng web không chạy | `journalctl -u dataexodus-portal -n 50`. Dịch vụ sẽ tự thử lại cho tới khi địa chỉ `10.42.0.1` xuất hiện. |
| DNS watch không chạy (cổng 53 bị chiếm) | `sudo ss -lunp 'sport = :53'`. Nếu là `systemd-resolved`: đặt `DNSStubListener=no` trong `/etc/systemd/resolved.conf`, rồi restart. |

## 6. Quyền riêng tư khi cho người khác dùng

- Không có gì được ghi nếu khách không tick *Show my device's connections*. Nếu tick, chỉ tên miền được tra cứu được ghi, giữ trong 24 giờ (`PORTAL_RETENTION_HOURS`), và mỗi thiết bị chỉ xem được dữ liệu của chính mình. **Forget this device** xoá ngay lập tức.
- Dashboard quản trị của bạn (`127.0.0.1:8020`) cũng **không** tính lượt tra cứu của khách: chỉ hiện số thiết bị đã vào mạng. Nói thật thêm một điều: người có quyền root trên Pi về kỹ thuật vẫn mở được file SQLite.
- Thiết bị được nhận ra bằng địa chỉ MAC trên mạng này. Phần lớn điện thoại dùng MAC ngẫu nhiên cho từng mạng. MAC vẫn là một mã định danh thiết bị: nó được lưu trên Pi và bị xoá khi khách bấm Forget.
- Về mặt kỹ thuật, Pi là router của mạng này, nên **có thể** thấy metadata của kết nối. DataExodus không ghi lại thứ đó và không giải mã HTTPS. Nếu thầy hỏi, hãy nói rõ như vậy.
- Chỉ cho người **được mời** dùng (thầy, bạn cùng lớp). Không mở Wi‑Fi này cho người lạ ở nơi công cộng.
- Link mẫu dùng thương hiệu hư cấu. Dữ liệu gửi vào form của ngân hàng giả bị bỏ đi, không lưu và không ghi log.

## 7. Giới hạn cần nói khi bảo vệ

- Điểm số dựa trên **một lần mở ẩn danh**. Trang lừa đảo có thể cho trình duyệt tự động xem một nội dung khác (cloaking). Điểm thấp không chứng minh link an toàn.
- Quy tắc chấm điểm là heuristic, công khai trên trang *How it works*. Chưa đo độ chính xác trên một bộ link lừa đảo thật có nhãn.
- Sandbox giảm rủi ro nhưng không phải máy ảo phân tích mã độc.
- DNS watch không thấy DoH/DoT/VPN, và chỉ đếm lượt tra cứu, không đếm lượt gửi dữ liệu.
- Cửa sổ đăng nhập tự bật đã được kiểm thử bằng Chromium trên Windows, chưa thử trên iPhone/Android thật cho đến khi bạn làm mục 3.
