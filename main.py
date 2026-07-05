from fastapi import FastAPI, Header, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import time
import base64

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 59
RATE_LIMIT = 20
WINDOW = 10  # seconds

# Stores
idempotency_store = {}
rate_limit_store = {}


# -----------------------------
# Models
# -----------------------------
class Order(BaseModel):
    item: str = "demo"
    quantity: int = 1


# -----------------------------
# Cursor helpers
# -----------------------------
def encode_cursor(index: int):
    return base64.urlsafe_b64encode(str(index).encode()).decode()


def decode_cursor(cursor: str):
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0


# -----------------------------
# Rate Limiting Middleware
# -----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Only rate-limit requests that provide X-Client-Id
    client = request.headers.get("X-Client-Id")

    if client:
        now = time.time()

        timestamps = rate_limit_store.get(client, [])

        # keep only last 10 seconds
        timestamps = [t for t in timestamps if now - t < WINDOW]

        if len(timestamps) >= RATE_LIMIT:
            return Response(
                status_code=429,
                headers={"Retry-After": "10"},
                content="Rate limit exceeded"
            )

        timestamps.append(now)
        rate_limit_store[client] = timestamps

    response = await call_next(request)
    return response


# -----------------------------
# Home
# -----------------------------
@app.get("/")
def root():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: Order,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):

    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    order_id = str(uuid.uuid4())

    created = {
        "id": order_id,
        "item": order.item,
        "quantity": order.quantity,
    }

    idempotency_store[idempotency_key] = created

    return created


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(limit: int = 10, cursor: str = ""):

    if limit < 1:
        limit = 1

    start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append({
            "id": i,
            "item": f"Item {i}"
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }
