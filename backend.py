"""
============================================
SHOPNEXUS E-COMMERCE BACKEND
============================================
Backend Python avec FastAPI + SQLite
Communication temps réel via WebSocket
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import sqlite3
import asyncio
from datetime import datetime
import uvicorn
import os

# ============================================
# CONFIGURATION
# ============================================
DATABASE = "ecommerce.db"

# ============================================
# DATA MODELS (Pydantic)
# ============================================
class Product(BaseModel):
    id: Optional[int] = None
    name: str
    description: str
    price: float
    stock: int
    emoji: str

class OrderItem(BaseModel):
    productId: int
    quantity: int
    price: float

class Order(BaseModel):
    id: Optional[int] = None
    items: List[OrderItem]
    total: float
    customer: Optional[str] = "Client"
    status: str = "pending"
    created_at: Optional[str] = None

# ============================================
# DATABASE INITIALIZATION
# ============================================
def init_database():
    """Initialise la base de données SQLite"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Table Products
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            emoji TEXT
        )
    """)
    
    # Table Orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    # Table Order Items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)
    
    # Check if products exist, if not add sample data
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ("MacBook Pro", "Ordinateur portable haute performance", 2499.99, 15, "💻"),
            ("iPhone 15 Pro", "Smartphone dernière génération", 1299.99, 30, "📱"),
            ("AirPods Pro", "Écouteurs sans fil avec réduction de bruit", 279.99, 50, "🎧"),
            ("Apple Watch", "Montre connectée élégante", 449.99, 25, "⌚"),
            ("iPad Air", "Tablette puissante et polyvalente", 699.99, 20, "📱"),
            ("Magic Mouse", "Souris sans fil design", 89.99, 40, "🖱️"),
            ("HomePod", "Enceinte intelligente", 349.99, 18, "🔊"),
            ("AirTag", "Traceur Bluetooth compact", 29.99, 100, "📍"),
        ]
        
        cursor.executemany("""
            INSERT INTO products (name, description, price, stock, emoji)
            VALUES (?, ?, ?, ?, ?)
        """, sample_products)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

# ============================================
# DATABASE OPERATIONS
# ============================================
class Database:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def get_all_products():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        products = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return products
    
    @staticmethod
    def get_product(product_id: int):
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        conn.close()
        return dict(product) if product else None
    
    @staticmethod
    def update_stock(product_id: int, quantity: int):
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE products 
            SET stock = stock - ? 
            WHERE id = ? AND stock >= ?
        """, (quantity, product_id, quantity))
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    
    @staticmethod
    def create_order(order: Order):
        conn = Database.get_connection()
        cursor = conn.cursor()
        
        # Create order
        cursor.execute("""
            INSERT INTO orders (customer, total, status, created_at)
            VALUES (?, ?, ?, ?)
        """, (order.customer, order.total, order.status, datetime.now().isoformat()))
        
        order_id = cursor.lastrowid
        
        # Add order items
        for item in order.items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (order_id, item.productId, item.quantity, item.price))
            
            # Update stock
            Database.update_stock(item.productId, item.quantity)
        
        conn.commit()
        conn.close()
        return order_id
    
    @staticmethod
    def get_all_orders():
        conn = Database.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
        orders = []
        
        for order_row in cursor.fetchall():
            order = dict(order_row)
            
            # Get order items
            cursor.execute("""
                SELECT oi.*, p.name, p.emoji
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = ?
            """, (order['id'],))
            
            order['items'] = [dict(row) for row in cursor.fetchall()]
            orders.append(order)
        
        conn.close()
        return orders

# ============================================
# FASTAPI APP
# ============================================
app = FastAPI(title="ShopNexus API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# WEBHOOK MANAGER (WebSocket connections)
# ============================================
class WebhookManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ Client connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"⚠️ Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, event: str, payload: Any):
        """Broadcast event to all connected clients"""
        message = json.dumps({"event": event, "payload": payload})
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"❌ Error sending to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)
    
    async def send_to_client(self, websocket: WebSocket, event: str, payload: Any):
        """Send event to specific client"""
        message = json.dumps({"event": event, "payload": payload})
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"❌ Error sending to specific client: {e}")

