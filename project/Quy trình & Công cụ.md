# Báo cáo quy trình — Dự án "Sun Riser 2026"
### Deck: BE PROFESSIONAL @ SUN.STUDIO (Intern L&D)

> File này tổng hợp lại **toàn bộ** những gì đã được sử dụng trong dự án: skill, tool, và cách xử lý từng tình huống phát sinh. Dùng để bạn nắm rõ quy trình & tái sử dụng cho lần sau.

---

## 1. Skill (kỹ năng) đã sử dụng

| # | Skill | Mục đích sử dụng trong dự án | Trạng thái |
|---|-------|------------------------------|-----------|
| 1 | **SUN.STUDIO Design System** (design system) | Skill bắt buộc — quy định toàn bộ màu, font, spacing, component. Mọi visual phải bám theo. Là nguồn gốc của fonts (Proxima Nova), palette (cam/xanh/lime/violet), mascot Dio, hoạ tiết XO. | ✅ Đang dùng |
| 2 | **Make a deck** (làm slide deck HTML) | Định hình quy trình dựng deck: dùng `deck-stage` làm khung, mỗi slide là 1 `<section>`, scaling/nav/print sẵn có. | ✅ Đã áp dụng |
| 3 | **Hi-fi design** *(quy trình ngầm)* | Quy trình thiết kế hi-fi: đọc design context → hỏi câu hỏi → chốt style trên slide mẫu → build full. | ✅ Đã áp dụng |

> **Lưu ý:** Các skill khác có sẵn nhưng **CHƯA dùng** trong dự án này (sẽ dùng khi tới bước tương ứng): `Export as PPTX`, `Save as PDF`, `Save as standalone HTML`, `Send to Canva`, `Make tweakable`, `Animated video`, `Speaker notes`, `Handoff to Claude Code`.

---

## 2. Connector (kết nối ngoài) đã sử dụng

| Connector | Dùng để làm gì | Kết quả |
|-----------|----------------|---------|
| **Canva** (`canva__get-design-content`) | Truy cập link Canva gốc, rút **nội dung text** của deck mẫu | ✅ Lấy được toàn bộ text. ⚠️ KHÔNG lấy được layout/ảnh/style (giới hạn của connector) |

---

## 3. Tool (công cụ) đã sử dụng

### 3.1 Khám phá & đọc tài nguyên
| Tool | Dùng để |
|------|---------|
| `list_files` | Quét cấu trúc design system & project |
| `read_file` | Đọc CSS tokens, slide mẫu, component của design system |
| `view_image` | Xem mascot Dio + logo để biết cách dùng |
| `image_metadata` | Kiểm tra kích thước/độ trong suốt của ảnh |

### 3.2 Tạo & chỉnh sửa file
| Tool | Dùng để |
|------|---------|
| `write_file` | Viết deck HTML, `deck.css`, file harness, report |
| `str_replace_edit` | Sửa nhanh từng đoạn (sửa text, tinh chỉnh CSS, đổi size font) |
| `copy_files` | Copy fonts, logo, mascot Dio từ design system vào project |
| `copy_starter_component` | Lấy sẵn `deck-stage.js` (khung deck) + `image-slot.js` (ô kéo-thả ảnh) |

### 3.3 Xem trước & kiểm thử (verify)
| Tool | Dùng để |
|------|---------|
| `show_html` | Render deck trong iframe để xem nhanh |
| `save_screenshot` | Chụp từng slide để tự đối chiếu visual |
| `eval_js` | Truy vấn DOM — chẩn đoán lỗi không thấy nội dung (hit-test) |
| `done` | Mở file cho bạn xem + trả về lỗi console + cảnh báo slide |
| `update_todos` | Quản lý checklist tiến độ |
| `questions_v2` | Hỏi bạn 8 câu để chốt hướng đi đầu dự án |
| `snip` | Dọn bớt context cũ đã xử lý xong cho gọn |

---

## 4. Cách xử lý các tình huống (tình huống → cách giải quyết)

### Tình huống 1 — "Truy cập Canva được không?"
- **Vấn đề:** Cần đọc nội dung deck gốc trên Canva.
- **Xử lý:** Dùng connector Canva → rút được text. **Chủ động cảnh báo** giới hạn: connector chỉ lấy text, không lấy được layout/ảnh/style.

