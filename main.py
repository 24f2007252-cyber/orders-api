from fastapi import FastAPI, Header, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 59
RATE_LIMIT = 20
WINDOW = 10

idempotency_store = {}
rate_limit_store = {}


class Order(BaseModel):
    item: str = "demo"
    quantity: int = 1


def encode_cursor(n: int) -> str:
    return base64.urlsafe_b64encode(str(n).encode()).decode()


def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor or cursor in ("null", "None"):
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client = request.headers.get("X-Client-Id")

    if client:
        now = time.time()

        timestamps = rate_limit_store.get(client, [])
        timestamps = [t for t in timestamps if now - t < WINDOW]

        if len(timestamps) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "10"},
                content={"detail": "Too Many Requests"},
            )

        timestamps.append(now)
        rate_limit_store[client] = timestamps

    return await call_next(request)


@app.get("/")
def root():
    return {"status": "running"}


@app.post("/orders")
def create_order(
    order: Order,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    created = {
        "id": str(uuid.uuid4()),
        "item": order.item,
        "quantity": order.quantity,
    }

    idempotency_store[idempotency_key] = created

    response.status_code = 201
    return created


@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):
    if limit <= 0:
        limit = 1

    start = decode_cursor(cursor)

    items = []
    current = start + 1

    while current <= TOTAL_ORDERS and len(items) < limit:
        items.append(
            {
                "id": current,
                "item": f"Item {current}",
            }
        )
        current += 1

    if current <= TOTAL_ORDERS:
        next_cursor = encode_cursor(current - 1)
    else:
        next_cursor = ""

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
