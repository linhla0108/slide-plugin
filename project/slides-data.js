/* Slide markup for the variation canvas. Attached to window.SLIDES.
   Each value is an innerHTML string for a 1920x1080 .vslide. */
(function () {
  const LOGO = 'assets/logo.png';
  const DIO = 'assets/dio/m2-wink.png';

  // Pre-build the XO grid markup (canonical: 8 rows × 13 cols, alt offset, 3 hot cells)
  const X_SVG = '<svg viewBox="0 0 100 100"><path d="M24 24L76 76M76 24L24 76" fill="none" stroke="currentColor" stroke-width="18" stroke-linecap="round"/></svg>';
  const O_SVG = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="31" fill="none" stroke="currentColor" stroke-width="17" stroke-linecap="round"/></svg>';
  let xoRows = '';
  for (let row = 0; row < 8; row++) {
    let cells = '';
    for (let col = 0; col < 13; col++) {
      const isX = col % 2 === 0;
      const hot = (row === 1 && col === 10) || (row === 4 && col === 7) || (row === 6 && col === 2);
      cells += `<span class="xo-cell ${isX ? 'x' : 'o'}${hot ? ' hot' : ''}">${isX ? X_SVG : O_SVG}</span>`;
    }
    xoRows += `<div class="xo-row${row % 2 ? ' offset' : ''}">${cells}</div>`;
  }
  const xoPattern = `<div class="xo-pattern" aria-hidden="true"><div class="xo-grid">${xoRows}</div></div><div class="wash" aria-hidden="true"></div>`;

  // Pre-built barcode (deterministic so it doesn't reshuffle on re-render)
  function barcode(extra) {
    const ws = [4,2,3,2,4,2,2,3,4,2,3,2,2,4,3,2,4,2,3,2,4,3];
    const hs = [40,26,34,22,44,28,24,36,42,20,32,30,26,44,38,22,40,24,34,28,42,30];
    let bars = '';
    for (let i = 0; i < 22; i++) bars += `<i style="width:${ws[i]}px;height:${hs[i]}px"></i>`;
    return `<div class="barcode"${extra || ''}>${bars}</div>`;
  }

  /* ---------- shared title hero ---------- */
  function titleHero(eyebrowClass, eyebrowText) {
    return `
      <div class="t-hero">
        <span class="t-eyebrow ${eyebrowClass}">${eyebrowText}</span>
        <h1 class="t-h1"><span class="l">Be Professional</span><span class="tab">@SUN.STUDIO</span></h1>
      </div>`;
  }

  /* ===================== TITLE ===================== */
  const TITLE_A = `
    ${xoPattern}
    <img class="v-logo" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out">Intern L&amp;D</span><span class="v-pill out">2026</span></div>
    <div class="t-dio-halo light"></div>
    <img class="t-dio" src="${DIO}" alt="Dio">
    ${titleHero('ink', 'Intern Onboarding')}
    <div class="t-tagline" style="color:var(--ink)">SUN RISES. GAME ON.</div>
    <div class="v-num">#01</div>`;

  const TITLE_B = `
    ${xoPattern}
    <img class="v-logo white" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill solid">Intern L&amp;D</span><span class="v-pill out-w">2026</span></div>
    <div class="t-dio-halo white"></div>
    <img class="t-dio" src="${DIO}" alt="Dio">
    ${titleHero('solid', 'Intern Onboarding')}
    <div class="t-tagline" style="color:#fff">SUN RISES. GAME ON.</div>
    <div class="v-num">#01</div>`;

  const TITLE_C = `
    ${xoPattern}
    <img class="v-logo white" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out-w">Intern L&amp;D</span><span class="v-pill out-w">2026</span></div>
    <div class="t-dio-halo glow"></div>
    <img class="t-dio" src="${DIO}" alt="Dio">
    ${titleHero('orange', 'Intern Onboarding')}
    <div class="t-tagline" style="color:#fff">SUN RISES. GAME ON.</div>
    <div class="v-num">#01</div>`;

  /* ===================== AGENDA ===================== */
  const DAYS = [
    { n: '01', day: 'Start', topic: 'Cùng thảo luận nào!', sub: 'Khởi động & kỳ vọng', c: 'var(--orange)' },
    { n: '02', day: 'Mon', topic: 'Ấn tượng đầu tiên', sub: 'Monday Tips', c: 'var(--blue)' },
    { n: '03', day: 'Tue', topic: 'Đi trễ / vắng mặt', sub: 'Khi có sự cố', c: 'var(--ink)' },
    { n: '04', day: 'Wed', topic: 'Tình huống công việc', sub: 'Một số ca thường gặp', c: 'var(--orange)' },
    { n: '05', day: 'Thu', topic: 'Hình ảnh “online”', sub: 'Online presence', c: 'var(--blue)' },
    { n: '06', day: 'Fri', topic: 'Tài sản SUN.STUDIO', sub: 'Sử dụng đúng cách', c: 'var(--ink)' },
  ];
  const head = `
    <div class="a-head"><span class="a-kicker">6 chủ đề · Mon → Fri</span>
      <h2 class="a-title">Agenda<span class="dot">.</span></h2></div>`;

  // A — horizontal ticket rows
  const AGENDA_A = `${xoPattern}
    <img class="v-logo" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out">Intern L&amp;D</span></div>
    ${head}
    <div class="rows">
      ${DAYS.map(d => `
        <div class="ticket" style="--c:${d.c}">
          <div class="stub"><span class="tnum">${d.n}</span><span class="tday">${d.day}</span><span class="perf"></span></div>
          <span class="notch top"></span><span class="notch bot"></span>
          <div class="body"><div class="topic">${d.topic} <span class="reg">· ${d.sub}</span></div></div>
          ${barcode()}
        </div>`).join('')}
    </div>
    <div class="v-num">#02</div>`;

  // B — vertical ticket cards 3x2
  const AGENDA_B = `${xoPattern}
    <img class="v-logo" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out">Intern L&amp;D</span></div>
    ${head}
    <div class="grid">
      ${DAYS.map(d => `
        <div class="ticket" style="--c:${d.c}">
          <div class="stub"><span class="tnum">${d.n}</span><span class="tday">${d.day}</span></div>
          <span class="perf"></span><span class="notch l"></span><span class="notch r"></span>
          <div class="body"><div class="topic">${d.topic}</div><div class="sub">${d.sub}</div>
            ${barcode(' style="margin-top:18px"')}</div>
        </div>`).join('')}
    </div>
    <div class="v-num">#02</div>`;

  // C — boarding-pass strips
  const AGENDA_C = `${xoPattern}
    <img class="v-logo" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out">Intern L&amp;D</span></div>
    ${head}
    <div class="strips">
      ${DAYS.map(d => `
        <div class="pass" style="--c:${d.c}">
          <div class="stub"><span class="tnum">${d.n}</span><span class="tday">${d.day}</span></div>
          <span class="punch t"></span><span class="punch b"></span>
          <div class="mid"><div class="topic">${d.topic}</div><div class="sub">${d.sub}</div></div>
          <div class="seat"><span class="lbl">Pass</span>${barcode()}</div>
        </div>`).join('')}
    </div>
    <div class="v-num">#02</div>`;

  /* ===================== CARDS ===================== */
  const IC_CLOCK = '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#fff" stroke-width="2.2"/><path d="M12 7v5l3.5 2" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const IC_EAR = '<svg viewBox="0 0 24 24" fill="none"><path d="M3 11a9 9 0 0118 0v5a3 3 0 01-3 3M3 11v3a3 3 0 003 3h1v-6H6a3 3 0 00-3 3m18-3a3 3 0 00-3-3h-1v6h1" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const IC_CHAT = '<svg viewBox="0 0 24 24" fill="none"><path d="M21 11.5a8.4 8.4 0 01-11.3 7.9L4 20.5l1.1-5.6A8.4 8.4 0 1121 11.5z" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/><path d="M9.4 9.6a2.6 2.6 0 015 .9c0 1.7-2.6 2.5-2.6 2.5M12 16.3h.01" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const IC_CHECK = '<svg viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function cardsHead() {
    return `<div class="c-head"><span class="c-kicker">04.1 · Văn hoá Meeting</span>
      <h2 class="c-title">Văn hoá Meeting: không chỉ <span class="hl">“ngồi nghe”</span></h2></div>`;
  }
  function cardBodies() {
    return `
      <div class="mc c1"><span class="gnum">1</span><div class="chip">${IC_CLOCK}</div>
        <h3>Chuẩn bị &amp;<br>Đúng giờ</h3>
        <ul><li><b>Đọc trước</b> tài liệu, nội dung cuộc họp.</li>
          <li><b>Sẵn sàng trước 5 phút.</b>
            <ul><li>Offline: sổ, bút, laptop, tài liệu…</li><li>Online: check mic / cam / âm thanh.</li></ul></li></ul></div>
      <div class="mc c2"><span class="gnum">2</span><div class="chip">${IC_EAR}</div>
        <h3>Tập trung<br>lắng nghe</h3>
        <ul><li>Không làm việc riêng hay dùng điện thoại.</li>
          <li>Lắng nghe &amp; ghi chú nội dung trao đổi trong buổi họp.</li></ul></div>
      <div class="mc c3"><span class="gnum">3</span><div class="chip">${IC_CHAT}</div>
        <h3>Hỏi &amp;<br>Đề xuất</h3>
        <p class="lede">Sau khi đã hiểu bối cảnh buổi họp:</p>
        <ul><li>Mạnh dạn đặt câu hỏi nếu chưa rõ.</li><li>Đề xuất ý tưởng, giải pháp &amp; giải thích lý do.</li></ul>
        <div class="q">“Em có một ý kiến này muốn trình bày thử…”</div></div>
      <div class="mc c4"><span class="gnum">4</span><div class="chip">${IC_CHECK}</div>
        <h3>Công việc<br>tiếp theo</h3>
        <p class="lede">Xác nhận rõ phần việc của mình sau họp:</p>
        <div class="q">“Em xác nhận lại: update phần candidate tracking và gửi bản sửa trước 3PM ngày mai.”</div></div>`;
  }
  const cardsChrome = `<img class="v-logo" src="${LOGO}" alt="SUN.STUDIO">
    <div class="v-pills"><span class="v-pill out">Project Presentation</span></div>`;

  const CARDS_A = `${cardsChrome}${cardsHead()}<div class="c-cards">${cardBodies()}</div><div class="v-num">#03</div>`;
  const CARDS_B = CARDS_A;
  const CARDS_C = CARDS_A;

  window.SLIDES = {
    TITLE_A, TITLE_B, TITLE_C,
    AGENDA_A, AGENDA_B, AGENDA_C,
    CARDS_A, CARDS_B, CARDS_C,
  };
})();
