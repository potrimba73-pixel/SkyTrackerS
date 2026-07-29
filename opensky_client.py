import httpx
import math
import os
import json
from typing import List, Dict, Optional, Any

OPENSKY_URL = "https://opensky-network.org/api/states/all"

REGIONS_JSON = os.getenv("REGIONS", """
[
  {"name": "Sesimbra", "lat": 38.4435, "lon": -9.1015, "radius_km": 80, "color": "#ef4444"},
  {"name": "Setubal", "lat": 38.5244, "lon": -8.8882, "radius_km": 60, "color": "#3b82f6"},
  {"name": "Lisboa", "lat": 38.7223, "lon": -9.1393, "radius_km": 70, "color": "#22c55e"}
]
""")

def get_regions() -> List[Dict[str, Any]]:
    try:
        return json.loads(REGIONS_JSON)
    except:
        return [
            {"name": "Sesimbra", "lat": 38.4435, "lon": -9.1015, "radius_km": 80, "color": "#ef4444"},
            {"name": "Setubal", "lat": 38.5244, "lon": -8.8882, "radius_km": 60, "color": "#3b82f6"},
            {"name": "Lisboa", "lat": 38.7223, "lon": -9.1393, "radius_km": 70, "color": "#22c55e"}
        ]

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_bounding_box(lat: float, lon: float, radius_km: float) -> tuple:
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon)

# Dados de demonstracao para quando a OpenSky nao responde
DEMO_FLIGHTS = [
    {"icao24": "abc123", "callsign": "TAP1234", "origin_country": "Portugal", "latitude": 38.72, "longitude": -9.14, "altitude": 15000, "velocity": 750, "heading": 45, "on_ground": False, "vertical_rate": 0, "geo_altitude": 15000, "squawk": "1234"},
    {"icao24": "def456", "callsign": "RYR5678", "origin_country": "Ireland", "latitude": 38.52, "longitude": -8.89, "altitude": 28000, "velocity": 820, "heading": 120, "on_ground": False, "vertical_rate": 50, "geo_altitude": 28000, "squawk": "5678"},
    {"icao24": "ghi789", "callsign": "EZY9012", "origin_country": "United Kingdom", "latitude": 38.44, "longitude": -9.10, "altitude": 32000, "velocity": 780, "heading": 270, "on_ground": False, "vertical_rate": -20, "geo_altitude": 32000, "squawk": "9012"},
    {"icao24": "jkl012", "callsign": "BAW3456", "origin_country": "United Kingdom", "latitude": 38.65, "longitude": -9.00, "altitude": 12000, "velocity": 650, "heading": 180, "on_ground": False, "vertical_rate": 100, "geo_altitude": 12000, "squawk": "3456"},
    {"icao24": "mno345", "callsign": "AFR7890", "origin_country": "France", "latitude": 38.50, "longitude": -8.70, "altitude": 35000, "velocity": 850, "heading": 90, "on_ground": False, "vertical_rate": 0, "geo_altitude": 35000, "squawk": "7890"},
]

async def fetch_opensky_data(lamin: float, lamax: float, lomin: float, lomax: float) -> List[Dict]:
    async with httpx.AsyncClient(timeout=60.0) as client:  # Aumentado para 60s
        try:
            print(f"🌐 OpenSky: lat[{lamin:.3f}, {lamax:.3f}], lon[{lomin:.3f}, {lomax:.3f}]")
            response = await client.get(
                OPENSKY_URL,
                params={"lamin": lamin, "lamax": lamax, "lomin": lomin, "lomax": lomax}
            )
            print(f"📡 Status: {response.status_code}")

            if response.status_code != 200:
                print(f"⚠️ OpenSky erro HTTP {response.status_code}: {response.text[:200]}")
                return []

            data = response.json()
            states = data.get("states", [])
            print(f"📊 Estados brutos: {len(states)}")

            if not states:
                print("ℹ️ OpenSky: nenhum estado retornado")
                return []

            flights = []
            for state in states:
                if state[5] is None or state[6] is None:
                    continue

                flight = {
                    "icao24": state[0] or "N/A",
                    "callsign": (state[1] or "").strip(),
                    "origin_country": state[2] or "Desconhecido",
                    "time_position": state[3],
                    "last_contact": state[4],
                    "longitude": state[5],
                    "latitude": state[6],
                    "altitude": state[7] or 0,
                    "on_ground": state[8] or False,
                    "velocity": (state[9] or 0) * 3.6,
                    "heading": state[10] or 0,
                    "vertical_rate": state[11] or 0,
                    "geo_altitude": state[14] or 0,
                    "squawk": state[14] or "",
                }
                flights.append(flight)

            print(f"✈️ Voos validos: {len(flights)}")
            return flights

        except httpx.TimeoutException:
            print(f"⏱️ OpenSky timeout (60s) - usando dados de demonstracao")
            return []
        except httpx.HTTPStatusError as e:
            print(f"⚠️ OpenSky HTTP erro: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"⚠️ OpenSky erro: {type(e).__name__}: {e}")
            return []

async def fetch_all_regions() -> List[Dict]:
    regions = get_regions()
    all_flights = []

    center_lat = 39.5
    center_lon = -8.0
    max_radius = 300

    lamin, lamax, lomin, lomax = get_bounding_box(center_lat, center_lon, max_radius)

    flights = await fetch_opensky_data(lamin, lamax, lomin, lomax)

    # Se OpenSky falhar, usar dados de demonstracao
    if not flights:
        print("🎮 Usando dados de demonstracao")
        flights = DEMO_FLIGHTS.copy()

    for flight in flights:
        lat, lon = flight["latitude"], flight["longitude"]

        closest_region = None
        min_distance = float('inf')

        for region in regions:
            dist = haversine(lat, lon, region["lat"], region["lon"])
            if dist <= region["radius_km"] and dist < min_distance:
                min_distance = dist
                closest_region = region

        if closest_region:
            flight["region"] = closest_region["name"]
            flight["region_color"] = closest_region["color"]
            flight["distance_km"] = round(min_distance, 2)
            all_flights.append(flight)
            print(f"   📍 {flight['callsign'] or flight['icao24']} -> {closest_region['name']} ({min_distance:.1f}km)")

    print(f"📍 Voos nas regioes: {len(all_flights)}/{len(flights)}")
    return all_flights
