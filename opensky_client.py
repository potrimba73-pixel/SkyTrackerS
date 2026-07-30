import os
import json
import math
import traceback
import asyncio
from datetime import datetime

import httpx

REGIONS = json.loads(os.getenv("REGIONS", '[{"name":"Sesimbra","lat":38.4435,"lon":-9.1015,"radius_km":80,"color":"#ef4444"},{"name":"Setubal","lat":38.5244,"lon":-8.8882,"radius_km":60,"color":"#3b82f6"},{"name":"Lisboa","lat":38.7223,"lon":-9.1393,"radius_km":70,"color":"#22c55e"}]'))

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_bounding_box():
    lats = [r["lat"] for r in REGIONS]
    lons = [r["lon"] for r in REGIONS]
    max_radius = max(r["radius_km"] for r in REGIONS)
    lat_margin = max_radius / 111.0
    lon_margin = max_radius / (111.0 * math.cos(math.radians(sum(lats)/len(lats))))
    return {
        "lamin": min(lats) - lat_margin,
        "lamax": max(lats) + lat_margin,
        "lomin": min(lons) - lon_margin,
        "lomax": max(lons) + lon_margin
    }

async def fetch_with_retry(url, params=None, max_retries=3, timeout=30.0):
    """Faz fetch com retry e backoff exponencial"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    wait = 2 ** attempt
                    print(f"⏳ Rate limit, esperando {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    print(f"⚠️ HTTP {response.status_code} em {url}")
                    return None
        except httpx.ConnectTimeout:
            print(f"⏱️ Timeout (tentativa {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except httpx.ReadTimeout:
            print(f"⏱️ Read timeout (tentativa {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            print(f"⚠️ Erro: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
    return None

async def fetch_opensky():
    bbox = get_bounding_box()
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": bbox["lamin"],
        "lamax": bbox["lamax"],
        "lomin": bbox["lomin"],
        "lomax": bbox["lomax"]
    }

    response = await fetch_with_retry(url, params, max_retries=3, timeout=30.0)
    if response and response.status_code == 200:
        try:
            data = response.json()
            states = data.get("states", []) or []
            print(f"📡 OpenSky: {len(states)} estados")
            return states
        except Exception as e:
            print(f"⚠️ Erro ao parsear OpenSky: {e}")
    return []

async def fetch_adsbexchange():
    """Fallback gratuito: ADS-B Exchange (sem API key, dados limitados)"""
    try:
        # ADS-B Exchange API pública (limitada, mas gratuita)
        bbox = get_bounding_box()
        url = "https://api.adsbexchange.com/v2/lat/38.52/lon/-8.89/dist/100/"
        response = await fetch_with_retry(url, timeout=15.0, max_retries=2)
        if response and response.status_code == 200:
            data = response.json()
            ac = data.get("ac", [])
            print(f"📡 ADS-B Exchange: {len(ac)} aeronaves")
            # Converter formato para compatível com OpenSky
            states = []
            for a in ac:
                states.append([
                    a.get("hex", ""),           # icao24
                    a.get("flight", "").strip(), # callsign
                    a.get("country", ""),        # origin_country
                    None, None,                  # time_position, last_contact
                    a.get("lon"),                # longitude
                    a.get("lat"),                # latitude
                    a.get("alt_baro", 0) == 0,  # on_ground
                    a.get("gs", 0) * 0.514444,  # velocity (knots -> m/s)
                    a.get("track", 0),           # heading
                    a.get("baro_rate", 0),       # vertical_rate
                    None, None,                  # sensors, geoaltitude
                    a.get("alt_baro", 0),        # altitude
                    a.get("squawk", ""),         # squawk
                    None, None                   # spi, position_source
                ])
            return states
    except Exception as e:
        print(f"⚠️ ADS-B Exchange erro: {e}")
    return []

def parse_state(state):
    if not state or len(state) < 17:
        return None
    return {
        "icao24": str(state[0]).strip().upper() if state[0] else "",
        "callsign": str(state[1]).strip().upper() if state[1] else None,
        "origin_country": state[2],
        "time_position": state[3],
        "last_contact": state[4],
        "longitude": state[5],
        "latitude": state[6],
        "altitude": state[13] if state[13] else (state[7] if state[7] else 0),
        "on_ground": state[8],
        "velocity": state[9],
        "heading": state[10],
        "vertical_rate": state[11],
        "squawk": state[14],
    }

def assign_region(lat, lon):
    for region in REGIONS:
        dist = haversine(lat, lon, region["lat"], region["lon"])
        if dist <= region["radius_km"]:
            return region["name"], dist
    return None, None

async def fetch_all_regions():
    # Tentar OpenSky primeiro
    states = await fetch_opensky()
    source = "opensky"
    
    # Se falhar, tentar ADS-B Exchange
    if not states:
        print("🔄 Tentando ADS-B Exchange...")
        states = await fetch_adsbexchange()
        source = "adsbexchange"
    
    # Se ainda falhar, usar dados de demonstração
    if not states:
        print("📊 Usando dados de demonstração...")
        demo_flights = [
            {"icao24": "ABC123", "callsign": "TAP1923", "origin_country": "Portugal", "latitude": 38.72, "longitude": -9.14, "altitude": 15000, "velocity": 220, "heading": 45, "region": "Lisboa", "distance_from_center": 0.3, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "1234"},
            {"icao24": "DEF456", "callsign": "RYR5678", "origin_country": "Ireland", "latitude": 38.52, "longitude": -8.89, "altitude": 28000, "velocity": 230, "heading": 120, "region": "Setubal", "distance_from_center": 0.5, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "5678"},
            {"icao24": "GHI789", "callsign": "EZY9012", "origin_country": "United Kingdom", "latitude": 38.44, "longitude": -9.10, "altitude": 32000, "velocity": 210, "heading": 200, "region": "Sesimbra", "distance_from_center": 0.4, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "9012"},
            {"icao24": "JKL012", "callsign": "BAW3456", "origin_country": "United Kingdom", "latitude": 38.65, "longitude": -9.25, "altitude": 12000, "velocity": 180, "heading": 315, "region": "Lisboa", "distance_from_center": 14.5, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "3456"},
            {"icao24": "MNO345", "callsign": "AFR7890", "origin_country": "France", "latitude": 38.40, "longitude": -8.95, "altitude": 35000, "velocity": 240, "heading": 90, "region": "Setubal", "distance_from_center": 16.6, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "7890"},
        ]
        for f in demo_flights:
            f["last_seen"] = datetime.utcnow()
        return demo_flights

    flights = []
    valid_count = 0
    for state in states:
        parsed = parse_state(state)
        if not parsed or not parsed["latitude"] or not parsed["longitude"]:
            continue
        valid_count += 1
        region_name, dist = assign_region(parsed["latitude"], parsed["longitude"])
        if region_name:
            parsed["region"] = region_name
            parsed["distance_from_center"] = round(dist, 1)
            parsed["last_seen"] = datetime.utcnow()
            flights.append(parsed)
            print(f"📍 {parsed['callsign'] or parsed['icao24']} -> {region_name} ({dist:.1f}km)")

    print(f"✈️ Voos validos: {valid_count} (fonte: {source})")
    print(f"📍 Voos nas regioes: {len(flights)}/{len(states)}")
    return flights
