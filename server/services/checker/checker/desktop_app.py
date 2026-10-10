"""Same-origin web application used only by the packaged desktop runtime."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from checker.api import app as api_app
from checker.api import lifespan


class LoopbackGuard:
    """Reject DNS rebinding and browser requests originating outside the app."""

    def __init__(self, app: ASGIApp, authority: str):
        self.app = app
        self.authority = authority
        self.origin = f"http://{authority}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            hosts = [value.decode("latin1") for key, value in scope["headers"] if key.lower() == b"host"]
            origins = [value.decode("latin1") for key, value in scope["headers"] if key.lower() == b"origin"]
            if hosts != [self.authority] or (origins and origins != [self.origin]):
                response = JSONResponse({"detail": "仅允许桌面应用的本地请求"}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class DesktopFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            is_page = path in {"new", "history"} or (
                path.startswith("jobs/") and len(path.split("/")) == 2 and "." not in path
            )
            if exc.status_code == 404 and is_page:
                return await super().get_response("index.html", scope)
            raise


def create_desktop_app(web_dir: Path, port: int) -> FastAPI:
    web_dir = web_dir.resolve()
    if not (web_dir / "index.html").is_file():
        raise ValueError(f"前端文件缺失：{web_dir / 'index.html'}")
    application = FastAPI(
        title="标书查重桌面应用", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    # Reuse the API routes with this application's state and run its lifespan
    # once. include_router(api_app.router) would merge the same lifespan twice.
    application.router.routes.extend(route for route in api_app.routes if isinstance(route, APIRoute))
    application.add_middleware(LoopbackGuard, authority=f"127.0.0.1:{port}")
    application.mount("/", DesktopFiles(directory=web_dir, html=True), name="desktop")
    return application
