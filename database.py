import os
import json
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "skytracker")

_client = None
_db = None

async def init_db():
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URI)
    _db = _client[DB_NAME]
    print(f"✅ MongoDB conectado: {DB_NAME}")

async def get_db():
    if _db is None:
        await init_db()
    return _db

async def save_flight(flight):
    try:
        db = await get_db()
        flights_col = db["flights"]

        # Usar icao24 + timestamp como identificador único
        flight_doc = {
            "icao24": flight.get("icao24"),
            "callsign": flight.get("callsign"),
            "origin_country": flight.get("origin_country"),
            "latitude": flight.get("latitude"),
            "longitude": flight.get("longitude"),
            "altitude": flight.get("altitude"),
            "altitude_gps": flight.get("altitude_gps"),
            "velocity": flight.get("velocity"),
            "heading": flight.get("heading"),
            "vertical_rate": flight.get("vertical_rate"),
            "squawk": flight.get("squawk"),
            "on_ground": flight.get("on_ground"),
            "region": flight.get("region"),
            "distance_from_center": flight.get("distance_from_center"),
            "nearest_airport": flight.get("nearest_airport"),
            "route": flight.get("route"),
            "aircraft_info": flight.get("aircraft_info"),
            "aircraft_specs": flight.get("aircraft_specs"),
            "weather": flight.get("weather"),
            "mach": flight.get("mach"),
            "last_seen": flight.get("last_seen", datetime.utcnow()),
            "timestamp": datetime.utcnow(),
        }

        # Upsert baseado no icao24 e hora atual (janela de 5 min)
        time_window = datetime.utcnow() - timedelta(minutes=5)
        result = await flights_col.update_one(
            {"icao24": flight_doc["icao24"], "timestamp": {"$gte": time_window}},
            {"$set": flight_doc},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ Erro ao guardar voo: {e}")
        return False

async def get_active_flights(minutes=5):
    try:
        db = await get_db()
        flights_col = db["flights"]
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        cursor = flights_col.find({"timestamp": {"$gte": cutoff}}).sort("timestamp", -1)
        flights = []
        async for doc in cursor:
            doc.pop("_id", None)
            for key, value in list(doc.items()):
                if isinstance(value, datetime):
                    doc[key] = value.isoformat()
            flights.append(doc)
        return flights
    except Exception as e:
        print(f"❌ Erro ao buscar voos ativos: {e}")
        return []

async def get_stats(hours=24):
    try:
        db = await get_db()
        flights_col = db["flights"]
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        # Total de voos
        total = await flights_col.count_documents({"timestamp": {"$gte": cutoff}})

        # Voos ativos (últimos 5 min)
        active_cutoff = datetime.utcnow() - timedelta(minutes=5)
        active = await flights_col.count_documents({"timestamp": {"$gte": active_cutoff}})

        # Países únicos
        countries = await flights_col.distinct("origin_country", {"timestamp": {"$gte": cutoff}})

        # Altitude máxima
        max_alt_doc = await flights_col.find_one(
            {"timestamp": {"$gte": cutoff}, "altitude": {"$gt": 0}},
            sort=[("altitude", -1)]
        )
        max_altitude = max_alt_doc["altitude"] if max_alt_doc else 0

        # Detecções por hora
        hourly = []
        for h in range(hours):
            h_start = datetime.utcnow() - timedelta(hours=h+1)
            h_end = datetime.utcnow() - timedelta(hours=h)
            count = await flights_col.count_documents({"timestamp": {"$gte": h_start, "$lt": h_end}})
            hourly.append({"hour": (datetime.utcnow() - timedelta(hours=h)).hour, "count": count})
        hourly.reverse()

        # Top países
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$origin_country", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        countries_data = []
        async for doc in flights_col.aggregate(pipeline):
            countries_data.append({"country": doc["_id"] or "Desconhecido", "count": doc["count"]})

        # Distribuição de altitude
        alt_ranges = [
            {"range": "0-5000 ft", "min": 0, "max": 5000},
            {"range": "5000-15000 ft", "min": 5000, "max": 15000},
            {"range": "15000-25000 ft", "min": 15000, "max": 25000},
            {"range": "25000-35000 ft", "min": 25000, "max": 35000},
            {"range": "35000+ ft", "min": 35000, "max": 999999},
        ]
        altitude_distribution = []
        for r in alt_ranges:
            count = await flights_col.count_documents({
                "timestamp": {"$gte": cutoff},
                "altitude": {"$gte": r["min"], "$lt": r["max"]}
            })
            altitude_distribution.append({"range": r["range"], "count": count})

        return {
            "total_flights": total,
            "active_flights": active,
            "unique_countries": len(countries),
            "max_altitude": max_altitude,
            "hourly": hourly,
            "countries": countries_data,
            "altitude_distribution": altitude_distribution,
        }
    except Exception as e:
        print(f"❌ Erro ao buscar stats: {e}")
        return {}

async def cleanup_old(days=7):
    try:
        db = await get_db()
        flights_col = db["flights"]
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await flights_col.delete_many({"timestamp": {"$lt": cutoff}})
        print(f"🧹 Limpo {result.deleted_count} voos antigos")
    except Exception as e:
        print(f"❌ Erro ao limpar dados antigos: {e}")
