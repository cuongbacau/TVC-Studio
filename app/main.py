import asyncio
import json
import os
import re
import secrets
import signal
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

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


def rows():
    with conn() as c:
        return [dict(x) for x in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 500')]


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


@app.get('/api/jobs')
def jobs(_: None = Depends(auth)):
    return {'jobs': rows(), 'paused': paused}


@app.post('/api/scan')
async def scan(payload: Scan, _: None = Depends(auth)):
    platform = platform_of(payload.url)
    # Never resolve arbitrary domains or run a shell. yt-dlp may follow platform redirects.
    cmd = ['yt-dlp', '--dump-single-json', '--flat-playlist', '--playlist-end', str(payload.limit), '--no-warnings', '--no-download', payload.url]
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
        items.append({'url': link, 'title': entry.get('title') or entry.get('id') or 'Video', 'thumbnail': entry.get('thumbnail') or ''})
    return {'platform': platform, 'channel': data.get('channel') or data.get('uploader') or data.get('title') or platform, 'items': items, 'limited': len(items) >= payload.limit}


@app.post('/api/jobs')
def add(payload: Add, _: None = Depends(auth)):
    platform = platform_of(payload.url)
    if payload.mode not in ('video', 'channel'):
        raise HTTPException(422, 'Chế độ không hợp lệ')
    engine = ('f2' if platform in ('Douyin', 'TikTok') and payload.mode == 'channel' else 'yt-dlp') if payload.engine == 'auto' else payload.engine
    if engine not in ('f2', 'yt-dlp') or (engine == 'f2' and platform not in ('Douyin', 'TikTok')):
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
        return ['f2', alias, '-M', mode, '-u', job['url'], '-p', str(destination)]
    archive = ROOT / 'archive.txt'
    return ['yt-dlp', '--newline', '--no-warnings', '--continue', '--download-archive', str(archive), '--retries', '5', '--fragment-retries', '5', '-o', str(destination / '%(upload_date)s_%(id)s_%(title).100B.%(ext)s'), job['url']]


async def run_job(job):
    jid = job['id']
    update(jid, status='running', attempts=job['attempts'] + 1, message='Đang tải')
    log = []
    try:
        proc = await asyncio.create_subprocess_exec(*command_for(job), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
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
            update(jid, status='done', progress=100, message='Hoàn tất')
        else:
            msg = '\n'.join(log)[-500:] or f'Bộ tải thoát mã {code}'
            update(jid, status='failed', message=msg)
    except Exception as exc:
        if get_job(jid)['status'] == 'running':
            update(jid, status='failed', message=str(exc)[:500])
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
