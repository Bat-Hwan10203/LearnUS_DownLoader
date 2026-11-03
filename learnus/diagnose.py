"""Public, credential-free connectivity check. Never reads saved credentials."""
from .client import Session
from .errors import UserError


def main():
    with Session() as session:
        session.stage = '공개 페이지 연결 진단'
        for url in ('https://ys.learnus.org/login/index.php', 'https://infra.yonsei.ac.kr/'):
            try:
                response = session.get(url, allow_redirects=False)
                print(f'{url}: HTTP {response.status_code} (연결 성공; 로그인 성공을 뜻하지 않음)')
            except UserError as exc:
                print(str(exc))

if __name__ == '__main__':
    main()
