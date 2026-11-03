from urllib.parse import urlsplit
import requests


class UserError(Exception):
    pass


def connection_error(exc, url, stage='서버 요청'):
    """Only locally generated labels; never show response bodies or exception text."""
    host = urlsplit(url).hostname or '서버'
    if isinstance(exc, requests.exceptions.SSLError):
        reason = 'TLS 인증서 검증 실패. Windows 날짜·시간과 인증서/보안 프로그램 설정을 확인하세요.'
    elif isinstance(exc, requests.exceptions.ProxyError):
        reason = '프록시 연결 실패. Windows 또는 회사·학교의 프록시 설정을 확인하세요.'
    elif isinstance(exc, requests.exceptions.Timeout):
        reason = '서버 응답 시간 초과. 잠시 후 재시도하세요.'
    elif isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else '알 수 없음'
        if code == 404:
            reason = 'HTTP 404: 요청한 주소가 없습니다. 로그인 경로가 바뀌었을 수 있습니다. 비밀번호 오류를 뜻하지 않습니다. 최신 diagnose.bat 결과가 필요합니다.'
        else:
            reason = f'HTTP {code}. 서버가 요청을 거부하거나 처리하지 못했습니다.'
    elif isinstance(exc, requests.exceptions.ConnectionError):
        reason = '연결 실패. DNS·방화벽·인터넷 연결 또는 서버 상태를 확인하세요.'
    else:
        reason = '네트워크 요청 실패.'
    return UserError(f'{stage} [{host}]\n{reason}')
