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
  models: () => fetch('/api/models').then(r => r.json()),
  switchModel: (modelId) => fetch('/api/switch-model', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model_id: modelId}),
  }).then(r => r.json()),
  exportCorrections: () => fetch('/api/export-corrections').then(r => r.json()),
  syncCorrections: (corrections) => fetch('/api/sync-corrections', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({corrections}),
  }).then(r => r.json()),
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
  await loadModels();
  await loadDocuments();
  setupEventListeners();
  updateStats();
  restoreSession();
});

// ── Model switcher ──
async function loadModels() {
  try {
    const data = await API.models();
    const sel = $('#model-selector');
    sel.innerHTML = '';
    (data.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.description || m.id;
      if (m.is_default) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch (_) { /* model API not available */ }
}

async function loadDocuments() {
  try {
    state.documents = await API.documents();
    if (state.documents.length > 0) {
      await selectDocument(0);
    } else {
      const emptyEl = $('#empty-state');
      emptyEl.innerHTML = `
        <div style="text-align:center;max-width:400px">
          <div style="font-size:48px;margin-bottom:16px">&#128195;</div>
          <p style="font-size:18px;font-weight:600;margin-bottom:8px">아직 검수할 문서가 없습니다</p>
          <p style="font-size:14px;color:var(--subtext);margin-bottom:8px">사용 방법:</p>
          <div style="text-align:left;font-size:13px;color:var(--subtext);margin-bottom:20px;line-height:2">
            <div>1. 대시보드에서 <b style="color:var(--text)">템플릿을 선택</b>합니다</div>
            <div>2. <b style="color:var(--text)">PDF 파일을 업로드</b>합니다</div>
            <div>3. <b style="color:var(--green)">OCR 실행</b> 버튼을 클릭합니다</div>
            <div>4. 이 페이지에서 결과를 확인합니다</div>
          </div>
          <a href="/" style="display:inline-block;padding:12px 28px;background:var(--blue);color:var(--bg);border-radius:8px;text-decoration:none;font-size:15px;font-weight:600">대시보드로 이동하기</a>
        </div>`;
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
    saveSession();
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

    div.title = `${field.label} (${field.confidence.toFixed(2)}) - 모서리를 드래그하여 크기 조정`;
    div.addEventListener('click', (e) => { if (!e.target.classList.contains('resize-handle')) selectField(idx); });

    // Resize handle (bottom-right corner)
    const handle = document.createElement('div');
    handle.className = 'resize-handle';
    handle.addEventListener('mousedown', (e) => startResize(e, idx, div));
    div.appendChild(handle);

    // Move handle (whole overlay drag)
    div.addEventListener('mousedown', (e) => {
      if (e.target.classList.contains('resize-handle')) return;
      startMove(e, idx, div);
    });

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
      saveSession();
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
      showToast('엑셀 다운로드 중...', 'success');
      // 생성된 엑셀 파일을 브라우저로 다운로드
      const a = document.createElement('a');
      a.href = '/api/download-excel';
      a.download = 'result_reviewed.xlsx';
      a.click();
    } else {
      showToast('엑셀 생성 실패: ' + (result.error || ''), 'error');
    }
  });

  // Help & Stats buttons
  $('#btn-help').addEventListener('click', () => toggleModal('shortcut-modal'));
  $('#btn-stats').addEventListener('click', () => openStatsModal());

  // Model switcher
  $('#model-selector').addEventListener('change', async (e) => {
    const modelId = e.target.value;
    showToast('모델 전환 중: ' + modelId, 'info');
    const result = await API.switchModel(modelId);
    if (result.ok) {
      showToast('모델 전환 완료: ' + modelId, 'success');
    } else {
      showToast('모델 전환 실패: ' + (result.error || ''), 'error');
    }
  });

  // Sync corrections
  $('#btn-sync').addEventListener('click', async () => {
    showToast('교정 데이터 내보내기 중...', 'info');
    const result = await API.exportCorrections();
    if (result.corrections && result.corrections.length > 0) {
      // Save to localStorage for cross-machine transfer
      const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `corrections_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`${result.total}건 교정 데이터 다운로드 완료`, 'success');
    } else {
      showToast('내보낼 교정 데이터가 없습니다', 'info');
    }
  });

  // Bulk confirm
  $('#btn-bulk-confirm').addEventListener('click', bulkConfirmHighConfidence);

  // Filter
  $('#filter-status').addEventListener('change', (e) => {
    state.filter = e.target.value;
    renderFieldList();
  });

  // Field search
  $('#field-search').addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    $$('#field-list-items li').forEach(li => {
      const text = li.textContent.toLowerCase();
      li.style.display = text.includes(query) ? '' : 'none';
    });
  });

  // Quick-fix toolbar
  $$('.quickfix-btn').forEach(btn => {
    btn.addEventListener('click', () => applyQuickFix(btn.dataset.action));
  });

  // Modal overlay click-to-close
  $$('.modal-overlay').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });
  });

  // Keyboard navigation
  document.addEventListener('keydown', (e) => {
    const input = $('#edit-input');
    const searchInput = $('#field-search');
    const isInputFocused = document.activeElement === input;
    const isSearchFocused = document.activeElement === searchInput;
    const isModalOpen = $$('.modal-overlay[style*="display: flex"], .modal-overlay:not([style*="display:none"]):not([style*="display: none"])').length > 0
      || ($('#shortcut-modal').style.display !== 'none') || ($('#stats-modal').style.display !== 'none');

    // Close modal with Escape
    if (e.key === 'Escape' && isModalOpen) {
      e.preventDefault();
      $$('.modal-overlay').forEach(m => m.style.display = 'none');
      return;
    }

    // ? key for help (when not typing)
    if (e.key === '?' && !isInputFocused && !isSearchFocused) {
      e.preventDefault();
      toggleModal('shortcut-modal');
      return;
    }

    // Ctrl shortcuts
    if (e.ctrlKey || e.metaKey) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); selectDocument(state.currentDocIdx - 1); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); selectDocument(state.currentDocIdx + 1); return; }
      if (e.key === 'e' || e.key === 'E') { e.preventDefault(); $('#btn-export').click(); return; }
      if (e.key === 'd' || e.key === 'D') { e.preventDefault(); openStatsModal(); return; }
    }

    if (e.key === 'Enter' && isInputFocused) {
      e.preventDefault();
      confirmField();
    } else if (e.key === 'Escape' && !isModalOpen) {
      e.preventDefault();
      skipField();
    } else if (e.key === 'Tab' && !e.ctrlKey && !isSearchFocused) {
      e.preventDefault();
      if (e.shiftKey) {
        moveToPrevReviewField();
      } else {
        if (isInputFocused && input.value !== (state.fields[state.currentFieldIdx]?.value || '')) {
          confirmField();
        } else {
          moveToNextReviewField();
        }
      }
    } else if (e.key === 'z' && (e.ctrlKey || e.metaKey) && isInputFocused) {
      e.preventDefault();
      const field = state.fields[state.currentFieldIdx];
      if (field) {
        input.value = field.raw_text || '';
        showToast('원본 값 복원', 'info');
      }
    }
  });
}

// ── Bbox drag/resize ──

function startResize(e, idx, div) {
  e.preventDefault();
  e.stopPropagation();
  const container = $('#field-overlays');
  const rect = container.getBoundingClientRect();
  const field = state.fields[idx];
  const startX = e.clientX;
  const startY = e.clientY;
  const startW = field.bbox_norm[2];
  const startH = field.bbox_norm[3];

  function onMove(e2) {
    const dx = (e2.clientX - startX) / rect.width;
    const dy = (e2.clientY - startY) / rect.height;
    field.bbox_norm[2] = Math.max(0.01, startW + dx);
    field.bbox_norm[3] = Math.max(0.005, startH + dy);
    div.style.width = (field.bbox_norm[2] * 100) + '%';
    div.style.height = (field.bbox_norm[3] * 100) + '%';
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    saveBbox(field);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function startMove(e, idx, div) {
  e.preventDefault();
  const container = $('#field-overlays');
  const rect = container.getBoundingClientRect();
  const field = state.fields[idx];
  const startX = e.clientX;
  const startY = e.clientY;
  const startLeft = field.bbox_norm[0];
  const startTop = field.bbox_norm[1];

  function onMove(e2) {
    const dx = (e2.clientX - startX) / rect.width;
    const dy = (e2.clientY - startY) / rect.height;
    field.bbox_norm[0] = Math.max(0, Math.min(1 - field.bbox_norm[2], startLeft + dx));
    field.bbox_norm[1] = Math.max(0, Math.min(1 - field.bbox_norm[3], startTop + dy));
    div.style.left = (field.bbox_norm[0] * 100) + '%';
    div.style.top = (field.bbox_norm[1] * 100) + '%';
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    saveBbox(field);
    selectField(idx);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

async function saveBbox(field) {
  try {
    await fetch('/api/update-bbox', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        document_id: state.currentDocId,
        field_key: field.field_key,
        bbox_norm: field.bbox_norm,
      }),
    });
    showToast('위치 조정 저장됨', 'success');
  } catch (_) {
    showToast('위치 저장 실패', 'error');
  }
}

// ── Modal helpers ──

function toggleModal(id) {
  const modal = $('#' + id);
  modal.style.display = modal.style.display === 'none' ? 'flex' : 'none';
}

function closeModal(id) {
  $('#' + id).style.display = 'none';
}

// ── Quick-fix toolbar ──

function applyQuickFix(action) {
  const input = $('#edit-input');
  if (!input) return;
  let v = input.value;
  switch (action) {
    case 'trim': v = v.trim(); break;
    case 'remove-special': v = v.replace(/[^가-힣a-zA-Z0-9\s\-]/g, ''); break;
    case 'remove-spaces': v = v.replace(/\s+/g, ''); break;
    case 'dash-rrn':
      // Add hyphen to 13-digit RRN: 1234561234567 -> 123456-1234567
      const digits = v.replace(/\D/g, '');
      if (digits.length === 13) v = digits.slice(0, 6) + '-' + digits.slice(6);
      break;
    case 'clear': v = ''; break;
  }
  input.value = v;
  input.focus();
  showToast('빠른 수정 적용', 'info');
}

// ── Session persistence ──

function saveSession() {
  if (!state.currentDocId) return;
  const session = {
    docId: state.currentDocId,
    docIdx: state.currentDocIdx,
    fieldIdx: state.currentFieldIdx,
    filter: state.filter,
    ts: Date.now(),
  };
  try {
    localStorage.setItem('ocr_review_session', JSON.stringify(session));
  } catch (_) { /* quota exceeded */ }
}

function restoreSession() {
  try {
    const raw = localStorage.getItem('ocr_review_session');
    if (!raw) return;
    const session = JSON.parse(raw);
    // Only restore if less than 24h old
    if (Date.now() - session.ts > 86400000) return;

    // Find document
    const docIdx = state.documents.findIndex(d => d.document_id === session.docId);
    if (docIdx >= 0 && docIdx !== state.currentDocIdx) {
      // Update filter first
      if (session.filter) {
        state.filter = session.filter;
        $('#filter-status').value = session.filter;
      }
      selectDocument(docIdx).then(() => {
        if (session.fieldIdx >= 0 && session.fieldIdx < state.fields.length) {
          selectField(session.fieldIdx);
        }
      });
      showToast('이전 세션 복원됨', 'info');
    }
  } catch (_) { /* corrupt data */ }
}

// ── Bulk confirm ──

async function bulkConfirmHighConfidence() {
  const threshold = 0.80;
  const toConfirm = state.fields.filter(f =>
    f.status !== 'ok' && f.status !== 'unchecked' && f.confidence >= threshold
  );

  if (toConfirm.length === 0) {
    showToast('일괄 확인할 고신뢰도 필드가 없습니다', 'info');
    return;
  }

  const msg = `신뢰도 ${(threshold * 100).toFixed(0)}% 이상 필드 ${toConfirm.length}개를 일괄 확인하시겠습니까?`;
  if (!confirm(msg)) return;

  let success = 0;
  for (const field of toConfirm) {
    try {
      const result = await API.update({
        document_id: state.currentDocId,
        field_key: field.field_key,
        value: field.value || field.raw_text || '',
      });
      if (result.ok) {
        field.status = 'ok';
        field.confidence = 1.0;
        field.edited = true;
        success++;
      }
    } catch (_) { /* skip failed */ }
  }

  showToast(`${success}/${toConfirm.length} 필드 일괄 확인 완료`, 'success');
  renderFieldOverlays();
  renderFieldList();
  updateDocProgressLocal();
  moveToNextReviewField();
}

// ── Statistics dashboard ──

async function openStatsModal() {
  toggleModal('stats-modal');
  if ($('#stats-modal').style.display === 'none') return;

  try {
    const stats = await API.stats();
    const totalDocs = stats.total_docs || 0;
    const completedDocs = stats.completed_docs || 0;
    const reviewDocs = totalDocs - completedDocs;

    $('#stat-total-docs').textContent = totalDocs;
    $('#stat-completed-docs').textContent = completedDocs;
    $('#stat-review-docs').textContent = reviewDocs;

    // Count error fields from current state
    let errorCount = 0;
    if (state.fields) {
      errorCount = state.fields.filter(f =>
        f.status !== 'ok' && f.status !== 'unchecked'
      ).length;
    }
    $('#stat-error-fields').textContent = errorCount;

    // Confidence distribution chart
    renderConfidenceChart();

    // Error by field type
    renderErrorByType();

    // Active learning stats
    const al = stats.active_learning || {};
    $('#al-stats-detail').innerHTML = `
      <div>총 수정 건수: <strong>${al.total_corrections || 0}</strong></div>
      <div>재학습 트리거 임계값: <strong>${al.retrain_threshold || 500}</strong></div>
      <div>진행률: <strong>${((al.total_corrections || 0) / (al.retrain_threshold || 500) * 100).toFixed(1)}%</strong></div>
    `;
  } catch (e) {
    $('#stats-body').innerHTML = '<p style="color:var(--red)">통계 로드 실패: ' + e.message + '</p>';
  }
}

function renderConfidenceChart() {
  const chart = $('#confidence-chart');
  chart.innerHTML = '';

  if (!state.fields || state.fields.length === 0) {
    chart.innerHTML = '<span style="color:var(--subtext);font-size:12px">데이터 없음</span>';
    return;
  }

  // Bucket into 10 bins (0-10%, 10-20%, ..., 90-100%)
  const bins = new Array(10).fill(0);
  state.fields.forEach(f => {
    const bucket = Math.min(9, Math.floor(f.confidence * 10));
    bins[bucket]++;
  });

  const maxVal = Math.max(...bins, 1);
  bins.forEach((count, i) => {
    const bar = document.createElement('div');
    bar.className = 'conf-bar';
    bar.style.height = (count / maxVal * 100) + '%';
    if (i < 5) bar.classList.add('low');
    else if (i < 8) bar.classList.add('medium');
    else bar.classList.add('high');
    bar.title = `${i * 10}-${(i + 1) * 10}%: ${count}개`;
    chart.appendChild(bar);
  });
}

function renderErrorByType() {
  const container = $('#error-by-type');
  container.innerHTML = '';

  if (!state.fields) return;

  const typeCounts = {};
  state.fields.forEach(f => {
    if (f.status !== 'ok' && f.status !== 'unchecked') {
      typeCounts[f.field_type] = (typeCounts[f.field_type] || 0) + 1;
    }
  });

  const entries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    container.innerHTML = '<span style="color:var(--subtext);font-size:12px">오류 필드 없음</span>';
    return;
  }

  const maxCount = entries[0][1];
  entries.forEach(([type, count]) => {
    const row = document.createElement('div');
    row.className = 'error-type-row';
    row.innerHTML = `
      <span class="type-name">${type}</span>
      <div class="bar-bg"><div class="bar-fill" style="width:${count / maxCount * 100}%"></div></div>
      <span class="type-count">${count}</span>
    `;
    container.appendChild(row);
  });
}
