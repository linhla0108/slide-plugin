# Hướng Dẫn Sử Dụng Plugin

Hướng dẫn nhanh, dễ hiểu để tạo slide bằng **ứng dụng Claude trên máy tính**.
Bạn không cần biết kỹ thuật — chỉ cần trò chuyện, Claude sẽ làm phần còn lại.

> **Mẹo đọc tài liệu:** Mỗi phần đều có **khung hội thoại mẫu** (bạn gõ gì,
> Claude trả lời gì), **sơ đồ các bước**, và **chỗ để chèn ảnh chụp màn hình**
> thật của bạn.

---

## Trước Khi Bắt Đầu

- Bạn chỉ cần mở **ứng dụng Claude trên máy tính**.
- Không cần cài đặt gì cả. Chỉ cần nói chuyện với Claude bằng lời bình thường.
- Chuẩn bị sẵn nội dung của bạn (văn bản, ghi chú, hoặc file muốn biến thành
  slide).

Vậy là xong. Giờ hãy chọn việc bạn muốn làm.

<!--
  CHÈN ẢNH: Màn hình chính của ứng dụng Claude với ô chat trống.
  ![Màn hình chính của Claude](./images/01-man-hinh-chinh.png)
-->

---

## 1. Tạo Slide — "Slide Generator"

Dùng khi bạn muốn có một bài thuyết trình hoàn toàn mới.

### Sơ đồ các bước

```text
  ┌────────────────────────────────────┐
  │ 1. Bạn nói:                        │
  │    "Tạo cho tôi bài thuyết trình…" │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 2. Claude hỏi vài câu đơn giản     │◀──────────┐
  └──────────────┬─────────────────────┘           │
                 ▼                                  │
  ┌────────────────────────────────────┐           │
  │ 3. Claude đưa bản kế hoạch ngắn    │           │
  └──────────────┬─────────────────────┘           │
                 ▼                                  │
            ┌─────────┐   "Đổi lại…"                │
            │ Bạn xem │ ────────────────────────────┘
            │ & duyệt │
            └────┬────┘
                 │ "Làm đi"
                 ▼
  ┌────────────────────────────────────┐
  │ 4. Claude dựng slide               │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 5. Nhận file PowerPoint (.pptx)    │
  │    chỉnh sửa được ✅               │
  └────────────────────────────────────┘
```

### Hội thoại mẫu

```text
┌─────────────────────────────────────────────────────────────┐
│  BẠN:                                                        │
│  Tạo cho tôi bài thuyết trình 5 slide về chương trình        │
│  đào tạo nhân viên mới.                                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Tuyệt! Mình hỏi nhanh vài câu nhé:                          │
│  • Đối tượng xem là nhân viên mới, đúng không? (gợi ý: Đúng) │
│  • Bạn muốn phong cách trẻ trung, năng động? (gợi ý: Có)     │
│  Bạn chỉ cần trả lời "đúng" hoặc chọn gợi ý.                 │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BẠN:  Đúng hết.                                             │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Đây là kế hoạch 5 slide:                                    │
│   1. Lời chào mừng   2. Mục tiêu   3. Lịch trình             │
│   4. Người liên hệ   5. Bước tiếp theo                       │
│  Bạn duyệt thì mình bắt đầu dựng nhé?                        │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BẠN:  Làm đi.                                               │
└─────────────────────────────────────────────────────────────┘
```

**Hoặc nếu bạn đã có ghi chú/file sẵn:**

> "Biến tài liệu này thành bộ slide." *(rồi đính kèm hoặc dán nội dung của bạn)*

### Bạn sẽ nhận được gì

1. Claude hỏi vài câu đơn giản (chủ đề, số slide, phong cách). Mỗi câu đều có
   sẵn gợi ý — bạn chỉ cần nói "đúng" hoặc chọn.
2. Claude đưa bản kế hoạch ngắn trước khi dựng. Xem qua rồi nói **"làm đi"** khi
   thấy ổn.
3. Claude dựng slide và đưa cho bạn một **file PowerPoint (.pptx)** mà bạn tự mở
   và chỉnh sửa được.

**Cần biết thêm:**

- Nếu bạn nói "PowerPoint", "PPT" hay "PPTX", bạn sẽ nhận file PowerPoint chỉnh
  sửa được (mặc định).
- Bạn luôn có thể yêu cầu sửa: *"Rút gọn slide 3"* hoặc *"Dùng màu sáng hơn."*

