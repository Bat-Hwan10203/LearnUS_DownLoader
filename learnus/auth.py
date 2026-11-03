"""Direct login using the public Yonsei SSO form and its RSA protocol.

The earlier adapter was based on Henry Min's MIT-licensed learnus-dl;
see THIRD_PARTY_LICENSE.txt. Credentials and SSO tokens are never logged.
"""
import json
import html
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from .errors import UserError

BASE = 'https://ys.learnus.org'
INFRA = 'https://infra.yonsei.ac.kr'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0')


def fields(response, stage, *names):
    soup = BeautifulSoup(response.text, 'html.parser')
    result = []
    for name in names:
        item = soup.find('input', {'name': name})
        if item is None or not item.get('value'):
            raise UserError(f'{stage}: 예상한 SSO 응답이 없습니다. 로그인 거부·추가 인증·사이트 변경 가능성이 있습니다.')
        result.append(item['value'])
    return result


def trusted_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in {'ys.learnus.org', 'infra.yonsei.ac.kr'}
            or p.username or p.password or p.port not in (None, 443)):
        raise UserError('예상하지 않은 인증 서버 주소입니다. 계정 정보를 전송하지 않았습니다.')
    return url


def request(session, method, url, *, referer=None, data=None):
    """Validate every redirect before following it, including 307/308 POSTs."""
    headers = {'Referer': referer} if referer else {}
    if method == 'POST' and referer:
        origin = urlsplit(referer)
        headers['Origin'] = f'{origin.scheme}://{origin.netloc}'
    for _ in range(8):
        trusted_url(url)
        response = session.request(method, url, data=data, headers=headers, allow_redirects=False)
        if not response.is_redirect:
            return response
        target = trusted_url(urljoin(response.url, response.headers.get('Location', '')))
        if response.status_code in (307, 308) and method == 'POST' and urlsplit(target).hostname != urlsplit(url).hostname:
            raise UserError('인증 요청이 다른 서버로 재전송되어 중단했습니다.')
        if response.status_code == 303 or (response.status_code in (301, 302) and method == 'POST'):
            method, data = 'GET', None
        headers = {'Referer': response.url}
        if method == 'POST':
            origin = urlsplit(response.url)
            headers['Origin'] = f'{origin.scheme}://{origin.netloc}'
        url = target
    raise UserError('SSO 리다이렉트가 너무 많습니다.')


def form_data(form):
    return {item['name']: item.get('value', '') for item in form.select('input[name]')
            if not item.has_attr('disabled') and item.get('type', 'text').lower() not in ('submit', 'button', 'checkbox', 'radio')}


def prepare_login(session):
    """Fetch public forms and RSA parameters. Does not submit an account/password."""
    session.headers['User-Agent'] = USER_AGENT
    session.stage = '1/5 LearnUS 로그인 화면 연결'
    page = request(session, 'GET', BASE + '/login.php')
    entry = request(session, 'GET', BASE + '/passni/sso/spLogin2.php', referer=page.url)
    soup = BeautifulSoup(entry.text, 'html.parser')
    form = soup.find('form')
    if form is None:
        raise UserError('1/5: SSO 진입 폼을 찾지 못했습니다. 사이트 구성이 변경되었을 수 있습니다.')
    action = trusted_url(urljoin(entry.url, form.get('action', '')))
    if action != INFRA + '/sso/PmSSOService':
        raise UserError('1/5: 예상한 SSO 진입 경로가 아닙니다.')
    session.stage = '2/5 연세대 SSO 인증 준비'
    response = request(session, 'POST', action, referer=entry.url, data=form_data(form))
    soup = BeautifulSoup(response.text, 'html.parser')
    form = soup.find('form', attrs={'name': 'ssoLoginForm'})
    if form is None:
        form = soup.find('form', action=re.compile(r'PmSSOAuthService'))
    if form is None or not form.select('input[name="loginPasswd"]'):
        raise UserError('2/5: 학번·비밀번호 로그인 폼을 찾지 못했습니다. 추가 인증이 필요할 수 있습니다.')
    action = trusted_url(urljoin(response.url, form.get('action', '')))
    if action != INFRA + '/sso/PmSSOAuthService':
        raise UserError('2/5: 예상한 계정 인증 경로가 아닙니다.')
    data = form_data(form)
    if data.get('captcha_yn', '').upper() == 'Y':
        raise UserError('CAPTCHA 인증이 필요합니다. 일반 로그인 화면에서 확인한 뒤 다시 시도하세요.')
    # Match data literals only; never evaluate JavaScript or retain the page on disk.
    scripts = '\n'.join(tag.get_text() for tag in soup.find_all('script', src=False))
    challenge = re.search(r'''\b(?:var\s+)?ssoChallenge\s*=\s*["']([^"']+)["']''', scripts)
    public_key = re.search(r'''\.setPublic\(\s*["']([0-9a-fA-F]+)["']\s*,\s*["']([0-9a-fA-F]+)["']\s*\)''', scripts)
    if not challenge or not public_key:
        raise UserError('2/5: SSO RSA 인증 정보를 찾지 못했습니다. 사이트 구성이 변경되었을 수 있습니다.')
    return response, action, data, challenge[1], RSA.construct((int(public_key[1], 16), int(public_key[2], 16)))


def script_value(scripts, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*([\"'])((?:\\.|(?!\1).)*)\1", scripts)
    if not match:
        return ''
    value = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), match[2])
    value = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)), value)
    return value.replace(r"\'", "'").replace(r'\"', '"').replace(r'\n', '\n').replace(r'\r', '\r')


