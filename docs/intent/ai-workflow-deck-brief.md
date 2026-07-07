# Brief Deck: AI WORKFLOW — LÀM VIỆC THÔNG MINH HƠN VỚI AI

> Brief nội dung cho deck chia sẻ nội bộ. Xác nhận intent 2026-07-06. Bản v3 — hoàn chỉnh, toàn bộ mục cần điền đã chốt.

## Intent

- **Outcome:** Deck 9 slides về AI workflow (Claude apps + AI tools trong công việc hàng ngày), content ngắn gọn, tiếng Việt.
- **Audience:** Đồng nghiệp cùng team, mix dev + non-dev.
- **Mục tiêu:** Sau buổi trình bày, người nghe biết chọn app/model/skill phù hợp và thử dùng ngay tuần này.
- **Out of scope:** Không render slide ngay; không pitch ROI cho lãnh đạo; không hướng dẫn setup chi tiết.

## Quy tắc thiết kế (SUN.STUDIO)

- **Nền:** theo brand guideline — KHÔNG ép so le cam/trắng. Nền mỗi slide bám theo component/template đã chọn và canonical wash của brand (paper ấm `#FFFDF8`, trắng, hoặc gradient cam gốc `#FF5533` khi phù hợp intent). Không dùng hoạ tiết/pattern nền; layout pattern chung (card, chevron flow, numbered steps, capsule) vẫn dùng bình thường.
- **Canvas:** 1920×1080 · **Font:** Proxima Nova.
- **Text:** trên nền cam = trắng; trên nền trắng = ink `#171717`, accent orange `#FF5533` / blue `#3333FF`. Green/red chỉ semantic Do/Don't.
- **Voice:** chân thành, súc tích, action-oriented; "chúng ta"/"bạn", giữ keyword tiếng Anh canonical.
- **Chung:** headline/kicker UPPERCASE, body sentence case; 1 visual anchor/slide; DIO chỉ dùng title/closing.
- **Highlight:** label uppercase blue là styling hệ thống (không tính highlight); highlight đậm orange chỉ 1-3 điểm nhấn nội dung/slide.
- Dựng thật: import `colors_and_type.css` + fonts bundled từ `sun-studio-design-system`; gradient cam build từ token `#FF5533`, không chế màu ngoài hệ.

## Cấu trúc

| # | Slide |
|---|-------|
| 1 | Title — hook |
| 2 | AI làm được gì cho từng người |
| 3 | Ví dụ thật (slide đinh) |
| 4 | Chọn đúng app: Chat / Cowork / Code |
| 5 | Chọn đúng model + tier được cấp |
| 6 | Dùng đúng cách: 4 nguyên tắc |
| 7 | Skills — vũ khí bí mật |
| 8 | Mẹo dùng Claude như dân pro (+ nâng cao sơ qua) |
| 9 | Closing — CTA + bắt đầu ở đâu |

> Nền từng slide do component/template đã chọn quyết định (theo brand guideline), không cố định cam/trắng.

---

## Slide 1 — Title: "BẠN ĐANG TỐN THỜI GIAN VÀO VIỆC GÌ?"

- **Content:** Kicker "AI WORKFLOW · INTERNAL SHARING" + headline hook + sub: "AI không thay bạn — nó xử lý phần lặp lại để bạn tập trung phần cần suy nghĩ."
- **Visual:** text theo nền của component (nền đậm/cam = trắng, nền sáng = ink); DIO pose `m2-wink` làm anchor; logo master `logo.png` (không có bản trắng riêng — đặt trong badge/khối trắng nếu tương phản kém với nền), đúng clear space 2x letter-O.

## Slide 2 — AI LÀM ĐƯỢC GÌ CHO TỪNG NGƯỜI

- **Content:** 3 mục theo vai trò, mỗi mục 1 dòng:
  - **DEV** — Claude Code: viết/review code, debug, tự động hoá.
  - **CONTENT/DESIGN** — draft nội dung, brief slide, chỉnh tone.
  - **MỌI NGƯỜI** — tổng hợp tài liệu, soạn email, brainstorm.
- **Visual:** 3 card/cột, label vai trò uppercase blue, text ink; grid = anchor. Không DIO.

## Slide 3 — VÍ DỤ THẬT TỪ CHÚNG TA *(slide đinh)*

