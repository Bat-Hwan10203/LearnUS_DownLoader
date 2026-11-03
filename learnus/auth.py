"""Direct login using the public Yonsei SSO form and its RSA protocol.

The earlier adapter was based on Henry Min's MIT-licensed learnus-dl;
see THIRD_PARTY_LICENSE.txt. Credentials and SSO tokens are never logged.
"""
import json
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
        if soup.select('input[type="password"]'):
            raise UserError('SSO에서 로그인을 완료하지 못했습니다. 학번·비밀번호 또는 추가 인증 여부를 확인하세요.')
        scripts = '\n'.join(tag.get_text() for tag in soup.find_all('script', src=False))
        form = soup.find('form')
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