def safe_server_message(message, sensitive):
    from urllib.parse import quote, quote_plus
    message = BeautifulSoup(html.unescape(message), 'html.parser').get_text(' ', strip=True)
    for value in sensitive:
        if value:
            for variant in (value, quote(value, safe=''), quote_plus(value)):
                message = message.replace(variant, '[숨김]')
    # Never show credential dumps or long opaque tokens, even in server errors.
    if re.search(r'password\s*[:=]|userpw\s*[:=]|cookie\s*[:=]|authorization\s*[:=]', message, re.I):
        return '서버 메시지에 민감정보 형식이 포함되어 표시하지 않았습니다.'
    message = re.sub(r'https?://\S+', '[주소 숨김]', message)
    message = re.sub(r'[A-Za-z0-9+/=_-]{24,}', '[토큰 숨김]', message)
    message = re.sub(r'[^\s@]+@[^\s@]+\.[^\s@]+', '[이메일 숨김]', message)
    return ' '.join(message.split())[:350]


def rejection(scripts, *, rendered_message=None, sensitive=()):
    # Detailed text is enabled only with credential-redaction context.
    message = script_value(scripts, 'returnMessage')
    code = script_value(scripts, 'retCode') or script_value(scripts, 'returnCode')
    if not re.fullmatch(r'(?:\[[A-Z_]{1,20}\])?[A-Z0-9_-]{1,16}', code):
        code = '없음'
    if re.search(r'잠[금김]|locked', message, re.I):
        reason = '계정 잠금 안내'
    elif re.search(r'캡차|captcha|추가.*인증|인증.*추가', message, re.I):
        reason = '추가 인증 안내'
    elif re.search(r'비밀번호.*(?:변경|만료)|password.*(?:expir|change)', message, re.I):
        reason = '비밀번호 변경/만료 안내'
    elif re.search(r'일치|올바르지|invalid|incorrect', message, re.I):
        reason = '계정 정보 불일치 안내'
    else:
        reason = '서버의 상세 사유를 자동 분류하지 못함'
    detail = safe_server_message(rendered_message or message, sensitive) if sensitive else ''
    reason = reason + ('\n서버 안내: ' + detail if detail else '')
    return UserError(f'SSO에서 로그인을 완료하지 못했습니다.\n{reason} (서버 코드: {code}).\n자동 재시도는 하지 않았습니다. 일반 LearnUS 로그인에서 계정 상태를 확인하세요.')


def login_sso(username, password, session):
    page, action, data, challenge, public_key = prepare_login(session)
    payload = json.dumps({'userid': username, 'userpw': password, 'ssoChallenge': challenge},
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    try:
        data['E2'] = PKCS1_v1_5.new(public_key).encrypt(payload).hex()
    except ValueError:
        raise UserError('SSO 암호화 입력 길이가 서버에서 지원하는 범위를 넘었습니다.') from None
    # The official JavaScript clears both plaintext fields before form submission.
    data['loginId'] = ''
    data['loginPasswd'] = ''
    data['loginType'] = 'invokeID'
    session.stage = '3/5 연세대 계정 인증'
    response = request(session, 'POST', action, referer=page.url, data=data)
    session.stage = '4/5 LearnUS 세션 생성'
    for _ in range(6):
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = '\n'.join(tag.get_text() for tag in soup.find_all('script', src=False))
        form = soup.find('form', attrs={'name': 'ssoLoginForm'})
        if form is None:
            form = soup.find('form')
        # The SSO template can keep its password UI after authentication.
        # Relay only with explicit callback URL AND returned authentication fields.
        login_url = script_value(scripts, 'login_url')
        if form is not None and login_url and soup.select('input[type="password"]'):
            callback = trusted_url(urljoin(response.url, login_url))
            action = trusted_url(urljoin(response.url, form.get('action', '')))
            relay = form_data(form)
            if (urlsplit(callback).hostname == 'ys.learnus.org' and callback == action
                    and any(relay.get(name) for name in ('E3', 'E4', 'S2'))
                    and re.search(r'\.submit\s*\(', scripts)):
                relay['loginId'] = ''
                relay['loginPasswd'] = ''
                response = request(session, 'POST', action, referer=response.url, data=relay)
                continue
        if soup.select('input[type="password"]'):
            raise rejection(scripts)
        if form is not None and re.search(r'\.submit\s*\(', scripts):
            if any(item.get('type', 'text').lower() not in ('hidden', 'submit', 'button') for item in form.select('input')):
                raise UserError('SSO에 추가 입력이 필요합니다. 자동 로그인을 중단했습니다.')
            action = trusted_url(urljoin(response.url, form.get('action', '')))
            method = form.get('method', 'get').upper()
            if method != 'POST':
                raise UserError('예상하지 않은 SSO 콜백 방식입니다.')
            response = request(session, 'POST', action, referer=response.url, data=form_data(form))
            continue
        redirect = re.search(r'''(?:document\.|window\.)?location(?:\.href)?\s*=\s*["']([^"']+)["']\s*;''', scripts)
        if redirect:
            response = request(session, 'GET', trusted_url(urljoin(response.url, redirect[1])), referer=response.url)
            continue
        break
    else:
        raise UserError('SSO 세션 생성 단계를 완료하지 못했습니다.')
    session.stage = '5/5 로그인 결과 확인'
    return session
