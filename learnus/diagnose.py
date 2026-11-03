"""Read public login structure only. Never submit credentials or dump HTML/cookies."""
import json
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from .client import Session
from .errors import UserError


def safe_url(url):
    parsed = urlsplit(url)
    # Drop userinfo, query, fragment, path parameters, and long opaque path IDs.
    path = '/'.join('[id]' if len(part) > 48 else part.split(';', 1)[0] for part in parsed.path.split('/'))
    return f'{parsed.scheme}://{parsed.hostname}{path}'


def field_name(name):
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:-]{0,63}', name or '') else '[field]'


def page_structure(response):
    soup = BeautifulSoup(response.text, 'html.parser')
    forms = []
    for form in soup.find_all('form', limit=12):
        forms.append({
            'action': safe_url(urljoin(response.url, form.get('action', ''))),
            'method': form.get('method', 'get').upper(),
            'fields': [field_name(tag.get('name')) for tag in form.select('input[name], select[name], button[name]')][:40],
        })
    candidates = []
    for tag in soup.select('a[href], script[src], form[action]'):
        raw = tag.get('href') or tag.get('src') or tag.get('action') or ''
        if re.search(r'login|sso|passni|auth', raw, re.I):
            candidate = safe_url(urljoin(response.url, raw))
            if candidate not in candidates:
                candidates.append(candidate)
    # Recognize only URLs in inline scripts; never print raw JS or inline values.
    for script in soup.find_all('script'):
        for raw in re.findall(r'''["']((?:https://|/)[^"'\s<>]+)["']''', script.get_text()):
            if re.search(r'login|sso|auth', raw, re.I):
                candidate = safe_url(urljoin(response.url, raw))
                if candidate not in candidates:
                    candidates.append(candidate)
    return {
        'final_page': safe_url(response.url),
        'redirects': [{'status': item.status_code, 'page': safe_url(item.url)} for item in response.history],
        'status': response.status_code,
        'forms': forms,
        'login_references': candidates[:30],
    }


def main():
    print('LearnUS public login diagnostics v2 — no credentials submitted')
    with Session() as session:
        session.stage = '공개 로그인 페이지 구조 확인'
        try:
            response = session.get('https://ys.learnus.org/login/index.php')
            print(json.dumps(page_structure(response), ensure_ascii=False, indent=2))
            print('위 내용은 로그인 성공 여부가 아니라 현재 로그인 페이지 구조입니다.')
        except UserError as exc:
            print(str(exc))

if __name__ == '__main__':
    main()
