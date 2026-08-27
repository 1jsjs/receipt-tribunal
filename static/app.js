/* 영수증 소비 재판소 — 프론트엔드 (TASK-F001~F013)
 *
 * 계약: docs/02(API 명세)·docs/05 §12(분석 응답)
 * RULE 001/007 — 통계·유형·판결문은 전부 서버 값을 그대로 렌더한다. 프론트 계산 금지.
 *   → 목록 화면의 총지출도 직접 합산하지 않고 GET /api/analysis의 totalExpense를 쓴다.
 *     (월별로 캐시해 판결 화면과 공유 → Bedrock 중복 호출 방지, 두 화면 수치 불일치도 원천 차단)
 * RULE 003/004 — 카테고리 코드 6종·거래유형 2종은 서버와 동일 문자열.
 */

// ─────────────── 상수 (docs/05 §4·§7) ───────────────
const CATEGORIES = [
  ['DELIVERY_DINING', '배달·외식'],
  ['CONVENIENCE_STORE', '편의점'],
  ['CAFE_SNACK', '카페·간식'],
  ['GROCERIES', '식재료·생필품'],
  ['SHOPPING_HOBBY', '쇼핑·취미'],
  ['OTHER', '기타'],
];
const CATEGORY_LABEL = Object.fromEntries(CATEGORIES);

// ─────────────── TASK-F001 공통 유틸 ───────────────
const $ = (sel) => document.querySelector(sel);
const won = (n) => Number(n).toLocaleString('ko-KR') + '원';
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** 공통 응답 규약({success,data}/{success,error})을 풀어주는 fetch 헬퍼.
 *  실패는 전부 예외로 던져 호출부에서 한 번만 처리한다. */
async function api(path, options = {}) {
  let res, body;
  try {
    res = await fetch('/api' + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    body = await res.json();
  } catch (e) {
    throw new Error('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
  }
  if (!res.ok || !body.success) {
    throw new Error((body && body.error && body.error.message) || '요청을 처리하지 못했습니다.');
  }
  return body.data;
}

let toastTimer;
function toast(msg, isError = false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ''), 2600);
}

// 분석 결과 월별 캐시 — 데이터가 바뀌면 통째로 비운다
const analysisCache = new Map();
const invalidate = () => analysisCache.clear();
async function getAnalysis(month) {
  if (analysisCache.has(month)) return analysisCache.get(month);
  const data = await api(`/analysis?month=${month}`);
  analysisCache.set(month, data);
  return data;
}

// ─────────────── 탭 전환 ───────────────
const views = { input: $('#view-input'), list: $('#view-list'), result: $('#view-result') };
function showView(name) {
  Object.entries(views).forEach(([k, el]) => (el.hidden = k !== name));
  document.querySelectorAll('nav button').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === name));
  if (name === 'list') loadList();
  if (name === 'result') loadResult();
}
document.querySelectorAll('nav button').forEach((b) =>
  b.addEventListener('click', () => showView(b.dataset.view)));

// ─────────────── TASK-F002 폼 초기화 ───────────────
function fillCategories(select) {
  select.innerHTML = CATEGORIES.map(([code, label]) => `<option value="${code}">${label}</option>`).join('');
}
fillCategories($('#category'));
fillCategories($('#edit-category'));

const today = new Date();
const pad = (n) => String(n).padStart(2, '0');
const todayStr = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
const thisMonth = todayStr.slice(0, 7);
$('#date').value = todayStr;
$('#month-list').value = thisMonth;   // TASK-F005 기본값 = 현재 월
$('#month-result').value = thisMonth;

// ─────────────── TASK-F003 저장 ───────────────
$('#expense-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#submit-btn');
  const payload = {
    storeName: $('#storeName').value.trim(),
    date: $('#date').value,
    amount: Number($('#amount').value),          // RULE 005 숫자로 전송
    category: $('#category').value,
    transactionType: document.querySelector('input[name="transactionType"]:checked').value,
  };

  btn.disabled = true;
  btn.textContent = '제출 중...';
  try {
    await api('/expenses', { method: 'POST', body: JSON.stringify(payload) });
    invalidate();
    $('#expense-form').reset();
    $('#date').value = todayStr;                  // 날짜는 오늘로 되돌림
    $('#storeName').focus();
    toast('증거가 접수되었습니다 📄');
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '증거로 제출하기';
  }
});

