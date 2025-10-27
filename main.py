import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Checkin, Order, Bill

app = FastAPI(title="Hotel Frontdesk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "hotel-frontdesk-api"}


# -----------------------------
# Check-ins
# -----------------------------

@app.get("/api/checkins")
def list_checkins():
    docs = get_documents("checkin", {})
    # normalize id
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"items": docs}


@app.post("/api/checkins")
def create_checkin(payload: Checkin):
    data = payload.model_dump()
    if not data.get("createdAt"):
        data["createdAt"] = datetime.now(timezone.utc)
    # Ensure status default
    data["status"] = data.get("status") or "Occupied"

    # Prevent duplicate active check-in for same room
    existing = db["checkin"].find_one({"room": data["room"], "status": "Occupied"})
    if existing:
        raise HTTPException(status_code=400, detail="Room is already occupied")

    new_id = create_document("checkin", data)
    return {"id": new_id, "ok": True}


# -----------------------------
# Orders
# -----------------------------

@app.get("/api/orders")
def list_orders():
    docs = get_documents("order", {})
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"items": docs}


@app.post("/api/orders")
def create_order(payload: Order):
    data = payload.model_dump()
    if not data.get("createdAt"):
        data["createdAt"] = datetime.now(timezone.utc)
    # Auto-compute total if items provided
    if data.get("items"):
        data["total"] = sum((it.get("qty", 0) * it.get("price", 0)) for it in data["items"]) or data.get("total", 0)
    new_id = create_document("order", data)
    return {"id": new_id, "ok": True}


# -----------------------------
# Bills
# -----------------------------

@app.get("/api/bills")
def list_bills():
    docs = get_documents("bill", {})
    for d in docs:
        d["_id"] = str(d.get("_id"))
    return {"items": docs}


class PayRequest(BaseModel):
    mode: str


@app.post("/api/bills/{bill_id}/pay")
def mark_bill_paid(bill_id: str, payload: PayRequest):
    res = db["bill"].update_one({"id": bill_id}, {"$set": {"status": "Paid", "mode": payload.mode, "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bill not found")
    return {"ok": True}


# -----------------------------
# Checkout flow -> Create Bill and free room
# -----------------------------

class CheckoutRequest(BaseModel):
    room: str
    phone: str


@app.post("/api/checkout")
def create_final_bill(req: CheckoutRequest):
    # Fetch active check-in
    c = db["checkin"].find_one({"room": req.room, "phone": req.phone, "status": "Occupied"})
    if not c:
        raise HTTPException(status_code=404, detail="Active check-in not found")

    # Nights calculation
    created_at = c.get("createdAt") or c.get("created_at")
    try:
        start_dt = created_at if isinstance(created_at, datetime) else datetime.fromisoformat(str(created_at))
    except Exception:
        start_dt = datetime.now(timezone.utc)
    nights = max(1, int(((datetime.now(timezone.utc) - start_dt).total_seconds()) // 86400) + 1)

    rate = float(c.get("rate", 0))
    room_charges = nights * rate

    # Unpaid in-house orders for this room
    orders_cursor = db["order"].find({"type": "inhouse", "room": req.room, "status": "Unpaid"})
    orders = list(orders_cursor)
    food_total = float(sum(o.get("total", 0) for o in orders))

    tax_rate = 0.12
    subtotal = room_charges + food_total
    tax = round(subtotal * tax_rate)
    grand = subtotal + tax - float(c.get("advance", 0))

    bill = Bill(
        id="BILL-" + os.urandom(4).hex().upper(),
        guest=c.get("name"),
        phone=c.get("phone"),
        room=c.get("room"),
        nights=nights,
        roomCharges=room_charges,
        foodTotal=food_total,
        advance=float(c.get("advance", 0)),
        tax=float(tax),
        total=float(grand),
        status="Unpaid",
        mode="Cash",
        createdAt=datetime.now(timezone.utc),
    )

    create_document("bill", bill)

    # Mark orders as synced
    db["order"].update_many({"_id": {"$in": [o["_id"] for o in orders]}}, {"$set": {"synced": True, "updated_at": datetime.now(timezone.utc)}})

    # Free the room (check-out)
    db["checkin"].update_one({"_id": c["_id"]}, {"$set": {"status": "Checked-out", "updated_at": datetime.now(timezone.utc)}})

    return {"ok": True, "bill_id": bill.id}


# -----------------------------
# Health and DB test
# -----------------------------

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
