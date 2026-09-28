'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let scanItems = [], jobs = [], mediaFiles = [], queuePaused = false, busy = false, activeJobFilter = 'all';
let lastMediaRefresh = 0;
const names = {queued:'Đang chờ',running:'Đang tải',paused:'Tạm dừng',done:'Hoàn tất',failed:'Lỗi'};
const filterTitles = {queued:'Đang chờ',running:'Đang tải',done:'Hoàn tất',failed:'Cần kiểm tra'};
function note(message, error = false) { $('notice').textContent = message; $('notice').style.color = error ? '#ffacb6' : '#cdb8ff'; }
async function api(path, method = 'GET', body) {
  const response = await fetch('/api' + path, {method, headers: body ? {'Content-Type':'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(typeof value.detail === 'string' ? value.detail : 'Lỗi ' + response.status);
  return value;
}
function enteredUrl() {
  const raw = $('url').value.trim(), match = raw.match(/https?:\/\/[^\s\u3000-\u9fff<>"']+/i);
  return match ? match[0].replace(/[.,;:!?)}\]，。！？；、）》】]+$/u, '') : raw;
}
function updateSourceHelp() {
  const value = enteredUrl();
  const label = /douyin\.com/i.test(value) ? 'Douyin' : /tiktok\.com/i.test(value) ? 'TikTok' : /(facebook\.com|fb\.watch)/i.test(value) ? 'Facebook' : /youtu\.?be/i.test(value) ? 'YouTube' : '';
  $('sourceHelp').textContent = label ? 'Đã nhận link ' + label + '. ' + (label === 'Facebook' ? 'Dùng link tab Reels của Trang để Quét kênh hoặc Tải cả kênh; link /share/r/ chỉ tải một video.' : 'Bấm Quét kênh để xem trước, hoặc Thêm URL tải nếu đây là một video.') : 'Bấm mẫu để điền đầu link kênh, rồi thêm tên hoặc ID. Có thể dán nguyên đoạn chia sẻ chứa link.';
}
document.querySelectorAll('[data-example]').forEach(button => button.onclick = () => { $('url').value = button.dataset.example; $('url').focus(); updateSourceHelp(); });
$('url').addEventListener('input', updateSourceHelp);
$('url').addEventListener('paste', () => setTimeout(() => { const url = enteredUrl(); if (url !== $('url').value.trim()) { $('url').value = url; note('Đã tách link từ đoạn chia sẻ.'); } updateSourceHelp(); }, 0));
function folder() { return $('folder').value.trim(); }
async function add(url, mode = 'video', title = '', quiet = false) {
  try {
    const value = await api('/jobs', 'POST', {url, mode, title, folder:folder(), engine:'auto'});
    if (!quiet) note(value.duplicate ? 'Link này đã nằm trong hàng đợi.' : 'Đã thêm vào hàng đợi.');
    await refresh(); return true;
  } catch (error) { note(error.message, true); return false; }
}
$('singleBtn').onclick = () => enteredUrl() ? add(enteredUrl()) : note('Dán URL video trước.', true);
$('channelBtn').onclick = () => enteredUrl() ? add(enteredUrl(), 'channel', 'Tải cả kênh') : note('Dán URL kênh trước.', true);
$('scanBtn').onclick = async () => {
  const url = enteredUrl(); if (!url) return note('Dán URL kênh trước.', true); if (busy) return;
  busy = true; $('scanBtn').disabled = true; $('scanBtn').textContent = 'Đang quét…'; note('Đang lấy danh sách video…');
  try {
    const data = await api('/scan', 'POST', {url, limit:Number($('limit').value)});
    scanItems = data.items; $('resultsTitle').textContent = data.channel;
    $('resultsMeta').textContent = data.platform + ' · ' + data.items.length + ' video' + (data.limited ? ' (đã đạt giới hạn quét)' : '');
    renderResults(); note(data.items.length ? 'Chọn video rồi nhấn Tải đã chọn.' : 'Không có video xem trước. Có thể dùng Tải cả kênh.');
  } catch (error) { note(error.message, true); }
  finally { busy = false; $('scanBtn').disabled = false; $('scanBtn').textContent = 'Quét kênh'; }
};
function syncResultSelection() {
  const picks = [...document.querySelectorAll('#results .pick')];
  $('selectResults').checked = picks.length > 0 && picks.every(x => x.checked);
  $('selectResults').indeterminate = picks.some(x => x.checked) && !picks.every(x => x.checked);
  $('selectedBtn').textContent = 'Tải đã chọn (' + picks.filter(x => x.checked).length + ')';
}
function renderResults() {
  $('selectResultsWrap').hidden = $('selectedBtn').hidden = !scanItems.length;
  $('selectResults').checked = false;
  $('results').innerHTML = scanItems.length ? scanItems.map((item, i) => `<div class="item"><span class="num">${i + 1}</span><input type="checkbox" class="pick" data-index="${i}" aria-label="Chọn video số ${i + 1}">${item.thumbnail ? `<img class="thumb" src="${esc(item.thumbnail)}" alt="Ảnh xem trước" loading="lazy" referrerpolicy="no-referrer">` : '<div class="thumb">▶</div>'}<div class="itemmain"><div class="itemtitle" title="${esc(item.title)}">${esc(item.title)}</div><div class="meta">${esc(item.url)}</div></div><div class="actions"><button class="mini" data-preview="${i}">▶ Xem</button><button class="mini" data-add="${i}">⇩ Tải</button></div></div>`).join('') : '<div class="empty">Không có video nào.</div>';
  $('results').querySelectorAll('img.thumb').forEach(image => image.onerror = () => { const fallback = document.createElement('div'); fallback.className = 'thumb'; fallback.textContent = '▶'; image.replaceWith(fallback); });
  $('results').querySelectorAll('.pick').forEach(box => box.onchange = syncResultSelection);
  $('results').querySelectorAll('[data-add]').forEach(button => button.onclick = () => { const item = scanItems[Number(button.dataset.add)]; add(item.url, 'video', item.title); });
  $('results').querySelectorAll('[data-preview]').forEach(button => button.onclick = () => window.TVCViewer.preview(scanItems[Number(button.dataset.preview)]));
  syncResultSelection();
}
$('selectResults').onchange = event => { document.querySelectorAll('#results .pick').forEach(box => box.checked = event.target.checked); syncResultSelection(); };
$('selectedBtn').onclick = async () => {
  const indices = [...document.querySelectorAll('#results .pick:checked')].map(x => Number(x.dataset.index));
  if (!indices.length) return note('Chọn ít nhất một video.', true);
  $('selectedBtn').disabled = true; let count = 0;
  for (const i of indices) { const item = scanItems[i]; if (await add(item.url, 'video', item.title, true)) count++; }
  $('selectedBtn').disabled = false; note('Đã đưa ' + count + '/' + indices.length + ' video vào hàng đợi.');
};
function dateTime(seconds) { return seconds ? new Date(seconds * 1000).toLocaleString('vi-VN', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : ''; }
function fileControls(file, number, legacy = false) {
  const url = esc(file.url), title = esc(file.title), key = esc(file.name);
  return `<div class="file-row"><span class="num">${number}</span><label class="filename" title="${title}"><input type="checkbox" class="file-pick" data-file="${key}" aria-label="Chọn ${title}"> ${title}</label><span class="meta">${(file.size / 1048576).toFixed(1)} MB · ${dateTime(file.modified)}</span><span class="actions"><button class="mini" data-view="${key}" ${legacy ? 'data-legacy="1"' : ''}>▶ Xem</button><a class="mini" href="${url}?download=true" download>⇩ Tải về</a></span></div>`;
}
function selectJobFilter(status) {
  activeJobFilter = status;
  document.querySelectorAll('.stat[data-filter]').forEach(button => { const active = button.dataset.filter === status; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
  $('queueTitle').textContent = status === 'all' ? 'Hàng đợi tải' : filterTitles[status];
  $('allJobsBtn').hidden = status === 'all'; $('queue').scrollIntoView({behavior:'smooth',block:'start'}); renderJobs();
}
document.querySelectorAll('.stat[data-filter]').forEach(button => button.onclick = () => selectJobFilter(button.dataset.filter));
$('allJobsBtn').onclick = () => selectJobFilter('all');
function syncJobSelection() {
  const picks = [...document.querySelectorAll('#jobs .file-pick')];
  $('selectJobsWrap').hidden = $('downloadSelected').hidden = !picks.length;
  $('selectJobs').checked = picks.length > 0 && picks.every(box => box.checked);
  $('selectJobs').indeterminate = picks.some(box => box.checked) && !picks.every(box => box.checked);
  $('downloadSelected').textContent = 'Tải file đã chọn (' + picks.filter(box => box.checked).length + ')';
}
$('selectJobs').onchange = event => { document.querySelectorAll('#jobs .file-pick').forEach(box => box.checked = event.target.checked); syncJobSelection(); };
$('downloadSelected').onclick = () => {
  const selected = [...document.querySelectorAll('#jobs .file-pick:checked')].map(box => box.dataset.file);
  if (!selected.length) return note('Chọn ít nhất một file.', true);
  selected.forEach((name, index) => setTimeout(() => {
    const file = mediaFiles.find(x => x.name === name) || jobs.flatMap(job => job.files || []).find(x => x.name === name);
    if (file) { const link = document.createElement('a'); link.href = file.url + '?download=true'; link.download = file.title; document.body.append(link); link.click(); link.remove(); }
  }, index * 400));
  note('Đang tải ' + selected.length + ' file về thiết bị. Nếu trình duyệt hỏi, hãy cho phép tải nhiều file.');
};
function renderJobs() {
  const selectedNames = new Set([...document.querySelectorAll('#jobs .file-pick:checked')].map(box => box.dataset.file));
  const shown = activeJobFilter === 'all' ? jobs : jobs.filter(job => job.status === activeJobFilter);
  const jobOrdinals = new Map(jobs.map((job, index) => [job.id, index + 1]));
  const fileOrdinals = new Map();
  jobs.forEach(job => (job.files || []).forEach(file => { if (!fileOrdinals.has(file.name)) fileOrdinals.set(file.name, fileOrdinals.size + 1); }));
  const attached = new Set(jobs.flatMap(job => (job.files || []).map(file => file.name)));
  const legacy = (activeJobFilter === 'all' || activeJobFilter === 'done') ? mediaFiles.filter(file => !attached.has(file.name)) : [];
  $('queueCount').textContent = shown.length + ' tác vụ · ' + (shown.reduce((sum, job) => sum + (job.files || []).length, 0) + legacy.length) + ' file';
  const html = shown.map(job => `<div class="item job"><span class="num">${jobOrdinals.get(job.id)}</span><div class="thumb">⇩</div><div class="itemmain"><div class="itemtitle" title="${esc(job.title)}">${esc(job.title)}</div><div class="meta">${esc(job.platform)} · ${esc(job.engine)} · ${esc(job.folder)} · ${esc(job.message || '')}${job.status === 'done' ? ' · ' + dateTime(job.updated) : ''}</div><div class="progress"><i style="width:${Math.min(100,Math.max(0,Number(job.progress)||0))}%"></i></div>${(job.files || []).length ? `<div class="file-list">${job.files.map(file => fileControls(file, fileOrdinals.get(file.name))).join('')}</div>` : ''}</div><div class="actions"><span class="status ${job.status === 'failed' ? 'error' : ''}">${names[job.status] || esc(job.status)} ${job.status === 'running' && job.progress ? Math.round(job.progress) + '%' : ''}</span>${['queued','running'].includes(job.status) ? `<button class="mini" data-act="pause" data-id="${esc(job.id)}">Tạm dừng</button>` : ''}${['paused','failed'].includes(job.status) ? `<button class="mini" data-act="resume" data-id="${esc(job.id)}">Tiếp tục</button>` : ''}</div></div>`).join('');
  const older = legacy.length ? `<div class="legacy"><div class="file-subhead">File đã tải trước bản này (${legacy.length})</div>${legacy.map(file => { const number = fileOrdinals.size + mediaFiles.findIndex(x => x.name === file.name) + 1; return `<div class="item"><span class="num">${number}</span><div class="thumb">${file.kind === 'video' ? '▶' : '▧'}</div><div class="itemmain"><div class="itemtitle">${esc(file.title)}</div><div class="meta">${esc(file.name)}</div><div class="file-list">${fileControls(file, number, true)}</div></div></div>`; }).join('')}</div>` : '';
  $('jobs').innerHTML = html + older || `<div class="empty">${activeJobFilter === 'all' ? 'Chưa có tác vụ nào.' : 'Không có tác vụ ' + filterTitles[activeJobFilter].toLowerCase() + '.'}</div>`;
  $('jobs').querySelectorAll('[data-act]').forEach(button => button.onclick = async () => { try { await api('/jobs/' + button.dataset.id + '/' + button.dataset.act, 'POST'); await refresh(); } catch (error) { note(error.message, true); } });
  $('jobs').querySelectorAll('[data-view]').forEach(button => button.onclick = () => {
    const file = mediaFiles.find(x => x.name === button.dataset.view) || jobs.flatMap(job => job.files || []).find(x => x.name === button.dataset.view);
    if (file) window.TVCViewer.open(file.title, file.kind, file.url, file.url + '?download=true');
  });
  $('jobs').querySelectorAll('.file-pick').forEach(box => { box.checked = selectedNames.has(box.dataset.file); });
  $('jobs').querySelectorAll('.file-pick').forEach(box => box.onchange = syncJobSelection);
  syncJobSelection();
}
async function refresh() {
  try {
    const value = await api('/jobs'); jobs = value.jobs; queuePaused = value.paused;
    $('connection').textContent = '● Máy chủ sẵn sàng';
    for (const status of ['queued','running','done','failed']) $(status + 'Count').textContent = jobs.filter(job => job.status === status).length;
    $('globalBtn').textContent = queuePaused ? '▶ Tiếp tục hàng đợi' : '⏸ Tạm dừng hàng đợi';
    if (Date.now() - lastMediaRefresh > 10000) {
      const media = await api('/media'); mediaFiles = media.files; lastMediaRefresh = Date.now();
    }
    renderJobs();
  } catch (error) { $('connection').textContent = '● Mất kết nối'; note(error.message, true); }
}
$('globalBtn').onclick = async () => { try { await api('/queue/' + (queuePaused ? 'resume' : 'pause'), 'POST'); await refresh(); } catch (error) { note(error.message, true); } };
api('/version').then(value => { $('version').textContent = 'Phiên bản ' + value.version; $('versionMain').textContent = value.version; }).catch(() => {});
refresh(); setInterval(refresh, 5000);
