(() => {
  const byId = id => document.getElementById(id);
  const dialog = byId('viewer'), body = byId('viewerBody');
  let images = [], position = 0;
  const clear = () => { const v = body.querySelector('video'); if (v) { v.pause(); v.removeAttribute('src'); v.load(); } body.replaceChildren(); };
  function showImage(index) {
    position = index;
    clear();
    const img = document.createElement('img'); img.alt = byId('viewerTitle').textContent;
    img.src = images[index]; body.append(img);
    byId('viewerPrev').hidden = byId('viewerNext').hidden = images.length < 2;
    byId('viewerPosition').textContent = images.length > 1 ? `${index + 1} / ${images.length}` : '';
  }
  function open(title, kind, url, downloadUrl = '', gallery = [], hint = '') {
    clear(); byId('viewerTitle').textContent = title;
    byId('viewerHint').textContent = hint;
    images = gallery.length ? gallery : [url]; position = 0;
    byId('viewerPrev').hidden = byId('viewerNext').hidden = true;
    byId('viewerPosition').textContent = '';
    const link = byId('viewerDownload'); link.hidden = !downloadUrl;
    if (downloadUrl) link.href = downloadUrl;
    if (kind === 'image') showImage(0);
    else {
      const video = document.createElement('video'); video.controls = true; video.playsInline = true;
      video.preload = 'metadata'; video.src = url;
      video.onerror = () => { byId('viewerHint').textContent = 'Nguồn này không phát trực tiếp được. Hãy tải file về Ubuntu rồi xem trong Thư viện.'; };
      body.append(video);
    }
    if (!dialog.open) dialog.showModal();
  }
  byId('viewerClose').onclick = () => dialog.close();
  dialog.addEventListener('close', clear);
  byId('viewerPrev').onclick = () => showImage((position + images.length - 1) % images.length);
  byId('viewerNext').onclick = () => showImage((position + 1) % images.length);
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  async function json(path, opts) {
    const r = await fetch(path, opts); const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Lỗi ' + r.status);
    return data;
  }
  async function preview(item) {
    byId('viewerHint').textContent = 'Đang lấy video/ảnh xem trước…';
    try {
      const d = await json('/api/preview', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({url:item.url})});
      if (!d.available) throw Error('Nguồn này chưa có ảnh hoặc video xem trước.');
      open(d.title || item.title, d.kind, d.url, '', d.images || [], 'Xem trước từ nguồn; một số video cần cookie hoặc chặn phát trực tiếp.');
    } catch (e) { byId('viewerHint').textContent = e.message; if (!dialog.open) dialog.showModal(); }
  }
  async function loadMedia() {
    try {
      const data = await json('/api/media');
      byId('mediaCount').textContent = `${data.total} file trên Ubuntu · Tải về tạo bản sao trên thiết bị`;
      const list = byId('mediaList'); list.replaceChildren();
      if (!data.files.length) { const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = 'Chưa có file video hoặc ảnh đã tải.'; list.append(empty); return; }
      for (const item of data.files) {
        const row = document.createElement('div'); row.className = 'item';
        const thumb = document.createElement('div'); thumb.className = 'thumb'; thumb.textContent = item.kind === 'video' ? '▶' : '▧';
        const main = document.createElement('div'); main.className = 'itemmain';
        const title = document.createElement('div'); title.className = 'itemtitle'; title.textContent = item.title;
        const meta = document.createElement('div'); meta.className = 'meta'; meta.textContent = `${item.name} · ${(item.size / 1048576).toFixed(1)} MB`;
        main.append(title, meta);
        const actions = document.createElement('div'); actions.className = 'actions';
        const view = document.createElement('button'); view.className = 'mini'; view.textContent = '▶ Xem';
        view.onclick = () => open(item.title, item.kind, item.url, item.url + '?download=true');
        const save = document.createElement('a'); save.className = 'mini'; save.textContent = '⇩ Tải về'; save.href = item.url + '?download=true';
        actions.append(view, save); row.append(thumb, main, actions); list.append(row);
      }
    } catch (e) { byId('mediaCount').textContent = e.message; }
  }
  byId('reloadMedia').onclick = loadMedia;
  window.TVCViewer = {preview, loadMedia};
  loadMedia();
})();
