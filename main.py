from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import base64
import time

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 59
RATE_LIMIT = 20
WINDOW = 10  # seconds

# -----------------------------
# Idempotency storage
# -----------------------------
orders_by_key = {}

# -----------------------------
# Rate limiting storage
# -----------------------------
client_requests = {}

# -----------------------------
# Models
# -----------------------------
class Order(BaseModel):
    item: str = "demo"
    quantity: int = 1

# -----------------------------
# Helpers
# -----------------------------
def encode_cursor(index: int):
    return base64.urlsafe_b64encode(str(index).encode()).decode()

def decode_cursor(cursor: str):
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except:
        return 0

# -----------------------------
# Middleware
# -----------------------------
@app.middleware("http")
async def rate_limit(request, call_next):

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    timestamps = client_requests.get(client, [])

    timestamps = [t for t in timestamps if now - t < WINDOW]

    if len(timestamps) >= RATE_LIMIT:
        return Response(
            status_code=429,
            headers={
                "Retry-After": "10"
            }
        )

    timestamps.append(now)

    client_requests[client] = timestamps

    return await call_next(request)

# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: Order,
    response: Response,
    idempotency_key: str = Header(...)
):

    if idempotency_key in orders_by_key:
        return orders_by_key[idempotency_key]

    oid = str(uuid.uuid4())

    result = {
        "id": oid,
        "item": order.item,
        "quantity": order.quantity
    }

    orders_by_key[idempotency_key] = result

    return result

# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str = ""
):

    start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append({
            "id": i
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }

@app.get("/")
def home():
    return {"status": "running"}