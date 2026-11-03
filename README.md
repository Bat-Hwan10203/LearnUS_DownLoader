# LearnUS Downloader (Windows)

앱에서 학번·비밀번호로 로그인하고, 강좌 또는 영상 링크에서 목록을 수집해 선택 다운로드하는 초기 버전입니다. Edge 실행과 쿠키 복사가 필요하지 않습니다.

**현재 연세대 SSO 로그인과 실제 강의 다운로드는 계정으로 검증되지 않았습니다.** 기존 공개 프로젝트의 SSO 프로토콜을 바탕으로 구현했으므로 사이트 변경·추가 인증 시 로그인 어댑터 수정이 필요할 수 있습니다. 클라우드 테스트 통과가 실제 LearnUS 호환성을 뜻하지 않습니다.

## Windows 실행

1. python.org에서 Python 3.10 이상을 설치합니다. 기본 Tcl/Tk 구성요소를 포함하세요.
2. 이 폴더에서 `setup.bat`를 실행합니다. 최초 설치에 인터넷이 필요합니다.
3. `run.bat`를 실행합니다.
4. 앱에 학번·비밀번호를 입력하고 로그인합니다.
5. `https://ys.learnus.org/course/view.php?id=...` 또는 영상 페이지 링크를 입력하고 **영상 조회**를 누릅니다.
6. Ctrl/Shift로 영상을 선택하고 저장 폴더를 정한 다음 **선택 다운로드**를 누릅니다.

비밀번호와 세션은 메모리에서만 사용합니다. 앱을 다시 열면 로그인해야 합니다. 로그인 실패 화면에 비밀번호나 쿠키가 표시되지 않습니다. 채팅·이슈에 비밀번호나 세션 정보를 붙여넣지 마세요.

## 지원 범위와 제한

- 일반 HTML `<source>`/`<video>` 플레이어, VOD 링크, 기존 LABY content_id 방식의 조회를 구현했습니다.
- 직접 파일 다운로드와 완료된 MPEG-TS HLS, 기본 AES-128 HLS를 지원합니다. HLS는 `.ts`로 저장합니다. 확장자만 MP4로 바꾸지 않습니다.
- DRM, 별도 오디오 트랙, 분할 MP4 HLS, 라이브, 불연속·바이트 범위 HLS는 미지원입니다.
- JavaScript로만 만들어지는 플레이어는 수집되지 않을 수 있습니다. 미공개 주차의 접근 권한을 우회하지 않습니다.
- 취소는 현재 네트워크 요청/청크 처리 뒤 반영됩니다. 요청 제한 시간은 연결 10초·응답 대기 45초입니다. 중단된 파일은 삭제하고 완료된 파일은 유지합니다.
- 같은 이름은 숫자를 붙여 기존 파일을 보호합니다. 다운로드 중인 파일은 `.part`로 저장합니다.
- 본인이 접근·저장할 권한이 있는 강의에 사용하세요. 다운로드는 출석 처리가 아닙니다.

## 개발과 검증

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe 사용
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m learnus
```

GUI는 Tcl/Tk와 디스플레이가 필요합니다. 모의 HTTP 서버 테스트는 실제 파일 쓰기, HLS 상대 주소, AES-128 복호화, 기존 파일 보호, 취소와 실패 정리를 검증합니다. 실제 계정 로그인은 자동 테스트에 포함하지 않습니다.

Windows에서 `build-windows.bat` 실행 시 `dist/LearnUSDownloader/`에 실행 폴더를 만듭니다. 폴더 전체를 배포하세요. Windows 실행 파일 빌드는 Windows에서 별도 검증해야 합니다.

## 참고 및 라이선스

SSO 어댑터 `learnus/auth.py`는 [henryjmin/learnus-dl](https://github.com/henryjmin/learnus-dl)의 MIT 라이선스 코드에서 파생되었습니다. 저작권 고지는 `THIRD_PARTY_LICENSE.txt`에 보존되어 있습니다. 영상 유형 조사에는 [ashgold/Learnus-video-downloader](https://github.com/ashgold/Learnus-video-downloader)를 참고했으며 노트북 코드는 복사하지 않았습니다.
