# DataExodus: hướng phát triển thực tế

**Bản mở rộng Audit + Guard:** xem [GUARD_QUICKSTART_VI.md](GUARD_QUICKSTART_VI.md) cho extension bảo vệ, adapter Gemini/Web Risk, lab và lộ trình kiểm chứng mới. Phần agency audit dưới đây vẫn là hướng thứ nhất; Guard là hướng thứ hai cho người duyệt web. Chưa có browser acceptance hoặc API provider thật được xác minh. AI hiện chỉ giải thích tín hiệu đã lọc và không có quyền chặn/bỏ chặn.

Cập nhật ngày 22/10/2026. Đây là đề xuất phát triển và kế hoạch kiểm chứng sản phẩm, không phải bằng chứng đã có khách hàng hoặc doanh thu.

## 1. Khách hàng và vấn đề nên tập trung

Mình đề xuất khách hàng đầu tiên là web agency nhỏ và developer quản lý website cho doanh nghiệp. Họ cần biết một thay đổi ở Google Tag Manager, plugin hoặc SDK có khiến website gửi thông tin định danh ra ngoài hay không, và cần một báo cáo dễ giao lại cho khách hàng.

Giá trị sản phẩm nên diễn đạt như sau: **“DataExodus giúp người quản lý website tìm request có dữ liệu định danh, xác định nơi cần kiểm tra, và giữ bằng chứng trước/sau khi sửa.”**

Ví dụ giả định: một form tư vấn gửi email tới một integration ngoài website. DataExodus phát hiện email hoặc hash đã biết, ghi lại bề mặt chứa dữ liệu, đề xuất xem lại payload của integration, và đối chiếu lần chạy sau. Việc gửi hash có thể cho phép liên kết một người giữa các website, nhưng bản thân phép khớp không chứng minh bên nhận đã lập hồ sơ người dùng.

Ghostery đã cung cấp chức năng chặn tracker; Blacklight đã kiểm tra công nghệ theo dõi của website; Cookiebot có scanner và quản lý consent. Vì vậy lợi thế cần thử nghiệm của DataExodus là quy trình làm việc cụ thể: **định danh thử nghiệm → bằng chứng có thể kiểm tra → hướng xử lý → retest**, chạy cục bộ và dễ dùng với agency nhỏ. Đây là định vị cần xác nhận, chưa phải tuyên bố tính năng độc quyền.

## 2. Những gì đã phát triển trong bản này

| Hạng mục | Tác dụng thực tế | Trạng thái |
| --- | --- | --- |
| Khớp email/điện thoại dạng thô và MD5/SHA-1/SHA-256/SHA-512 | Kiểm tra request có mang định danh đã cấu hình hay không | Đã kiểm thử |
| Ghi URL/body/cookie/header làm vị trí phát hiện | Giúp developer biết cần kiểm tra trường nào | Đã kiểm thử |
| Báo cáo HTML cục bộ, lọc ưu tiên và xem bằng chứng | Chủ website có thể đọc mà không cài Grafana | Đã kiểm thử logic giao diện bằng DOM |
| Gợi ý xử lý theo quy tắc | Chuyển phát hiện thành công việc sửa tag/plugin/SDK | Đã triển khai; không tự sửa website |
| So sánh baseline với retest | Hiển thị phát hiện mới, còn tồn tại, không quan sát thấy hoặc chưa thể kết luận | Đã kiểm thử |
| Kiểm tra điều kiện so sánh | Tránh đánh dấu cải thiện khi crawl lỗi hoặc cấu hình detector đã đổi | Đã kiểm thử |
| Xuất báo cáo che giá trị định danh | Chia sẻ kết quả mà không đưa raw email/body/cookie vào báo cáo | Đã kiểm thử các trường xuất |
| Ghép sự kiện extension bằng requestId | Tránh đếm đôi body và header của cùng request | Đã kiểm thử với Chrome API giả lập |
| Hai website và collector trong lab cục bộ | Cho thầy xem cơ chế gửi cùng hash tới bên thứ ba | HTTP server đã kiểm thử; browser end-to-end cần chạy trên máy bạn |
| Pipeline xử lý có transaction và không cộng trùng | Chạy lại để tái lập báo cáo mà không làm sai số lượng | Đã kiểm thử |

Không cần gửi email hoặc số điện thoại thật vào cuộc trò chuyện. Demo mặc định dùng `student.demo@example.com`. Cấu hình định danh riêng, nếu cần cho một bài kiểm tra được phép, nằm trên máy của bạn.

## 3. Cách trình diễn để thầy thấy giá trị

