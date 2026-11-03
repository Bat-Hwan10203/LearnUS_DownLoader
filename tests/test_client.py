import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from Crypto.Cipher import AES
from learnus.client import Client, UserError, Video, safe_name, validate_link

KEY = b'0123456789abcdef'
DATA = b'example transport stream payload'
PAD = 16 - len(DATA) % 16
CIPHER = AES.new(KEY, AES.MODE_CBC, (7).to_bytes(16, 'big')).encrypt(DATA + bytes([PAD]) * PAD)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get('Referer') != 'https://ys.learnus.org/mod/vod/viewer.php?id=1':
            self.send_error(403)
            return
        bodies = {
            '/video.mp4': (b'mp4 fixture', 'video/mp4'),
            '/movie.m3u8': (b'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXT-X-MEDIA-SEQUENCE:7\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXTINF:5,\nsegment.ts\n#EXT-X-ENDLIST\n', 'application/vnd.apple.mpegurl'),
            '/key': (KEY, 'application/octet-stream'),
            '/segment.ts': (CIPHER, 'video/mp2t'),
            '/broken.m3u8': (b'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:5,\nmissing.ts\n#EXT-X-ENDLIST\n', 'application/vnd.apple.mpegurl'),
            '/login.mp4': (b'<html>Login</html>', 'text/html'),
        }
        if self.path not in bodies:
            self.send_error(404)
            return
        data, kind = bodies[self.path]
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.client = Client()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.client.session.close()
        self.tmp.cleanup()

    def video(self, path):
        return Video('강의: 1', f'http://127.0.0.1:{self.server.server_port}/{path}', 'https://ys.learnus.org/mod/vod/viewer.php?id=1')

    def test_mp4_and_collision(self):
        a = self.client.download(self.video('video.mp4'), self.tmp.name)
        b = self.client.download(self.video('video.mp4'), self.tmp.name)
        self.assertEqual(a.read_bytes(), b'mp4 fixture')
        self.assertNotEqual(a, b)

    def test_encrypted_hls_sequence_and_relative_urls(self):
        output = self.client.download(self.video('movie.m3u8'), self.tmp.name)
        self.assertEqual(output.suffix, '.ts')
        self.assertEqual(output.read_bytes(), DATA)

    def test_failure_removes_partial(self):
        with self.assertRaises(Exception):
            self.client.download(self.video('broken.m3u8'), self.tmp.name)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_cancel(self):
        self.client.cancel.set()
        with self.assertRaises(UserError):
            self.client.download(self.video('video.mp4'), self.tmp.name)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_html_is_not_saved_as_video(self):
        with self.assertRaises(UserError):
            self.client.download(self.video('login.mp4'), self.tmp.name)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

class ParsingTests(unittest.TestCase):
    def test_link_restrictions_and_windows_names(self):
        for url in ['https://evil.test/course/view.php?id=1', 'http://ys.learnus.org/course/view.php?id=1', 'https://ys.learnus.org@evil.test/mod/vod/viewer.php?id=1']:
            with self.assertRaises(UserError):
                validate_link(url)
        self.assertEqual(safe_name('CON'), '_CON')
        self.assertEqual(safe_name('../a:*'), '_a__')

    def test_collection_and_deduplication(self):
        from bs4 import BeautifulSoup
        client = Client()
        client.logged_in = True
        course = BeautifulSoup('<a href="/mod/vod/view.php?id=1">a</a><a href="/mod/vod/view.php?id=1">b</a>', 'html.parser')
        video = BeautifulSoup('<h1>강의</h1><source src="https://cdn.example/video.mp4">', 'html.parser')
        with patch.object(client, 'page', side_effect=[(type('R', (), {'url':'https://ys.learnus.org/course/view.php?id=1'})(), course), (None, video)]) as get:
            result = client.collect('https://ys.learnus.org/course/view.php?id=1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, '강의')
        self.assertIn('viewer.php', get.call_args.args[0])

    def test_login_requires_positive_confirmation(self):
        client = Client()
        fake = type('R', (), {'text':'<html>not logged in</html>', 'url':'https://ys.learnus.org/my/'})()
        with patch('learnus.client.legacy_login'), patch('learnus.client.Session.get', return_value=fake):
            with self.assertRaises(UserError):
                client.login('dummy', 'dummy')
        self.assertFalse(client.logged_in)


class SSOTests(unittest.TestCase):
    def test_protocol_and_password_json_escaping(self):
        import json
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5
        from learnus.auth import legacy_login
        from unittest.mock import Mock
        key = RSA.generate(1024)
        def response(**fields):
            from html import escape
            return type('R', (), {'text': ''.join(f'<input name="{k}" value="{escape(v, quote=True)}">' for k, v in fields.items())})()
        session = Mock()
        session.post.side_effect = [response(S1='initial'), response(ssoChallenge='challenge', keyModulus=format(key.n, 'x')), response(S1='next'), response(E3='e3', E4='e4', S2='s2', CLTID='client'), response()]
        password = 'quote"slash\\한글'
        self.assertIs(legacy_login('student', password, session), session)
        encrypted = session.post.call_args_list[3].kwargs['data']['E2']
        decrypted = PKCS1_v1_5.new(key).decrypt(bytes.fromhex(encrypted), b'bad')
        self.assertEqual(json.loads(decrypted)['userpw'], password)
        self.assertEqual(session.post.call_count, 5)
        self.assertTrue(all(call.args[0].startswith('https://') for call in session.post.call_args_list))


class ErrorTests(unittest.TestCase):
    def test_network_errors_are_specific_and_redacted(self):
        import requests
        from learnus.client import Session
        cases = [
            (requests.exceptions.SSLError, 'TLS'),
            (requests.exceptions.ProxyError, '프록시'),
            (requests.exceptions.Timeout, '시간 초과'),
            (requests.exceptions.ConnectionError, '연결 실패'),
        ]
        for error, expected in cases:
            with self.subTest(error=error.__name__):
                with Session() as session:
                    session.stage = '2/6 연세대 SSO 연결'
                    with patch('requests.Session.request', side_effect=error('password=SECRET cookie=SECRET')):
                        with self.assertRaises(UserError) as ctx:
                            session.get('https://infra.yonsei.ac.kr/sso/?token=SECRET')
                message = str(ctx.exception)
                self.assertIn(expected, message)
                self.assertIn('2/6', message)
                self.assertIn('infra.yonsei.ac.kr', message)
                self.assertNotIn('SECRET', message)

    def test_http_error_reports_status_only(self):
        import requests
        from learnus.client import Session
        response = requests.Response()
        response.status_code = 404
        with Session() as session, patch('requests.Session.request', return_value=response):
            with self.assertRaisesRegex(UserError, 'HTTP 404'):
                session.get('https://ys.learnus.org/passni/sso/coursemosLogin.php')

    def test_missing_sso_fields_do_not_leak_server_response(self):
        from learnus.auth import fields
        response = type('R', (), {'text':'<html>password=SECRET</html>'})()
        with self.assertRaises(UserError) as ctx:
            fields(response, '4/6 계정 인증', 'E3')
        self.assertIn('4/6', str(ctx.exception))
        self.assertNotIn('SECRET', str(ctx.exception))

if __name__ == '__main__':
    unittest.main()
