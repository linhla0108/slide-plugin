# SUN.STUDIO — All-Hands Deck Prompt

> Dựng **cả bộ deck All-Hands** (họp toàn công ty) bằng skill **Make a deck** + skill **SUN.STUDIO**.
> Ngôn ngữ hình ảnh: **XO-pattern** (`slides/` + `components/`) — năng lượng, metrics, numbered circles, do/don't.
> Paste đoạn BASE PROMPT bên dưới. Claude sẽ hỏi lại nội dung trước khi dựng.

---

## BASE PROMPT (copy-paste)

```
Dùng skill "Make a deck" (Slide presentation in HTML) + skill SUN.STUDIO (sun-studio-design).

Bạn là designer SUN.STUDIO. Dựng cho tôi MỘT BỘ DECK ALL-HANDS (họp toàn công ty) theo ngôn ngữ
XO-PATTERN (reference deck: slides/, components tái dùng: components/). Tuân thủ:
- Tokens màu + font: colors_and_type.css (chỉ brand colors, Proxima Nova).
- Brand context, voice, visual foundations, iconography: README.md.
- Hard rules: SKILL.md.

NGÔN NGỮ: tiếng Việt, rải English keyword theo brand voice. Headline ALL CAPS, body sentence case,
số viết bằng chữ số (promote số liệu lên cỡ display).

CẤU TRÚC DECK MẶC ĐỊNH (điều chỉnh theo nội dung tôi cấp):
01. Title — "ALL-HANDS" + kỳ (quý/tháng) (XO wash + tab-orange)
02. Agenda — 01–04 (component agenda)
03. Highlights kỳ vừa rồi — 3–4 điểm chính
04. Key metrics — số liệu promote cỡ display, numbered/ratio (component donut/ratio-split)
05. Wins & misses — contrast Do/Don't (semantic green/red đúng chỗ)
06. Product / launch updates — timeline hoặc swimlane (component phase-timeline)
07. Ưu tiên kỳ tới — danh sách action-oriented + mũi tên logic
08. Shout-outs — ghi nhận con người
09. Q&A — numbered Q&A (component)
10. Closing — capsule footer + tagline "SUN RISES. GAME ON."

TRƯỚC KHI DỰNG: nếu thiếu bất kỳ nội dung cụ thể nào ở "Câu hỏi bắt buộc" bên dưới, HỎI TÔI TRƯỚC
bằng form câu hỏi — TUYỆT ĐỐI không bịa số liệu, tên người hay kết quả. Nếu tôi cho phép, có thể
draft cấu trúc mẫu để tôi điền.

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
| 1 | **Kỳ nào** (Q? / tháng? / năm)? | Title + khung thời gian toàn deck |
| 2 | **Key metrics thật** (tên chỉ số + giá trị + so kỳ trước)? | Slide metrics — không bịa số |
| 3 | **Highlights / wins & misses** kỳ vừa rồi? | Slide 03 & 05 |
| 4 | **Product / launch updates** + mốc thời gian? | Slide timeline |
| 5 | **Ưu tiên kỳ tới** (3–5 mục)? | Slide ưu tiên |
| 6 | **Tên người / team** cho shout-outs? | Slide ghi nhận — không bịa tên |
| 7 | Có phần **Q&A** / câu hỏi định sẵn không? | Bật/tắt slide Q&A |
| 8 | Số slide mục tiêu / thời lượng buổi họp? | Co giãn cấu trúc |

---

## RESPONSE FRAME (trước khi code, trả lời đúng dạng này)

```
Hệ thống tôi sẽ dùng:
- Ngôn ngữ hình ảnh: XO-pattern · nền warm paper + XO wash
- Mạch slide: [liệt kê các slide cuối cùng + 1 dòng vai trò mỗi slide]
- Component dùng lại: [agenda / donut / phase-timeline / numbered Q&A …]
- Metrics: số nào promote cỡ display
- Highlight cam: từ khóa "[…]" trên slide trọng tâm
```

Rồi dựng deck, kết thúc bằng `done`.