// ─────────────── TASK-F004 목록 ───────────────
async function loadList() {
  const month = $('#month-list').value;
  if (!month) return;
  const body = $('#list-body');
  body.innerHTML = '<div class="loading">불러오는 중...</div>';
  $('#list-total').textContent = '—';

  try {
    const rows = await api(`/expenses?month=${month}`);
    $('#list-count').textContent = rows.filter((r) => r.transactionType === 'EXPENSE').length;

    if (rows.length === 0) {
      body.innerHTML = `<div class="empty">이번 달에는 아직 소비 기록이 없습니다.<br>
        판결을 원하시면 소비 내역부터 제출하세요 👨‍⚖️</div>`;
    } else {
      body.innerHTML = rows.map(renderItem).join('');
    }

    // 총지출은 서버 분석값 (RULE 001) — 목록을 먼저 그리고 비동기로 채운다
    const stats = await getAnalysis(month);
    $('#list-total').textContent = won(stats.totalExpense);
  } catch (err) {
    body.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    $('#list-total').textContent = '0원';
  }
}

function renderItem(r) {
  const isTransfer = r.transactionType === 'TRANSFER';
  return `<div class="item">
    <div class="date">${esc(r.date.slice(5))}</div>
    <div class="info">
      <div class="store">${esc(r.storeName)}</div>
      <div>
        <span class="badge">${esc(CATEGORY_LABEL[r.category] || r.category)}</span>
        ${isTransfer ? '<span class="badge transfer">이체 · 분석 제외</span>' : ''}
      </div>
    </div>
    <div class="amt ${isTransfer ? 'transfer' : ''}">${won(r.amount)}</div>
    <div class="acts">
      <button title="수정" data-edit="${r.id}">✏️</button>
      <button title="삭제" data-del="${r.id}">🗑️</button>
    </div>
  </div>`;
}

$('#month-list').addEventListener('change', loadList);
$('#go-judge').addEventListener('click', () => {
  $('#month-result').value = $('#month-list').value;
  showView('result');
});

// ─────────────── TASK-F006 수정 / F007 삭제 ───────────────
let pendingDelete = null;

$('#list-body').addEventListener('click', async (e) => {
  const editId = e.target.dataset.edit;
  const delId = e.target.dataset.del;

  if (editId) {
    try {
      const r = await api(`/expenses/${editId}`);
      $('#edit-id').value = r.id;
      $('#edit-storeName').value = r.storeName;
      $('#edit-date').value = r.date;
      $('#edit-amount').value = r.amount;
      $('#edit-category').value = r.category;
      document.querySelector(`input[name="edit-tt"][value="${r.transactionType}"]`).checked = true;
      $('#edit-modal').hidden = false;
    } catch (err) { toast(err.message, true); }
  }

  if (delId) {
    const store = e.target.closest('.item').querySelector('.store').textContent;
    pendingDelete = delId;
    $('#del-desc').textContent = `"${store}" 기록이 영구히 사라집니다.`;
    $('#del-modal').hidden = false;
  }
});

