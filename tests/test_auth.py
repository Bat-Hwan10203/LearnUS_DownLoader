import json
import unittest
from unittest.mock import Mock
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from learnus.auth import login_sso, prepare_login, request, BASE, INFRA
from learnus.errors import UserError


def response(url, text='', status=200, location=None):
    return type('Response', (), {'url': url, 'text': text, 'status_code': status,
                                'is_redirect': location is not None,
                                'headers': {'Location': location} if location else {}})()


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = RSA.generate(1024)

    def setup_session(self, captcha='N'):
        session = Mock()
        session.headers = {}
        html = f'''<form name="ssoLoginForm" action="/sso/PmSSOAuthService" method="post">
        <input name="loginId"><input name="loginPasswd" type="password">
        <input name="captcha_yn" type="hidden" value="{captcha}">
        <input name="loginType" type="hidden" value="invokeID">
        <input name="app_id" type="hidden" value="ednetYonsei"></form>
        <script>var ssoChallenge="challenge"; rsa.setPublic('{self.key.n:x}', '10001');</script>'''
        session.request.side_effect = [
            response(BASE+'/login.php'),
            response(BASE+'/passni/sso/spLogin2.php', '<form action="https://infra.yonsei.ac.kr/sso/PmSSOService" method="post"><input type="hidden" name="S1" value="token"></form>'),
            response(INFRA+'/sso/PmSSOService', html),
            response(INFRA+'/sso/PmSSOAuthService', '<form action="https://ys.learnus.org/passni/sso/callback.php" method="post"><input type="hidden" name="S2" value="result"></form><script>document.f.submit();</script>'),
            response(BASE+'/passni/sso/callback.php', '<script>document.location.href="/my/";</script>'),
            response(BASE+'/my/', '<a href="/login/logout.php">Logout</a>'),
        ]
        return session

    def test_current_flow_encrypts_credentials_and_follows_callback(self):
        session = self.setup_session()
        password = 'quote"slash\\한글'
        self.assertIs(login_sso('student', password, session), session)
        calls = session.request.call_args_list
        payload = calls[3].kwargs['data']
        decrypted = PKCS1_v1_5.new(self.key).decrypt(bytes.fromhex(payload['E2']), b'bad')
        self.assertEqual(json.loads(decrypted), dict(userid='student', userpw=password, ssoChallenge='challenge'))
        self.assertEqual(payload['loginId'], '')
        self.assertEqual(payload['loginPasswd'], '')
        self.assertIn('Referer', calls[1].kwargs['headers'])
        self.assertEqual(calls[4].args[1], BASE+'/passni/sso/callback.php')
        self.assertEqual(calls[5].args[1], BASE+'/my/')
        for call in calls:
            self.assertNotIn(password, str(call))
            self.assertNotIn('coursemosLogin.php', str(call))

    def test_captcha_stops_before_credentials(self):
        session = self.setup_session('Y')
        with self.assertRaisesRegex(UserError, 'CAPTCHA'):
            login_sso('student', 'password', session)
        self.assertEqual(session.request.call_count, 3)

    def test_untrusted_callback_is_not_contacted(self):
        session = self.setup_session()
        replies = list(session.request.side_effect)
        replies[3] = response(INFRA+'/sso/PmSSOAuthService', '<form method="post" action="https://evil.example/steal"><input type="hidden" name="S2" value="result"></form><script>document.f.submit();</script>')
        session.request.side_effect = replies
        with self.assertRaisesRegex(UserError, '예상하지 않은 인증 서버'):
            login_sso('student', 'password', session)
        self.assertEqual(session.request.call_count, 4)

    def test_redirect_is_validated_before_following(self):
        session = Mock()
        session.request.return_value = response(BASE, status=302, location='https://evil.example/')
        with self.assertRaises(UserError):
            request(session, 'GET', BASE)
        self.assertEqual(session.request.call_count, 1)

    def test_rejected_credentials_are_not_retried(self):
        session = self.setup_session()
        replies = list(session.request.side_effect)
        replies[3] = response(INFRA+'/sso/PmSSOAuthService', '<input type="password" name="loginPasswd">')
        session.request.side_effect = replies
        with self.assertRaisesRegex(UserError, '로그인을 완료하지 못했습니다'):
            login_sso('student', 'wrong', session)
        self.assertEqual(session.request.call_count, 4)

    def test_authenticated_template_with_password_ui_is_relayed(self):
        session = self.setup_session()
        replies = list(session.request.side_effect)
        replies[3] = response(INFRA+'/sso/PmSSOAuthService', '''
        <form name="ssoLoginForm" action="https://ys.learnus.org/passni/sso/callback.php" method="post">
        <input type="password" name="loginPasswd"><input name="loginId">
        <input type="hidden" name="E3" value="auth-result"></form>
        <script>var login_url='https://ys.learnus.org/passni/sso/callback.php';
        if (login_url != '') { document.ssoLoginForm.submit(); }</script>''')
        session.request.side_effect = replies
        login_sso('student', 'password', session)
        relay = session.request.call_args_list[4].kwargs['data']
        self.assertEqual(relay['E3'], 'auth-result')
        self.assertEqual(relay['loginPasswd'], '')
        self.assertEqual(session.request.call_args_list[3].kwargs['headers']['Origin'], INFRA)

    def test_rejection_code_and_reason_are_redacted(self):
        from learnus.auth import rejection
        error = rejection("var retCode='[PM_UAN]038'; var returnMessage='비밀번호 변경 필요 SECRET';")
        self.assertIn('[PM_UAN]038', str(error))
        self.assertIn('변경/만료', str(error))
        self.assertNotIn('SECRET', str(error))

    def test_login_url_without_auth_result_is_not_treated_as_success(self):
        session = self.setup_session()
        replies = list(session.request.side_effect)
        replies[3] = response(INFRA+'/sso/PmSSOAuthService', '''
        <form name="ssoLoginForm" action="https://ys.learnus.org/passni/sso/callback.php" method="post">
        <input type="password" name="loginPasswd"></form>
        <script>var login_url='https://ys.learnus.org/passni/sso/callback.php'; document.ssoLoginForm.submit();</script>''')
        session.request.side_effect = replies
        with self.assertRaises(UserError):
            login_sso('student', 'password', session)
        self.assertEqual(session.request.call_count, 4)

    def test_escaped_server_message_can_be_understood_without_credentials(self):
        from learnus.auth import rejection, script_value
        scripts = r"var retCode='[PM_UAN]011'; var returnMessage='\uc778\uc99d \uc815\ubcf4 \ud655\uc778';"
        self.assertEqual(script_value(scripts, 'returnMessage'), '인증 정보 확인')
        error = rejection(scripts, rendered_message='학번 student 비밀번호 secret <b>확인</b>', sensitive=('student', 'secret'))
        self.assertIn('서버 안내', str(error))
        self.assertNotIn('student', str(error))
        self.assertNotIn('secret', str(error))
        self.assertIn('[PM_UAN]011', str(error))
