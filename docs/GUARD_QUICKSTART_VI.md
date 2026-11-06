# DataExodus Guard 0.5: hướng dẫn chạy

Cập nhật 27/10/2026 (giờ Sydney). Guard **0.5.0** = bản 0.4 (gộp từ hai bản Guard 0.3, cộng X-Ray và sandbox trên Raspberry Pi), thêm **điểm rủi ro 0–100 kèm lý do** ngay trong kết quả *Preview in isolated sandbox*. Kết quả "Dangerous" sẽ không có nút mở link sạch một chạm. Chi tiết: `docs/VALIDATION.md`. Trọng tâm demo của bản 0.5 là Wi‑Fi cho thầy thử bằng điện thoại: xem `docs/HOTSPOT_VI.md`.

**Đã kiểm chứng trên Chromium thật (bản 156):** extension được nạp unpacked và điều khiển phòng lab qua 2 giai đoạn (baseline và protected). Mọi con số đều lấy từ **phía nhận** của lab, không giả lập chặn. Kết quả ở `docs/evidence/guard-v05-browser-acceptance.json` (bản 0.4 trước đó: `guard-v04-browser-acceptance.json`). Web Risk mới chỉ được test bằng phản hồi giả lập, chưa gọi bằng key thật. Phần Raspberry Pi xem `docs/RASPBERRY_PI_VI.md`.

## Guard làm gì

| Dấu hiệu / thao tác | Guard 0.5 xử lý | Giới hạn |
| --- | --- | --- |
| Email bảo vệ, hoặc SHA-1/256/512 hex của nó, nằm trong URL gửi sang bên thứ ba | Quy tắc Chrome (DNR) chặn **trước khi gửi**, kể cả tới domain chưa từng biết | Chỉ các dạng biểu diễn được hỗ trợ |
| Định danh nằm trong **body POST** gửi sang site khác | Quan sát được khi request rời trình duyệt. Guard tạo session rule cho cặp *site nguồn → đích*, nên lần gửi sau bị chặn | Lần POST đầu đã đi ra; DNR không đọc được body |
| Domain nằm trong danh sách chặn | Chặn subresource; điều hướng top-level bị đưa vào **Quarantine** | Danh sách khởi đầu nhỏ; có thể nhập danh sách từ audit |
| **Nhấn quảng cáo** (Google/Bing/Amazon/Taboola/Outbrain/Criteo/Xandr…) | Chrome chuyển cú nhấp sang Quarantine **trước khi** mạng quảng cáo nhận được | Edge không cho extension chuyển hướng điều hướng tới bing.com |
| Popup / pop-under bằng script | **Từ 0.5.1:** Chrome báo cho Guard mọi tab mà trang tự mở, dù mở bằng cách nào. Tab sang site khác mà bạn không bấm (hoặc chuột phải) vào link dẫn tới đó sẽ bị đóng ngay, kèm thông báo nhỏ. Không mở tab Quarantine | Tab có thể hiện lên chớp nhoáng trước khi bị đóng; mạng quảng cáo vẫn có thể đã nhận được request đầu tiên. Cửa sổ "Sign in with…" mở bằng nút bấm có thể bị đóng nhầm |
| Lớp phủ trong suốt (link vô hình phủ lên nội dung) | Chặn thao tác, rồi mở tab Quarantine (chỉ khi có cú nhấp thật) | Trang có thể vô hiệu hook; báo cáo từ trang là "unverified" |
| Link thường, POST cùng site | Vẫn hoạt động (đối chứng âm trong lab) | Cần tự thử OAuth/thanh toán thật |
| Cửa sổ "Sign in with…" mở bằng script sang site khác | **Có thể bị chặn nhầm** bởi lớp chặn popup | Thêm site đó vào *Allow sites*; ghi lại thành false positive |

**Trang Quarantine** không tải trang đích. Nó chỉ hiển thị origin và số lượng thành phần URL trong một iframe `sandbox=""`, kèm CSP chặn mọi kết nối. Từ đây bạn chọn:

- **Preview in isolated sandbox:** dịch vụ DataExodus mở link trong một Chromium headless dùng một lần (không cookie, không đăng nhập, không lưu trữ, không tải file, từ chối địa chỉ nội bộ). Kết quả: **điểm 0–100 kèm từng lý do**, chuỗi chuyển hướng, tracker, ảnh chụp, link sạch. Dịch vụ có thể chạy trên laptop hoặc trên **Raspberry Pi** (khuyên dùng).
- **Open clean destination:** mở trang nhà quảng cáo **không kèm click-ID** (`gclid`, `fbclid`, `utm_*`…).
- **Open advertiser page directly:** khi link quảng cáo có sẵn đích (`adurl=`), Guard mở thẳng đích đó, bỏ qua hoàn toàn mạng quảng cáo.
- **Open original link anyway:** mở link gốc, chỉ cho riêng tab này và chỉ một lần.

