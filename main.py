import os
import asyncio
import json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from database import (
    init_db, get_active_flights, get_stats, get_hourly_stats,
    get_country_stats, get_altitude_distribution, get_pending_alerts,
    get_all_alerts, mark_alert_notified, cleanup_old_data
)
from opensky_client import fetch_all_regions, get_regions
from worker import worker, start_worker

# ============ LIFESPAN ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Inicia worker em background
    worker_task = asyncio.create_task(start_worker())

    yield

    # Shutdown
    worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="SkyTracker 24/7", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ WEBSOCKET ============
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Broadcast periodicamente
async def broadcast_updates():
    """Envia atualizacoes para todos os clientes WebSocket"""
    while True:
        try:
            if manager.active_connections:
                flights = await get_active_flights()
                regions = get_regions()
                stats = await get_stats(hours=24)
                pending_alerts = await get_pending_alerts()

                await manager.broadcast({
                    "type": "update",
                    "flights": flights,
                    "regions": regions,
                    "stats": stats,
                    "pending_alerts": len(pending_alerts),
                    "timestamp": datetime.utcnow().isoformat()
                })
            await asyncio.sleep(10)
        except Exception as e:
            print(f"WebSocket broadcast erro: {e}")
            await asyncio.sleep(10)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Envia estado inicial
        flights = await get_active_flights()
        regions = get_regions()
        stats = await get_stats(hours=24)

        await websocket.send_json({
            "type": "init",
            "flights": flights,
            "regions": regions,
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        })

        while True:
            # Mantem conexao aberta, recebe pings do cliente
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket erro: {e}")
        manager.disconnect(websocket)

# ============ REST API ============
@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "worker": {
            "running": worker.running,
            "total_polls": worker.stats["total_polls"],
            "last_poll": worker.stats["last_poll_time"]
        }
    }

@app.get("/api/flights")
async def get_flights(region: str = Query(None, description="Filtrar por regiao")):
    """Retorna voos ativos"""
    region_filter = {"name": region} if region else None
    flights = await get_active_flights(region_filter)
    return {
        "flights": flights,
        "count": len(flights),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/flights/refresh")
async def refresh_flights():
    """Forca atualizacao manual dos dados"""
    flights = await fetch_all_regions()
    from worker import SkyTrackerWorker
    temp_worker = SkyTrackerWorker()
    await temp_worker.process_flights(flights)

    return {
        "flights": flights,
        "count": len(flights),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/regions")
async def get_regions_api():
    """Retorna regioes configuradas"""
    return {"regions": get_regions()}

@app.get("/api/stats")
async def get_stats_api(hours: int = Query(24, ge=1, le=168)):
    """Retorna estatisticas"""
    return {
        "stats": await get_stats(hours=hours),
        "hourly": await get_hourly_stats(hours=hours),
        "countries": await get_country_stats(hours=hours),
        "altitude": await get_altitude_distribution(hours=hours),
        "hours": hours
    }

@app.get("/api/alerts")
async def get_alerts(pending_only: bool = Query(False)):
    """Retorna alertas"""
    if pending_only:
        alerts = await get_pending_alerts()
    else:
        alerts = await get_all_alerts()
    return {"alerts": alerts, "count": len(alerts)}

@app.post("/api/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    """Marca alerta como notificado/lido"""
    await mark_alert_notified(alert_id)
    return {"status": "ok", "message": "Alerta marcado como lido"}

@app.post("/api/cleanup")
async def trigger_cleanup(days: int = Query(7, ge=1, le=30)):
    """Dispara limpeza manual"""
    result = await cleanup_old_data(days=days)
    return {"status": "ok", "result": result}

@app.get("/api/worker/stats")
async def get_worker_stats():
    """Retorna estatisticas do worker"""
    return {
        "running": worker.running,
        "stats": worker.stats,
        "regions": get_regions(),
        "alert_aircraft": [a.strip() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]
    }

# ============ STATIC FILES ============
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/manifest.json")
async def get_manifest():
    return {
        "name": "SkyTracker 24/7",
        "short_name": "SkyTracker",
        "description": "Rastreamento de avioes em tempo real - Sesimbra, Portugal",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#3b82f6",
        "orientation": "any",
        "icons": [
            {"src": "/static/icon-72.png", "sizes": "72x72", "type": "image/png"},
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }

@app.get("/service-worker.js", response_class=HTMLResponse)
async def get_service_worker():
    content = """
const CACHE_NAME = 'skytracker-v1';
const urlsToCache = [
    '/',
    '/static/index.html',
    '/manifest.json'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );
    self.skipWaiting();
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) return response;
                return fetch(event.request);
            })
    );
});

self.addEventListener('push', event => {
    const data = event.data.json();
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/icon-192.png',
            badge: '/static/icon-72.png',
            tag: data.tag || 'skytracker-alert',
            requireInteraction: true
        })
    );
});
"""
    return HTMLResponse(content=content, media_type="application/javascript")

# Inicia broadcast em background
@app.on_event("startup")
async def startup_broadcast():
    asyncio.create_task(broadcast_updates())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
