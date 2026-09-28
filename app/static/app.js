'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let scanItems = [], jobs = [], mediaFiles = [], queuePaused = false, busy = false, activeJobFilter = 'all';
let lastMediaRefresh = 0;
const names = {queued:'Đang chờ',running:'Đang tải',paused:'Tạm dừng',done:'Hoàn tất',failed:'Lỗi'};
const filterTitles = {queued:'Đang chờ',running:'Đang tải',done:'Hoàn tất',failed:'Cần kiểm tra'};
$('menuToggle').onclick = () => { const open = $('menuToggle').getAttribute('aria-expanded') !== 'true'; document.querySelector('.side').classList.toggle('menu-open', open); $('menuToggle').setAttribute('aria-expanded', String(open)); };
document.querySelectorAll('.nav a').forEach(link => link.onclick = () => { document.querySelector('.side').classList.remove('menu-open'); $('menuToggle').setAttribute('aria-expanded','false'); });
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
  const shortFacebook = /facebook\.com\/share\/[rv]\//i.test(value);
  $('resolveBtn').hidden = !shortFacebook;
  const label = /douyin\.com/i.test(value) ? 'Douyin' : /tiktok\.com/i.test(value) ? 'TikTok' : /(facebook\.com|fb\.watch)/i.test(value) ? 'Facebook' : /youtu\.?be/i.test(value) ? 'YouTube' : '';
  $('sourceHelp').textContent = shortFacebook ? 'Link chia sẻ Facebook: chọn Tải một video riêng; ứng dụng tự giải mã khi tải.' : label ? 'Đã nhận link ' + label + '. Chọn cách quét kênh hoặc tải một video ở ô Chế độ.' : 'Bấm mẫu để điền đầu link kênh, rồi thêm tên hoặc ID. Có thể dán nguyên đoạn chia sẻ chứa link.';
}
document.querySelectorAll('[data-example]').forEach(button => button.onclick = () => { $('url').value = button.dataset.example; $('url').focus(); updateSourceHelp(); });
$('url').addEventListener('input', updateSourceHelp);
$('url').addEventListener('paste', () => setTimeout(() => { const url = enteredUrl(); if (url !== $('url').value.trim()) { $('url').value = url; note('Đã tách link từ đoạn chia sẻ.'); } updateSourceHelp(); }, 0));
function folder() { return $('folder').value.trim(); }
async function add(url, mode = 'video', title = '', quiet = false) {
  try {
    if (mode === 'video' && /facebook\.com\/share\/[rv]\//i.test(url)) {
      note('Đang giải mã link Facebook…');
      const decoded = await api('/resolve', 'POST', {url});
      if (enteredUrl() === url) { $('url').value = decoded.url; updateSourceHelp(); }
      url = decoded.url;
    }
    const value = await api('/jobs', 'POST', {url, mode, title, folder:folder(), engine:'auto'});
    if (!quiet) note(value.duplicate ? 'Link này đã nằm trong hàng đợi.' : 'Đã thêm vào hàng đợi.');
    await refresh(); return true;
  } catch (error) { note(error.message, true); return false; }
}
$('resolveBtn').onclick = async () => {
  const url = enteredUrl(); $('resolveBtn').disabled = true; note('Đang giải mã link Facebook…');
  try {
    const decoded = await api('/resolve', 'POST', {url});
    $('url').value = decoded.url; updateSourceHelp(); note(decoded.resolved ? 'Đã tìm thấy link Reel gốc: ' + decoded.url : 'Link này đã là link gốc.');
  } catch (error) { note(error.message, true); }
  finally { $('resolveBtn').disabled = false; }
};
const modeLabels = {'20':'Quét 20 video mới nhất','50':'Quét 50 video mới nhất',all:'Quét toàn kênh',single:'Tải video riêng',channel:'Tải cả kênh'};
$('scanMode').onchange = () => { $('scanBtn').textContent = modeLabels[$('scanMode').value]; };
$('scanBtn').onclick = async () => {
  const url = enteredUrl(), mode = $('scanMode').value;
  if (!url) return note('Dán URL trước.', true);
  if (busy) return;
  if (mode === 'single') {
    if (/(?:facebook\.com\/(?:profile\.php|[^/]+\/reels)|tiktok\.com\/@[^/]+\/?$|douyin\.com\/user\/)/i.test(url)) return note('Đây là link kênh. Hãy chọn một chế độ quét.', true);
    busy = true; $('scanBtn').disabled = true;
    try { await add(url); } finally { busy = false; $('scanBtn').disabled = false; }
    return;
  }
  if (mode === 'channel') {
    busy = true; $('scanBtn').disabled = true;
    try { await add(url, 'channel', 'Tải cả kênh'); } finally { busy = false; $('scanBtn').disabled = false; }
    return;
  }
  busy = true; $('scanBtn').disabled = true; $('scanBtn').textContent = 'Đang quét…'; note('Đang lấy danh sách video…');
  try {
    const data = await api('/scan', 'POST', {url, limit:mode === 'all' ? 2000 : Number(mode)});
    scanItems = data.items.map(item => ({...item, platform:data.platform})); $('resultsTitle').textContent = data.channel;
    $('resultsMeta').textContent = data.platform + ' · ' + data.items.length + ' video' + (data.limited ? ' (đã đạt giới hạn quét)' : '');
    renderResults(); note(data.items.length ? 'Chọn video rồi nhấn Tải đã chọn. Thông tin nào nguồn không trả sẽ để trống.' : 'Không có video xem trước.');
  } catch (error) { note(error.message, true); }
  finally { busy = false; $('scanBtn').disabled = false; $('scanBtn').textContent = modeLabels[$('scanMode').value]; }
};
function scanMeta(item) {
  const bits = [item.platform];
  if (item.upload_date) bits.push(String(item.upload_date).replace(/^(\d{4})(\d{2})(\d{2})$/, '$3/$2/$1'));
  if (item.duration != null) bits.push(Math.floor(item.duration / 60) + ':' + String(Math.floor(item.duration % 60)).padStart(2, '0'));
  bits.push(item.view_count != null ? new Intl.NumberFormat('vi-VN').format(item.view_count) + ' lượt xem' : (item.view_label || 'Lượt xem: chưa có dữ liệu'));
  return bits.filter(Boolean).join(' · ');
}
function syncResultSelection() {
  const picks = [...document.querySelectorAll('#results .pick')];
  const selected = picks.filter(x => x.checked).length;
  $('selectResults').checked = picks.length > 0 && picks.every(x => x.checked);
  $('selectResults').indeterminate = picks.some(x => x.checked) && !picks.every(x => x.checked);
  $('selectedBtn').hidden = !selected;
  $('selectedBtn').textContent = 'Tải đã chọn (' + selected + ')';
}
function renderResults() {
  $('selectResultsWrap').hidden = !scanItems.length;
  $('selectResults').checked = false;
  $('results').innerHTML = scanItems.length ? scanItems.map((item, i) => `<article class="result-card"><div class="result-poster">${item.thumbnail ? `<img src="${esc(item.thumbnail)}" alt="Ảnh xem trước" loading="lazy" referrerpolicy="no-referrer">` : '<div class="poster-empty">▶</div>'}<span class="result-index">#${i + 1}</span><label class="result-pick" title="Chọn video"><input type="checkbox" class="pick" data-index="${i}" aria-label="Chọn video số ${i + 1}"></label><button class="poster-play" data-preview="${i}" aria-label="Xem video số ${i + 1}">▶</button></div><div class="result-info"><div class="itemtitle" title="${esc(item.title)}">${esc(item.title)}</div><div class="result-metadata">${esc(scanMeta(item))}</div>${item.caption ? `<div class="scan-caption" title="${esc(item.caption)}"><b>Caption:</b> ${esc(item.caption)}</div>` : ''}${item.hashtags?.length ? `<div class="scan-tags" title="${esc(item.hashtags.map(tag => '#' + tag).join(' '))}">${item.hashtags.map(tag => '#' + esc(tag)).join(' ')}</div>` : ''}<div class="result-actions"><button class="mini" data-preview="${i}">▶ Xem</button><button class="mini" data-add="${i}">⇩ Tải</button></div></div></article>`).join('') : '<div class="empty">Không có video nào.</div>';
  $('results').querySelectorAll('.result-poster img').forEach(image => image.onerror = () => { const fallback = document.createElement('div'); fallback.className = 'poster-empty'; fallback.textContent = '▶'; image.replaceWith(fallback); });
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
  const selected = picks.filter(box => box.checked).length;
  $('selectJobsWrap').hidden = !picks.length;
  $('downloadSelected').hidden = !selected;
  $('selectJobs').checked = picks.length > 0 && picks.every(box => box.checked);
  $('selectJobs').indeterminate = picks.some(box => box.checked) && !picks.every(box => box.checked);
  $('downloadSelected').textContent = 'Tải file đã chọn (' + selected + ')';
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
function fileCard(file, job, number) {
  const title = job && job.mode !== 'channel' && !/^https?:/.test(job.title) ? job.title : file.title;
  const platform = job ? job.platform : file.name.split('/')[0];
  const name = esc(file.name), fileUrl = esc(file.url), thumbUrl = esc(file.thumbnail || file.url);
  return `<div class="item queue-card"><span class="num">${number}</span><div class="queue-thumb-wrap"><img class="thumb" src="${thumbUrl}" alt="" loading="lazy"><span class="thumb-fallback" hidden>▶</span></div><div class="itemmain"><div class="itemtitle" title="${esc(title)}">${esc(title)}</div><div class="meta">${esc(platform)} · ${((file.size || 0) / 1048576).toFixed(1)} MB · ${dateTime(file.modified)}</div><span class="status-chip">✓ Hoàn tất</span></div><button class="mini queue-more" type="button" aria-label="Chi tiết file" aria-expanded="false">⋮</button><label class="queue-select" title="Chọn file"><input type="checkbox" class="file-pick" data-file="${name}" aria-label="Chọn ${esc(file.title)}"></label><div class="actions"><button class="mini" data-view="${name}">▶ Xem</button><a class="mini download-action" href="${fileUrl}?download=true" download>⇩ Tải về</a></div><div class="progress"><i style="width:100%"></i></div><div class="queue-detail" hidden>${name}</div></div>`;
}
function pendingCard(job, number) {
  const pct = Math.min(100, Math.max(0, Number(job.progress) || 0));
  return `<div class="item queue-card"><span class="num">${number}</span><div class="queue-thumb-wrap"><div class="thumb">⇩</div></div><div class="itemmain"><div class="itemtitle" title="${esc(job.title)}">${esc(job.title)}</div><div class="meta">${esc(job.platform)} · ${esc(job.folder)} · ${dateTime(job.created)}</div><span class="status-chip ${job.status === 'failed' ? 'status-failed' : ''}">${names[job.status] || esc(job.status)} ${job.status === 'running' ? Math.round(pct) + '%' : ''}</span></div><button class="mini queue-more" type="button" aria-label="Chi tiết tác vụ" aria-expanded="false">⋮</button><div class="actions">${['queued','running'].includes(job.status) ? `<button class="mini" data-act="pause" data-id="${esc(job.id)}">⏸ Tạm dừng</button>` : ''}${['paused','failed'].includes(job.status) ? `<button class="mini" data-act="resume" data-id="${esc(job.id)}">▶ Tiếp tục</button>` : ''}</div><div class="progress"><i style="width:${pct}%"></i></div><div class="queue-detail" hidden>${esc(job.message || job.url)}</div></div>`;
}
function renderJobs() {
  const selectedNames = new Set([...document.querySelectorAll('#jobs .file-pick:checked')].map(box => box.dataset.file));
  const shown = activeJobFilter === 'all' ? jobs : jobs.filter(job => job.status === activeJobFilter);
  const jobOrdinals = new Map(jobs.map((job, index) => [job.id, index + 1]));
  const fileOrdinals = new Map();
  jobs.forEach(job => (job.files || []).forEach(file => { if (!fileOrdinals.has(file.name)) fileOrdinals.set(file.name, fileOrdinals.size + 1); }));
  const legacy = (activeJobFilter === 'all' || activeJobFilter === 'done') ? mediaFiles.filter(file => !fileOrdinals.has(file.name)) : [];
  const shownCount = shown.reduce((sum, job) => sum + Math.max(1, (job.files || []).length), 0);
  $('queueCount').textContent = shownCount + ' mục · ' + (shown.reduce((sum, job) => sum + (job.files || []).length, 0) + legacy.length) + ' file';
  const cards = shown.flatMap(job => (job.files || []).length ? job.files.map(file => fileCard(file, job, fileOrdinals.get(file.name))) : [pendingCard(job, jobOrdinals.get(job.id))]);
  if (legacy.length) cards.push(`<div class="file-subhead">File đã tải trước bản này (${legacy.length})</div>`);
  legacy.forEach(file => cards.push(fileCard(file, null, fileOrdinals.size + mediaFiles.findIndex(x => x.name === file.name) + 1)));
  $('jobs').innerHTML = cards.join('') || `<div class="empty">${activeJobFilter === 'all' ? 'Chưa có tác vụ nào.' : 'Không có tác vụ ' + filterTitles[activeJobFilter].toLowerCase() + '.'}</div>`;
  $('jobs').querySelectorAll('img.thumb').forEach(image => image.onerror = () => { image.hidden = true; image.nextElementSibling.hidden = false; });
  $('jobs').querySelectorAll('[data-act]').forEach(button => button.onclick = async () => { try { await api('/jobs/' + button.dataset.id + '/' + button.dataset.act, 'POST'); await refresh(); } catch (error) { note(error.message, true); } });
  $('jobs').querySelectorAll('[data-view]').forEach(button => button.onclick = () => {
    const file = mediaFiles.find(x => x.name === button.dataset.view) || jobs.flatMap(job => job.files || []).find(x => x.name === button.dataset.view);
    if (file) window.TVCViewer.open(file.title, file.kind, file.url, file.url + '?download=true');
  });
  $('jobs').querySelectorAll('.queue-more').forEach(button => button.onclick = () => { const detail = button.closest('.queue-card').querySelector('.queue-detail'); detail.hidden = !detail.hidden; button.setAttribute('aria-expanded', String(!detail.hidden)); });
  $('jobs').querySelectorAll('.file-pick').forEach(box => { box.checked = selectedNames.has(box.dataset.file); box.onchange = syncJobSelection; });
  syncJobSelection();
}

async function refresh() {
  try {
    const value = await api('/jobs'); jobs = value.jobs; queuePaused = value.paused;
    $('connection').textContent = '● Máy chủ sẵn sàng';
    $('mobileConnection').textContent = '● Máy chủ sẵn sàng';
    for (const status of ['queued','running','done','failed']) $(status + 'Count').textContent = jobs.filter(job => job.status === status).length;
    $('globalBtn').textContent = queuePaused ? '▶ Tiếp tục hàng đợi' : '⏸ Tạm dừng hàng đợi';
    if (Date.now() - lastMediaRefresh > 10000) {
      const media = await api('/media'); mediaFiles = media.files; lastMediaRefresh = Date.now();
    }
    renderJobs();
  } catch (error) { $('connection').textContent = '● Mất kết nối'; $('mobileConnection').textContent = '● Mất kết nối'; note(error.message, true); }
}
$('globalBtn').onclick = async () => { try { await api('/queue/' + (queuePaused ? 'resume' : 'pause'), 'POST'); await refresh(); } catch (error) { note(error.message, true); } };
api('/version').then(value => { $('version').textContent = 'Phiên bản ' + value.version; $('versionMain').textContent = value.version; }).catch(() => {});
refresh(); setInterval(refresh, 5000);
