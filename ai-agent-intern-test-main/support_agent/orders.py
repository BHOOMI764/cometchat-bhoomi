from __future__ import annotations

import json
import re
from pathlib import Path


def normalize_order_id(raw: str | None):
    if raw is None:
        return None
    value = str(raw).strip().upper()
    if not value:
        return None
    value = value.replace(" ", "")
    match = re.search(r"ORD-\d+", value)
    if match:
        return match.group(0)
    return None


def load_orders(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["order_id"].upper(): item for item in data.get("orders", [])}


def lookup_order(order_id: str, path: Path):
    normalized = normalize_order_id(order_id)
    orders = load_orders(path)
    order = orders.get(normalized) if normalized else None
    if not order:
        return {"found": False, "order_id": normalized, "status": None}
    return {"found": True, "order_id": normalized, "status": order.get("status"), "payload": order}


def safe_order_summary(order_payload: dict):
    if not order_payload:
        return "I could not find that order ID. Please check the order ID or contact support."
    status = (order_payload.get("status") or "unknown").lower()
    carrier = order_payload.get("carrier")
    estimated = order_payload.get("estimated_delivery")
    if status == "cancelled":
        return "This order was cancelled and will not be shipped."
    if status == "returned":
        return "This order has already been returned and processed."
    if status == "delivered":
        if estimated:
            return f"This order was delivered on {estimated}."
        return "This order was delivered."
    if status in {"shipped", "in_transit", "delayed"}:
        bits = [f"The order is currently {status}."]
        if carrier:
            bits.append(f"Carrier: {carrier}.")
        if estimated:
            bits.append(f"Estimated delivery: {estimated}.")
        return " ".join(bits)
    return f"The order status is {status}."
