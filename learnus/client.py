import html
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import m3u8
import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from .browser_auth import login_browser
from .errors import UserError, connection_error

BASE = 'https://ys.learnus.org'

class Session(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', (10, 45))
        try:
            response = super().request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise connection_error(exc, url, getattr(self, 'stage', '서버 요청')) from None

@dataclass(frozen=True)
class Video:
    title: str
    url: str
    referer: str


def validate_link(url):
    p = urlsplit(url.strip())
    if p.scheme != 'https' or p.hostname != 'ys.learnus.org' or p.username or p.password or p.port not in (None, 443):
        raise UserError('https://ys.learnus.org/ 로 시작하는 강좌 또는 영상 링크를 입력하세요.')
    if not p.path.startswith(('/course/', '/mod/')):
        raise UserError('강좌 또는 영상 페이지 링크가 필요합니다.')
    return url.strip()


def safe_name(title):
    name = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '_', title).strip(' .')[:140] or 'video'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}:
        name = '_' + name
    return name


class Client:
    def __init__(self):
        self.session = Session()
        self.cancel = threading.Event()
        self.logged_in = False

    def login(self, username, password, show_login=False):
        self.logged_in = False
        self.session.close()
        self.session = Session()
        try:
            login_browser(username, password, self.session, self.cancel, show_login=show_login)
            self.session.stage = '로그인 결과 확인'
            page = self.session.get(BASE + '/my/')
            soup = BeautifulSoup(page.text, 'html.parser')
            if '/login/' in page.url or not soup.select('a[href*="logout.php"]'):
                raise UserError('로그인을 확인하지 못했습니다. 입력 정보 또는 현재 SSO 지원 여부를 확인하세요.')
        except (TypeError, KeyError, ValueError, AttributeError):
            self.session.cookies.clear()
            raise UserError('SSO 응답을 처리하지 못했습니다. 로그인 정보, 추가 인증 또는 사이트 변경을 확인하세요.') from None
        except Exception:
            self.session.cookies.clear()
            raise
        self.session.stage = '서버 요청'
        self.logged_in = True

    def _check_cancel(self):
        if self.cancel.is_set():
            raise UserError('작업을 취소했습니다.')

    def page(self, url):
        self._check_cancel()
        r = self.session.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        if '/login/' in r.url or soup.select('input[type="password"]'):
            self.logged_in = False
            raise UserError('로그인이 필요하거나 세션이 만료되었습니다.')
        return r, soup

    def collect(self, url, report=lambda text: None):
        if not self.logged_in:
            raise UserError('먼저 로그인하세요.')
        url = validate_link(url)
        r, soup = self.page(url)
        pages = [(r.url, soup)]
        if urlsplit(url).path.startswith('/course/'):
            links = []
            for tag in soup.select('a[href], [onclick]'):
                candidates = [tag.get('href', '')] + re.findall(r"['\"]([^'\"]+)['\"]", tag.get('onclick', ''))
                for candidate in candidates:
                    link = urljoin(r.url, html.unescape(candidate))
                    p = urlsplit(link)
                    if p.hostname == 'ys.learnus.org' and re.match(r'/mod/(vod|laby|econtents)/', p.path):
                        if p.path.endswith('/view.php') and '/vod/' in p.path:
                            link = link.replace('/vod/view.php', '/vod/viewer.php')
                        if link not in links:
                            links.append(link)
            pages = []
            for i, link in enumerate(links, 1):
                report(f'영상 페이지 확인 {i}/{len(links)}')
                _, child = self.page(link)
                pages.append((link, child))
        elif '/vod/view.php' in url:
            url = url.replace('/vod/view.php', '/vod/viewer.php')
            _, soup = self.page(url)
            pages = [(url, soup)]
        result = []
        seen = set()
        for link, page in pages:
            self._check_cancel()
            title_tag = page.select_one('#vod_header h1, h1, title')
            title = title_tag.get_text(' ', strip=True) if title_tag else '영상'
            sources = [t.get('src') for t in page.select('source[src], video[src]')]
            # Older LABY players expose a content_id and return XML media URLs.
            match = re.search(r'content_id=([^&\s"\'<>]+)', str(page))
            if match and not any(sources):
                response = self.session.get('https://alrs.yonsei.ac.kr/HttpAPI/GetContentinfobyPlayer', params={'cnt_uid': match[1], 'cos_uid': '', 'cnt_playtype': '0'})
                content = BeautifulSoup(response.text, 'html.parser')
                sources += [t.get_text(strip=True) for t in content.find_all(re.compile(r'^content_url\d+$'))]
            for index, source in enumerate(filter(None, sources), 1):
                media = urljoin(link, html.unescape(source))
                if urlsplit(media).scheme != 'https':
                    continue
                if media not in seen:
                    seen.add(media)
                    result.append(Video(f'{title} ({index})' if index > 1 else title, media, link))
        if not result:
            raise UserError('영상을 찾지 못했습니다. 수강 권한·공개 기간 또는 지원되지 않는 플레이어인지 확인하세요.')
        return result

    def download(self, video, folder, report=lambda text: None):
        self._check_cancel()
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        headers = {'Referer': video.referer}
        response = self.session.get(video.url, headers=headers, stream=True)
        is_hls = '.m3u8' in urlsplit(response.url).path.lower() or 'mpegurl' in response.headers.get('Content-Type', '').lower()
        suffix = '.ts' if is_hls else '.mp4'
        path = folder / (safe_name(video.title) + suffix)
        n = 2
        while path.exists() or path.with_suffix(path.suffix + '.part').exists():
            path = folder / f'{safe_name(video.title)} ({n}){suffix}'
            n += 1
        partial = path.with_suffix(path.suffix + '.part')
        try:
            if not is_hls:
                if 'text/html' in response.headers.get('Content-Type', '').lower():
                    raise UserError('영상 대신 로그인/오류 페이지를 받았습니다.')
                with partial.open('xb') as output:
                    for chunk in response.iter_content(256 * 1024):
                        self._check_cancel()
                        output.write(chunk)
            else:
                playlist = m3u8.loads(response.text, uri=response.url)
                response.close()
                if playlist.is_variant:
                    selected = max(playlist.playlists, key=lambda p: p.stream_info.bandwidth or 0)
                    if selected.stream_info.audio:
                        raise UserError('별도 오디오 트랙이 있는 HLS는 아직 지원하지 않습니다.')
                    child = self.session.get(selected.absolute_uri, headers=headers)
                    playlist = m3u8.loads(child.text, uri=child.url)
                if not playlist.is_endlist or not playlist.segments:
                    raise UserError('완료된 VOD 재생목록만 지원합니다.')
                if any(s.init_section or s.byterange or s.discontinuity for s in playlist.segments):
                    raise UserError('분할 MP4·바이트 범위·불연속 HLS는 아직 지원하지 않습니다.')
                keys = {}
                with partial.open('xb') as output:
                    for i, segment in enumerate(playlist.segments):
                        self._check_cancel()
                        key = segment.key
                        if key and key.method not in ('NONE', 'AES-128'):
                            raise UserError('이 영상의 암호화 방식은 지원하지 않습니다.')
                        data = self.session.get(segment.absolute_uri, headers=headers).content
                        if key and key.method == 'AES-128':
                            if key.keyformat not in (None, 'identity'):
                                raise UserError('DRM 영상은 지원하지 않습니다.')
                            key_url = key.absolute_uri
                            if key_url not in keys:
                                keys[key_url] = self.session.get(key_url, headers=headers).content
                            iv = bytes.fromhex(key.iv[2:].zfill(32)) if key.iv else (playlist.media_sequence + i).to_bytes(16, 'big')
                            data = AES.new(keys[key_url], AES.MODE_CBC, iv).decrypt(data)
                            pad = data[-1] if data else 0
                            if not 1 <= pad <= 16 or data[-pad:] != bytes([pad]) * pad:
                                raise UserError('영상 조각 복호화 결과가 올바르지 않습니다.')
                            data = data[:-pad]
                        output.write(data)
                        report(f'영상 조각 {i+1}/{len(playlist.segments)}')
            partial.rename(path)
            return path
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        finally:
            response.close()
