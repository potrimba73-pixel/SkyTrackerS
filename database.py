import os
import traceback
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import AsyncMongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "")

_db_client = None
_db = None

async def get_db_client():
    global _db_client
    if _db_client is None:
        _db_client = AsyncMongoClient(MONGODB_URI)
    return _db_client

async def get_db():
    global _db
    if _db is None:
        client = await get_db_client()
        _db = client.get_database("skytracker")
    return _db

async def init_db():
    db = await get_db()
    flights_col = db["flights"]
    history_col = db["history"]
    alerts_col = db["alerts"]
    await flights_col.create_index("icao24")
    await flights_col.create_index("last_seen")
    await history_col.create_index("timestamp")
    await history_col.create_index("icao24")
    await alerts_col.create_index("timestamp")
    print("✅ Base de dados inicializada")

def clean_doc(doc):
    if doc is None:
        return None
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    for key, value in result.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [str(v) if isinstance(v, ObjectId) else v for v in value]
    return result

async def save_flight(flight_data):
    try:
        db = await get_db()
        flights_col = db["flights"]
        history_col = db["history"]

        await flights_col.update_one(
            {"icao24": flight_data["icao24"]},
            {"$set": flight_data, "$setOnInsert": {"first_seen": datetime.utcnow()}},
            upsert=True
        )

        await history_col.insert_one({
            **flight_data,
            "timestamp": datetime.utcnow()
        })
        return True
    except Exception as e:
        print(f"Erro ao guardar voo: {e}")
        traceback.print_exc()
        return False

async def get_active_flights():
    try:
        db = await get_db()
        flights_col = db["flights"]
        cursor = flights_col.find({"last_seen": {"$gte": datetime.utcnow() - timedelta(minutes=5)}})
        flights = []
        async for doc in cursor:
            flights.append(clean_doc(doc))
        return flights
    except Exception as e:
        print(f"Erro ao obter voos ativos: {e}")
        traceback.print_exc()
        return []

async def get_stats(hours=24):
    try:
        db = await get_db()
        history_col = db["history"]
        flights_col = db["flights"]

        since = datetime.utcnow() - timedelta(hours=hours)

        # Total flights
        total = await history_col.count_documents({"timestamp": {"$gte": since}})

        # Active flights
        active = await flights_col.count_documents({"last_seen": {"$gte": datetime.utcnow() - timedelta(minutes=5)}})

        # Unique countries
        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {"_id": "$origin_country", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        agg_cursor = await history_col.aggregate(pipeline)
        countries = await agg_cursor.to_list(length=10)
        countries = [clean_doc(c) for c in countries]

        # Max altitude
        pipeline_max = [
            {"$match": {"timestamp": {"$gte": since}, "altitude": {"$exists": True}}},
            {"$group": {"_id": None, "max_alt": {"$max": "$altitude"}}}
        ]
        agg_cursor_max = await history_col.aggregate(pipeline_max)
        max_alt_result = await agg_cursor_max.to_list(length=1)
        max_altitude = max_alt_result[0]["max_alt"] if max_alt_result else 0

        # Hourly distribution
        pipeline_hourly = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {"_id": {"$hour": "$timestamp"}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        agg_cursor_hourly = await history_col.aggregate(pipeline_hourly)
        hourly_raw = await agg_cursor_hourly.to_list(length=24)
        hourly = [{"hour": str(h["_id"]).zfill(2), "count": h["count"]} for h in hourly_raw]

        # Altitude distribution
        alt_ranges = [
            {"range": "0-1k", "min": 0, "max": 1000},
            {"range": "1k-5k", "min": 1000, "max": 5000},
            {"range": "5k-10k", "min": 5000, "max": 10000},
            {"range": "10k-20k", "min": 10000, "max": 20000},
            {"range": "20k-30k", "min": 20000, "max": 30000},
            {"range": "30k-40k", "min": 30000, "max": 40000},
            {"range": "40k+", "min": 40000, "max": 999999},
        ]
        alt_distribution = []
        for r in alt_ranges:
            count = await history_col.count_documents({
                "timestamp": {"$gte": since},
                "altitude": {"$gte": r["min"], "$lt": r["max"]}
            })
            alt_distribution.append({"range": r["range"], "count": count})

        return {
            "total_flights": total,
            "active_flights": active,
            "unique_countries": len(countries),
            "max_altitude": max_altitude,
            "countries": countries,
            "hourly": hourly,
            "altitude_distribution": alt_distribution
        }
    except Exception as e:
        print(f"Erro stats: {e}")
        traceback.print_exc()
        return {}

async def cleanup_old(days=7):
    try:
        db = await get_db()
        history_col = db["history"]
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await history_col.delete_many({"timestamp": {"$lt": cutoff}})
        print(f"🧹 Limpos {result.deleted_count} registos antigos")
    except Exception as e:
        print(f"Erro cleanup: {e}")
