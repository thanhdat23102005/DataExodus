# Demo ở TAFE bằng dữ liệu di động của điện thoại

```
điện thoại của bạn (4G/5G) ──cáp USB──> Raspberry Pi 5 ──Wi‑Fi "DataExodus-Box"──> điện thoại của thầy, laptop của bạn
```

Pi lấy Internet từ điện thoại qua cáp USB (USB tethering), rồi phát Wi‑Fi `DataExodus-Box`. Pi không cần mạng của TAFE, cũng không cần ổ cắm mạng.

## Mang theo

- Pi 5 và **nguồn chính hãng 27 W (USB‑C)**, cắm vào ổ điện. Không dùng sạc điện thoại hay pin dự phòng yếu, vì Pi sẽ thiếu điện.
- **Cáp USB có truyền dữ liệu**, một đầu USB‑A (cắm vào Pi), đầu kia vừa với điện thoại. Nhớ thử cáp ở nhà trước.
- Điện thoại có 4G/5G, pin đầy, còn ít nhất 1 GB data.
- Thẻ QR đã in: mở `reports/wifi-card.html` trên laptop rồi bấm Ctrl+P.
- Laptop và sạc laptop (để demo phần Guard).
- **Phương án dự phòng** nếu Pi trục trặc: trên laptop chạy `python -m examples.run_box_acceptance --out reports\box-run --headed`. Lệnh này chạy toàn bộ luồng của thầy ngay trên laptop.

## Trước buổi demo (ở nhà, làm một lần)

Pi đã được chuẩn bị sẵn (`--prepare`): mạng Wi‑Fi, cổng web và link mẫu đều đã cài, nhưng Pi vẫn đang dùng Wi‑Fi nhà.

1. Nếu muốn chạy thêm nghiên cứu 50 site, hãy chạy **trước bước 2**, vì lúc đó Pi còn dùng Internet nhà:
   ```bash
   sudo systemctl start dataexodus-study
   ```
2. **Bật chế độ demo.** Gõ trong cửa sổ `admin@Lab`:
   ```bash
   cd ~/DataExodus_Final && sudo bash pi/hotspot.sh --on
   ```
   Script báo phiên SSH sắp rớt và đếm 10 giây; điều này là bình thường. Từ lúc này, mỗi lần bật nguồn, Pi đều tự phát `DataExodus-Box`. Nếu muốn, bạn nhắn tôi làm bước này.
3. **Tập thử ở nhà, làm y hệt các bước ở TAFE bên dưới.** Dùng laptop hoặc một điện thoại thứ hai để vào Wi‑Fi `DataExodus-Box`, không dùng chiếc điện thoại đang chia sẻ mạng.

## Ở TAFE (khoảng 5 phút trước giờ trình bày)

1. **Cắm nguồn Pi.** Chờ khoảng 1 phút cho tới khi mạng `DataExodus-Box` hiện trong danh sách Wi‑Fi của laptop.
2. **Trên điện thoại của bạn:** **tắt Wi‑Fi** để chắc chắn điện thoại dùng 4G/5G chứ không bắt Wi‑Fi của trường, và **bật dữ liệu di động**.
3. **Cắm cáp** từ điện thoại vào cổng USB‑A của Pi, rồi bật chia sẻ mạng:
   - **Android:** Cài đặt → Kết nối → Điểm truy cập di động và Chia sẻ kết nối → **Chia sẻ kết nối qua USB**. Trên Pixel: Network & internet → Hotspot & tethering → USB tethering.
   - **iPhone:** Cài đặt → Điểm truy cập cá nhân → bật **Cho phép người khác kết nối**, rồi bấm **Tin cậy** khi cắm cáp. Pi đã cài sẵn gói cần cho iPhone.
4. **Kiểm tra bằng laptop:**
   1. Vào Wi‑Fi `DataExodus-Box`. Trang chào sẽ tự mở; nếu không, mở `http://10.42.0.1`.
   2. Bấm **Join and continue**.
   3. Vào **Check a link** và thử một link mẫu.
   4. Thử thêm một link thật, ví dụ `https://www.abc.net.au`. Link thật chạy được nghĩa là Internet qua điện thoại đã thông.
5. **Phần Guard trên laptop.** Laptop vẫn ở Wi‑Fi `DataExodus-Box`. Mở PowerShell rồi chạy:
   ```powershell
   cd E:\claude\DataExodus_Final
   powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost 10.42.0.1 -User admin -CopyToken
   ```
   Lệnh sẽ hỏi mật khẩu `admin` của Pi. Để cửa sổ này mở trong suốt buổi demo.
