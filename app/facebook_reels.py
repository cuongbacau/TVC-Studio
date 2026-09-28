"""Collect public reel permalinks from a Facebook profile's Reels tab.

This runs in a separate process so a stalled browser can be stopped by the API.
Inspired by duongxthanh/facebook-reels-downloader (MIT); uses an existing
Netscape cookie file, never accepts a password through the web interface.
"""

import json
import re
import sys
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse


def reel_links(html):
    # Facebook emits both anchor URLs and JSON-escaped paths in page data.
    html = html.replace('\\/', '/')
    ids = set(re.findall(r'/(?:reel|reels)/(\d{6,})', html))
    return [f'https://www.facebook.com/reel/{value}/' for value in sorted(ids)]


def visible_reels(browser):
    # Prefer the poster shown in the actual Reels grid. Facebook's page JSON
    # contains additional reel links without a matching image.
    return browser.execute_script('''
      return Array.from(document.querySelectorAll('a[href*="/reel/"]')).map(a => {
        let node = a, images = [];
        for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
          images = Array.from(node.querySelectorAll('img')).filter(img =>
            (img.naturalWidth || img.width) >= 100 && (img.naturalHeight || img.height) >= 100);
          if (images.length) break;
        }
        images.sort((left, right) => {
          const score = img => {
            const width = img.naturalWidth || img.width, height = img.naturalHeight || img.height;
            return width * height * (height > width ? 2 : 1);
          };
          return score(right) - score(left);
        });
        const img = images[0];
        const background = !img && node ? getComputedStyle(node).backgroundImage : '';
        const match = background && background.match(/url\\(["']?(https:\\/\\/[^"')]+)["']?\\)/);
        return {href: a.href, thumbnail: img ? (img.currentSrc || img.src) : (match ? match[1] : '')};
      });
    ''')


def collect(url, cookie_path, limit):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.binary_location = '/usr/bin/chromium'
    for arg in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
                '--disable-gpu', '--window-size=1280,960'):
        options.add_argument(arg)
    browser = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)
    browser.set_page_load_timeout(35)
    try:
        browser.get('https://www.facebook.com/')
        jar = MozillaCookieJar(cookie_path)
        jar.load(ignore_discard=True, ignore_expires=False)
        for cookie in jar:
            domain = cookie.domain.lstrip('.').lower()
            if domain != 'facebook.com' and not domain.endswith('.facebook.com'):
                continue
            try:
                browser.add_cookie({'name': cookie.name, 'value': cookie.value,
                                    'domain': cookie.domain, 'path': cookie.path or '/'})
            except Exception:
                continue
        browser.get(url)
        found = {}
        stagnant = 0
        for _ in range(min(240, max(12, limit // 4 + 12))):
            before = (len(found), sum(bool(poster) for poster in found.values()))
            for item in visible_reels(browser):
                match = re.search(r'/(?:reel|reels)/(\d{6,})', item.get('href') or '')
                if match:
                    link = f'https://www.facebook.com/reel/{match.group(1)}/'
                    thumbnail = item.get('thumbnail') or ''
                    if thumbnail.startswith('https://') and (not found.get(link) or len(thumbnail) > len(found[link])):
                        found[link] = thumbnail
                    else:
                        found.setdefault(link, '')
            for link in reel_links(browser.page_source):
                found.setdefault(link, '')
            if sum(bool(poster) for poster in found.values()) >= limit:
                break
            browser.execute_script('window.scrollTo(0, document.body.scrollHeight)')
            import time
            time.sleep(1.5)
            stagnant = stagnant + 1 if (len(found), sum(bool(poster) for poster in found.values())) == before else 0
            if stagnant >= 5:
                break
        links = sorted(found, key=lambda link: not bool(found[link]))[:limit]
        return [{'url': link, 'thumbnail': found[link]} for link in links]
    finally:
        browser.quit()


if __name__ == '__main__':
    try:
        source, cookie_path, count = sys.argv[1:4]
        if urlparse(source).hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
            raise ValueError('Chỉ nhận link Facebook')
        print(json.dumps({'items': collect(source, cookie_path, min(2000, int(count)))}))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
