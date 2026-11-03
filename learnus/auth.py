"""SSO protocol adapted from henryjmin/learnus-dl (MIT, Henry Min 2023).
See THIRD_PARTY_LICENSE.txt. Current LearnUS compatibility requires local validation.
"""
import json
import requests
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from .errors import UserError

def fields(response, stage, *names):
    soup = BeautifulSoup(response.text, 'html.parser')
    result = []
    for name in names:
        item = soup.find('input', {'name': name})
        if item is None or not item.get('value'):
            raise UserError(f'{stage}: 예상한 SSO 응답이 없습니다. 로그인 거부·추가 인증·사이트 변경 가능성이 있습니다.')
        result.append(item['value'])
    return result


def legacy_login(id: str, pw: str, s: requests.Session) -> requests.Session:
    LEARNUS_URL = 'https://ys.learnus.org'
    YONSEI_URL = 'https://infra.yonsei.ac.kr'
    data1 = {
        'ssoGubun': 'Login',
        'logintype': 'sso',
        'type': 'popup_login',
        'username': id,
        'password': pw
    }
    s.stage = '1/6 LearnUS 로그인 시작'
    res = s.post(LEARNUS_URL + '/passni/sso/coursemosLogin.php', data=data1)
    s1, = fields(res, s.stage, 'S1')

    data2 = {
        'app_id': 'ednetYonsei',
        'retUrl': LEARNUS_URL,
        'failUrl': LEARNUS_URL + '/login/index.php',
        'baseUrl': LEARNUS_URL,
        'S1':  s1,
        'loginUrl': LEARNUS_URL + '/passni/sso/coursemosLogin.php',
        'ssoGubun': 'Login',
        'refererUrl': LEARNUS_URL,
        'test': 'SSOAuthLogin',
        'loginType': 'invokeID',
        'E2': '',
        'username': id,
        'password': pw
    }
    s.stage = '2/6 연세대 SSO 연결'
    res = s.post(YONSEI_URL + '/sso/PmSSOService', data=data2)
    sc, km = fields(res, s.stage, 'ssoChallenge', 'keyModulus')

    data3 = {
        'app_id': 'ednetYonsei',
        'retUrl': LEARNUS_URL,
        'failUrl': LEARNUS_URL + '/login/index.php',
        'baseUrl': LEARNUS_URL,
        'loginUrl': LEARNUS_URL + '/passni/sso/coursemosLogin.php',
        'ssoChallenge': sc,
        'loginType': 'invokeID',
        'returnCode': '',
        'returnMessage': '',
        'keyModulus': km,
        'keyExponent': '10001',
        'ssoGubun': 'Login',
        'refererUrl': LEARNUS_URL,
        'test': 'SSOAuthLogin',
        'username': id,
        'password': pw
    }
    s.stage = '3/6 SSO 인증 준비'
    res = s.post(LEARNUS_URL + '/passni/sso/coursemosLogin.php', data=data3)
    s1, = fields(res, s.stage, 'S1')
    json_str = json.dumps(dict(userid=id, userpw=pw, ssoChallenge=sc), ensure_ascii=False)
    key_pair = RSA.construct((int(km, 16), 0x10001))
    cipher = PKCS1_v1_5.new(key_pair)
    e2 = cipher.encrypt(json_str.encode()).hex()

    data4 = {
        'app_id': 'ednetYonsei',
        'retUrl': LEARNUS_URL,
        'failUrl': LEARNUS_URL + '/login/index.php',
        'baseUrl': LEARNUS_URL,
        'S1':  s1,
        'loginUrl': LEARNUS_URL + '/passni/sso/coursemosLogin.php',
        'ssoGubun': 'Login',
        'refererUrl': LEARNUS_URL,
        'test': 'SSOAuthLogin',
        'loginType': 'invokeID',
        'E2': e2,
        'username': id,
        'password': pw
    }
    s.stage = '4/6 연세대 계정 인증'
    res = s.post(YONSEI_URL + '/sso/PmSSOAuthService', data=data4)
    e3, e4, s2, cltid = fields(res, s.stage, 'E3', 'E4', 'S2', 'CLTID')

    data5 = {
        'app_id': 'ednetYonsei',
        'retUrl': LEARNUS_URL,
        'failUrl': LEARNUS_URL + '/login/index.php',
        'baseUrl': LEARNUS_URL,
        'loginUrl': LEARNUS_URL + '/passni/sso/coursemosLogin.php',
        'E3': e3,
        'E4': e4,
        'S2': s2,
        'CLTID': cltid,
        'ssoGubun': 'Login',
        'refererUrl': LEARNUS_URL,
        'test': 'SSOAuthLogin',
        'username': id,
        'password': pw
    }
    s.stage = '5/6 LearnUS 세션 생성'
    s.post(LEARNUS_URL + '/passni/sso/spLoginData.php', data=data5)

    s.stage = '6/6 로그인 마무리'
    s.get(LEARNUS_URL + '/passni/spLoginProcess.php')
    return s