- **Content:** case thật — chính deck này được làm bằng Claude:
  - **Input:** 1 câu yêu cầu "viết brief deck AI workflow cho team".
  - **AI làm gì:** interview làm rõ yêu cầu → đọc brand guideline trong repo → viết brief → tự review bằng subagent → search docs kiểm chứng thông tin.
  - **Output:** brief 9 slides hoàn chỉnh, đúng brand, có nguồn kiểm chứng.
  - **Thời gian:** ~30 phút thay vì nửa ngày.
- **Punchline:** "Deck bạn đang xem chính là sản phẩm của quy trình này."
- **Visual:** chevron flow 4 bước dạng card nổi trên nền, text ink trong card; card tương phản rõ với nền của component; "30 phút thay vì nửa ngày" = highlight đậm.
- **Speaker note:** demo live 2-3 phút nếu được (mở lại session Claude cho xem).

## Slide 4 — CHỌN ĐÚNG APP: CHAT · COWORK · CODE

- **Content:** mở đầu 1 dòng: "**Claude Desktop app** phù hợp mọi đối tượng — 3 tab, chọn theo việc. **Claude Code** (terminal) phù hợp nhất cho dev."
  - **CHAT** — hỏi đáp, brainstorm, soạn thảo; việc nhanh, không đụng file.
  - **COWORK** — Claude làm việc trực tiếp trên thư mục/file bạn cho phép (đọc, tạo, sửa tài liệu, dùng app trên máy); dành cho knowledge work, non-dev dùng thoải mái.
  - **CODE** — giao diện đồ hoạ của Claude Code: sửa codebase, xem diff, accept/reject; dành cho dev.
- **Chốt 1 dòng:** "Không code mà cần làm trên file → Cowork · Làm phần mềm → Code · Còn lại → Chat."
- **Visual:** strip 3 card ngang Chat · Cowork · Code, label uppercase blue, mỗi card đúng 1 dòng mô tả + 1 dòng "dành cho ai"; highlight orange duy nhất ở "phù hợp mọi đối tượng". Không DIO.

## Slide 5 — CHỌN ĐÚNG MODEL CHO ĐÚNG VIỆC

- **Content:** nguyên tắc: "Model mạnh nhất ≠ lựa chọn tốt nhất — chọn theo độ khó và tốc độ cần." Kèm 3 tier, mỗi tier ví dụ cả dev lẫn non-dev:
  - **NHANH & NHẸ** (Claude Haiku) — tóm tắt meeting notes, soạn email, dịch, hỏi đáp nhanh, brainstorm ý tưởng.
  - **CÂN BẰNG** (Claude Sonnet) — mặc định hàng ngày: viết code, draft content, phân tích tài liệu dài.
  - **MẠNH NHẤT** (Claude Opus / Fable) — bài toán khó: debug hóc búa, thiết kế hệ thống, phân tích chiến lược nhiều bước. Chậm và tốn hơn — dùng khi thật cần.
- **Tier được cấp (quota công ty):** Lead/manager và dev dùng AI nhiều → **tier premium**; nhu cầu vừa phải → **tier standard**; tần suất rất thấp → đề xuất **tier free**.
- **Visual:** 3 card dạng thang tăng dần nổi trên nền, label tier uppercase; dải quota mảnh dưới cùng, text tương phản với nền. Highlight đậm ở dòng nguyên tắc.

## Slide 6 — DÙNG ĐÚNG CÁCH: 4 NGUYÊN TẮC

- **Content:**
  1. Kiểm tra output — bạn chịu trách nhiệm kết quả cuối.
  2. Không đưa dữ liệu nhạy cảm — thông tin khách hàng, hợp đồng, lương thưởng, credentials; phân vân thì hỏi lead trước.
  3. Prompt cụ thể = kết quả tốt (context, format, ví dụ mẫu).
  4. **Prompt bằng tiếng Anh** khi có thể — output thường chính xác và phong phú hơn; yêu cầu "trả lời bằng tiếng Việt" nếu cần.
- **Visual:** số thứ tự orange, text ink; Do/Don't mới dùng green/red semantic.

## Slide 7 — SKILLS — VŨ KHÍ BÍ MẬT CỦA CLAUDE