6. **Đưa thẻ QR cho thầy.** Kịch bản 7 phút nằm ở `docs/HOTSPOT_VI.md`, mục 4.

## Khi có trục trặc

Từ laptop đang ở Wi‑Fi `DataExodus-Box`, chạy `ssh admin@10.42.0.1`, rồi:

```bash
nmcli device                      # wlan0: DataExodus-AP; usb0 (hoặc enx...): connected = có Internet từ điện thoại
ip -4 route show default          # dòng đầu phải có dev usb0
systemctl is-active dataexodus-portal dataexodus-dnswatch dataexodus-guard
```

| Triệu chứng | Cách xử lý |
| --- | --- |
| Sau 2 phút vẫn không thấy `DataExodus-Box` | Pi chưa được bật chế độ demo (bước `--on`), hoặc thiếu nguồn. Thử cắm lại nguồn; nếu vẫn không được thì dùng phương án dự phòng trên laptop. |
| Vào được Wi‑Fi nhưng link thật báo không mở được | USB tethering chưa bật, hoặc cáp chỉ để sạc. Lệnh `nmcli device` phải thấy `usb0` ở trạng thái connected. Thử tắt rồi bật lại USB tethering. |
| Điện thoại thầy báo "không có Internet" | Thầy cần bấm **Join and continue** trước. Nếu vẫn báo vậy, kiểm tra USB tethering như dòng trên. |
| Trang chào không tự bật | Mở `http://10.42.0.1`. Điện thoại có VPN hoặc Private DNS sẽ không tự bật trang này. |
| Không có sóng 4G trong phòng | Cổng web và 4 link mẫu vẫn chạy offline, kể cả Safe Browse trên link mẫu. Link thật và mục My device với app thật thì cần Internet. |
| Điện thoại nóng hoặc tụt pin | Pi có cấp điện qua cáp USB nhưng ít. Nên sạc đầy trước buổi demo. |

### Wi‑Fi chập chờn hoặc chậm

Chạy trên Pi (qua `ssh admin@10.42.0.1`) rồi đọc kết quả:

```bash
vcgencmd get_throttled            # 0x0 = nguồn đủ; khác 0x0 (ví dụ 0x50005) = THIẾU ĐIỆN → dùng nguồn 27 W chính hãng
ip -4 route show default          # phải có dev usb0 (hoặc enx...) = đang có mạng từ điện thoại
ping -c 5 -q 1.1.1.1 | tail -2    # mất gói hoặc trên ~150 ms = sóng 4G yếu
sudo iw dev wlan0 info | grep -E 'channel|txpower'
sudo iw dev wlan0 station dump | grep -E 'Station|signal:|tx bitrate'
```

**Chuyển Wi‑Fi sang 5 GHz** (nhanh hơn, ít nhiễu hơn 2,4 GHz; gần như mọi điện thoại đời mới đều hỗ trợ). Lệnh dưới tự quay về 2,4 GHz nếu 5 GHz không khởi động được. Phiên SSH sẽ rớt khoảng 10 giây, sau đó vào lại `DataExodus-Box`:

```bash
sudo setsid nohup bash -c 'nmcli connection modify DataExodus-AP 802-11-wireless.band a 802-11-wireless.channel 36 && nmcli connection up DataExodus-AP || { nmcli connection modify DataExodus-AP 802-11-wireless.band bg 802-11-wireless.channel 6; nmcli connection up DataExodus-AP; }' > /dev/null 2>&1 &
```

Với bản `hotspot.sh` mới, làm cách khác: `sudo HOTSPOT_BAND=a bash pi/hotspot.sh --prepare && sudo bash pi/hotspot.sh --on`.

**Lượng data:** mỗi lần kiểm tra link tốn khoảng 1–5 MB, một phiên Safe Browse vài MB. Buổi demo 15 phút thường tốn 50–200 MB. Nên nhắc thầy đừng mở video khi dùng Wi‑Fi này.

## Sau buổi demo

Về nhà, khi Pi đã ở trong vùng phủ Wi‑Fi nhà: cho laptop vào `DataExodus-Box`, chạy `ssh admin@10.42.0.1`, rồi:

```bash
cd ~/DataExodus_Final && sudo bash pi/hotspot.sh --home
```

Phiên SSH sẽ rớt và Pi quay về Wi‑Fi nhà, địa chỉ lại là `192.168.0.83`. Muốn demo lần nữa thì chạy `--on`.
