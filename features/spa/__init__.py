"""Feature: React SPA + blocked paths."""

from __future__ import annotations

from pathlib import Path

from core.config import DIST, SPA_ROUTES, is_blocked, normalize_request_path
from core.context import AppContext
from core.router import Router


def register(router: Router, ctx: AppContext) -> None:
    dist = ctx.dist if ctx.dist.is_dir() else DIST
    spa_routes = {normalize_request_path(route) for route in SPA_ROUTES}

    def serve_spa(handler) -> None:
        index = dist / "index.html"
        if not index.is_file():
            handler.send_error(404, "Сначала соберите фронт: npm run build")
            return
        data = index.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def spa_catch_all(handler, path: str) -> bool:
        if is_blocked(path):
            handler.send_error(404)
            return True

        normalized = normalize_request_path(path)
        if dist.is_dir() and (
            normalized in spa_routes
            or (
                not normalized.startswith("/assets/")
                and not normalized.startswith("/app/")
                and not normalized.startswith("/node_modules")
                and not normalized.startswith("/src/")
                and not normalized.startswith("/core/")
                and not normalized.startswith("/features/")
                and "." not in Path(normalized).name
            )
        ):
            serve_spa(handler)
            return True
        return False

    router.add_catch_all("GET", spa_catch_all)