**Demo 1 — Có sẵn, dùng để giải thích phần mềm:** chạy `python -m analysis.demo`, mở `reports/demo/audit.html`. Hai website giả lập tạo tổng cộng 10 request; 4 request khớp định danh. Sau thay đổi giả lập còn 6 request, không có request khớp định danh. Báo cáo thể hiện hash giống nhau ở hai website, vị trí phát hiện và gợi ý xử lý. Dữ liệu này là fixture, phải ghi nhãn rõ.

**Demo 2 — Bằng chứng browser thật trong lab của mình:** cài Chromium, chạy `python -m examples.run_local_lab --out reports/local-lab-run1`. Browser thật truy cập hai website cục bộ và collector nhận hash email thử nghiệm. Lần sau integration đã được bỏ. Đối chiếu capture với `collector_receipts.json`. Toàn bộ lab chạy trên loopback, không gửi email thử nghiệm tới dịch vụ bên ngoài. Bản này chưa chạy được bước Chromium trong môi trường phát triển vì tải browser thất bại; bạn cần chạy và lưu bằng chứng trên máy mình.

**Demo 3 — Tác động với website thực tế:** dùng staging website do mình quản lý hoặc có quyền kiểm tra. Lặp lại cùng một hành trình và cùng test identity trước/sau khi sửa tag. Giữ raw capture, cấu hình, phiên bản reference list, kết quả kiểm tra thủ công và báo cáo. Một ví dụ đã sửa và đo lại tốt thường có sức thuyết phục hơn một dashboard nhiều biểu đồ nhưng không giải thích được hành động tiếp theo.

## 4. Phạm vi nên hoàn thành cho final project

Thời lượng dưới đây là ước lượng khi bạn còn khoảng 2–4 tuần; cần chỉnh theo deadline và rubric thực tế.

| Giai đoạn | Việc cần làm | Bằng chứng hoàn thành |
| --- | --- | --- |
| 1. Xác nhận môi trường | Chạy test, demo fixture, local browser lab | Log test, capture và receipt thật trong lab |
| 2. Kiểm tra trên staging | Chọn một integration, tái hiện bằng test identity, sửa và retest | Một case study có before/after và mô tả thay đổi thật |
| 3. Hoàn thành nghiên cứu | Crawl danh sách đã chốt, lưu lỗi, phiên bản và điều kiện đo; kiểm tra nhãn bằng tay | Dataset có nguồn gốc và bảng kiểm tra chất lượng |
| 4. Viết và bảo vệ | Trình bày kết quả, giới hạn, giá trị người dùng, đánh giá và hướng thương mại | Báo cáo A4 và demo tái lập được |

Năm nhóm trong `data/sites.yaml` thực tế là government, health, education, news_media và ecommerce. Handoff cũ mô tả nhầm một số nhóm. Một số website sức khoẻ là website quốc tế. Cần mô tả đúng danh sách mẫu thay vì gọi tất cả là tổ chức của Úc.

Charter và Project Plan cũ vẫn được giữ nguyên. Một số câu trong đó nói “đã verified”, có kết quả ML 99.3% hoặc mô tả monitoring. Archive hiện thiếu raw data và bằng chứng của các kết quả ấy; cần rà lại trước khi đưa vào bản nộp cuối. Không coi tài liệu kế hoạch là bằng chứng phần mềm đã chạy thành công.

## 5. Các tính năng tiếp theo có giá trị cao

1. **Kiểm tra theo hành trình và trạng thái consent.** So sánh chưa tương tác, từ chối và chấp nhận; cấu hình selector riêng cho từng website, lưu bằng chứng hành động. Không suy diễn rằng crawler mặc định đã bấm “Reject”.
2. **Phát hiện regression sau cập nhật website.** Khi thêm plugin hoặc thay tag, chạy lại cùng test suite và báo những recipient/field mới. Bản hiện tại so sánh các nhóm phát hiện, chưa có tag-change attribution đầy đủ.
3. **Hồ sơ vấn đề cho developer.** Thêm cách tìm script/tag chịu trách nhiệm, người xử lý và xác nhận thủ công. Hiện tại báo cáo biết destination và surface, chưa biết chắc plugin nào gây ra request.
4. **Bảng đối chiếu privacy policy có người duyệt.** Đặt hành vi quan sát được cạnh nội dung policy, ghi “cần xác minh” khi thiếu ngữ cảnh. Không tự kết luận vi phạm pháp luật chỉ từ quốc gia đích hoặc tên tracker.
5. **Bảo vệ dữ liệu và quản lý dự án.** Xác thực agent, phân quyền, xoá theo thời hạn, mã hoá dữ liệu lưu, cơ chế secret và nhật ký thao tác. Đây là phần cần trước khi phục vụ dữ liệu của khách hàng.

