# LearnUS Downloader (Windows)

앱에서 학번·비밀번호를 입력하고 강좌/영상 링크의 목록을 조회한 뒤 선택 다운로드하는 초기 버전입니다.

## Windows 실행

1. Python 3.10 이상을 Tcl/Tk 구성요소와 함께 설치합니다.
2. Chrome을 설치합니다. Chrome이 없으면 설치된 Microsoft Edge 엔진을 사용합니다.
3. ZIP을 새 폴더에 풀고 `setup.bat`를 실행합니다. 새 로그인 엔진 의존성 때문에 업데이트 시에도 필요합니다.
4. `run.bat`를 실행합니다.
5. 앱에 학번·비밀번호를 입력해 로그인합니다. 별도 브라우저 창이나 쿠키 복사는 필요하지 않습니다.
6. `https://ys.learnus.org/course/view.php?id=...` 또는 영상 페이지 링크를 입력하고 **영상 조회**를 누릅니다.
7. Ctrl/Shift로 영상을 선택하고 저장 폴더를 지정한 다음 **선택 다운로드**를 누릅니다.

## 로그인 방식과 검증 범위

기본 로그인은 Playwright로 **설치된 Chrome을 headless(창 없음) 모드**에서 실행합니다. 직접 HTTP 요청으로 암호화/폼 전송을 재현하던 방식 대신, 공식 LearnUS·연세대 SSO 화면의 JavaScript가 로그인 버튼의 동작을 처리합니다. SSO 팝업의 부모 창 관계도 유지합니다. 기존 Chrome 프로필이나 로그인 정보를 읽지 않고 별도 임시 컨텍스트를 사용합니다.

인증이 완료되면 로그인 세션을 앱의 메모리로 전달하고 브라우저 엔진을 종료합니다. 앱에서 비밀번호·세션을 파일에 저장하지 않으며, 재실행 시 다시 로그인합니다. 오류에 원문 Playwright 로그를 표시하지 않습니다. 추가 인증·CAPTCHA를 우회하지 않고, 자격증명 제출을 자동 재시도하지 않습니다.

**실제 공개 서버에서 headless Chromium으로 로그인 화면과 입력란/버튼까지 도달하는 것을 확인했습니다. 실제 계정 로그인, 인증 이후 세션 전달과 Windows Chrome 실행은 사용자 로컬 검증이 필요합니다.** 이 사전 확인은 로그인 성공을 뜻하지 않습니다. 회사/학교 정책이 headless 실행을 막거나 추가 인증을 요구하면 지원 범위를 추가 검토해야 합니다.

`learnus/auth.py`의 직접 HTTP SSO 구현은 조사/회귀 검증용으로 남아 있지만 기본 앱 로그인에는 사용하지 않습니다.

## 영상 지원 범위

- 일반 HTML `<source>`/`<video>` 플레이어, VOD 링크, 기존 LABY content_id 방식의 조회를 구현했습니다.
- 직접 파일과 완료된 MPEG-TS HLS, 기본 AES-128 HLS를 지원합니다. HLS는 `.ts`로 저장합니다.
- DRM, 별도 오디오 트랙, 분할 MP4 HLS, 라이브, 불연속·바이트 범위 HLS는 미지원입니다.
- JavaScript로만 만들어지는 영상 플레이어는 수집되지 않을 수 있습니다. 수강 권한이나 미공개 주차의 접근 제한을 우회하지 않습니다.
- 취소는 현재 네트워크 요청/화면 대기 후 반영됩니다. 완료된 파일은 유지하고 중단된 `.part` 파일은 삭제합니다.
- 같은 이름은 숫자를 붙여 기존 파일을 보호합니다.
- 본인이 접근·저장할 권한이 있는 강의에 사용하세요. 다운로드는 출석 처리가 아닙니다.

## 오류 진단

앱 제목에 **공식 로그인 엔진**이 표시되는지 확인하세요. 로그인 오류 메시지와 일반 웹사이트에서 로그인되는지 알려주시면 됩니다. 비밀번호·쿠키는 보내지 마세요.

`diagnose.bat`는 계정 정보 없이 공개 로그인 페이지 구조만 확인합니다. 실제 인증 실패의 상세 원인이나 headless 엔진 성공 여부를 검증하지는 않습니다. 인증서 검증을 끄지 마세요.

## 개발·검증

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe 사용
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m learnus
```

GUI는 Tcl/Tk와 디스플레이가 필요합니다. Linux 로그인 엔진은 시스템 Chromium/Chrome을 사용합니다. 모의 HTTP 서버 테스트는 다운로드와 복호화·실패 정리를 검증합니다. 인증 테스트는 모의 SSO, 엔진 종료, 쿠키 전달, 비밀번호 오류 비노출 등을 확인하며 실제 계정은 사용하지 않습니다.

Windows에서 `build-windows.bat`를 실행하면 `dist/LearnUSDownloader/`에 실행 폴더를 만듭니다. 폴더 전체를 배포하세요. 대상 컴퓨터의 Chrome/Edge도 필요합니다. Windows 빌드는 별도 검증이 필요합니다.

## 참고 및 라이선스

초기 SSO 어댑터는 [henryjmin/learnus-dl](https://github.com/henryjmin/learnus-dl)의 MIT 코드에서 파생되었고 `THIRD_PARTY_LICENSE.txt`에 고지를 보존했습니다. 영상 유형 조사에는 [ashgold/Learnus-video-downloader](https://github.com/ashgold/Learnus-video-downloader)를 참고했으며 노트북 코드는 복사하지 않았습니다.
