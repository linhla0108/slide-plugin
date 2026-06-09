# SUN.STUDIO — Policy Announcement Deck Prompt

> Dựng **cả bộ deck Policy Announcement** (công bố chính sách / thay đổi quy định) bằng skill **Make a deck** + skill **SUN.STUDIO**.
> Ngôn ngữ hình ảnh: **editorial / tactile** (`slides-v2/` + `slide-kit/SLIDE_GUIDELINES.md`) — trang trọng, one-anchor, dùng ink slide tạo sức nặng.
> Paste đoạn BASE PROMPT bên dưới. Claude sẽ hỏi lại nội dung trước khi dựng.

---

## BASE PROMPT (copy-paste)

```
Dùng skill "Make a deck" (Slide presentation in HTML) + skill SUN.STUDIO (sun-studio-design).

Bạn là designer SUN.STUDIO. Dựng cho tôi MỘT BỘ DECK CÔNG BỐ CHÍNH SÁCH (policy announcement)
nội bộ, theo ngôn ngữ EDITORIAL / TACTILE (reference: slides-v2/, quy tắc:
slide-kit/SLIDE_GUIDELINES.md). Giọng trang trọng, rõ ràng, mỗi slide một thông điệp; dùng ink slide
ở các điểm cần sức nặng. Tuân thủ:
- Tokens màu + font: colors_and_type.css (chỉ brand colors, Proxima Nova + Times italic làm giọng phụ).
- Brand context, voice, visual foundations: README.md.
- Hard rules: SKILL.md.

NGÔN NGỮ: tiếng Việt, rải English keyword khi là thuật ngữ chuẩn. Headline ALL CAPS, body sentence
case, số/ngày viết bằng chữ số. Giọng "Sincerity + Competence" — thành thật, rõ, có takeaway.

CẤU TRÚC DECK MẶC ĐỊNH (điều chỉnh theo nội dung tôi cấp):
01. Cover — tên chính sách + ngày hiệu lực (ink slide, anchor là tên policy)
02. Vì sao thay đổi — bối cảnh / lý do (ngắn, thành thật)
03. Điều gì thay đổi — THE ONE MESSAGE (1 anchor lớn, highlight cam 1 từ khóa)
04. Chi tiết — nội dung cụ thể, áp dụng cho ai
05. Bạn cần làm gì — action items (checklist, imperative)
06. Timeline / hiệu lực — mốc ngày (stamp/tape tactile)
07. FAQ / câu hỏi thường gặp + đầu mối liên hệ
08. Closing — nhắc lại thông điệp + kênh hỏi đáp

TRƯỚC KHI DỰNG: nếu thiếu bất kỳ nội dung cụ thể nào ở "Câu hỏi bắt buộc" bên dưới, HỎI TÔI TRƯỚC
bằng form câu hỏi — TUYỆT ĐỐI không bịa nội dung chính sách, ngày hiệu lực, phạm vi hay đầu mối.
Chính sách là nội dung nhạy cảm: chỉ dùng đúng câu chữ tôi cấp; nếu cần diễn đạt lại, xin phép để tôi duyệt.

Khi đã đủ thông tin: nêu cấu trúc + ngôn ngữ hình ảnh sẽ dùng (1–2 câu mỗi mục), rồi mới code.

ĐẦU RA: deck HTML 1920×1080, mỗi slide một canvas scale bằng transform: scale() trên #stage,
link colors_and_type.css + copy fonts/ và assets cần dùng. Có thể xuất PPTX/PDF sau.

HARD RULES: không sửa logo · chỉ brand colors · chỉ Proxima Nova (Times italic cho giọng phụ) ·
highlight cam ≤3/slide · chỉ Dio làm nhân vật (dùng tiết chế cho chủ đề trang trọng) · no photography.
```

---

## CÂU HỎI BẮT BUỘC (hỏi lại khi thiếu)

| # | Hỏi | Vì sao cần |
|---|---|---|
| 1 | **Tên chính sách** / tiêu đề công bố? | Cover + anchor |
| 2 | **Ngày hiệu lực** (và ngày công bố)? | Cover + timeline — không bịa ngày |
| 3 | **Điều gì thay đổi** — câu chữ chính xác? | Slide THE ONE MESSAGE — nội dung nhạy cảm |
| 4 | **Phạm vi áp dụng** — ai/bộ phận nào chịu ảnh hưởng? | Slide chi tiết |
| 5 | **Action items** — nhân viên cần làm gì, hạn nào? | Slide hành động |
| 6 | **FAQ** có sẵn? **Đầu mối liên hệ** (người/kênh)? | Slide FAQ/liên hệ |
| 7 | Mức độ trang trọng / có dùng Dio không? | Điều tiết tactile & mascot |
| 8 | Số slide mục tiêu? | Co giãn cấu trúc |

---

## RESPONSE FRAME (trước khi code, trả lời đúng dạng này)

```
Hệ thống tôi sẽ dùng:
- Ngôn ngữ hình ảnh: editorial/tactile · nền ink (cover/closing), cream (content)
- Mạch slide: [liệt kê các slide cuối cùng + 1 dòng vai trò mỗi slide]
- THE ONE MESSAGE: "[câu thay đổi cốt lõi]" — highlight cam từ khóa "[…]"
- DIO: dùng/không (tiết chế cho chủ đề trang trọng)
- Tactile: stamp/tape ở slide timeline
```

Rồi dựng deck, kết thúc bằng `done`.