- **Content:**
  - **Skill là gì:** gói kiến thức + quy trình đóng sẵn — Claude tự đọc khi task khớp, không cần prompt dài. Dùng được cả trong Cowork lẫn Code.
  - **Tìm:** plugin marketplace (`/plugins` trong Code), repo skill của team, cộng đồng.
  - **Cài:** thêm vào `.claude/skills/` của repo hoặc cài plugin; skill tự kích hoạt theo mô tả.
  - **Dùng:** gọi `/tên-skill` hoặc để Claude tự chọn khi yêu cầu khớp.
  - **Ví dụ thật từ team:** `slide-generator` (dựng slide theo brand), `interview-me` (làm rõ yêu cầu trước khi làm), `deep-research` (nghiên cứu đa nguồn có kiểm chứng), `caveman` (tiết kiệm token).
  - **Quy tắc vàng:** *"Mỗi repo mới — tìm skill phù hợp TRƯỚC khi bắt đầu, để tối ưu performance và hạn chế agent overwhelm."*
- **Visual:** timeline ngang 3 bước Tìm → Cài → Dùng (khác nhịp card của slide 3/5), ví dụ skill dạng tag nhỏ; quy tắc vàng là capsule nổi bật cuối slide (chữ tương phản với capsule) = highlight chính.

## Slide 8 — MẸO DÙNG CLAUDE NHƯ DÂN PRO

- **Content:** 5 mẹo, mỗi mẹo 1 dòng (mẹo 1-2 cho dev/Code user, 3-5 cho mọi người):
  1. **Tạo memory/note cho project** *(dev)* — file `CLAUDE.md` ghi context, convention; Claude tự đọc mỗi session, khỏi giải thích lại.
  2. **Log mỗi task đã làm** *(dev)* — bảo Claude append log sau mỗi việc; session sau nối tiếp ngay.
  3. **Plan trước, làm sau** — việc lớn thì yêu cầu Claude lên plan, duyệt xong mới cho làm.
  4. **Lưu prompt tốt thành template** — kèm 1 ví dụ mẫu khi cần format cố định (report, email, slide).
  5. **Đổi chủ đề = session mới** — context sạch cho kết quả tập trung hơn hội thoại dài.
- **Nâng cao (trong Claude Desktop app — Cowork, giới thiệu sơ):** *Scheduled tasks* — hẹn giờ Claude tự chạy việc định kỳ (báo cáo sáng, tổng hợp tuần); *Dispatch* — giao task từ điện thoại, máy tính ở nhà/văn phòng tự chạy và trả kết quả.
- **Visual:** danh sách 5 mẹo số orange, tag nhỏ "DEV" blue ở mẹo 1-2; footer strip mảnh "NÂNG CAO · CLAUDE DESKTOP APP" label blue. Không DIO.

## Slide 9 — Closing: "THỬ 1 LẦN TUẦN NÀY"

- **Content:**
  - **Bắt đầu ngay:** mở **Claude Desktop app** → tab Chat hoặc Cowork; chưa có tài khoản/quyền thì xin qua lead/manager.
  - 2 bước: (1) chọn 1 task lặp lại, giao AI thử; (2) lưu kết quả tốt lẫn tệ vào ghi chú chung — đính kèm ảnh chụp màn hình nếu có — hẹn checkpoint cuối tuần cùng xem lại.
  - Người hỗ trợ: **Linh** — hỏi trực tiếp khi kẹt.
- **Visual:** text theo nền của component; DIO pose `m5-dancing` làm anchor closing; CTA capsule nổi bật "THỬ 1 LẦN TUẦN NÀY" (chữ tương phản với capsule).

---

## Checklist trước khi dựng

- [ ] Import `colors_and_type.css` + fonts từ `sun-studio-design-system`
- [ ] Check tương phản logo trên nền cuối của component (chỉ có `logo.png`, không có bản trắng — dùng badge trắng nếu nền tối/cam)

## Nguồn đã kiểm chứng (2026-07)

- Chat / Cowork / Code là 3 tab của Claude Desktop app; Cowork = agent trên file local cho knowledge work; Code = GUI của Claude Code — [claude.com tutorial](https://claude.com/resources/tutorials/navigating-the-claude-desktop-app), [Cowork Help Center](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)
- Scheduled tasks (chạy định kỳ trong Cowork) — [Help Center](https://support.claude.com/en/articles/13854387-schedule-recurring-tasks-in-claude-cowork)
- Dispatch (giao task từ điện thoại, chạy trên máy) — [Help Center](https://support.claude.com/en/articles/13947068-assign-tasks-to-claude-from-anywhere-in-cowork)
