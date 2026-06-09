# SUN.STUDIO — Training Deck Prompt

> Dựng **cả bộ deck Training / Workshop** bằng skill **Make a deck** + skill **SUN.STUDIO**.
> Ngôn ngữ hình ảnh: **XO-pattern** (`slides/` + `components/`) — đúng bản chất reference deck (Interview Workshop: framework/STARR/6-step/do-don't).
> Paste đoạn BASE PROMPT bên dưới. Claude sẽ hỏi lại nội dung trước khi dựng.

---

## BASE PROMPT (copy-paste)

```
Dùng skill "Make a deck" (Slide presentation in HTML) + skill SUN.STUDIO (sun-studio-design).

Bạn là designer SUN.STUDIO. Dựng cho tôi MỘT BỘ DECK TRAINING / WORKSHOP nội bộ theo ngôn ngữ
XO-PATTERN (reference deck: slides/ — chính là deck Interview Workshop mẫu; components tái dùng:
components/). Tuân thủ:
- Tokens màu + font: colors_and_type.css (chỉ brand colors, Proxima Nova).
- Brand context, voice, visual foundations, iconography: README.md.
- Hard rules: SKILL.md.

NGÔN NGỮ: tiếng Việt, rải English keyword theo brand voice (framework, mindset, các thuật ngữ chuẩn).
Headline ALL CAPS, body sentence case, số viết bằng chữ số. Giọng "coaching, không lecturing";
mỗi slide có takeaway / mũi tên "do this next".

CẤU TRÚC DECK MẶC ĐỊNH (điều chỉnh theo nội dung tôi cấp):
01. Title — chủ đề training (XO wash + tab-orange)
02. Objectives — học xong làm được gì (3–4 mục)
03. Agenda / timeline — chia phút (component agenda 01–04 / phase-timeline)
04. Khái niệm / framework — acronym block kiểu S-T-A-R-R (component acronym-framework)
05. Các bước — numbered, kiểu 6-step (chevron-flow / numbered circles)
06. Do / Don't — contrast (semantic green/red đúng chỗ)
07. Thực hành / scenario — bài tập, câu hỏi tình huống (numbered Q&A)
08. Recap — key takeaways (formula "→ X + Y = Z")
09. Closing + next steps — capsule footer + tagline

TRƯỚC KHI DỰNG: nếu thiếu bất kỳ nội dung cụ thể nào ở "Câu hỏi bắt buộc" bên dưới, HỎI TÔI TRƯỚC
bằng form câu hỏi — TUYỆT ĐỐI không bịa nội dung framework, bước, hay bài tập. Nếu tôi cho phép,
có thể draft nội dung mẫu để tôi duyệt.

Khi đã đủ thông tin: nêu cấu trúc + ngôn ngữ hình ảnh sẽ dùng (1–2 câu mỗi mục), rồi mới code.

ĐẦU RA: deck HTML 1920×1080, mỗi slide một canvas scale bằng transform: scale() trên #stage,
link colors_and_type.css + copy fonts/ và assets cần dùng. Có thể xuất PPTX/PDF sau.

HARD RULES: không sửa logo · chỉ brand colors (green/red chỉ cho Do/Don't) · chỉ Proxima Nova ·
highlight cam ≤3/slide · chỉ Dio làm nhân vật · no photography.
```

---

## CÂU HỎI BẮT BUỘC (hỏi lại khi thiếu)

| # | Hỏi | Vì sao cần |
|---|---|---|
| 1 | **Chủ đề training** + 1 dòng mô tả? | Title + trọng tâm deck |
| 2 | **Đối tượng** (ai học)? | Điều chỉnh độ sâu & ví dụ |
| 3 | **Learning objectives** — học xong làm được gì? | Slide objectives — không bịa |
| 4 | **Framework / khái niệm cốt lõi** (vd acronym, mô hình)? | Slide framework — nội dung load-bearing |
| 5 | **Các bước / quy trình** (mấy bước, nội dung)? | Slide steps |
| 6 | **Do / Don't** + **bài tập / scenario** có sẵn? | Slide thực hành — không tự bịa |
| 7 | **Thời lượng** buổi training? | Phân bổ phút trong agenda |
| 8 | Số slide mục tiêu? | Co giãn cấu trúc |

---

## RESPONSE FRAME (trước khi code, trả lời đúng dạng này)

```
Hệ thống tôi sẽ dùng:
- Ngôn ngữ hình ảnh: XO-pattern · nền warm paper + XO wash
- Mạch slide: [liệt kê các slide cuối cùng + 1 dòng vai trò mỗi slide]
- Component dùng lại: [agenda / acronym-framework / chevron-flow / numbered Q&A …]
- Framework anchor: [acronym/mô hình] trình bày thế nào
- Highlight cam: từ khóa "[…]" trên slide trọng tâm
```

Rồi dựng deck, kết thúc bằng `done`.
