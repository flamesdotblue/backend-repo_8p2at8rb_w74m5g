from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Hotel Frontdesk Management Schemas

class Checkin(BaseModel):
    name: str
    phone: str
    idtype: Optional[str] = None
    id: Optional[str] = None
    address: Optional[str] = None
    room: str
    roomType: Optional[str] = None
    rate: float = 0
    adults: int = 1
    children: int = 0
    advance: float = 0
    mode: Optional[str] = "Cash"
    remarks: Optional[str] = None
    createdAt: Optional[datetime] = None
    status: str = Field("Occupied", description="Occupied or Checked-out")

class OrderItem(BaseModel):
    name: str
    qty: int
    price: float

class Order(BaseModel):
    # type: inhouse | outside
    type: str = Field("inhouse")
    room: Optional[str] = None
    name: Optional[str] = None
    phone: str
    items: List[OrderItem] = []
    total: float = 0
    status: str = Field("Unpaid")
    mode: str = Field("Cash")
    createdAt: Optional[datetime] = None
    synced: Optional[bool] = False

class Bill(BaseModel):
    id: str
    guest: str
    phone: str
    room: str
    nights: int
    roomCharges: float
    foodTotal: float
    advance: float = 0
    tax: float
    total: float
    status: str = Field("Unpaid")
    mode: str = Field("Cash")
    createdAt: Optional[datetime] = None
