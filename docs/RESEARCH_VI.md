# Phần nghiên cứu: 50 website (chạy trên Raspberry Pi)

Cập nhật 28/10/2026. Đồ án gồm hai phần dùng chung một bộ phân loại và một luận điểm (*hashing is not anonymisation*, góc nhìn APP 8):

1. **Sản phẩm:** DataExodus Box. Thầy thử bằng điện thoại qua Wi‑Fi của Pi. Xem `HOTSPOT_VI.md`.
2. **Nghiên cứu:** đo 50 website trong danh sách đã đóng băng từ tuần 1 (`data/sites.yaml`). Danh sách chia 5 nhóm, mỗi nhóm 10 site: chính phủ, y tế, giáo dục, báo chí, thương mại điện tử.

## Câu hỏi nghiên cứu

| | Câu hỏi | Công cụ | Kết quả nằm ở |
| --- | --- | --- | --- |
| RQ1 | Trang chủ của 50 website gửi request tới bao nhiêu bên thứ ba và tracker? Của công ty nào? Máy chủ ở nước nào? Có khác nhau giữa các nhóm không? | Crawler của nghiên cứu (`dataexodus-study`) | `/var/lib/dataexodus/runs/<giờ UTC>/report/report.md`, `audit/audit.html` |
| RQ2 | Bộ chấm điểm của sản phẩm xếp 50 site hợp pháp này vào mức nào? Có bao nhiêu lần **báo nhầm "Dangerous"**? | `analysis/score_sites.py` | `summary.md`, `scores.csv` |
| Thực nghiệm | Email đã hash vẫn là định danh và nối được giữa các site (lab có kiểm soát, dùng định danh giả) | `examples/run_local_lab.py` | `docs/evidence/local-lab-browser.json` |

## Giao thức đo (ghi nguyên văn vào báo cáo)

- **Thiết bị:** Raspberry Pi 5, 4 GB, Debian 13 (Raspberry Pi OS), Chromium headless của hệ điều hành, điều khiển bằng Playwright, chạy dưới tài khoản `dataexodus` có tường lửa riêng.
- **DNS:** 1.1.1.1 và 1.0.0.1 (Cloudflare), đặt chung cho mọi mạng trong `/etc/NetworkManager/conf.d/90-dataexodus-dns.conf`. **Lý do:** DNS của router nhà trả `10.10.10.1` cho tên miền tracker, làm số liệu bị thiếu. Mỗi lần chạy đều ghi DNS đã dùng vào `status.json`, và dashboard hiển thị ở cột *DNS used*.
- **Với mỗi site:** mở trang chủ, chờ `DOMContentLoaded`, ở lại 8 giây, timeout 30 giây. Không bấm banner cookie, không đăng nhập, không điền form. Mỗi site dùng một trình duyệt mới, giữ nguyên user-agent của trình duyệt headless (không giả làm người dùng). Site nào chặn bot thì ghi nhận là thất bại.
- **Tham chiếu:** EasyPrivacy, DuckDuckGo Tracker Radar, GeoLite2-Country. Các file này giữ cố định giữa các lần chạy để so sánh được.
- **Ghi lại thêm:** ngày giờ, mạng đang dùng (Wi‑Fi nhà hay 4G), vị trí (ví dụ Sydney). Vị trí và nhà mạng ảnh hưởng tới việc CDN trả về máy chủ ở nước nào.

## Cách chạy

**RQ1: crawl 50 site** (khoảng 15–20 phút), trong cửa sổ `admin@Lab`:

```bash
sudo systemctl start dataexodus-study                   # chạy một lần ngay
sudo tail -f /var/lib/dataexodus/runs/*/crawl.log        # xem tiến độ, Ctrl+C để thoát
ls /var/lib/dataexodus/runs/*/raw | wc -l                # hoặc: số site đã ghi xong (tối đa 50)
cat /var/lib/dataexodus/runs/*/status.json               # ok: true khi xong
```

Kết quả hiện trên dashboard (`http://127.0.0.1:8020`, qua tunnel). Lần chạy thứ hai trở đi tự so sánh với lần trước. Nên có ít nhất **2–3 lần chạy vào các ngày khác nhau** trước hạn nộp. Muốn Pi tự chạy mỗi Chủ nhật: `sudo systemctl enable --now dataexodus-study.timer`. Chỉ nên bật khi Pi cắm mạng nhà, vì mỗi lần chạy tải vài trăm MB, rất tốn nếu đi qua 4G.

**RQ2: chấm điểm 50 site** (khoảng 5 phút):

```bash
cd /opt/dataexodus
export DATAEXODUS_GUARD_TOKEN="$(grep '^DATAEXODUS_GUARD_TOKEN=' /etc/dataexodus/dataexodus.env | cut -d= -f2-)"
.venv/bin/python -m analysis.score_sites --out ~/site-scores-$(date +%Y%m%d)
```

