import asyncio
import json
import os
import re
import secrets
import signal
import sqlite3
import sys
import time
import uuid
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, quote, parse_qs

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(os.getenv('TVC_DATA', './data')).resolve()
DOWNLOADS = ROOT / 'downloads'
DB = ROOT / 'queue.sqlite3'
ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOADS.mkdir(exist_ok=True)
app = FastAPI(title='TVC Downloader', docs_url=None, redoc_url=None)
VERSION = (Path(__file__).parent.parent / 'VERSION').read_text().strip() if (Path(__file__).parent.parent / 'VERSION').exists() else 'dev'
security = HTTPBasic()
active = {}
worker_task = None
paused = False
VIDEO_EXT = {'.mp4', '.webm', '.mov', '.m4v', '.mkv'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}


def auth(credentials: HTTPBasicCredentials = Depends(security)):
    user = os.getenv('TVC_USER', 'admin')
    password = os.getenv('TVC_PASSWORD', '')
    if not password or not (secrets.compare_digest(credentials.username, user) and secrets.compare_digest(credentials.password, password)):
        raise HTTPException(401, 'Sai tài khoản hoặc mật khẩu', headers={'WWW-Authenticate': 'Basic'})


def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
          platform TEXT NOT NULL, mode TEXT NOT NULL, engine TEXT NOT NULL,
          folder TEXT NOT NULL, status TEXT NOT NULL, progress REAL DEFAULT 0,
          message TEXT DEFAULT '', attempts INTEGER DEFAULT 0,
          created REAL NOT NULL, updated REAL NOT NULL)''')
        c.execute("UPDATE jobs SET status='queued', message='Tiếp tục sau khi khởi động lại' WHERE status='running'")
        c.execute('''CREATE TABLE IF NOT EXISTS job_files (
          job_id TEXT NOT NULL, name TEXT NOT NULL,
          PRIMARY KEY(job_id, name))''')


def rows():
    with conn() as c:
        jobs = [dict(x) for x in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 500')]
        attached = {}
        for row in c.execute('SELECT job_id, name FROM job_files'):
            attached.setdefault(row['job_id'], []).append(row['name'])
        for job in jobs:
            job['files'] = [media_entry(DOWNLOADS / name) for name in attached.get(job['id'], [])
                            if safe_media_path(name)]
        return jobs


def safe_media_path(name):
    path = (DOWNLOADS / name).resolve()
    return (path.is_relative_to(DOWNLOADS) and path.is_file() and not path.is_symlink()
            and path.suffix.lower() in VIDEO_EXT | IMAGE_EXT)


def media_entry(path):
    stat = path.stat()
    name = path.relative_to(DOWNLOADS).as_posix()
    return {'name': name, 'title': path.name,
            'kind': 'video' if path.suffix.lower() in VIDEO_EXT else 'image',
            'size': stat.st_size, 'modified': stat.st_mtime,
            'url': '/api/media/file/' + quote(name, safe='/')}


def folder_media(job):
    destination = DOWNLOADS / job['platform'] / job['folder']
    return {p.relative_to(DOWNLOADS).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in destination.rglob('*') if p.is_file() and not p.is_symlink()
            and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT}


def update(jid, **fields):
    fields['updated'] = time.time()
    with conn() as c:
        c.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', [*fields.values(), jid])


def get_job(jid):
    with conn() as c:
        row = c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Không có tác vụ')
        return dict(row)


def platform_of(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise HTTPException(422, 'Cần link http(s) hợp lệ')
    host = (parsed.hostname or '').lower().rstrip('.')
    if host in ('douyin.com', 'www.douyin.com', 'v.douyin.com', 'iesdouyin.com'):
        return 'Douyin'
    if host in ('tiktok.com', 'www.tiktok.com', 'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com'):
        return 'TikTok'
    if host in ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'fb.watch'):
        return 'Facebook'
    if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        return 'YouTube'
    raise HTTPException(422, 'Chỉ nhận link Douyin, TikTok, Facebook hoặc YouTube')


def clean_url(value):
    # Share sheets (notably Douyin) copy a caption and URL in the same text.
    match = re.search(r'https?://[^\s\u3000-\u9fff<>"\']+', value, flags=re.IGNORECASE)
    if not match:
        raise HTTPException(422, 'Dán link http(s) của video hoặc kênh')
    url = match.group(0).rstrip('.,;:!?)]}，。！？；、）》】')
    platform_of(url)
    return url


def facebook_reels_url(url):
    parsed = urlparse(url)
    if platform_of(url) != 'Facebook':
        raise HTTPException(422, 'Cần link Trang Facebook')
    parts = [p for p in parsed.path.split('/') if p]
    if parts == ['profile.php']:
        profile_id = parse_qs(parsed.query).get('id', [''])[0]
        if not re.fullmatch(r'\d{10,20}', profile_id):
            raise HTTPException(422, 'Link Trang thiếu ID Facebook')
        return f'https://www.facebook.com/profile.php?id={profile_id}&sk=reels_tab'
    if len(parts) in (1, 2) and parts[0].lower() not in ('share', 'reel', 'watch', 'videos', 'groups'):
        if len(parts) == 1 or parts[1].lower() in ('reels', 'videos'):
            return f'https://www.facebook.com/{parts[0]}/reels/'
    raise HTTPException(422, 'Đây là link video. Để quét Reels, dán link Trang Facebook (mục Reels).')


async def facebook_items(url, limit):
    cookies = cookie_file('Facebook')
    if not cookies:
        raise HTTPException(422, 'Quét toàn bộ Reels cần cookie Facebook tại data/cookies/facebook.txt trên Ubuntu.')
    cmd = [sys.executable, '-m', 'app.facebook_reels', facebook_reels_url(url), str(cookies), str(limit)]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=480)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(504, 'Quét Reels quá thời gian; thử lại hoặc giảm số video.')
    if proc.returncode:
        raise HTTPException(422, err.decode(errors='replace')[-450:] or 'Không đọc được Reels Facebook')
    try:
        result = json.loads(out)
        items = result.get('items') if 'items' in result else [{'url': url, 'thumbnail': ''} for url in result.get('urls', [])]
    except (ValueError, KeyError):
        raise HTTPException(502, 'Danh sách Reels không hợp lệ')
    if not items:
        raise HTTPException(422, 'Không thấy Reel nào. Kiểm tra cookie Facebook còn hạn và Trang có Reels công khai.')
    return [{'url': item['url'], 'title': item.get('title') or 'Reel ' + item['url'].rstrip('/').split('/')[-1],
             'thumbnail': item.get('thumbnail') or ''} for item in items[:limit]]


def cookie_file(platform):
    path = ROOT / 'cookies' / (platform.lower() + '.txt')
    if path.is_file() and path.stat().st_size > 0:
        return path
    return None


def f2_cookie(platform):
    path = cookie_file(platform)
    if not path:
        return None
    hosts = {'TikTok': ('tiktok.com',), 'Douyin': ('douyin.com',)}.get(platform, ())
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) != 7:
            continue
        domain, _, _, _, expiry, name, value = parts
        if not any(domain.lstrip('.') == host or domain.lstrip('.').endswith('.' + host) for host in hosts):
            continue
        if expiry.isdigit() and int(expiry) and int(expiry) < time.time():
            continue
        values[name] = value
    return '; '.join(f'{k}={v}' for k, v in values.items()) or None


def folder_name(value):
    value = re.sub(r'[^\w .-]', '_', value, flags=re.UNICODE).strip(' .')[:80]
    if not value or value in ('.', '..'):
        raise HTTPException(422, 'Tên thư mục không hợp lệ')
    return value


class Scan(BaseModel):
    url: str
    limit: int = Field(60, ge=1, le=200)


class Add(BaseModel):
    url: str
    title: str = ''
    mode: str = 'video'
    folder: str = ''
    engine: str = 'auto'


@app.get('/')
def home(_: None = Depends(auth)):
    return FileResponse(Path(__file__).parent / 'static' / 'index.html')


@app.get('/api/version')
def version(_: None = Depends(auth)):
    return {'version': VERSION}


@app.get('/api/media')
def media(_: None = Depends(auth)):
    files = []
    for path in DOWNLOADS.rglob('*'):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in VIDEO_EXT | IMAGE_EXT:
            continue
        try:
            files.append(media_entry(path))
        except OSError:
            continue
    files.sort(key=lambda item: item['modified'], reverse=True)
    return {'files': files[:500], 'total': len(files)}


@app.get('/api/media/file/{name:path}')
def media_file(name: str, download: bool = False, _: None = Depends(auth)):
    path = (DOWNLOADS / name).resolve()
    if not path.is_relative_to(DOWNLOADS) or not path.is_file() or path.suffix.lower() not in VIDEO_EXT | IMAGE_EXT:
        raise HTTPException(404, 'Không tìm thấy file')
    # The source file stays on Ubuntu. Browser download is a copy.
    return FileResponse(path, filename=path.name if download else None,
                        content_disposition_type='attachment' if download else 'inline',
                        media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')


class Preview(BaseModel):
    url: str


@app.post('/api/preview')
async def preview(payload: Preview, _: None = Depends(auth)):
    payload.url = clean_url(payload.url)
    platform = platform_of(payload.url)
    cmd = ['yt-dlp', '--dump-single-json', '--no-playlist', '--no-warnings', '--skip-download']
    if cookies := cookie_file(platform):
        cmd += ['--cookies', str(cookies)]
    cmd.append(payload.url)
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(504, 'Xem trước quá thời gian')
    if proc.returncode:
        raise HTTPException(422, (err.decode(errors='replace')[-400:] or 'Không xem trước được'))
    try:
        info = json.loads(out)
    except ValueError:
        raise HTTPException(502, 'Dữ liệu xem trước không hợp lệ')
    formats = [f for f in (info.get('formats') or []) if str(f.get('url') or '').startswith('https://') and
               f.get('ext') == 'mp4' and f.get('vcodec') != 'none' and f.get('acodec') != 'none' and
               f.get('protocol') in (None, 'https')]
    formats.sort(key=lambda f: ((f.get('height') or 0) > 720, abs((f.get('height') or 720) - 720), -(f.get('height') or 0)))
    source = formats[0]['url'] if formats else (info.get('url') if str(info.get('url') or '').startswith('https://') and info.get('ext') == 'mp4' else '')
    photos = [e.get('url') for e in (info.get('entries') or []) if isinstance(e, dict) and str(e.get('url') or '').startswith('https://') and ('.' + str(e.get('ext', '')).lower()) in IMAGE_EXT]
    thumbnail = info.get('thumbnail') or ''
    return {'title': info.get('title') or 'Xem trước', 'kind': 'video' if source else 'image',
            'url': source or (photos[0] if photos else thumbnail), 'images': photos,
            'thumbnail': thumbnail, 'available': bool(source or photos or thumbnail)}


@app.get('/api/jobs')
def jobs(_: None = Depends(auth)):
    return {'jobs': rows(), 'paused': paused}


@app.post('/api/scan')
async def scan(payload: Scan, _: None = Depends(auth)):
    payload.url = clean_url(payload.url)
    platform = platform_of(payload.url)
    if platform == 'Facebook':
        url = facebook_reels_url(payload.url)
        items = await facebook_items(url, payload.limit)
        return {'platform': platform, 'channel': 'Facebook Reels',
                'items': items, 'limited': len(items) >= payload.limit}
    # Never resolve arbitrary domains or run a shell. yt-dlp may follow platform redirects.
    cmd = ['yt-dlp', '--dump-single-json', '--flat-playlist', '--playlist-end', str(payload.limit), '--no-warnings', '--no-download']
    if cookies := cookie_file(platform):
        cmd += ['--cookies', str(cookies)]
    cmd.append(payload.url)
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(504, 'Quét quá thời gian. Thử link khác hoặc thêm cookie trên máy chủ.')
    if proc.returncode:
        raise HTTPException(422, (err.decode(errors='replace')[-500:] or 'Không quét được kênh'))
    try:
        data = json.loads(out)
    except ValueError:
        raise HTTPException(502, 'Không đọc được dữ liệu từ yt-dlp')
    items = []
    for entry in (data.get('entries') or [data])[:payload.limit]:
        if not entry:
            continue
        link = entry.get('webpage_url') or entry.get('url') or ''
        if not link.startswith('http'):
            link = entry.get('original_url') or ''
        if not link.startswith('http'):
            continue
        try:
            platform_of(link)
        except HTTPException:
            continue
        thumbs = entry.get('thumbnails') or []
        thumbnail = entry.get('thumbnail') or next((t.get('url') for t in reversed(thumbs) if isinstance(t, dict) and t.get('url')), '')
        items.append({'url': link, 'title': entry.get('title') or entry.get('id') or 'Video', 'thumbnail': thumbnail})
    return {'platform': platform, 'channel': data.get('channel') or data.get('uploader') or data.get('title') or platform, 'items': items, 'limited': len(items) >= payload.limit}


@app.post('/api/jobs')
def add(payload: Add, _: None = Depends(auth)):
    payload.url = clean_url(payload.url)
    platform = platform_of(payload.url)
    if payload.mode not in ('video', 'channel'):
        raise HTTPException(422, 'Chế độ không hợp lệ')
    if platform == 'Facebook' and payload.mode == 'channel':
        payload.url = facebook_reels_url(payload.url)
    engine = ('facebook-reels' if platform == 'Facebook' and payload.mode == 'channel' else
              'f2' if platform == 'Douyin' or (platform == 'TikTok' and payload.mode == 'channel') else 'yt-dlp') if payload.engine == 'auto' else payload.engine
    if engine not in ('f2', 'yt-dlp', 'facebook-reels') or (engine == 'f2' and platform not in ('Douyin', 'TikTok')) or (engine == 'facebook-reels' and (platform != 'Facebook' or payload.mode != 'channel')):
        raise HTTPException(422, 'Bộ tải không hỗ trợ nền tảng này')
    folder = folder_name(payload.folder or platform)
    title = (payload.title or payload.url)[:180]
    with conn() as c:
        existing = c.execute("SELECT id FROM jobs WHERE url=? AND folder=? AND mode=? AND status IN ('queued','running')", (payload.url, folder, payload.mode)).fetchone()
        if existing:
            return {'id': existing['id'], 'duplicate': True}
        jid = str(uuid.uuid4())
        now = time.time()
        c.execute('INSERT INTO jobs (id,url,title,platform,mode,engine,folder,status,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?)', (jid,payload.url,title,platform,payload.mode,engine,folder,'queued',now,now))
    return {'id': jid, 'duplicate': False}


@app.post('/api/jobs/{jid}/pause')
async def pause_job(jid: str, _: None = Depends(auth)):
    job = get_job(jid)
    if job['status'] == 'running':
        proc = active.get(jid)
        if proc:
            proc.terminate()
        update(jid, status='paused', message='Đã tạm dừng')
    elif job['status'] == 'queued':
        update(jid, status='paused', message='Đã tạm dừng')
    return {'ok': True}


@app.post('/api/jobs/{jid}/resume')
def resume_job(jid: str, _: None = Depends(auth)):
    job = get_job(jid)
    if job['status'] in ('paused', 'failed'):
        update(jid, status='queued', message='Chờ tải', progress=0)
    return {'ok': True}


@app.post('/api/queue/pause')
def pause_queue(_: None = Depends(auth)):
    global paused
    paused = True
    for jid, proc in list(active.items()):
        update(jid, status='queued', message='Hàng đợi tạm dừng; sẽ tiếp tục')
        proc.terminate()
    return {'ok': True}


@app.post('/api/queue/resume')
def resume_queue(_: None = Depends(auth)):
    global paused
    paused = False
    return {'ok': True}


def command_for(job):
    destination = DOWNLOADS / job['platform'] / job['folder']
    destination.mkdir(parents=True, exist_ok=True)
    if job['engine'] == 'f2':
        alias = 'dy' if job['platform'] == 'Douyin' else 'tk'
        mode = 'post' if job['mode'] == 'channel' else 'one'
        cmd = ['f2', alias, '-M', mode, '-u', job['url'], '-p', str(destination)]
        if cookie := f2_cookie(job['platform']):
            cmd += ['-k', cookie]
        return cmd
    archive = ROOT / 'archive.txt'
    cmd = ['yt-dlp', '--newline', '--no-warnings', '--continue', '--download-archive', str(archive), '--retries', '5', '--fragment-retries', '5']
    if cookies := cookie_file(job['platform']):
        cmd += ['--cookies', str(cookies)]
    return cmd + ['-o', str(destination / '%(upload_date)s_%(id)s_%(title).100B.%(ext)s'), job['url']]


async def run_job(job):
    jid = job['id']
    before = folder_media(job)
    update(jid, status='running', attempts=job['attempts'] + 1, message='Đang tải')
    log = []
    try:
        cmd = command_for(job)
        if job['engine'] == 'facebook-reels':
            update(jid, message='Đang quét Reels Facebook (có thể mất vài phút)')
            items = await facebook_items(job['url'], 2000)
            if paused:
                update(jid, status='queued', message='Hàng đợi tạm dừng; sẽ quét lại')
                return
            if get_job(jid)['status'] != 'running':
                return
            list_path = ROOT / ('facebook-reels-' + jid + '.txt')
            list_path.write_text('\n'.join(item['url'] for item in items) + '\n', encoding='utf-8')
            cmd = cmd[:-1] + ['-a', str(list_path)]
            update(jid, message=f'Đã tìm {len(items)} Reels; đang tải')
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        active[jid] = proc
        while line := await proc.stdout.readline():
            s = line.decode(errors='replace').strip()
            log.append(s)
            log = log[-8:]
            percent = re.search(r'\[download\]\s+(\d+(?:\.\d+)?)%', s)
            if percent:
                update(jid, progress=float(percent.group(1)), message='Đang tải')
            elif 'ERROR:' in s or 'WARNING:' in s:
                update(jid, message=s[-240:])
        code = await proc.wait()
        current = get_job(jid)
        if current['status'] != 'running':
            return
        if code == 0:
            after = folder_media(job)
            changed = [name for name, signature in after.items() if before.get(name) != signature]
            if changed:
                with conn() as c:
                    c.executemany('INSERT OR IGNORE INTO job_files (job_id,name) VALUES (?,?)',
                                  [(jid, name) for name in changed])
            update(jid, status='done', progress=100, message='Hoàn tất')
        else:
            msg = '\n'.join(log)[-500:] or f'Bộ tải thoát mã {code}'
            update(jid, status='failed', message=msg)
    except Exception as exc:
        if get_job(jid)['status'] == 'running':
            update(jid, status='failed', message=str(exc.detail if isinstance(exc, HTTPException) else exc)[:500])
    finally:
        active.pop(jid, None)


async def worker():
    while True:
        if not paused:
            with conn() as c:
                row = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                await run_job(dict(row))
                continue
        await asyncio.sleep(1)


@app.on_event('startup')
async def startup():
    global worker_task
    init_db()
    worker_task = asyncio.create_task(worker())


@app.on_event('shutdown')
async def shutdown():
    if worker_task:
        worker_task.cancel()
    for proc in active.values():
        proc.terminate()


app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
