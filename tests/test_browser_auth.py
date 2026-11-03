import threading
import unittest
from unittest.mock import Mock, patch, MagicMock
import requests
from playwright.sync_api import Error
from learnus.browser_auth import login_browser, transfer_cookies, launch_browser
from learnus.errors import UserError


class BrowserAuthTests(unittest.TestCase):
    def test_cookie_domain_path_and_security_preserved(self):
        session=requests.Session()
        transfer_cookies([
            dict(name='MoodleSession',value='test-session',domain='ys.learnus.org',path='/',secure=True,httpOnly=True,expires=-1),
            dict(name='unrelated',value='no',domain='evil.example',path='/'),
        ],session)
        cookies=list(session.cookies)
        self.assertEqual(len(cookies),1)
        self.assertEqual(cookies[0].domain,'ys.learnus.org')
        self.assertTrue(cookies[0].secure)
        self.assertIsNone(cookies[0].expires)

    def test_windows_fallback_only_before_login(self):
        playwright=Mock()
        playwright.chromium.launch.side_effect=[Error('Chrome absent'),Mock()]
        with patch('learnus.browser_auth.sys.platform','win32'):
            launch_browser(playwright)
        self.assertEqual([c.kwargs['channel'] for c in playwright.chromium.launch.call_args_list],['chrome','msedge'])

    def test_engine_exception_never_displays_password(self):
        manager=MagicMock()
        manager.__enter__.side_effect=Error('fill password=SECRET')
        session=requests.Session()
        with patch('learnus.browser_auth.sync_playwright',return_value=manager):
            with self.assertRaises(UserError) as error:
                login_browser('student','SECRET',session)
        self.assertNotIn('SECRET',str(error.exception))

    def test_browser_closes_on_cancellation(self):
        manager=MagicMock()
        browser=Mock()
        context=browser.new_context.return_value
        cancel=threading.Event();cancel.set()
        with patch('learnus.browser_auth.sync_playwright',return_value=manager), patch('learnus.browser_auth.launch_browser',return_value=browser), patch('learnus.browser_auth.open_login',return_value=(Mock(),Mock())):
            with self.assertRaisesRegex(UserError,'취소'):
                login_browser('student','SECRET',requests.Session(),cancel)
        browser.close.assert_called_once()

    def test_success_submits_once_transfers_cookies_and_closes(self):
        manager=MagicMock();browser=Mock();context=browser.new_context.return_value
        popup=Mock();popup.is_closed.return_value=True
        response=context.request.get.return_value
        response.ok=True;response.url='https://ys.learnus.org/my/'
        response.text.return_value='<a href="/login/logout.php">Logout</a>'
        context.cookies.return_value=[dict(name='MoodleSession',value='success',domain='ys.learnus.org',path='/',secure=True,httpOnly=True)]
        context.pages=[Mock()];context.pages[0].evaluate.return_value='test-UA'
        popup.expect_navigation.return_value=MagicMock()
        with patch('learnus.browser_auth.sync_playwright',return_value=manager), patch('learnus.browser_auth.launch_browser',return_value=browser), patch('learnus.browser_auth.open_login',return_value=(Mock(),popup)):
            session=requests.Session()
            login_browser('student','secret',session)
        popup.locator.assert_any_call('#loginBtn')
        popup.locator.return_value.click.assert_called_once()
        self.assertEqual(session.cookies.get('MoodleSession'),'success')
        browser.close.assert_called_once()
