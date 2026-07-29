import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/skytracker")

client = AsyncMongoClient(MONGODB_URI, server_api=ServerApi('1'))
from urllib.parse import urlparse
parsed = urlparse(MONGODB_URI)
db_name = parsed.path.lstrip('/').split('?')[0] or 'skytracker'
db = client[db_name]

flights_col = db.flights
history_col = db.history
alerts_col = db.alerts
stats_col = db.stats

async def init_db():
    await flights_col.create_index("icao24")
    await flights_col.create_index("last_contact", expireAfterSeconds=3600)
    await history_col.create_index("icao24")
    await history_col.create_index("timestamp")
    await alerts_col.create_index([("icao24", 1), ("alert_time", 1)])
    await stats_col.create_index("date")
    await stats_col.create_index("hour")
    print("✅ Base de dados inicializada")

async def save_flight(flight_data: dict):
    flight_data["updated_at"] = datetime.utcnow()
    await flights_col.update_one(
        {"icao24": flight_data["icao24"]},
        {"$set": flight_data, "$setOnInsert": {"first_seen": datetime.utcnow()}},
        upsert=True
    )

async def save_snapshot(snapshot: dict):
    await history_col.insert_one(snapshot)

async def save_alert(alert: dict):
    alert["alert_time"] = datetime.utcnow()
    alert["notified"] = False
    await alerts_col.insert_one(alert)

async def check_recent_alert(icao24: str, minutes: int = 30) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    count = await alerts_col.count_documents({"icao24": icao24, "alert_time": {"$gte": cutoff}})
    return count > 0

async def get_active_flights(region_filter: Optional[dict] = None) -> List[Dict]:
    query = {}
    if region_filter:
        query["region"] = region_filter.get("name")
    cursor = flights_col.find(query).sort("updated_at", -1)
    return await cursor.to_list(length=500)

async def get_flight_history(icao24: str, hours: int = 24) -> List[Dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cursor = history_col.find({"icao24": icao24, "timestamp": {"$gte": cutoff}}).sort("timestamp", 1)
    return await cursor.to_list(length=10000)

async def get_stats(hours: int = 24) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": None,
            "total_detections": {"$sum": 1},
            "unique_aircraft": {"$addToSet": "$icao24"},
            "unique_countries": {"$addToSet": "$origin_country"},
            "max_altitude": {"$max": "$altitude"},
            "avg_altitude": {"$avg": "$altitude"},
            "max_speed": {"$max": "$velocity"}
        }},
        {"$project": {
            "total_detections": 1,
            "unique_aircraft": {"$size": "$unique_aircraft"},
            "unique_countries": {"$size": "$unique_countries"},
            "max_altitude": {"$round": ["$max_altitude", 0]},
            "avg_altitude": {"$round": ["$avg_altitude", 0]},
            "max_speed": {"$round": ["$max_speed", 0]}
        }}
    ]
    # CORRECAO: await aggregate() primeiro, depois to_list()
    agg_cursor = await history_col.aggregate(pipeline)
    result = await agg_cursor.to_list(length=1)
    return result[0] if result else {
        "total_detections": 0, "unique_aircraft": 0, "unique_countries": 0,
        "max_altitude": 0, "avg_altitude": 0, "max_speed": 0
    }

async def get_hourly_stats(hours: int = 24) -> List[Dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": {"$hour": "$timestamp"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    agg_cursor = await history_col.aggregate(pipeline)
    return await agg_cursor.to_list(length=24)

async def get_country_stats(hours: int = 24) -> List[Dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}, "origin_country": {"$ne": None}}},
        {"$group": {"_id": "$origin_country", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    agg_cursor = await history_col.aggregate(pipeline)
    return await agg_cursor.to_list(length=10)

async def get_altitude_distribution(hours: int = 24) -> List[Dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}, "altitude": {"$gt": 0}}},
        {"$bucket": {
            "groupBy": "$altitude",
            "boundaries": [0, 1000, 5000, 10000, 20000, 30000, 40000, 50000],
            "default": "40k+",
            "output": {"count": {"$sum": 1}}
        }}
    ]
    agg_cursor = await history_col.aggregate(pipeline)
    return await agg_cursor.to_list(length=10)

async def get_pending_alerts() -> List[Dict]:
    cursor = alerts_col.find({"notified": False}).sort("alert_time", -1)
    return await cursor.to_list(length=100)

async def mark_alert_notified(alert_id: str):
    from bson import ObjectId
    await alerts_col.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"notified": True, "notified_at": datetime.utcnow()}}
    )

async def get_all_alerts(limit: int = 50) -> List[Dict]:
    cursor = alerts_col.find().sort("alert_time", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def cleanup_old_data(days: int = 7):
    cutoff = datetime.utcnow() - timedelta(days=days)
    result_history = await history_col.delete_many({"timestamp": {"$lt": cutoff}})
    result_alerts = await alerts_col.delete_many({"alert_time": {"$lt": cutoff}})
    print(f"🧹 Limpeza: {result_history.deleted_count} snapshots, {result_alerts.deleted_count} alertas antigos removidos")
    return {"history_deleted": result_history.deleted_count, "alerts_deleted": result_alerts.deleted_count}
