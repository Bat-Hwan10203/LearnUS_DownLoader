"""SSO protocol adapted from henryjmin/learnus-dl (MIT, Henry Min 2023).
See THIRD_PARTY_LICENSE.txt. Current LearnUS compatibility requires local validation.
"""
import json
import requests
from bs4 import BeautifulSoup
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

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
    res = s.post(LEARNUS_URL + '/passni/sso/coursemosLogin.php', data=data1)
    soup = BeautifulSoup(res.text, features='html.parser')
    s1 = soup.find('input', {'name': 'S1'})['value']

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
    res = s.post(YONSEI_URL + '/sso/PmSSOService', data=data2)
    soup = BeautifulSoup(res.text, features='html.parser')
    sc = soup.find('input', {'name': 'ssoChallenge'})['value']
    km = soup.find('input', {'name': 'keyModulus'})['value']

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
    res = s.post(LEARNUS_URL + '/passni/sso/coursemosLogin.php', data=data3)
    soup = BeautifulSoup(res.text, features='html.parser')
    s1 = soup.find('input', {'name': 'S1'})['value']
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
    res = s.post(YONSEI_URL + '/sso/PmSSOAuthService', data=data4)
    soup = BeautifulSoup(res.text, features='html.parser')
    e3 = soup.find('input', {'name': 'E3'})['value']
    e4 = soup.find('input', {'name': 'E4'})['value']
    s2 = soup.find('input', {'name': 'S2'})['value']
    cltid = soup.find('input', {'name': 'CLTID'})['value']

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
    s.post(LEARNUS_URL + '/passni/sso/spLoginData.php', data=data5)

    s.get(LEARNUS_URL + '/passni/spLoginProcess.php')
    return s
