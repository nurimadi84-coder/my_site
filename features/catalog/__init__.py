"""Feature: каталог товаров."""

from __future__ import annotations

from core.context import AppContext
from core.http import content_length, read_body, read_json_body, send_json
from core.router import Router

from . import service


def setup(ctx: AppContext) -> None:
    service.setup()


def register(router: Router, ctx: AppContext) -> None:
    def list_public(handler) -> None:
        send_json(
            handler,
            {
                "products": [
                    service.public_product(item)
                    for item in service.load_products()
                    if item.get("visible", True)
                ]
            },
        )

    def list_admin(handler) -> None:
        send_json(
            handler,
            {"products": [service.public_product(item) for item in service.load_products()]},
        )

    def create(handler) -> None:
        body = read_json_body(handler)
        if body is None:
            return
        try:
            item = service.create_product(body)
        except ValueError as err:
            send_json(handler, {"error": str(err)}, 400)
            return
        send_json(handler, {"product": service.public_product(item)}, 201)

    def update(handler, product_id: str) -> None:
        body = read_json_body(handler)
        if body is None:
            return
        try:
            item = service.update_product(product_id, body)
        except ValueError as err:
            send_json(handler, {"error": str(err)}, 400)
            return
        if item is None:
            send_json(handler, {"error": "Товар не найден"}, 404)
            return
        send_json(handler, {"product": service.public_product(item)})

    def delete(handler, product_id: str) -> None:
        removed = service.delete_product(product_id)
        if removed is None:
            send_json(handler, {"error": "Товар не найден"}, 404)
            return
        service.discard_images(service.product_images(removed))
        send_json(handler, {"ok": True})

    def upload(handler) -> None:
        kind = handler.headers.get("Content-Type", "").split(";")[0].strip().lower()
        extension = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(kind)
        if not extension:
            send_json(handler, {"error": "Нужна фотография JPG, PNG или WebP"}, 400)
            return
        length = content_length(handler)
        if length <= 0 or length > service.MAX_IMAGE:
            send_json(handler, {"error": "Фото слишком большое. Сожмите его до 6 МБ."}, 400)
            return
        data = read_body(handler, length)
        if data is None:
            send_json(handler, {"error": "Фото загружено не полностью"}, 400)
            return
        real_extension = service.image_extension(data)
        if real_extension is None:
            send_json(handler, {"error": "Файл не похож на фотографию JPG, PNG или WebP"}, 400)
            return
        image = service.save_upload(data, real_extension)
        send_json(handler, {"image": image})

    # CatalogTool уже в default registry engine; при желании можно ctx.tools.register(...)
    from core.ai.catalog import CatalogTool

    ctx.tools.register(CatalogTool())

    router.add("GET", "/api/products", list_public)
    router.add("GET", "/api/admin/products", list_admin, auth=True)
    router.add("POST", "/api/products", create, auth=True)
    router.add("POST", "/api/upload", upload, auth=True)
    router.add_prefix("PUT", "/api/products/", update, auth=True)
    router.add_prefix("DELETE", "/api/products/", delete, auth=True)