ML có thể là thí nghiệm phụ sau khi phần đo lường đã ổn định. Nhãn từ blocklist không phải ground truth độc lập; mô hình học lại nhãn ấy không chứng minh phát hiện tracker mới chính xác. Nếu giữ ML, cần tập kiểm tra theo website/domain và nhãn được kiểm tra độc lập.

## 6. Đo “hữu ích” như thế nào

| Tiêu chí | Cách đo | Mục tiêu thử nghiệm, chưa phải kết quả |
| --- | --- | --- |
| Độ chính xác định danh | Gắn nhãn thủ công test case dương và âm; báo TP/FP/FN | Không có false positive trong bộ kiểm thử đã định nghĩa; công bố giới hạn |
| Giá trị cho developer | Nhờ 3–5 người đọc báo cáo và xác định hành động tiếp theo | Người đọc xác định đúng điểm cần sửa trong khoảng 5 phút |
| Tác động sửa lỗi | So sánh cùng hành trình trước/sau, có xác nhận thay đổi thật | Phát hiện mục tiêu không còn quan sát thấy trong retest hợp lệ |
| Khả năng tái lập | Chạy lại pipeline trên cùng raw capture và cấu hình | Không tăng số lượng request hoặc đổi nhóm phát hiện vô cớ |
| Hiệu quả vận hành | Ghi thời gian crawl, phân tích, xử lý báo cáo | Đo chi phí thực tế trước khi đặt giá bán |

Đồng thời ghi website truy cập thất bại, anti-bot, GeoIP thiếu, coverage định danh và khác biệt theo thời điểm. API fingerprint có thể được dùng hợp pháp; việc quan sát một lệnh canvas không chứng minh theo dõi người dùng.

## 7. Hướng thử thương mại

Bắt đầu bằng một dịch vụ audit có công cụ hỗ trợ: agency gửi website staging và hành trình cần kiểm tra; mình cung cấp báo cáo, buổi giải thích ngắn và một lần retest. Cách này giúp học vấn đề khách hàng trước khi đầu tư nền tảng SaaS nhiều tài khoản.

Phỏng vấn khoảng 5 agency/developer và hỏi về case gần đây: họ tìm ra tag lỗi như thế nào, mất bao lâu, ai chịu trách nhiệm, bằng chứng nào khách hàng cần, và họ có sẵn sàng trả tiền cho một pilot cụ thể không. Đây là hoạt động bạn tự thực hiện; chưa có ai được liên hệ trong phiên này.

Chỉ quyết định gói giá sau khi có dữ liệu pilot. Có thể thử mô hình phí theo website/lần audit, hoặc theo số website quản lý và số lần retest. Những con số doanh thu, mức giá hay nhu cầu chưa được kiểm chứng không nên ghi như dữ liệu thị trường trong bài cuối.

Điều kiện để tiến tới sản phẩm thương mại: người dùng ngoài dự án hiểu và dùng được báo cáo; detector được đánh giá độc lập; có quy trình dữ liệu/consent rõ; có xác thực và cách xoá dữ liệu; điều khoản sử dụng và giấy phép phần mềm/dataset được kiểm tra. Mã nguồn hiện chưa có file LICENSE dù README cũ nói MIT, nên chưa thể coi giấy phép phân phối đã được chốt.

## 8. Nguồn tham khảo cho định vị và giới hạn

- [FTC — No, hashing still doesn't make your data anonymous](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/07/no-hashing-still-doesnt-make-your-data-anonymous): hashing có thể duy trì định danh và khả năng liên kết.
- [OAIC — Chapter 8, APP 8](https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines/chapter-8-app-8-cross-border-disclosure-of-personal-information): đánh giá tiết lộ xuyên biên giới cần điều kiện và ngữ cảnh; vị trí IP không đủ để kết luận.
- [Ghostery FAQ](https://www.ghostery.com/faq): sản phẩm và khả năng của extension hiện có.
- [The Markup — How We Built a Real-time Privacy Inspector](https://themarkup.org/blacklight/2020/09/22/how-we-built-a-real-time-privacy-inspector): thiết kế scanner Blacklight và cách kiểm tra tracking.
- [Cookiebot — Understanding the scan report](https://support.cookiebot.com/hc/en-us/articles/5007079527580-Understanding-the-scan-report): báo cáo scanner và giới hạn liên quan tới việc truy cập website.

Đọc phần `README.md` trước để chạy; xem `docs/FINAL_PROJECT_GUIDE.md` để chuẩn bị bằng chứng và phần hỏi đáp.
