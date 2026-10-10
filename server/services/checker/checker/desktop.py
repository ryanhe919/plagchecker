"""Standalone entry point for Python and PyInstaller desktop child processes."""

import argparse
import json
import os
import signal
import socket
import subprocess
import threading
from pathlib import Path

import uvicorn


def parent_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied does not mean exited.
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_orphan(stop: threading.Event) -> None:
    stop.set()
    if os.name == "nt":
        # Terminate OCR children as well as this process after an Electron crash.
        subprocess.run(
            [str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/taskkill.exe"),
             "/PID", str(os.getpid()), "/T", "/F"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    elif os.getpgrp() == os.getpid():
        os.killpg(os.getpgrp(), signal.SIGTERM)


def watch_parent(pid: int, stop: threading.Event) -> threading.Thread:
    def monitor() -> None:
        while not stop.wait(1):
            if not parent_running(pid):
                stop_orphan(stop)
                return

    thread = threading.Thread(target=monitor, name="electron-parent-watchdog", daemon=True)
    thread.start()
    return thread


def configure_runtime(data_dir: Path) -> None:
    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CHECKER_JOBS_DIR"] = str(data_dir)
    os.environ.pop("CHECKER_TESSERACT_CWD", None)
    command = os.environ.get("TESSERACT_CMD")
    if command:
        from pytesseract import pytesseract

        executable = Path(command).expanduser().resolve()
        if not executable.is_file():
            raise ValueError(f"OCR 可执行文件缺失：{executable}")
        pytesseract.tesseract_cmd = str(executable)
    tessdata = os.environ.get("TESSDATA_PREFIX")
    if not tessdata and command and os.name == "nt":
        tessdata = str(executable.parent / "tessdata")
    if tessdata:
        languages = Path(tessdata).expanduser().resolve()
        for language in ("chi_sim", "eng"):
            if not (languages / f"{language}.traineddata").is_file():
                raise ValueError(f"OCR 语言包缺失：{language}.traineddata")
        os.environ["TESSDATA_PREFIX"] = str(languages)
        if command and os.name == "nt":
            # Use Unicode cwd via CreateProcessW, then ASCII '.' in the native
            # OCR CLI. This also supports custom model directories in Chinese.
            os.environ["CHECKER_TESSERACT_CWD"] = str(languages)


def write_ready_file(path: Path, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    endpoint = {"host": "127.0.0.1", "port": port, "pid": os.getpid()}
    launch_token = os.environ.get("CHECKER_LAUNCH_TOKEN")
    if launch_token is not None:
        endpoint["launch_token"] = launch_token
    temporary.write_text(json.dumps(endpoint), encoding="utf-8")
    os.replace(temporary, path)


class DesktopServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, ready_file: Path, port: int):
        super().__init__(config)
        self.ready_file = ready_file
        self.port = port

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            write_ready_file(self.ready_file, self.port)

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        try:
            await super().shutdown(sockets=sockets)
        finally:
            # Uvicorn re-raises SIGTERM after shutdown, before run() unwinds.
            self.ready_file.unlink(missing_ok=True)


def serve(web_dir: Path, ready_file: Path, port: int, stop: threading.Event) -> None:
    from checker.desktop_app import create_desktop_app

    ready_file = ready_file.expanduser().resolve()
    ready_file.unlink(missing_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", port))
        actual_port = listener.getsockname()[1]
        application = create_desktop_app(web_dir, actual_port)
        config = uvicorn.Config(
            application,
            host="127.0.0.1",
            port=actual_port,
            workers=1,
            loop="asyncio",
            http="h11",
            ws="none",
            proxy_headers=False,
            access_log=False,
        )
        server = DesktopServer(config, ready_file, actual_port)
        def stop_server() -> None:
            stop.wait()
            server.should_exit = True

        threading.Thread(target=stop_server, name="desktop-server-stop", daemon=True).start()
        try:
            server.run(sockets=[listener])
        finally:
            stop.set()
            ready_file.unlink(missing_ok=True)


def parser() -> argparse.ArgumentParser:
    arguments = argparse.ArgumentParser(description="标书查重桌面后端")
    commands = arguments.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker", help="运行持久化任务处理进程")
    worker.add_argument("--data-dir", type=Path, required=True)
    worker.add_argument("--parent-pid", type=int)
    server = commands.add_parser("serve", help="在本地回环地址提供界面及 API")
    server.add_argument("--data-dir", type=Path, required=True)
    server.add_argument("--parent-pid", type=int)
    server.add_argument("--web-dir", type=Path, required=True)
    server.add_argument("--ready-file", type=Path, required=True)
    server.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    server.add_argument("--port", type=int, choices=range(65536), metavar="0-65535", default=0)
    return arguments


def main() -> None:
    arguments = parser()
    options = arguments.parse_args()
    if options.parent_pid is not None and options.parent_pid <= 0:
        arguments.error("--parent-pid 必须为正整数")
    stop = threading.Event()
    try:
        configure_runtime(options.data_dir)
        if options.parent_pid is not None:
            watch_parent(options.parent_pid, stop)
        if options.command == "serve":
            serve(options.web_dir, options.ready_file, options.port, stop)
        else:
            from checker.worker import main as worker_main

            worker_main(stop)
    except (OSError, ValueError) as exc:
        arguments.exit(1, f"桌面后端启动失败：{exc}\n")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