$('#edit-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = $('#edit-id').value;
  const payload = {
    storeName: $('#edit-storeName').value.trim(),
    date: $('#edit-date').value,
    amount: Number($('#edit-amount').value),
    category: $('#edit-category').value,
    transactionType: document.querySelector('input[name="edit-tt"]:checked').value,
  };
  try {
    await api(`/expenses/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    invalidate();
    $('#edit-modal').hidden = true;
    toast('증거가 수정되었습니다');
    loadList();
  } catch (err) { toast(err.message, true); }
});

$('#del-confirm').addEventListener('click', async () => {
  try {
    await api(`/expenses/${pendingDelete}`, { method: 'DELETE' });
    invalidate();
    $('#del-modal').hidden = true;
    toast('증거가 폐기되었습니다');
    loadList();
  } catch (err) { toast(err.message, true); }
});

// 모달 닫기 (취소 버튼 / 배경 클릭)
document.querySelectorAll('.backdrop').forEach((bd) => {
  bd.addEventListener('click', (e) => {
    if (e.target === bd || e.target.hasAttribute('data-close')) bd.hidden = true;
  });
});

// ─────────────── TASK-F008 분석 호출 ───────────────
async function loadResult() {
  const month = $('#month-result').value;
  if (!month) return;
  const body = $('#result-body');
  body.innerHTML = `<div class="card loading"><span class="gavel">🔨</span>법정 개정 중...<br>
    <span style="font-size:13px">증거를 검토하고 있습니다</span></div>`;
  try {
    body.innerHTML = renderResult(await getAnalysis(month));
  } catch (err) {
    body.innerHTML = `<div class="card empty">${esc(err.message)}</div>`;
  }
}
$('#month-result').addEventListener('change', loadResult);
$('#re-judge').addEventListener('click', () => { invalidate(); loadResult(); });

// ─────────────── F009~F012 결과 렌더 (서버 값 그대로) ───────────────
function renderResult(d) {
  if (d.paymentCount === 0) {
    return `<div class="card empty">이번 달에는 아직 소비 기록이 없습니다.<br>
      판결을 원하시면 소비 내역부터 제출하세요 👨‍⚖️</div>`;
  }
  const j = d.judgment;

  // F011 판결문 — 화면의 주인공
  const verdict = `<div class="verdict">
    <div class="stamp">판 결 문</div>
    <div class="crime">${esc(j.crime)}</div>
    <div class="type-label">${esc(d.month)} · 피고인의 소비 생활에 관하여</div>

    <div class="vsec"><h4>증 거</h4><ul>${j.evidence.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="vsec"><h4>주 문</h4><p>${esc(j.verdict)}</p></div>
    <div class="vsec"><h4>이 유</h4><p class="reasoning">${esc(j.reasoning)}</p></div>
    <div class="vsec"><h4>형 량</h4><p class="sentence">${esc(j.sentence)}</p></div>
  </div>`;

  // F012 소비 유형 배너 (클릭 → F013 MZ 팝업)
  const banner = `<button class="type-banner" id="type-banner">
    <span>
      <span class="tb-label">피고인의 소비 유형</span><br>
      <span class="tb-name">${esc(d.consumerType.label)}</span>
    </span>
    <span class="tb-hint">눌러보기 👆</span>
  </button>`;

  // F009 총지출 + 세부 통계
  const largest = d.largestSingleExpense;
  const stats = `<div class="card">
    <div class="total-line">
      <span style="color:var(--muted);font-size:14px">${esc(d.month)} 총지출</span>
      <span class="amt">${won(d.totalExpense)}</span>
    </div>
    <div class="stat-grid" style="margin-top:14px">
      <div class="stat"><div class="k">결제 건수</div><div class="v">${d.paymentCount}건</div></div>
      <div class="stat"><div class="k">평균 결제</div><div class="v">${won(d.averagePaymentAmount)}</div></div>
      <div class="stat"><div class="k">소액(5천 이하)</div><div class="v">${d.smallPaymentCount}건</div></div>
    </div>
    ${largest ? `<p style="margin-top:12px;font-size:13px;color:var(--muted)">
      최대 단일 지출 · ${esc(largest.storeName)} <b style="color:var(--gold-soft)">${won(largest.amount)}</b>
      <span style="opacity:.7">(${esc(largest.date)})</span></p>` : ''}
  </div>`;

  // F010 카테고리 통계
  const cats = `<div class="card">
    <h2>카테고리별 지출</h2>
    ${d.categoryStats.filter((c) => c.amount > 0).map((c) => `
      <div class="cat-row">
        <div class="cat-head">
          <span>${esc(c.label)} <span class="n">${c.count}건</span></span>
          <span>${won(c.amount)} <span class="n">${c.percentage}%</span></span>
        </div>
        <div class="bar"><div style="width:${Math.min(c.percentage, 100)}%"></div></div>
      </div>`).join('')}
  </div>`;

  // 중요도 순서(docs/05 §16): 유형 > 판결문 > 총지출 > 카테고리
  return banner + verdict + stats + cats;
}

// ─────────────── TASK-F013 MZ 리액션 팝업 ───────────────
$('#result-body').addEventListener('click', async (e) => {
  if (!e.target.closest('#type-banner')) return;
  try {
    const d = await getAnalysis($('#month-result').value);
    $('#mz-msg').textContent = d.reactionMessage;
    $('#mz-modal').hidden = false;
  } catch (err) { toast(err.message, true); }
});

// 첫 진입 화면
showView('input');
