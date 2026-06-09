# v2 — Nhật ký quy trình: Polish 4 slide đầu "Be Professional @ SUN.STUDIO"

Tài liệu này liệt kê toàn bộ **skill (kỹ năng)**, **tool (công cụ)** đã dùng và **cách xử lý tình huống** trong quá trình làm việc.

---

## 1. Design System đã dùng

| Mục | Chi tiết |
|---|---|
| **Tên** | SUN.STUDIO Design System |
| **Vị trí** | `/projects/9360d42d-.../` (project nguồn, chỉ đọc) |
| **Áp dụng** | Mọi màu, font, spacing, component đều bám theo hệ thống này — không tự bịa |

**Token gốc đã tham chiếu:** `--sun-orange`, `--sun-blue`, `--ink`, `--xo-paper`, `--font-display` (Proxima Nova), shadow offset cứng, mẫu nền **XO grid** xoay -24°, **title tab cam bất đối xứng**, eyebrow tab mực đen.

---

## 2. Skill (kỹ năng) đã sử dụng

| Skill | Dùng để làm gì |
|---|---|
| **Make a deck** | Hiểu cấu trúc deck dạng slide HTML, dùng `deck-stage` web component, mỗi slide là 1 `<section>` con |
| **Hi-fi design** | Quy trình thiết kế: đọc design context → hỏi → tạo nhiều phương án → trình bày |
| **Design canvas (starter component)** | Trình bày 3 phương án/slide cạnh nhau để so sánh (pan/zoom, focus fullscreen) |
| **Đọc design system (binding)** | Bắt buộc: explore design system SUN.STUDIO trước khi vẽ, copy font/màu/pattern thật |

---

## 3. Tool (công cụ) đã sử dụng

### Khám phá & đọc
| Tool | Mục đích |
|---|---|
| `list_files` | Liệt kê cấu trúc project hiện tại + project design system |
| `read_file` | Đọc deck hiện tại, `deck.css`, `deck-stage.js`, slide gốc (01-title, 12-thank-you), slides-v2 |
| `grep` | (tìm pattern khi cần) |

### Tạo & sửa file
| Tool | Mục đích |
|---|---|
| `write_file` | Tạo `variations.css`, `slides-data.js`, `Variations.html`, ghi lại deck chính |
| `str_replace_edit` | Tinh chỉnh CSS (cỡ chữ title, khoảng cách Dio, gnum…) theo nhiều edit gộp 1 lần |
| `copy_files` | Copy bản backup `_src.html`, copy starter component |
| `copy_starter_component` | Lấy `design_canvas.jsx` làm khung so sánh phương án |
| `delete_file` | Dọn file tạm (`_src`, `_harness`, `_check`, screenshots) |

### Kiểm tra & xác minh
| Tool | Mục đích |
|---|---|
| `show_html` | Render file trong iframe để xem |
| `eval_js` | **Công cụ chủ lực để verify** — đo toạ độ DOM, kiểm tra overflow/va chạm, đếm phần tử |
| `get_webview_logs` | Kiểm tra lỗi console |
| `done` | Mở file cho user + chạy slide validators + trả lỗi console |
| `fork_verifier_agent` | Spawn agent nền kiểm tra độc lập (cả full sweep lẫn directed check) |
| `run_script` | Thử build harness render slide ngoài shadow DOM |

### Tương tác với user
| Tool | Mục đích |
|---|---|
| `questions_v2` | Hỏi hướng sáng tạo cho từng slide (độ "bold", hướng title/agenda/cards, số phương án…) |
| `update_todos` | Lập & cập nhật danh sách việc |
| `snip` | Dọn ngữ cảnh các giai đoạn đã xong |

---

## 4. Cách xử lý tình huống (vấn đề → giải pháp)

### Tình huống 1 — Screenshot không chụp được nội dung slide
- **Vấn đề:** Công cụ screenshot không rasterize được layout của `deck-stage` (shadow DOM + scale + filter) → ảnh trả về trống phần nội dung.
- **Cách xử lý:**
  1. Thử nhiều cách: harness DOM phẳng, scale thủ công, toggle từng slide.
  2. Khi vẫn không chụp được → **chuyển sang xác minh bằng `eval_js`**: đo `getBoundingClientRect()`, kiểm tra opacity, đếm phần tử, tính overflow/va chạm bằng số liệu thay vì mắt nhìn.
  3. Báo rõ cho user giới hạn này và khẳng định "sẽ hiển thị đúng trên trình duyệt".

### Tình huống 2 — Tên file có ký tự đặc biệt (`@`, khoảng trắng)
- **Vấn đề:** `run_script` báo lỗi `disallowed characters` với tên file `Be Professional @ SUN.STUDIO.html`.
- **Cách xử lý:** Dùng `copy_files` tạo bản sao tên an toàn `_src.html` để thao tác bằng script.

### Tình huống 3 — DesignCanvas re-render xoá node chèn động
- **Vấn đề:** Lưới XO và barcode chèn bằng JS sau render bị React (DesignCanvas) re-render xoá mất.
- **Cách xử lý:** **Bake sẵn** markup XO grid + barcode vào chuỗi HTML (deterministic, không random) trong `slides-data.js` — không còn gì để chèn động.

### Tình huống 4 — Câu hỏi định hướng bị timeout
- **Vấn đề:** Form `questions_v2` không nhận được trả lời (timeout).
- **Cách xử lý:** Chủ động đọc design system để lấy **title treatment chuẩn** (paper + XO) và tự quyết theo default, vẫn bám brand.

### Tình huống 5 — Tiêu đề slide va chạm mascot / pill
- **Vấn đề:** Dòng "BE PROFESSIONAL" chạm Dio; title slide 3 chạm pill góc phải.
- **Cách xử lý:** Đo bằng `eval_js`, giảm cỡ chữ (150→132px), tăng khoảng hở mascot, thêm `max-width` cho `.c-title` → đo lại xác nhận clear 37px.

### Tình huống 6 — Slide validators báo 11 findings
- **Vấn đề:** Cảnh báo chữ nhỏ < 24px và phần tử chồng nhau.
- **Cách xử lý:** Phân loại:
  - **Sửa thật:** title↔pill, card number↔heading, nâng body card lên 24px.
  - **Cố ý giữ:** micro-label theo brand spec (pill, kicker, nhãn ngày vé 16–20px) và watermark mờ `#1` của slide gốc #10.
  - Giải thích rõ cho user cái nào sửa, cái nào giữ.

### Tình huống 7 — Xác minh cuối khi không screenshot được
- **Cách xử lý:** Dùng `fork_verifier_agent` ở chế độ **directed check**, kèm hướng dẫn rõ "đừng báo slide trống từ screenshot, hãy verify bằng eval_js" (đếm 208 ô XO, 132 thanh barcode, 4 section, navigate goTo).

---

## 5. Kết quả chốt

| Slide | Phương án user chọn |
|---|---|
| **#1 Title** | **A** — nền giấy ấm + lưới XO (canonical), eyebrow mực, title tab cam |
| **#2 Agenda** | **C** — boarding-pass strips (stub số · topic · barcode "pass") |
| **#3 Meeting cards** | **A** — gradient đa sắc đậm, chữ trắng |
| **#4** | Giữ nguyên slide Do/Don't gốc (#10) |

**File chính:** `Be Professional @ SUN.STUDIO.html`
**File so sánh phương án:** `Variations.html` (vẫn giữ để xem lại các option khác)
**File hỗ trợ:** `variations.css`, `slides-data.js`
