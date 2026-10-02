"""Feature: CRM (заказы и клиенты)."""

from __future__ import annotations

from core.ai.handoff import HandoffTool
from core.context import AppContext
from core.http import client_ip, read_json_body, send_json
from core.router import Router

from . import service


def setup(ctx: AppContext) -> None:
    service.setup()


def register(router: Router, ctx: AppContext) -> None:
    ctx.tools.register(HandoffTool())

    def list_orders(handler) -> None:
        send_json(handler, {"orders": [service.public_order(item) for item in service.load_orders()]})

    def list_clients(handler) -> None:
        clients = service.load_clients()
        send_json(handler, {"clients": [service.public_client(item) for item in clients]})

    def create_order(handler) -> None:
        if not service.allow_order_create(client_ip(handler)):
            send_json(handler, {"error": "Слишком много заявок. Подождите минуту."}, 429)
            return
        body = read_json_body(handler)
        if body is None:
            return
        try:
            order = service.create_order(body)
        except ValueError as err:
            send_json(handler, {"error": str(err)}, 400)
            return
        send_json(handler, {"order": service.public_order(order)}, 201)

    def patch_order(handler, order_id: str) -> None:
        body = read_json_body(handler)
        if body is None:
            return
        raw_status = body.get("status")
        status = None if raw_status is None else str(raw_status).strip().lower()
        try:
            item = service.patch_order(order_id, status, body.get("note"))
        except ValueError as err:
            send_json(handler, {"error": str(err)}, 400)
            return
        if item is None:
            send_json(handler, {"error": "Заказ не найден"}, 404)
            return
        send_json(handler, {"order": service.public_order(item)})

    def delete_order(handler, order_id: str) -> None:
        if not service.delete_order(order_id):
            send_json(handler, {"error": "Заказ не найден"}, 404)
            return
        send_json(handler, {"ok": True})

    def patch_client(handler, client_id: str) -> None:
        body = read_json_body(handler)
        if body is None:
            return
        item = service.patch_client(client_id, body)
        if item is None:
            send_json(handler, {"error": "Клиент не найден"}, 404)
            return
        send_json(handler, {"client": service.public_client(item)})

    router.add("GET", "/api/admin/orders", list_orders, auth=True)
    router.add("GET", "/api/admin/clients", list_clients, auth=True)
    router.add("POST", "/api/orders", create_order)
    router.add_prefix("PATCH", "/api/orders/", patch_order, auth=True)
    router.add_prefix("DELETE", "/api/orders/", delete_order, auth=True)
    router.add_prefix("PATCH", "/api/clients/", patch_client, auth=True)
