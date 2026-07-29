import asyncio
import os
import traceback
from datetime import datetime, timedelta
from opensky_client import fetch_all_regions, get_regions
from database import (
    save_flight, save_snapshot, save_alert, check_recent_alert,
    cleanup_old_data, get_active_flights
)
from email_service import send_alert_email

ALERT_AIRCRAFT = [a.strip().upper() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
CLEANUP_DAYS = int(os.getenv("CLEANUP_DAYS", "7"))

class SkyTrackerWorker:
    def __init__(self):
        self.running = False
        self.last_cleanup = datetime.utcnow()
        self.stats = {
            "total_polls": 0,
            "total_flights_detected": 0,
            "last_poll_time": None,
            "last_poll_count": 0
        }

    async def process_flights(self, flights: list):
        alert_aircraft_upper = [a.upper() for a in ALERT_AIRCRAFT]

        for flight in flights:
            await save_flight(flight)

            snapshot = {
                "icao24": flight["icao24"],
                "callsign": flight["callsign"],
                "origin_country": flight["origin_country"],
                "latitude": flight["latitude"],
                "longitude": flight["longitude"],
                "altitude": flight["altitude"],
                "velocity": flight["velocity"],
                "heading": flight["heading"],
                "region": flight.get("region", "Desconhecido"),
                "distance_km": flight.get("distance_km", 0),
                "timestamp": datetime.utcnow()
            }
            await save_snapshot(snapshot)

            callsign = flight.get("callsign", "").strip().upper()
            icao24 = flight.get("icao24", "").strip().upper()

            if callsign and (callsign in alert_aircraft_upper or icao24 in alert_aircraft_upper):
                if not await check_recent_alert(flight["icao24"], minutes=30):
                    alert_data = {
                        "icao24": flight["icao24"],
                        "callsign": flight["callsign"],
                        "origin_country": flight["origin_country"],
                        "latitude": flight["latitude"],
                        "longitude": flight["longitude"],
                        "altitude": flight["altitude"],
                        "velocity": flight["velocity"],
                        "distance_km": flight.get("distance_km", 0),
                        "region": flight.get("region", "Desconhecido")
                    }
                    await save_alert(alert_data)
                    await send_alert_email(flight, flight.get("region", "Sesimbra"))
                    print(f"🔔 ALERTA: {flight['callsign']} ({flight['icao24']}) detetado em {flight.get('region', 'N/A')}!")

    async def run_poll(self):
        try:
            print(f"🔄 Polling OpenSky... {datetime.utcnow().strftime('%H:%M:%S')} UTC")

            flights = await fetch_all_regions()

            self.stats["total_polls"] += 1
            self.stats["total_flights_detected"] += len(flights)
            self.stats["last_poll_time"] = datetime.utcnow().isoformat()
            self.stats["last_poll_count"] = len(flights)

            print(f"✅ {len(flights)} voos detetados nas regioes configuradas")

            if flights:
                await self.process_flights(flights)

        except Exception as e:
            print(f"❌ Erro no polling: {e}")
            traceback.print_exc()

    async def run_cleanup(self):
        try:
            result = await cleanup_old_data(days=CLEANUP_DAYS)
            print(f"🧹 Limpeza automatica: {result}")
        except Exception as e:
            print(f"❌ Erro na limpeza: {e}")

    async def start(self):
        self.running = True
        print("🚀 SkyTracker Worker iniciado!")
        print(f"📍 Regioes: {[r['name'] for r in get_regions()]}")
        print(f"🔔 Alertas: {ALERT_AIRCRAFT if ALERT_AIRCRAFT else 'Nenhum configurado'}")
        print(f"⏱️ Intervalo: {POLL_INTERVAL}s")

        while self.running:
            await self.run_poll()

            if datetime.utcnow() - self.last_cleanup > timedelta(hours=6):
                await self.run_cleanup()
                self.last_cleanup = datetime.utcnow()

            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        self.running = False
        print("🛑 Worker parado")

worker = SkyTrackerWorker()

async def start_worker():
    await worker.start()