URL đầy đủ được giữ trong `chrome.storage.session`: chỉ nằm trong bộ nhớ, chỉ trang của extension đọc được, và bị xoá khi đóng tab. URL không xuất hiện trong evidence hay file export, và không được gửi đi đâu nếu bạn không nhấn Preview. Điều hướng mang định danh của bạn **không** được giữ URL (vì chính URL đó chứa định danh), nên không có nút Preview cho loại này.

**X-Ray:** nút *X-Ray this page* trong popup vẽ khung quanh pixel theo dõi của bên thứ ba, frame ẩn và link phủ trong suốt ngay trên trang, cùng một bảng tóm tắt. Đây là chế độ xem heuristic: nó cho biết trang **chứa** gì, không chứng minh trang đã **gửi** gì.

## 1. Cài đặt (Windows)

Mở PowerShell tại thư mục dự án:

```powershell
cd C:\DataExodus
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -c requirements-tested.txt
python -m pip install dnslib        # cho phần Raspberry Pi / DNS watch
python -m playwright install chromium
python setup_data.py                # EasyPrivacy, Tracker Radar, URLhaus; thêm --geoip-key/--geoip-account cho GeoLite2
```

Nếu đã tải dữ liệu ở lần trước, chép thẳng thư mục `data\blocklists` cũ sang đây là xong, không cần tải lại. Nếu PowerShell không cho chạy `Activate.ps1`, gọi thẳng `.venv\Scripts\python.exe`.

## 2. Nạp Guard vào Chrome hoặc Edge

1. Mở `chrome://extensions` (hoặc `edge://extensions`), bật **Developer mode**.
2. **Gỡ hoặc tắt** các bản cũ: DataExodus Guard 0.3, GhostShield, và extension nghiên cứu `extension/`. Nếu chạy nhiều bản cùng lúc, kết quả đo sẽ lẫn vào nhau.
3. **Load unpacked**, chọn thư mục `C:\DataExodus\guard`.
4. Ghim DataExodus Guard lên thanh công cụ, rồi mở **Settings**.
5. Điền **Protected email** là `student.demo@example.com` (email thử, đừng dùng email thật khi demo). Bật **Pre-block…**, **After a local identity observation…**, **Route ad clicks…**, rồi bấm **Save and apply rules**.

## 3. Dịch vụ DataExodus (sandbox, giải thích, kiểm tra URL)

**Cách A: trên Raspberry Pi** (khuyên dùng). Xem `docs/RASPBERRY_PI_VI.md`, chạy `pi\connect-pi.ps1 -CopyToken`, rồi dán token vào Settings.

**Cách B: ngay trên laptop** (luôn chạy từ thư mục dự án, nếu không sẽ gặp lỗi `No module named 'protection'`):

```powershell
cd C:\DataExodus
$env:DATAEXODUS_GUARD_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:DATAEXODUS_GUARD_TOKEN | Set-Clipboard
python -m uvicorn protection.api:app --host 127.0.0.1 --port 8010 --no-access-log
```

Dán token vào **Local service token** trong Settings rồi lưu. Token này chỉ bảo vệ API chạy trên máy. Đừng đẩy nó lên GitHub.

## 4. Demo trong phòng lab

```powershell
cd C:\DataExodus
python -m examples.guard_lab
```

Mở `http://127.0.0.1:8875`. Lab gồm 6 máy chủ loopback, mỗi máy một vai: website (.1), collector có trong danh sách (.2), máy chủ quảng cáo và bộ chuyển hướng `/aclk` (.3), collector chưa biết (.4), collector nhận POST (.5), trang của nhà quảng cáo (.6). Không có mã độc thật.

Muốn **xem trước quảng cáo của lab** trong sandbox, chạy dịch vụ trên laptop (cách B) với biến chỉ dành cho lab:

```powershell
cd C:\DataExodus
$env:SANDBOX_ALLOW_HOSTS = "127.0.0.3,127.0.0.6"   # CHỈ dùng trong lab
python -m uvicorn protection.api:app --host 127.0.0.1 --port 8010 --no-access-log
```

**Lượt A (baseline):** trong Settings tắt **Enable network protection**, lưu, tải lại trang lab, làm hết các thẻ 01–09, rồi bấm *Refresh receiver evidence*.

**Lượt B (protected):** Ctrl+C để dừng lab, chạy lại cho receipts về 0. Bật protection và **Enable local lab rules**, lưu, tải lại lab, lặp lại đúng chuỗi thao tác. Ở thẻ 06, gửi lần thứ nhất, mở popup đợi ô *Scoped collection rules* lên 1, rồi gửi lần hai.

