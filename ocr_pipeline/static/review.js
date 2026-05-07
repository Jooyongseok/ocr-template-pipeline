/* OCR 검수 UI -- 인라인 수정, 연관 필드 그룹, 키보드 네비게이션 */

const API = {
  documents: () => fetch('/api/documents').then(r => r.json()),
  fields: (docId) => fetch(`/api/document/${docId}/fields`).then(r => r.json()),
  cropUrl: (docId, fieldKey) => `/api/crop/${docId}/${fieldKey}`,
  pageImage: (docId, page) => `/api/page-image/${docId}/${page}`,
  update: (data) => fetch('/api/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  }).then(r => r.json()),
  skipDoc: (docId, reason) => fetch('/api/skip-document', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({document_id: docId, reason}),
  }).then(r => r.json()),
  stats: () => fetch('/api/stats').then(r => r.json()),
  exportExcel: () => fetch('/api/export-excel', {method: 'POST'}).then(r => r.json()),
};

// ── State ──
let state = {
  documents: [],
  currentDocIdx: 0,
  currentDocId: null,
  fields: [],
  currentFieldIdx: -1,
  reviewFields: [],  // 문제 필드만
  filter: 'review',
};

// ── DOM refs ──
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  await loadDocuments();
  setupEventListeners();
  updateStats();
});

async function loadDocuments() {
  try {
    state.documents = await API.documents();
    if (state.documents.length > 0) {
      await selectDocument(0);
    } else {
      $('#empty-state').textContent = '검수할 문서가 없습니다. OCR 파이프라인을 먼저 실행하세요.';
    }
  } catch (e) {
    showToast('문서 로드 실패: ' + e.message, 'error');
  }
}

async function selectDocument(idx) {
  if (idx < 0 || idx >= state.documents.length) return;
  state.currentDocIdx = idx;
  state.currentDocId = state.documents[idx].document_id;

  $('#current-doc-label').textContent = `문서 ${idx + 1}/${state.documents.length}`;

  // Load fields
  try {
    const data = await API.fields(state.currentDocId);
    state.fields = data.fields || [];

    // Load page image
    const pageImg = $('#page-image');
    pageImg.src = API.pageImage(state.currentDocId, 1);
    pageImg.onload = () => renderFieldOverlays();

    renderFieldList();
    updateDocProgress(data);

    // 첫 번째 문제 필드 선택
    state.reviewFields = state.fields.filter(f => f.status !== 'ok' && f.status !== 'unchecked');
    if (state.reviewFields.length > 0) {
      selectField(state.fields.indexOf(state.reviewFields[0]));
    } else {
      showEmpty('이 문서는 모든 필드가 확인되었습니다.');
    }
  } catch (e) {
    showToast('필드 로드 실패: ' + e.message, 'error');
  }
}

function renderFieldOverlays() {
  const container = $('#field-overlays');
  container.innerHTML = '';

  state.fields.forEach((field, idx) => {
    if (!field.bbox_norm) return;

    const [x, y, w, h] = field.bbox_norm;
    const div = document.createElement('div');
    div.className = 'field-overlay';
    div.dataset.idx = idx;

    // CSS percentage positioning
    div.style.left = (x * 100) + '%';
    div.style.top = (y * 100) + '%';
    div.style.width = (w * 100) + '%';
    div.style.height = (h * 100) + '%';

    // Status coloring
    const st = field.status;
    if (st === 'ok' || st === 'unchecked') {
      div.classList.add('status-ok');
    } else if (st === 'needs_review' || st === 'multiple_candidates' || st === 'low_confidence') {
      div.classList.add('status-review');
    } else {
      div.classList.add('status-error');
    }

    div.title = `${field.label} (${field.confidence.toFixed(2)})`;
    div.addEventListener('click', () => selectField(idx));
    container.appendChild(div);
  });
}

function renderFieldList() {
  const ul = $('#field-list-items');
  ul.innerHTML = '';

  const filtered = getFilteredFields();

  filtered.forEach(field => {
    const idx = state.fields.indexOf(field);
    const li = document.createElement('li');
    li.dataset.idx = idx;

    const st = field.status;
    let dotClass = 'ok';
    if (st === 'needs_review' || st === 'multiple_candidates' || st === 'low_confidence') dotClass = 'review';
    else if (st !== 'ok' && st !== 'unchecked') dotClass = 'error';

    li.innerHTML = `
      <span>${field.label}</span>
      <span class="status-dot ${dotClass}"></span>
    `;
    li.addEventListener('click', () => selectField(idx));
    ul.appendChild(li);
  });
}

function getFilteredFields() {
  const filter = state.filter;
  if (filter === 'all') return state.fields;
  if (filter === 'ok') return state.fields.filter(f => f.status === 'ok');
  return state.fields.filter(f => f.status !== 'ok' && f.status !== 'unchecked');
}

