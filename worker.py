import os
import asyncio
import traceback
from datetime import datetime, timedelta

from database import save_flight, cleanup_old, get_db
from opensky_client import fetch_all_regions

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
CLEANUP_DAYS = int(os.getenv("CLEANUP_DAYS", "7"))
ALERT_AIRCRAFT = [a.strip().upper() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]
ALERT_COOLDOWN = {}

_running = False
_broadcast_callback = None

async def check_alerts(flights):
    if not ALERT_AIRCRAFT:
        return

    try:
        db = await get_db()
        alerts_col = db["alerts"]
        now = datetime.utcnow()

        for flight in flights:
            cs = (flight.get("callsign") or "").upper()
            icao = flight.get("icao24", "").upper()

            for alert in ALERT_AIRCRAFT:
                if alert in cs or alert in icao:
                    key = f"{alert}_{flight.get('region', 'unknown')}"
                    last_alert = ALERT_COOLDOWN.get(key)
                    if last_alert and (now - last_alert) < timedelta(minutes=30):
                        continue

                    ALERT_COOLDOWN[key] = now
                    alert_doc = {
                        "callsign": flight.get("callsign", "N/A"),
                        "icao24": icao,
                        "region": flight.get("region", "N/A"),
                        "distance_km": flight.get("distance_from_center"),
                        "altitude": flight.get("altitude"),
                        "timestamp": now
                    }
                    await alerts_col.insert_one(alert_doc)
                    print(f"🔔 ALERTA: {flight.get('callsign', 'N/A')} detetado em {flight.get('region', 'N/A')}!")
    except Exception as e:
        print(f"Erro alerts: {e}")
        traceback.print_exc()

async def worker_loop():
    global _running
    _running = True
    cleanup_counter = 0

    print(f"⏱️ Intervalo: {POLL_INTERVAL}s")

    while _running:
        try:
            print(f"🔄 Polling OpenSky... {datetime.utcnow().strftime('%H:%M:%S')} UTC")
            flights = await fetch_all_regions()

            if flights:
                print(f"💾 A guardar {len(flights)} voos na base de dados...")
                saved = 0
                for flight in flights:
                    if await save_flight(flight):
                        saved += 1
                print(f"✅ {saved}/{len(flights)} voos guardados com sucesso")

                # Verificar alertas
                await check_alerts(flights)
            else:
                print("⚠️ Nenhum voo detetado neste poll")

            # Cleanup a cada 10 polls (~5 min)
            cleanup_counter += 1
            if cleanup_counter >= 10:
                await cleanup_old(CLEANUP_DAYS)
                cleanup_counter = 0

            # Broadcast via WebSocket
            if _broadcast_callback:
                try:
                    await _broadcast_callback()
                except Exception as e:
                    print(f"Erro broadcast: {e}")

            print(f"✅ {len(flights)} voos detetados nas regioes configuradas")

        except Exception as e:
            print(f"❌ Erro no worker: {e}")
            traceback.print_exc()

        await asyncio.sleep(POLL_INTERVAL)

async def start_worker(broadcast_callback=None):
    global _broadcast_callback
    _broadcast_callback = broadcast_callback
    await worker_loop()

def stop_worker():
    global _running
    _running = False
