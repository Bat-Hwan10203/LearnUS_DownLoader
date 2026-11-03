"""Use the official SSO JavaScript in a temporary, headless browser context."""
import os
import shutil
import sys
import time
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Error as BrowserError, TimeoutError as BrowserTimeout
from requests.cookies import create_cookie
from .auth import BASE, rejection, script_value
from .errors import UserError


def launch_browser(playwright, show_login=False):
    options = {'headless': not show_login}
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if proxy:
        parsed = urlsplit(proxy)
        if parsed.hostname:
            options['proxy'] = {'server': f'{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}'}
            if parsed.username:
                options['proxy']['username'] = parsed.username
                options['proxy']['password'] = parsed.password or ''
    if sys.platform == 'win32':
        # Only fall back between engines before any account is submitted.
        for channel in ('chrome', 'msedge'):
            try:
                return playwright.chromium.launch(channel=channel, **options)
            except BrowserError:
                continue
        raise UserError('Chrome 또는 Microsoft Edge 실행 엔진을 찾지 못했습니다. 설치 후 다시 실행하세요. 브라우저 창은 표시하지 않습니다.')
    executable = shutil.which('chromium') or shutil.which('google-chrome')
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options)


def open_login(context):
    main = context.new_page()
    main.goto(BASE + '/login.php', wait_until='domcontentloaded')
    # Use the site's real link so navigation matches a normal private Chrome tab.
    before = list(context.pages)
    main.locator('a[href*="/passni/sso/spLogin2.php"]').first.click()
    pages = [page for page in context.pages if page not in before]
    popup = pages[-1] if pages else main
    popup.wait_for_selector('#loginPasswd', state='visible')
    if urlsplit(popup.url).hostname != 'infra.yonsei.ac.kr' or urlsplit(popup.url).scheme != 'https':
        raise UserError('예상하지 않은 로그인 화면입니다. 계정 정보를 입력하지 않았습니다.')
    popup.on('dialog', lambda dialog: dialog.dismiss())
    return main, popup


def transfer_cookies(cookies, session):
    for item in cookies:
        domain = item['domain']
        if domain.lstrip('.') not in ('ys.learnus.org', 'infra.yonsei.ac.kr'):
            continue
        expires = item.get('expires', -1)
        session.cookies.set_cookie(create_cookie(
            item['name'], item['value'], domain=domain, path=item.get('path', '/'),
            secure=item.get('secure', False), expires=int(expires) if expires > 0 else None,
            rest={'HttpOnly': item.get('httpOnly', False)},
        ))


def login_browser(username, password, session, cancel=None, show_login=False):
    session.stage = '1/4 공식 로그인 엔진 시작'
    browser = None
    try:
        with sync_playwright() as playwright:
            try:
                browser = launch_browser(playwright, show_login=show_login)
                context = browser.new_context()  # Isolated from the user's Chrome profile.
                context.set_default_timeout(30000)
                session.stage = '2/4 공식 SSO 화면 연결'
                _, popup = open_login(context)
                if cancel is not None and cancel.is_set():
                    raise UserError('작업을 취소했습니다.')
                session.stage = '3/4 공식 화면에서 계정 인증'
                popup.locator('#loginId').fill(username)
                popup.locator('#loginPasswd').fill(password)
                try:
                    with popup.expect_navigation(wait_until='domcontentloaded', timeout=30000):
                        popup.locator('#loginBtn').click()
                except BrowserError:
                    if not popup.is_closed():
                        raise
                # Exactly one credential submission; GET checks below never retry it.
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if cancel is not None and cancel.is_set():
                        raise UserError('작업을 취소했습니다.')
                    if not popup.is_closed():
                        content = BeautifulSoup(popup.content(), 'html.parser')
                        scripts = '\n'.join(t.get_text() for t in content.find_all('script', src=False))
                        code = script_value(scripts, 'retCode') or script_value(scripts, 'returnCode')
                        if content.select('input[type="password"]') and code and code not in ('0', '0000'):
                            info = content.select_one('#info')
                            rendered = info.get_text(' ', strip=True) if info else ''
                            raise rejection(scripts, rendered_message=rendered, sensitive=(username, password))
                        if content.select('input[name="captcha_yn"][value="Y"]'):
                            raise UserError('SSO에서 CAPTCHA 인증을 요청했습니다. 자동 재시도하지 않았습니다.')
                    session.stage = '4/4 LearnUS 로그인 결과 확인'
                    result = context.request.get(BASE + '/my/', timeout=15000)
                    soup = BeautifulSoup(result.text(), 'html.parser')
                    if result.ok and urlsplit(result.url).hostname == 'ys.learnus.org' and soup.select('a[href*="logout.php"]'):
                        session.headers['User-Agent'] = context.pages[0].evaluate('navigator.userAgent')
                        transfer_cookies(context.cookies(), session)
                        return session
                    time.sleep(0.5)
                raise UserError('공식 SSO 로그인 완료를 확인하지 못했습니다. 추가 인증 또는 자동화 제한일 수 있습니다. 재시도는 하지 않았습니다.')
            finally:
                if browser is not None:
                    browser.close()
    except UserError:
        raise
    except BrowserTimeout:
        raise UserError(f'{session.stage}: 화면 또는 서버 응답 시간이 초과됐습니다. 로그인 창 없이 Chrome 엔진을 사용한 요청입니다.') from None
    except BrowserError:
        # Playwright errors can include locator.fill arguments. Never display them.
        raise UserError(f'{session.stage}: 공식 로그인 엔진 처리에 실패했습니다. Chrome 업데이트와 네트워크 상태를 확인하세요.') from None
