"""Resolve a Facebook share link in headless Chromium when HTTP metadata is absent."""

import json
import sys
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse


def resolve(source, cookie_path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.binary_location = '/usr/bin/chromium'
    for arg in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
                '--disable-gpu', '--window-size=1280,960'):
        options.add_argument(arg)
    browser = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)
    browser.set_page_load_timeout(30)
    try:
        if cookie_path:
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
        browser.get(source)
        candidates = [browser.current_url]
        candidates += browser.execute_script('''
          return Array.from(document.querySelectorAll(
            'link[rel="canonical"],meta[property="og:url"],meta[property="al:web:url"]'
          )).map(node => node.content || node.href || '').filter(Boolean);
        ''') or []
        return candidates
    finally:
        browser.quit()


if __name__ == '__main__':
    try:
        source, cookie_path = sys.argv[1:3]
        parsed = urlparse(source)
        if parsed.scheme != 'https' or parsed.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
            raise ValueError('Chỉ nhận link HTTPS Facebook')
        print(json.dumps({'candidates': resolve(source, cookie_path)}))
    except Exception as exc:
        print(str(exc)[:300], file=sys.stderr)
        sys.exit(1)