| Thao tác | Baseline | Protected (đã đo trong Chromium thật) |
| --- | --- | --- |
| 01 email / hash / body tới collector .2 | 3 lượt nhận | 0 |
| 05 email trong URL tới collector chưa biết .4 | 1 | 0 |
| 06 POST hai lần tới .5 | 2 | 1 (lần đầu lọt, lần sau bị quy tắc học chặn) |
| 07 POST cùng site | 1 | 1 (vẫn hoạt động) |
| 02 Play, 03 lớp phủ, 08 link quảng cáo trực tiếp | 3 lượt điều hướng quảng cáo | 0; mỗi cái một tab Quarantine |
| 04 tài liệu cùng site | mở được | mở được |
| 09 quảng cáo được tài trợ | bộ chuyển hướng ghi nhận cú nhấp; nhà quảng cáo nhận `gclid` | bộ chuyển hướng **không** thấy trình duyệt của bạn; sandbox đi theo chuỗi; trang sạch mở **không có click-ID** |

Thử thêm nút **X-Ray this page** trên trang lab: pixel 1×1 của máy chủ quảng cáo và link phủ ở thẻ 03 sẽ được khoanh lại.

Giữ `/receipts`, file export JSON từ popup và ảnh chụp màn hình làm bằng chứng. Không kết luận "dữ liệu đã bị ngăn" chỉ vì thấy một cảnh báo.

## 5. Kiểm thử tự động

```powershell
python -m pytest tests/ -q
node --test (Get-ChildItem tests\*.cjs).FullName                         # cần Node.js; DOM test cần jsdom
python -m examples.run_guard_acceptance --out reports/guard-browser-run2 --headed
```

Kịch bản acceptance tự bật dịch vụ ở `127.0.0.1:8010` (với SANDBOX_ALLOW_HOSTS cho lab) nếu cổng đó đang trống. Nếu tunnel tới Pi đang mở, cổng bị chiếm: kịch bản bỏ qua phần preview và đi đường *Open advertiser page directly*. Mỗi lần chạy cần một thư mục output mới.

## 6. Kiểm tra một URL (Web Risk) và chặn thủ công

Đặt `WEBRISK_API_KEY` ở dịch vụ. Trong Settings, nhập URL, xác nhận đồng ý gửi URL sang Google, rồi bấm **Check URL**. Nếu kết quả là `listed`, bạn có thể chọn **Block destination domain**. `not_listed` **không** có nghĩa là an toàn. Safe Browsing chỉ dành cho mục đích phi thương mại; dùng thương mại thì cần Web Risk.

## 7. Dùng chung danh sách với audit, và báo cáo evidence

```powershell
python -m protection.export_rules --out reports/guard-domains.json            # Settings → Import a reviewed audit domain export
python -m analysis.guard_report --events "C:\path\DataExodus_Guard_Evidence.json" --out reports/guard-audit
```

Báo cáo tách riêng 3 loại: *Chrome rule matches* (chặn mạng và điều hướng vào Quarantine), *page reports* chưa xác minh, và *observations*. Không cộng các con số này để ra "tỉ lệ chặn".

## 8. Đánh giá đóng góp của từng lớp

| Phiên bản | Đo cái gì |
| --- | --- |
| A: chỉ quy tắc domain | Request thật sự bị ngăn, chặn nhầm, ảnh hưởng chức năng |
| B: A + quy tắc định danh + quy tắc học | Định danh tới collector **chưa biết**; lần POST thứ hai |
| C: B + Quarantine/sandbox | Số cú nhấp quảng cáo mà mạng quảng cáo không ghi nhận được; số click-ID không tới nhà quảng cáo |

## 9. Giới hạn cần nói khi bảo vệ

- Guard bảo vệ trong phạm vi extension trình duyệt; nó không diệt mã độc đã chạy trên hệ điều hành.
- DNR không đọc body: lần POST đầu đi ra được, và quy tắc học chỉ áp dụng cho các lần sau.
- Hook MAIN-world (popup) có thể bị trang vô hiệu hoá; báo cáo đến từ trang có thể bị giả mạo, nên không bao giờ được dùng để tạo quy tắc chặn.
- Sandbox cho biết trang làm gì trong **một** lần mở ẩn danh, không phải phán quyết an toàn hay mã độc.
- Guard nhận diện email thử ở dạng raw hoặc hash SHA-1/256/512; không nhận MD5, số điện thoại hay cookie như pipeline nghiên cứu.
- Chưa thử với người dùng khác ngoài dự án; không có cam kết bảo vệ 100%.