### Tình huống 2 — Prompt của bạn chưa đủ rõ
- **Vấn đề:** Yêu cầu "polish + animation trên Canva" về mặt kỹ thuật **không khả thi** qua connector.
- **Xử lý:** Giải thích thẳng giới hạn, đề xuất **2 hướng** (A: dựng lại HTML hi-fi / B: chỉ sửa text). Dùng `questions_v2` hỏi 8 câu (output, độ chi tiết, phạm vi slide, mức animation, mascot, ngôn ngữ, tương tác, có đề xuất sửa câu chữ không) để **tối đa độ tự tin của prompt**.

### Tình huống 3 — "Bạn extract được file gì từ Canva?"
- **Xử lý:** Nói rõ chỉ lấy được **text thuần**, không có layout/ảnh. Tư vấn định dạng export tốt nhất để tôi "thấy" được wireframe: **PPTX > PDF > PNG**.

### Tình huống 4 — Cung cấp file gốc 3 định dạng
- **Xử lý:** Phân tích visual gốc → nhận diện hệ thống: palette 4 màu, section divider có hoạ tiết, pattern "THẢM HOẠ ❌ / CHUYÊN NGHIỆP 💚", thẻ bo góc khía, vòng tròn đồng tâm. Chốt **system** trước khi build.

### Tình huống 5 — ⭐ Screenshot không thấy nội dung slide
- **Vấn đề:** Công cụ chụp ảnh chỉ ra nền, không thấy text — dù `eval_js` chứng minh text **có** render (hit-test trúng tiêu đề).
- **Nguyên nhân:** `deck-stage` chiếu slide qua **shadow-DOM `<slot>`**, mà công cụ html-to-image không rasterize được slot.
- **Xử lý:** Tạo **file harness `_preview.html`** dùng plain-DOM (clone slide ra ngoài shadow root) → chụp ảnh hoạt động bình thường để tự kiểm tra. Deck giao cho bạn vẫn dùng `deck-stage` chuẩn.

### Tình huống 6 — Tránh trùng lặp markup
- **Vấn đề:** Ban đầu harness copy tay nội dung slide → dễ lệch với deck thật.
- **Xử lý:** Nâng cấp harness để **tự fetch** deck HTML, parse và clone slide ra preview → một nguồn sự thật duy nhất.

### Tình huống 7 — Tách CSS dùng chung
- **Xử lý:** Gom toàn bộ style vào **`deck.css`** (cả deck thật & harness cùng dùng) → sửa 1 chỗ, đồng bộ mọi nơi.

### Tình huống 8 — "Cần sáng tạo & polish hơn"
- **Xử lý:** Nâng cấp lên **v2**: thêm hoạ tiết thương hiệu **XO**, spotlight + halo cho Dio, animation pop-in, index Agenda đổi màu theo thứ tự, thẻ có gradient + chấm phát sáng, khối Do/Don't tô màu đỏ/xanh tương phản.

### Tình huống 9 — Cảnh báo "chữ quá nhỏ" từ validator
- **Xử lý:** Bump cỡ chữ chrome/eyebrow lên 24px, chữ trong card lên 24px (đọc tốt khi chiếu), dời số ghost "#1" tránh đè footer/tiêu đề.

---

## 5. Quy ước thiết kế đã chốt (design system của deck)

| Hạng mục | Quyết định |
|----------|-----------|
| **Font** | Proxima Nova — Black / Bold / SemiBold / Medium |
| **Màu chính** | Cam `#FF5533` · Xanh `#3333FF` · Lime `#A8E532` · Violet `#A974F5` |
| **Mascot Dio** | Dùng có chủ đích ở Title / Section / Thank-you |
| **Hoạ tiết** | XO pattern (tic-tac-toe), noise overlay, spotlight, vòng cung đồng tâm |
| **Animation** | Entrance fade/slide-up có stagger, tôn trọng `prefers-reduced-motion` & print |
| **Ngôn ngữ** | Tiếng Việt + keyword tiếng Anh (giữ nguyên 100%) |
| **Slide chuẩn** | 1920×1080, text tối thiểu ~21–24px |

---

## 6. Tiến độ hiện tại

- [x] Khám phá design system & rút tài nguyên (fonts, logo, Dio)
- [x] Định nghĩa palette mở rộng + type scale
- [x] Dựng 4 slide mẫu (Title · Agenda · Văn hoá Meeting · Do/Don't đi trễ)
- [x] Polish sáng tạo v2 (XO, halo, animation, màu hoá)
- [ ] **Chờ bạn duyệt style** trên 4 slide mẫu
- [ ] Build 24 slide còn lại (tổng 28, đúng 1:1 Canva)
- [ ] Report đề xuất chỉnh câu chữ cuối cùng

---

*Cập nhật: 04/06/2026 · Project: Sun Riser 2026*