<!--
  CHÈN ẢNH: Claude đang hỏi lại các câu đơn giản + bản kế hoạch slide.
  ![Claude hỏi và đưa kế hoạch](./images/02-tao-slide.png)

  CHÈN ẢNH: File PowerPoint .pptx kết quả đã mở lên.
  ![File PowerPoint kết quả](./images/03-ket-qua-pptx.png)
-->

---

## 2. Lấy Một Phần Từ Slide — "Component Extractor"

Dùng khi bạn thích **một phần của slide có sẵn** và muốn dùng lại — ví dụ một
biểu đồ, khối tiêu đề, hình nền, hoặc cả một slide.

### Sơ đồ các bước

```text
  ┌────────────────────────────────────┐
  │ 1. Bạn nói:                        │
  │    "Lấy phần … từ slide …"         │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 2. Cho biết file nào + phần nào    │◀────────────┐
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
  ┌────────────────────────────────────┐             │
  │ 3. Claude tách phần đó ra          │             │
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
  ┌────────────────────────────────────┐             │
  │ 4. Claude cho bạn xem trước        │             │
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
            ┌─────────┐  "Không phải cái này"         │
            │ Bạn xem │ ─────────────────────────────┘
            │ & duyệt │
            └────┬────┘
                 │ "Lưu lại"
                 ▼
  ┌────────────────────────────────────┐
  │ 5. Phần đó được lưu để dùng lại ✅ │
  └────────────────────────────────────┘
```

### Hội thoại mẫu

```text
┌─────────────────────────────────────────────────────────────┐
│  BẠN:                                                        │
│  Lấy biểu đồ màu cam ở slide 4 và lưu lại để tôi dùng lại.   │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Được! Mình đã tách biểu đồ màu cam ở slide 4 ra.            │
│  Đây là bản xem trước 👇  Bạn muốn mình lưu lại chứ?         │
│  [ xem trước biểu đồ ]                                       │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BẠN:  Đúng rồi, lưu lại đi.                                 │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Đã lưu! Lần sau bạn chỉ cần nói là mình chèn lại vào        │
│  slide mới cho bạn.                                          │
└─────────────────────────────────────────────────────────────┘
```

**Hoặc lấy cả bộ:**

> "Lưu mọi slide trong file này thành các phần dùng lại được."
> *(rồi chia sẻ file)*

### Bạn sẽ nhận được gì

1. Cho Claude biết **file nào** và **phần nào** bạn muốn (một slide, một dải
   trang, hoặc một thứ cụ thể như "phần chân trang" hay "tiêu đề").
2. Claude tách phần đó ra và cho bạn xem trước.
3. Bạn nói **"đúng, lưu lại"**, và nó được lưu để bạn (hoặc Claude) chèn vào các
   slide sau này.

**Cần biết thêm:**

- Việc này chỉ xảy ra khi bạn yêu cầu — Claude không tự ý lấy phần nào cả.
- Bạn duyệt từng phần trước khi nó được lưu.

<!--
  CHÈN ẢNH: Claude hiển thị bản xem trước của phần được tách ra.
  ![Xem trước phần được tách](./images/04-xem-truoc-component.png)
-->

---

## Mẹo Đơn Giản

- **Nói chuyện bình thường.** Không cần lệnh đặc biệt — viết thành câu đầy đủ là
  tốt nhất.
- **Làm từng việc một.** Tạo slide *hoặc* tách phần, xong rồi mới sang việc tiếp.
- **Nói "đúng" hoặc "đổi lại".** Claude luôn hỏi bạn trước các bước lớn, nên
  không có gì xảy ra mà chưa được bạn đồng ý.
- **Bí quá?** Cứ gõ *"giúp tôi bắt đầu"* và Claude sẽ hướng dẫn từng bước.

Vậy là bạn đã sẵn sàng. Chúc bạn làm slide vui vẻ!

---

### Ghi chú cho người chèn ảnh

Những dòng `<!-- CHÈN ẢNH ... -->` ở trên là chỗ gợi ý để dán ảnh chụp màn hình
thật. Cách thêm ảnh:

1. Chụp màn hình ứng dụng Claude theo đúng mô tả.
2. Lưu ảnh vào thư mục `docs/images/` (đặt tên như gợi ý, ví dụ
   `02-tao-slide.png`).
3. Bỏ phần `<!-- -->` để dòng `![...](...)` hiện ra thành ảnh.
