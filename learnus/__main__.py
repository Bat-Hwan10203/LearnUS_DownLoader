import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import requests
from .client import Client, UserError


class App:
    def __init__(self, root):
        self.root = root
        self.client = Client()
        self.events = queue.Queue()
        self.videos = []
        self.busy = False
        root.title('LearnUS Downloader — 공식 로그인 엔진')
        root.geometry('850x620')
        root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='LearnUS Downloader', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Chrome 엔진으로 창 없이 로그인 → 링크 조회 → 선택 다운로드').pack(anchor='w', pady=(4, 16))
        login = ttk.Frame(frame)
        login.pack(fill='x')
        ttk.Label(login, text='학번').pack(side='left')
        self.username = ttk.Entry(login, width=19)
        self.username.pack(side='left', padx=8)
        ttk.Label(login, text='비밀번호').pack(side='left')
        self.password = ttk.Entry(login, show='●', width=22)
        self.password.pack(side='left', padx=8)
        self.login_button = ttk.Button(login, text='로그인', command=self.login)
        self.login_button.pack(side='left')
        ttk.Label(frame, text='비밀번호·세션은 디스크에 저장하지 않습니다. 앱을 닫으면 다시 로그인해야 합니다.').pack(anchor='w', pady=8)
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        self.url = ttk.Entry(row)
        self.url.pack(side='left', fill='x', expand=True)
        self.lookup_button = ttk.Button(row, text='영상 조회', command=self.collect)
        self.lookup_button.pack(side='left', padx=(8, 0))
        ttk.Label(frame, text='Ctrl / Shift로 여러 영상을 선택할 수 있습니다.').pack(anchor='w')
        self.listbox = tk.Listbox(frame, selectmode='extended', exportselection=False)
        self.listbox.pack(fill='both', expand=True, pady=8)
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.folder = tk.StringVar(value=str(Path.home() / 'Downloads' / 'LearnUS'))
        ttk.Entry(row, textvariable=self.folder).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='저장 폴더', command=self.choose_folder).pack(side='left', padx=8)
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        self.all_button = ttk.Button(row, text='전체 선택', command=lambda: self.listbox.selection_set(0, 'end'))
        self.all_button.pack(side='left')
        self.download_button = ttk.Button(row, text='선택 다운로드', command=self.download)
        self.download_button.pack(side='left', padx=8)
        self.cancel_button = ttk.Button(row, text='취소', command=self.client.cancel.set, state='disabled')
        self.cancel_button.pack(side='left')
        self.status = tk.StringVar(value='로그인해 주세요. 현재 SSO 호환성은 실제 계정으로 확인이 필요합니다.')
        ttk.Label(frame, textvariable=self.status, wraplength=790).pack(anchor='w')
        root.after(100, self.poll)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder.set(path)

    def report(self, text):
        self.events.put(('status', text))

    def run(self, action, done):
        if self.busy:
            return
        self.busy = True
        self.client.cancel.clear()
        for button in (self.login_button, self.lookup_button, self.download_button, self.all_button):
            button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        def worker():
            try:
                self.events.put(('done', (done, action())))
            except UserError as exc:
                self.events.put(('error', str(exc)))
            except requests.RequestException:
                self.events.put(('error', '서버 연결에 실패했습니다. 네트워크·서버 상태를 확인하세요.'))
            except Exception:
                self.events.put(('error', '응답 처리에 실패했습니다. 사이트 형식 변경 또는 미지원 영상일 수 있습니다.'))
            finally:
                self.events.put(('idle', None))
        threading.Thread(target=worker, daemon=True).start()

    def login(self):
        username, password = self.username.get().strip(), self.password.get()
        if not username or not password:
            messagebox.showinfo('로그인', '학번과 비밀번호를 입력하세요.')
            return
        self.password.delete(0, 'end')
        self.videos = []
        self.listbox.delete(0, 'end')
        self.status.set('로그인 중…')
        self.run(lambda: self.client.login(username, password), lambda _: self.status.set('로그인 확인 완료'))

    def collect(self):
        url = self.url.get().strip()
        self.videos = []
        self.listbox.delete(0, 'end')
        self.status.set('영상 조회 중…')
        def done(videos):
            self.videos = videos
            for video in videos:
                self.listbox.insert('end', video.title)
            self.status.set(f'{len(videos)}개 영상 발견. 다운로드할 영상을 선택하세요.')
        self.run(lambda: self.client.collect(url, self.report), done)

    def download(self):
        videos = [self.videos[i] for i in self.listbox.curselection()]
        if not videos:
            messagebox.showinfo('다운로드', '다운로드할 영상을 선택하세요.')
            return
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showinfo('저장 폴더', '저장 폴더를 지정하세요.')
            return
        def work():
            paths = []
            for i, video in enumerate(videos, 1):
                self.report(f'{i}/{len(videos)} 다운로드 중')
                paths.append(self.client.download(video, folder, self.report))
            return paths
        self.run(work, lambda paths: self.status.set(f'{len(paths)}개 다운로드 완료: {folder}'))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                elif kind == 'done':
                    callback, result = value
                    callback(result)
                elif kind == 'error':
                    self.status.set(value)
                    messagebox.showerror('작업 실패', value)
                elif kind == 'idle':
                    self.busy = False
                    for button in (self.login_button, self.lookup_button, self.download_button, self.all_button):
                        button.configure(state='normal')
                    self.cancel_button.configure(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.client.cancel.set()
            messagebox.showinfo('작업 취소', '현재 요청이 끝나고 작업이 중지되면 창을 닫아 주세요.')
            return
        self.client.session.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
