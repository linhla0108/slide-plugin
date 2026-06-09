# SUN.STUDIO — Onboarding Deck Prompt

> Dựng **cả bộ deck Onboarding** (chào & dẫn dắt SUNer mới) bằng skill **Make a deck** + skill **SUN.STUDIO**.
> Ngôn ngữ hình ảnh: **editorial / tactile** (`slides-v2/` + `slide-kit/SLIDE_GUIDELINES.md`) — ấm, kể chuyện, chào mừng.
> Paste đoạn BASE PROMPT bên dưới. Claude sẽ hỏi lại nội dung trước khi dựng.

---

## BASE PROMPT (copy-paste)

```
Dùng skill "Make a deck" (Slide presentation in HTML) + skill SUN.STUDIO (sun-studio-design).

Bạn là designer SUN.STUDIO. Dựng cho tôi MỘT BỘ DECK ONBOARDING nội bộ để chào và dẫn dắt
một SUNer mới, theo ngôn ngữ EDITORIAL / TACTILE (reference: slides-v2/, quy tắc:
slide-kit/SLIDE_GUIDELINES.md). Tuân thủ:
- Tokens màu + font: colors_and_type.css (chỉ brand colors, Proxima Nova + Times italic làm giọng phụ).
- Brand context, voice, visual foundations: README.md.
- Hard rules: SKILL.md.

NGÔN NGỮ: tiếng Việt, rải English keyword theo brand voice. Headline ALL CAPS, body sentence case,
số viết bằng chữ số.

CẤU TRÚC DECK MẶC ĐỊNH (điều chỉnh theo nội dung tôi cấp):
01. Cover — "WELCOME TO SUN.STUDIO" + tên người mới (DIO m2-wink bleed góc dưới phải)
02. SUN.STUDIO là ai — studio game mobile, game ta ship (ngắn, mạnh)
03. Giá trị cốt lõi — Fast & Faster · Quality · Responsibility (2×2 list, italic sub)
04. Tính cách thương hiệu — Friendly · Skilled · Reliable
05. Gặp Dio & ngôn ngữ thương hiệu (XO, màu, giọng nói)
06. Cơ cấu tổ chức / team của bạn
07. Công cụ & quy trình (accounts, tools, cách làm việc)
08. Kế hoạch 30-60-90 ngày (3 cột mốc, action-oriented)
09. Ai để hỏi — buddy + danh bạ liên hệ
10. Closing — "SUN RISES. GAME ON." + lời chào (ink slide, DIO m2-wink + P.S.)

TRƯỚC KHI DỰNG: nếu thiếu bất kỳ nội dung cụ thể nào ở "Câu hỏi bắt buộc" bên dưới, HỎI TÔI TRƯỚC
bằng form câu hỏi — TUYỆT ĐỐI không bịa tên, ngày, tool hay danh bạ. Nếu tôi cho phép, có thể draft
nội dung mẫu để tôi duyệt.

Khi đã đủ thông tin: nêu cấu trúc + ngôn ngữ hình ảnh sẽ dùng (1–2 câu mỗi mục), rồi mới code.

ĐẦU RA: deck HTML 1920×1080, mỗi slide một canvas scale bằng transform: scale() trên #stage,
link colors_and_type.css + copy fonts/ và assets cần dùng (logo, dio). Có thể xuất PPTX/PDF sau.

HARD RULES: không sửa logo · chỉ brand colors · chỉ Proxima Nova (Times italic cho giọng phụ) ·
highlight cam ≤3/slide · chỉ Dio làm nhân vật · no photography.
```

---

## CÂU HỎI BẮT BUỘC (hỏi lại khi thiếu)

| # | Hỏi | Vì sao cần |
|---|---|---|
| 1 | **Tên người mới** (và cách xưng hô)? | Cover + lời chào cá nhân hóa |
| 2 | **Vai trò / team** họ sẽ vào? | Slide cơ cấu + 30-60-90 |
| 3 | **Ngày bắt đầu / tuần đầu**? | Mạch 30-60-90 |
| 4 | **Công cụ & tài khoản** cụ thể (Slack, Jira, Figma, repo…)? | Slide công cụ — không bịa |
| 5 | **Buddy / người liên hệ** + kênh? | Slide "ai để hỏi" |
| 6 | Các **mốc 30-60-90 ngày** có sẵn chưa, hay tôi draft để bạn duyệt? | Nội dung load-bearing, không tự bịa |
| 7 | Có muốn nhấn mạnh phần nào của thương hiệu (Dio, XO, giọng "Hire-to-Develop")? | Điều chỉnh trọng tâm |
| 8 | Số slide mục tiêu / độ dài mong muốn? | Co giãn cấu trúc mặc định |

---

## RESPONSE FRAME (trước khi code, trả lời đúng dạng này)

```
Hệ thống tôi sẽ dùng:
- Ngôn ngữ hình ảnh: editorial/tactile · nền cream (content), ink (open/close)
- Mạch slide: [liệt kê các slide cuối cùng + 1 dòng vai trò mỗi slide]
- Anchor mỗi slide: [display headline / numeral / DIO]
- DIO: pose + vị trí (bleed/tilt)
- Highlight cam: từ khóa "[…]" trên các slide trọng tâm
```

Rồi dựng deck, kết thúc bằng `done`.
