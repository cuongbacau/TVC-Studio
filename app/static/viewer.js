(() => {
  const byId = id => document.getElementById(id);
  const dialog = byId('viewer'), body = byId('viewerBody');
  let images = [], position = 0;
  const clear = () => { const video = body.querySelector('video'); if (video) { video.pause(); video.removeAttribute('src'); video.load(); } body.replaceChildren(); };
  function showImage(index) {
    position = index; clear();
    const img = document.createElement('img'); img.alt = byId('viewerTitle').textContent; img.src = images[index]; body.append(img);
    byId('viewerPrev').hidden = byId('viewerNext').hidden = images.length < 2;
    byId('viewerPosition').textContent = images.length > 1 ? `${index + 1} / ${images.length}` : '';
  }
  function open(title, kind, url, downloadUrl = '', gallery = [], hint = '') {
    clear(); byId('viewerTitle').textContent = title; byId('viewerHint').textContent = hint;
    images = gallery.length ? gallery : [url]; position = 0;
    byId('viewerPrev').hidden = byId('viewerNext').hidden = true;
    byId('viewerPosition').textContent = '';
    const link = byId('viewerDownload'); link.hidden = !downloadUrl;
    if (downloadUrl) { link.href = downloadUrl; link.download = title; }
    if (!dialog.open) dialog.showModal();
    if (kind === 'image') showImage(0);
    else {
      const video = document.createElement('video'); video.controls = true; video.playsInline = true;
      video.preload = 'auto'; video.src = url;
      video.onerror = () => { byId('viewerHint').textContent = 'Trình duyệt không phát được định dạng/nguồn này. Bấm Tải về thiết bị để xem.'; };
      body.append(video);
      video.play().catch(() => {
        video.muted = true;
        video.play().then(() => { byId('viewerHint').textContent = 'Đang phát tắt tiếng theo quy định của trình duyệt. Bấm biểu tượng loa để bật tiếng.'; })
          .catch(() => { byId('viewerHint').textContent = 'Trình duyệt chặn tự phát. Bấm ▶ trên video để xem.'; });
      });
    }
  }
  byId('viewerClose').onclick = () => dialog.close();
  dialog.addEventListener('close', clear);
  byId('viewerPrev').onclick = () => showImage((position + images.length - 1) % images.length);
  byId('viewerNext').onclick = () => showImage((position + 1) % images.length);
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  async function preview(item) {
    byId('viewerHint').textContent = 'Đang lấy video/ảnh xem trước…';
    try {
      const response = await fetch('api/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:item.url})});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(data.detail || 'Lỗi ' + response.status);
      if (!data.available) throw Error('Nguồn này chưa có ảnh hoặc video xem trước.');
      open(data.title || item.title, data.kind, data.url, '', data.images || [], 'Xem trước từ nguồn; một số video cần cookie hoặc chặn phát trực tiếp.');
    } catch (error) { byId('viewerHint').textContent = error.message; if (!dialog.open) dialog.showModal(); }
  }
  window.TVCViewer = {open, preview};
})();
