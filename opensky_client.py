import httpx
import math
import os
import json
from typing import List, Dict, Optional, Any

OPENSKY_URL = "https://opensky-network.org/api/states/all"

# Carrega regioes da env var ou usa defaults
REGIONS_JSON = os.getenv("REGIONS", """
[
  {"name": "Sesimbra", "lat": 38.4435, "lon": -9.1015, "radius_km": 80, "color": "#ef4444"},
  {"name": "Setubal", "lat": 38.5244, "lon": -8.8882, "radius_km": 60, "color": "#3b82f6"},
  {"name": "Lisboa", "lat": 38.7223, "lon": -9.1393, "radius_km": 70, "color": "#22c55e"}
]
""")

def get_regions() -> List[Dict[str, Any]]:
    """Retorna lista de regioes configuradas"""
    try:
        return json.loads(REGIONS_JSON)
    except:
        return [
            {"name": "Sesimbra", "lat": 38.4435, "lon": -9.1015, "radius_km": 80, "color": "#ef4444"},
            {"name": "Setubal", "lat": 38.5244, "lon": -8.8882, "radius_km": 60, "color": "#3b82f6"},
            {"name": "Lisboa", "lat": 38.7223, "lon": -9.1393, "radius_km": 70, "color": "#22c55e"}
        ]

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia em km entre dois pontos"""
    R = 6371  # Raio da Terra em km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_bounding_box(lat: float, lon: float, radius_km: float) -> tuple:
    """Calcula bounding box para uma regiao"""
    # Aproximacao: 1 grau = ~111km
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))

    return (
        lat - delta_lat,   # lamin
        lat + delta_lat,   # lamax
        lon - delta_lon,   # lomin
        lon + delta_lon    # lomax
    )

async def fetch_opensky_data(lamin: float, lamax: float, lomin: float, lomax: float) -> List[Dict]:
    """Busca dados da OpenSky para uma bounding box"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                OPENSKY_URL,
                params={
                    "lamin": lamin,
                    "lamax": lamax,
                    "lomin": lomin,
                    "lomax": lomax
                }
            )
            response.raise_for_status()
            data = response.json()

            states = data.get("states", [])
            if not states:
                return []

            # OpenSky retorna array de arrays, converter para dicts
            # [icao24, callsign, origin_country, time_position, last_contact,
            #  longitude, latitude, baro_altitude, on_ground, velocity,
            #  true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source]

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
                    "velocity": (state[9] or 0) * 3.6,  # m/s -> km/h
                    "heading": state[10] or 0,
                    "vertical_rate": state[11] or 0,
                    "geo_altitude": state[14] or 0,
                    "squawk": state[14] or "",
                }
                flights.append(flight)

            return flights

        except httpx.HTTPStatusError as e:
            print(f"⚠️ OpenSky HTTP erro: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"⚠️ OpenSky erro: {e}")
            return []

async def fetch_all_regions() -> List[Dict]:
    """Busca dados para todas as regioes configuradas"""
    regions = get_regions()
    all_flights = []

    # Calcula bounding box combinada para todas as regioes
    # (mais eficiente que fazer multiplas chamadas)
    all_lats = [r["lat"] for r in regions]
    all_lons = [r["lon"] for r in regions]
    max_radius = max(r["radius_km"] for r in regions)

    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)

    lamin, lamax, lomin, lomax = get_bounding_box(center_lat, center_lon, max_radius + 50)

    flights = await fetch_opensky_data(lamin, lamax, lomin, lomax)

    # Atribui cada voo a sua regiao mais proxima
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

    return all_flights