function selectField(idx) {
  if (idx < 0 || idx >= state.fields.length) return;
  state.currentFieldIdx = idx;
  const field = state.fields[idx];

  // Show review card
  $('#empty-state').style.display = 'none';
  $('#review-card').style.display = 'block';

  // Crop image (lazy-loaded)
  const cropImg = $('#crop-image');
  if (field.crop_path) {
    cropImg.src = API.cropUrl(state.currentDocId, field.field_key);
  } else {
    cropImg.src = '';
  }

  // Field info
  $('#field-label').textContent = field.label;
  $('#field-type-badge').textContent = field.field_type;

  const confBadge = $('#confidence-badge');
  confBadge.textContent = (field.confidence * 100).toFixed(0) + '%';
  confBadge.className = 'confidence-badge';
  if (field.confidence >= 0.8) confBadge.classList.add('high');
  else if (field.confidence >= 0.5) confBadge.classList.add('medium');
  else confBadge.classList.add('low');

  // Edit input
  const input = $('#edit-input');
  input.value = field.value || field.raw_text || '';
  input.focus();
  input.select();

  // Candidates
  const candUl = $('#candidates-items');
  candUl.innerHTML = '';
  const candidates = (field.candidates || []).slice(0, 5);
  candidates.forEach(c => {
    const li = document.createElement('li');
    const text = c.text || String(c.value || '');
    const conf = (c.confidence * 100).toFixed(0);
    li.textContent = `${text} (${conf}%)`;
    li.addEventListener('click', () => {
      input.value = text;
      input.focus();
    });
    candUl.appendChild(li);
  });
  $('#candidates-list').style.display = candidates.length > 0 ? 'block' : 'none';

  // Group section
  renderGroupSection(field);

  // Warning
  const warningBox = $('#warning-box');
  if (field.warning) {
    warningBox.textContent = field.warning;
    warningBox.style.display = 'block';
  } else {
    warningBox.style.display = 'none';
  }

  // Highlight active overlay
  $$('.field-overlay').forEach(el => el.classList.remove('active'));
  const overlay = $(`.field-overlay[data-idx="${idx}"]`);
  if (overlay) {
    overlay.classList.add('active');
    overlay.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  // Highlight active list item
  $$('#field-list-items li').forEach(el => el.classList.remove('active'));
  const listItem = $(`#field-list-items li[data-idx="${idx}"]`);
  if (listItem) {
    listItem.classList.add('active');
    listItem.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
}

function renderGroupSection(field) {
  const groupSection = $('#group-section');
  const groupUl = $('#group-fields');

  if (!field.group_name || field.group_fields.length <= 1) {
    groupSection.style.display = 'none';
    return;
  }

  groupSection.style.display = 'block';
  groupUl.innerHTML = '';

  field.group_fields.forEach(gfk => {
    const gf = state.fields.find(f => f.field_key === gfk);
    if (!gf) return;

    const li = document.createElement('li');
    const statusIcon = gf.status === 'ok' ? '\u2705' :
                       (gf.status === 'needs_review' || gf.status === 'low_confidence') ? '\u26a0\ufe0f' : '\u274c';

    li.innerHTML = `
      <span>${gf.label}: <strong>${gf.value || '(비어있음)'}</strong></span>
      <span>${statusIcon} ${(gf.confidence * 100).toFixed(0)}%</span>
    `;
    li.style.cursor = 'pointer';
    li.addEventListener('click', () => {
      const gIdx = state.fields.indexOf(gf);
      if (gIdx >= 0) selectField(gIdx);
    });
    groupUl.appendChild(li);
  });
}

// ── Actions ──

async function confirmField() {
  const field = state.fields[state.currentFieldIdx];
  if (!field) return;

  const newValue = $('#edit-input').value.trim();

  try {
    const result = await API.update({
      document_id: state.currentDocId,
      field_key: field.field_key,
      value: newValue,
    });

    if (result.ok) {
      // Update local state
      field.value = newValue;
      field.status = 'ok';
      field.confidence = 1.0;
      field.edited = true;

      showToast('저장 완료', 'success');

      // Active Learning notification
      if (result.active_learning && result.active_learning.trigger_retrain) {
        showALNotification(result.active_learning.trigger_message);
      }

      // Update AL badge
      if (result.active_learning && result.active_learning.total_corrections) {
        $('#al-badge').textContent = 'AL: ' + result.active_learning.total_corrections;
      }

      // Update UI
      renderFieldOverlays();
      renderFieldList();
      updateDocProgressLocal();

      // Move to next review field
      moveToNextReviewField();
    } else {
      showToast('저장 실패: ' + (result.error || ''), 'error');
    }
  } catch (e) {
    showToast('저장 실패: ' + e.message, 'error');
  }
}

function moveToNextReviewField() {
  const currentIdx = state.currentFieldIdx;
  // Find next field that needs review (after current)
  for (let i = currentIdx + 1; i < state.fields.length; i++) {
    const f = state.fields[i];
    if (f.status !== 'ok' && f.status !== 'unchecked') {
      selectField(i);
      return;
    }
  }
  // Wrap around
  for (let i = 0; i < currentIdx; i++) {
    const f = state.fields[i];
    if (f.status !== 'ok' && f.status !== 'unchecked') {
      selectField(i);
      return;
    }
  }
  // All done
  showEmpty('이 문서의 모든 필드가 확인되었습니다!');

  // Auto-advance to next document with review items
  const nextDocIdx = state.documents.findIndex((d, i) => i > state.currentDocIdx && d.review_count > 0);
  if (nextDocIdx >= 0) {
    showToast('다음 문서로 이동합니다...', 'success');
    setTimeout(() => selectDocument(nextDocIdx), 1000);
  }
}

function skipField() {
  moveToNextReviewField();
}

function moveToPrevReviewField() {
  const currentIdx = state.currentFieldIdx;
  for (let i = currentIdx - 1; i >= 0; i--) {
    const f = state.fields[i];
    if (f.status !== 'ok' && f.status !== 'unchecked') {
      selectField(i);
      return;
    }
  }
}

function showEmpty(msg) {
  $('#review-card').style.display = 'none';
  $('#empty-state').style.display = 'flex';
  $('#empty-state').querySelector('p').textContent = msg;
}

// ── Progress ──

function updateDocProgress(data) {
  const total = data.fields ? data.fields.length : 0;
  const ok = data.fields ? data.fields.filter(f => f.status === 'ok' || f.status === 'unchecked').length : 0;
  const pct = total > 0 ? (ok / total * 100) : 0;

  $('#doc-progress-bar').style.width = pct + '%';
  $('#doc-progress-text').textContent = `${ok}/${total} 필드 완료`;
}

function updateDocProgressLocal() {
  const total = state.fields.length;
  const ok = state.fields.filter(f => f.status === 'ok' || f.status === 'unchecked').length;
  const pct = total > 0 ? (ok / total * 100) : 0;

  $('#doc-progress-bar').style.width = pct + '%';
  $('#doc-progress-text').textContent = `${ok}/${total} 필드 완료`;
}

async function updateStats() {
  try {
    const stats = await API.stats();
    const done = stats.completed_docs || 0;
    const total = stats.total_docs || 0;
    const pct = total > 0 ? (done / total * 100) : 0;

    $('#batch-progress').textContent = `${done}/${total} 문서`;
    $('#batch-progress-bar').style.width = pct + '%';

    if (stats.active_learning) {
      $('#al-badge').textContent = 'AL: ' + (stats.active_learning.total_corrections || 0);
    }
  } catch (e) { /* silent */ }
}

// ── Toast ──

function showToast(msg, type = 'info') {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

function showALNotification(msg) {
  const el = $('#al-notification');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 10000);
}

// ── Event listeners ──

function setupEventListeners() {
  // Buttons
  $('#btn-confirm').addEventListener('click', confirmField);
  $('#btn-skip').addEventListener('click', skipField);
  $('#btn-prev-doc').addEventListener('click', () => selectDocument(state.currentDocIdx - 1));
  $('#btn-next-doc').addEventListener('click', () => selectDocument(state.currentDocIdx + 1));

  $('#btn-skip-doc').addEventListener('click', async () => {
    if (!state.currentDocId) return;
    const result = await API.skipDoc(state.currentDocId, 'user_skipped');
    if (result.ok) {
      showToast('문서 건너뛰기 완료', 'success');
      state.documents[state.currentDocIdx].status = 'skipped';
      selectDocument(state.currentDocIdx + 1);
    }
  });

  $('#btn-export').addEventListener('click', async () => {
    showToast('엑셀 생성 중...', 'info');
    const result = await API.exportExcel();
    if (result.ok) {
      showToast('엑셀 생성 완료: ' + result.path, 'success');
    } else {
      showToast('엑셀 생성 실패: ' + (result.error || ''), 'error');
    }
  });

  // Filter
  $('#filter-status').addEventListener('change', (e) => {
    state.filter = e.target.value;
    renderFieldList();
  });

  // Keyboard navigation
  document.addEventListener('keydown', (e) => {
    const input = $('#edit-input');
    const isInputFocused = document.activeElement === input;

    if (e.key === 'Enter' && isInputFocused) {
      e.preventDefault();
      confirmField();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      skipField();
    } else if (e.key === 'Tab' && !e.ctrlKey) {
      e.preventDefault();
      if (e.shiftKey) {
        moveToPrevReviewField();
      } else {
        // If input has changes, confirm first then move
        if (isInputFocused && input.value !== (state.fields[state.currentFieldIdx]?.value || '')) {
          confirmField();
        } else {
          moveToNextReviewField();
        }
      }
    } else if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      // Undo: restore original value
      const field = state.fields[state.currentFieldIdx];
      if (field) {
        input.value = field.raw_text || '';
        showToast('원본 값 복원', 'info');
      }
    }
  });
}
