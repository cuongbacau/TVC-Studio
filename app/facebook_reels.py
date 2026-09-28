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
        found = set()
        stagnant = 0
        for _ in range(min(240, max(12, limit // 4 + 12))):
            before = len(found)
            found.update(reel_links(browser.page_source))
            if len(found) >= limit:
                break
            browser.execute_script('window.scrollTo(0, document.body.scrollHeight)')
            import time
            time.sleep(1.5)
            stagnant = stagnant + 1 if len(found) == before else 0
            if stagnant >= 5:
                break
        return sorted(found)[:limit]
    finally:
        browser.quit()


if __name__ == '__main__':
    try:
        source, cookie_path, count = sys.argv[1:4]
        if urlparse(source).hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
            raise ValueError('Chỉ nhận link Facebook')
        print(json.dumps({'urls': collect(source, cookie_path, min(2000, int(count)))}))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
