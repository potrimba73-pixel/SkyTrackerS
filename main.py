import os
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, get_db, get_active_flights, get_stats
from worker import start_worker, stop_worker

# Ler HTML do ficheiro
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as f:
    DASHBOARD_HTML = f.read()

# Service Worker
SW_JS = """self.addEventListener('install', e => {
    e.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', e => {
    e.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', e => {
    e.respondWith(fetch(e.request).catch(() => new Response('Offline')));
});"""

# Manifest
MANIFEST_JSON = """{
    "name": "SkyTracker - Sesimbra",
    "short_name": "SkyTracker",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0f172a",
    "theme_color": "#0f172a",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
    ]
}"""

# Config
REGIONS = json.loads(os.getenv("REGIONS", '[{"name":"Sesimbra","lat":38.4435,"lon":-9.1015,"radius_km":80,"color":"#ef4444"},{"name":"Setubal","lat":38.5244,"lon":-8.8882,"radius_km":60,"color":"#3b82f6"},{"name":"Lisboa","lat":38.7223,"lon":-9.1393,"radius_km":70,"color":"#22c55e"}]'))
ALERT_AIRCRAFT = [a.strip() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]

# WebSocket Manager
class WSManager:
    def __init__(self):
        self.connections = []
    async def connect(self, ws):
        self.connections.append(ws)
    async def disconnect(self, ws):
        if ws in self.connections:
            self.connections.remove(ws)
    async def broadcast(self, message):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

manager = WSManager()

async def broadcast_updates():
    try:
        db = await get_db()
        flights_col = db["flights"]
        cursor = flights_col.find({"last_seen": {"$gte": datetime.utcnow() - timedelta(minutes=5)}})
        flights = []
        async for doc in cursor:
            doc.pop("_id", None)
            flights.append(doc)

        message = json.dumps({"type": "update", "flights": flights, "timestamp": datetime.utcnow().isoformat()})
        await manager.broadcast(message)
    except Exception as e:
        print(f"Broadcast error: {e}")
        traceback.print_exc()

# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("✅ Base de dados inicializada")
    worker_task = asyncio.create_task(start_worker(broadcast_updates))
    print("🚀 SkyTracker Worker iniciado!")
    print(f"📍 Regioes: {[r['name'] for r in REGIONS]}")
    print(f"🔔 Alertas: {', '.join(ALERT_AIRCRAFT) if ALERT_AIRCRAFT else 'Nenhum configurado'}")
    yield
    stop_worker()
    worker_task.cancel()
    print("🛑 Worker parado")

app = FastAPI(title="SkyTracker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content=json.loads(MANIFEST_JSON))

@app.get("/service-worker.js")
async def service_worker():
    return HTMLResponse(content=SW_JS, media_type="application/javascript")

@app.get("/icon-192.png")
@app.get("/icon-512.png")
async def icon():
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    return HTMLResponse(content=png, media_type="image/png")

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/regions")
async def get_regions():
    return REGIONS

@app.get("/api/flights")
async def get_flights_api():
    try:
        flights = await get_active_flights()
        return {"flights": flights, "count": len(flights)}
    except Exception as e:
        return {"flights": [], "count": 0, "error": str(e)}

@app.get("/api/stats")
async def get_stats_api(hours: int = Query(24, ge=1, le=168)):
    try:
        stats = await get_stats(hours=hours)
        return {"stats": stats}
    except Exception as e:
        return {"stats": {}}

@app.get("/api/alerts")
async def get_alerts_api():
    try:
        db = await get_db()
        alerts_col = db["alerts"]
        cursor = alerts_col.find().sort("timestamp", -1).limit(50)
        alerts = []
        async for doc in cursor:
            doc.pop("_id", None)
            if "timestamp" in doc and hasattr(doc["timestamp"], "isoformat"):
                doc["timestamp"] = doc["timestamp"].isoformat()
            alerts.append(doc)
        return {"alerts": alerts}
    except Exception as e:
        return {"alerts": []}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket)
    try:
        flights = await get_active_flights()
        await websocket.send_text(json.dumps({"type": "init", "flights": flights}))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket erro: {e}")
        await manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