**Chép kết quả về laptop** (PowerShell trên laptop; thay `<run>` bằng tên thư mục, ví dụ `20261027T1404Z`):

```powershell
scp -r admin@192.168.0.83:/var/lib/dataexodus/runs/<run>/report admin@192.168.0.83:/var/lib/dataexodus/runs/<run>/audit C:\DataExodus\reports\pi-study-<run>\
scp -r admin@192.168.0.83:~/site-scores-* C:\DataExodus\reports\
```

Dữ liệu thô (`raw/`, `study.duckdb`) cứ để trên Pi. Chúng chứa toàn bộ URL đã ghi lại, và báo cáo không cần đến.

## Đưa vào báo cáo thế nào

- **Phương pháp:** giao thức ở trên, danh sách 50 site, tỉ lệ crawl thành công (trong `status.json` và `crawl.log`).
- **Kết quả RQ1:** theo từng nhóm: tỉ lệ request tới tracker, số bên thứ ba, các công ty đứng sau nhiều nhất, tỉ lệ máy chủ ngoài Úc, việc dùng API fingerprint. Đây là bảng mô tả, **không** phải kiểm định thống kê.
- **Kết quả RQ2:** số site ở mỗi mức Low / Be careful / Dangerous, số lần báo nhầm, các quy tắc hay làm tăng điểm nhất. Nhấn mạnh: "Be careful" trên site hợp pháp nghĩa là site đó theo dõi nhiều, không phải độc hại.
- **Nối với sản phẩm:** các tracker và công ty xuất hiện nhiều nhất trong RQ1 chính là những thứ mục *Block known trackers* chặn trên Wi‑Fi DataExodus (`pi/dns_trackers.txt`).

## Kết quả lần chạy 1 (chạy thử, 28/10/2026)

Chi tiết và số liệu đầy đủ (tiếng Anh): `docs/evidence/research-run1/README.md`.

- **Độ phủ (RQ1):** 34 site ghi đầy đủ, 2 site ghi một phần, 14 site thất bại. Phần lớn site thất bại là do cơ chế chống bot trả về trang chặn cho trình duyệt tự động (ATO, Home Affairs, news.com.au, Woolworths, các trường đại học…). **Không tìm cách vượt qua** cơ chế chống bot: kết luận của RQ1 chỉ áp dụng cho các site ghi được, và độ phủ được báo cáo trung thực. Đây là một phát hiện về phương pháp, nên đưa vào báo cáo.
- **RQ1:** đã ghi được 5.166 request. Trong đó 3.542 đi tới bên thứ ba và 776 tới tracker có trong danh sách.
  - Tỉ lệ request tới tracker cao nhất ở nhóm y tế (17%) và giáo dục (17%).
  - Google Analytics/Tag Manager có mặt ở 28 site.
  - Microsoft Clarity (ghi lại phiên dùng) xuất hiện ở 7 site, trong đó có 2 site chính phủ.
  - TikTok analytics xuất hiện ở 5 site, trong đó có healthdirect.gov.au và Medibank.
- **RQ2:** chấm được 49/50 site. **Không có site nào bị xếp nhầm "Dangerous".** Có 28 site Low risk và 21 site Be careful (lý do chủ yếu là tracker và máy chủ ở nước ngoài). 48/49 site có máy chủ bên thứ ba ở nước ngoài.
- **Cải tiến rút ra từ nghiên cứu:** quy tắc "lời lẽ lừa đảo" bị kích hoạt sai ở 9 site, vì những cụm phổ biến như "gift card" (6 site bán lẻ/bảo hiểm) hay "act now" (Bộ Nội vụ). Quy tắc mới yêu cầu một cụm mạnh hoặc hai cụm yếu. Tính lại theo quy tắc mới được 31 Low, 18 Be careful, 0 Dangerous. Khi báo cáo, phải nói rõ quy tắc được chỉnh dựa trên chính 50 site này, nên đây chưa phải phép thử độc lập.

## Giới hạn cần nêu

- Chỉ đo trang chủ, một lần mở ẩn danh, không bấm đồng ý cookie. Trang con và người dùng đã đăng nhập có thể khác.
- Crawler không điền form, nên không thể quan sát việc email của người dùng bị gửi đi trên 50 site này. Luận điểm "hash không phải ẩn danh" được chứng minh bằng thực nghiệm lab có kiểm soát.
- Quốc gia là ước tính GeoIP của địa chỉ máy chủ. Nó không cho biết dữ liệu được lưu ở đâu, nên tự nó chưa chứng minh có vi phạm APP 8.
- Nhãn tracker dựa trên danh sách công khai; tên miền chưa có trong danh sách được xếp là "unknown".
- RQ2 chỉ đo báo nhầm trên site hợp pháp. Muốn đo khả năng **bắt** lừa đảo thật thì cần một bộ link lừa đảo có nhãn, và việc này chưa làm.