webhook_manager = WebhookManager()

# ============================================
# WEBSOCKET ENDPOINT
# ============================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await webhook_manager.connect(websocket)
    
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            event = message.get("event")
            payload = message.get("payload", {})
            
            print(f"📨 Received event: {event}")
            
            # Handle different events
            if event == "client.connected":
                # Send current products to newly connected client
                products = Database.get_all_products()
                await webhook_manager.send_to_client(
                    websocket, 
                    "products.updated", 
                    products
                )
            
            elif event == "order.placed":
                # Broadcast to all clients that a new order was placed
                await webhook_manager.broadcast("order.created", payload)
    
    except WebSocketDisconnect:
        webhook_manager.disconnect(websocket)
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        webhook_manager.disconnect(websocket)

# ============================================
# REST API ENDPOINTS
# ============================================

@app.get("/")
async def serve_frontend():
    """Sert le frontend (index.html)"""
    return FileResponse("index.html")

@app.get("/api")
async def root():
    return {"message": "ShopNexus API is running", "version": "1.0.0"}

@app.get("/api/products")
async def get_products():
    """Get all products"""
    try:
        products = Database.get_all_products()
        return {"success": True, "products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/{product_id}")
async def get_product(product_id: int):
    """Get single product"""
    try:
        product = Database.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"success": True, "product": product}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/orders")
async def create_order(order: Order):
    """Create new order"""
    try:
        # Validate stock availability
        for item in order.items:
            product = Database.get_product(item.productId)
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.productId} not found")
            if product['stock'] < item.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {product['name']}")
        
        # Create order
        order_id = Database.create_order(order)
        order.id = order_id
        order.created_at = datetime.now().isoformat()
        
        # Broadcast stock update
        products = Database.get_all_products()
        await webhook_manager.broadcast("products.updated", products)
        
        # Broadcast new order
        await webhook_manager.broadcast("order.created", order.dict())
        
        return {
            "success": True,
            "order_id": order_id,
            "message": "Order created successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders")
async def get_orders():
    """Get all orders"""
    try:
        orders = Database.get_all_orders()
        return {"success": True, "orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    """Get single order"""
    try:
        orders = Database.get_all_orders()
        order = next((o for o in orders if o['id'] == order_id), None)
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return {"success": True, "order": order}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/orders/{order_id}/status")
async def update_order_status(order_id: int, status: str):
    """Update order status"""
    try:
        conn = Database.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE orders 
            SET status = ? 
            WHERE id = ?
        """, (status, order_id))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        
        conn.commit()
        conn.close()
        
        # Broadcast status update
        await webhook_manager.broadcast("order.status_updated", {
            "order_id": order_id,
            "status": status
        })
        
        return {"success": True, "message": "Order status updated"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STARTUP / SHUTDOWN EVENTS
# ============================================
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting ShopNexus Backend...")
    init_database()
    print("✅ Backend ready!")
    print("📡 WebSocket available at: ws://localhost:8000/ws")
    print("🌐 API available at: http://localhost:8000")

@app.on_event("shutdown")
async def shutdown_event():
    print("👋 Shutting down ShopNexus Backend...")

# ============================================
# MAIN ENTRY POINT
# ============================================
if __name__ == "__main__":
    print("""
    ============================================
    🛍️  SHOPNEXUS E-COMMERCE BACKEND
    ============================================
    Architecture: 3 fichiers seulement!
    - index.html (Frontend)
    - backend.py (ce fichier)
    - webhook.py (communication layer)
    
    Starting server...
    ============================================
    """)
    
    uvicorn.run(
        "backend:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )