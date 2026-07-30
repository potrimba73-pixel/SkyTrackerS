import os
import json
import math
import traceback
import asyncio
from datetime import datetime

import httpx

REGIONS = json.loads(os.getenv("REGIONS", '[{"name":"Sesimbra","lat":38.4435,"lon":-9.1015,"radius_km":80,"color":"#ef4444"},{"name":"Setubal","lat":38.5244,"lon":-8.8882,"radius_km":60,"color":"#3b82f6"},{"name":"Lisboa","lat":38.7223,"lon":-9.1393,"radius_km":70,"color":"#22c55e"}]'))

# Cache
_aircraft_cache = {}
_airport_cache = {}
_weather_cache = {}

# Dados de aeronaves
AIRCRAFT_DB = {
    "A320": {"type": "Airbus A320", "manufacturer": "Airbus", "engine": "CFM56/IAE V2500", "wingspan": 35.8, "length": 37.6, "max_speed": 871, "ceiling": 39000, "passengers": 180},
    "A321": {"type": "Airbus A321", "manufacturer": "Airbus", "engine": "CFM56/IAE V2500", "wingspan": 35.8, "length": 44.5, "max_speed": 871, "ceiling": 39000, "passengers": 220},
    "A319": {"type": "Airbus A319", "manufacturer": "Airbus", "engine": "CFM56/IAE V2500", "wingspan": 34.1, "length": 33.8, "max_speed": 871, "ceiling": 39000, "passengers": 160},
    "A330": {"type": "Airbus A330", "manufacturer": "Airbus", "engine": "GE CF6/RR Trent", "wingspan": 60.3, "length": 58.8, "max_speed": 871, "ceiling": 41000, "passengers": 277},
    "A350": {"type": "Airbus A350", "manufacturer": "Airbus", "engine": "RR Trent XWB", "wingspan": 64.8, "length": 66.8, "max_speed": 903, "ceiling": 43000, "passengers": 325},
    "A380": {"type": "Airbus A380", "manufacturer": "Airbus", "engine": "RR Trent/EA GP7200", "wingspan": 79.8, "length": 72.7, "max_speed": 903, "ceiling": 43000, "passengers": 525},
    "B737": {"type": "Boeing 737", "manufacturer": "Boeing", "engine": "CFM56", "wingspan": 35.8, "length": 39.5, "max_speed": 876, "ceiling": 41000, "passengers": 189},
    "B738": {"type": "Boeing 737-800", "manufacturer": "Boeing", "engine": "CFM56-7B", "wingspan": 35.8, "length": 39.5, "max_speed": 876, "ceiling": 41000, "passengers": 189},
    "B739": {"type": "Boeing 737-900", "manufacturer": "Boeing", "engine": "CFM56-7B", "wingspan": 35.8, "length": 42.1, "max_speed": 876, "ceiling": 41000, "passengers": 220},
    "B747": {"type": "Boeing 747", "manufacturer": "Boeing", "engine": "GE CF6/RR Trent", "wingspan": 68.4, "length": 76.3, "max_speed": 917, "ceiling": 45000, "passengers": 416},
    "B777": {"type": "Boeing 777", "manufacturer": "Boeing", "engine": "GE90/RR Trent", "wingspan": 64.8, "length": 73.9, "max_speed": 892, "ceiling": 43100, "passengers": 396},
    "B787": {"type": "Boeing 787 Dreamliner", "manufacturer": "Boeing", "engine": "GEnx/RR Trent", "wingspan": 60.1, "length": 56.7, "max_speed": 903, "ceiling": 43100, "passengers": 296},
    "E190": {"type": "Embraer E190", "manufacturer": "Embraer", "engine": "GE CF34", "wingspan": 28.7, "length": 36.2, "max_speed": 871, "ceiling": 41000, "passengers": 114},
    "E195": {"type": "Embraer E195", "manufacturer": "Embraer", "engine": "GE CF34", "wingspan": 28.7, "length": 38.7, "max_speed": 871, "ceiling": 41000, "passengers": 124},
    "CRJ9": {"type": "Bombardier CRJ900", "manufacturer": "Bombardier", "engine": "GE CF34", "wingspan": 24.9, "length": 36.4, "max_speed": 830, "ceiling": 41000, "passengers": 90},
    "AT76": {"type": "ATR 72-600", "manufacturer": "ATR", "engine": "PW127", "wingspan": 27.1, "length": 27.2, "max_speed": 509, "ceiling": 25000, "passengers": 78},
}

# Aeroportos
AIRPORTS = {
    "LPPT": {"icao": "LPPT", "iata": "LIS", "name": "Aeroporto Humberto Delgado", "city": "Lisboa", "country": "Portugal", "lat": 38.7813, "lon": -9.1359, "elevation": 374},
    "LPFR": {"icao": "LPFR", "iata": "FAO", "name": "Aeroporto de Faro", "city": "Faro", "country": "Portugal", "lat": 37.0144, "lon": -7.9659, "elevation": 24},
    "LPPR": {"icao": "LPPR", "iata": "OPO", "name": "Aeroporto Francisco Sá Carneiro", "city": "Porto", "country": "Portugal", "lat": 41.2481, "lon": -8.6814, "elevation": 228},
    "LPCS": {"icao": "LPCS", "iata": "CAT", "name": "Aeródromo de Cascais", "city": "Cascais", "country": "Portugal", "lat": 38.7250, "lon": -9.3553, "elevation": 99},
    "LPEV": {"icao": "LPEV", "iata": "", "name": "Aeródromo de Évora", "city": "Évora", "country": "Portugal", "lat": 38.5333, "lon": -7.9000, "elevation": 240},
    "LEMD": {"icao": "LEMD", "iata": "MAD", "name": "Aeroporto Adolfo Suárez Madrid-Barajas", "city": "Madrid", "country": "Espanha", "lat": 40.4719, "lon": -3.5626, "elevation": 1998},
    "LEBL": {"icao": "LEBL", "iata": "BCN", "name": "Aeroporto Josep Tarradellas Barcelona-El Prat", "city": "Barcelona", "country": "Espanha", "lat": 41.2971, "lon": 2.0785, "elevation": 12},
    "LFPG": {"icao": "LFPG", "iata": "CDG", "name": "Aeroporto Charles de Gaulle", "city": "Paris", "country": "França", "lat": 49.0097, "lon": 2.5479, "elevation": 392},
    "EGLL": {"icao": "EGLL", "iata": "LHR", "name": "Aeroporto Heathrow", "city": "Londres", "country": "Reino Unido", "lat": 51.4700, "lon": -0.4543, "elevation": 83},
    "EHAM": {"icao": "EHAM", "iata": "AMS", "name": "Aeroporto Schiphol", "city": "Amesterdão", "country": "Países Baixos", "lat": 52.3105, "lon": 4.7683, "elevation": -11},
    "EDDF": {"icao": "EDDF", "iata": "FRA", "name": "Aeroporto de Frankfurt", "city": "Frankfurt", "country": "Alemanha", "lat": 50.0379, "lon": 8.5622, "elevation": 364},
    "LSZH": {"icao": "LSZH", "iata": "ZRH", "name": "Aeroporto de Zurique", "city": "Zurique", "country": "Suíça", "lat": 47.4647, "lon": 8.5492, "elevation": 1416},
    "LEZL": {"icao": "LEZL", "iata": "SVQ", "name": "Aeroporto de Sevilha", "city": "Sevilha", "country": "Espanha", "lat": 37.4180, "lon": -5.8931, "elevation": 111},
    "LPBJ": {"icao": "LPBJ", "iata": "BYJ", "name": "Aeroporto de Beja", "city": "Beja", "country": "Portugal", "lat": 38.0789, "lon": -7.9322, "elevation": 630},
    "LPLA": {"icao": "LPLA", "iata": "TER", "name": "Aeroporto das Lajes", "city": "Angra do Heroísmo", "country": "Portugal", "lat": 38.7618, "lon": -27.0908, "elevation": 180},
}

# Demo flights com trajetos realistas (aviões a voar, não parados)
# Cada voo tem: posição inicial, velocidade, rumo, altitude
_DEMO_FLIGHTS_BASE = [
    {"icao24": "495299", "callsign": "TAP1923", "origin_country": "Portugal", "typecode": "A320", "registration": "CS-TNV",
     "lat": 38.72, "lon": -9.14, "alt": 15000, "vel": 220, "hdg": 45, "vsi": 1500,
     "region": "Lisboa", "dist": 0.3, "squawk": "1234", "origin": "LPPT", "dest": "LEMD"},

    {"icao24": "4CA9C1", "callsign": "RYR5678", "origin_country": "Ireland", "typecode": "B738", "registration": "EI-DWJ",
     "lat": 38.52, "lon": -8.89, "alt": 28000, "vel": 230, "hdg": 120, "vsi": 0,
     "region": "Setubal", "dist": 0.5, "squawk": "5678", "origin": "EGLL", "dest": "LPFR"},

    {"icao24": "40643A", "callsign": "EZY9012", "origin_country": "United Kingdom", "typecode": "A319", "registration": "G-EZDA",
     "lat": 38.44, "lon": -9.10, "alt": 32000, "vel": 210, "hdg": 200, "vsi": -500,
     "region": "Sesimbra", "dist": 0.4, "squawk": "9012", "origin": "EHAM", "dest": "LPPT"},

    {"icao24": "4008B4", "callsign": "BAW3456", "origin_country": "United Kingdom", "typecode": "A320", "registration": "G-EUUY",
     "lat": 38.65, "lon": -9.25, "alt": 12000, "vel": 180, "hdg": 315, "vsi": -2000,
     "region": "Lisboa", "dist": 14.5, "squawk": "3456", "origin": "LEBL", "dest": "LPPT"},

    {"icao24": "39E68B", "callsign": "AFR7890", "origin_country": "France", "typecode": "A321", "registration": "F-GTAZ",
     "lat": 38.40, "lon": -8.95, "alt": 35000, "vel": 240, "hdg": 90, "vsi": 0,
     "region": "Setubal", "dist": 16.6, "squawk": "7890", "origin": "LFPG", "dest": "LPFR"},

    {"icao24": "3C66AC", "callsign": "DLH1234", "origin_country": "Germany", "typecode": "A320", "registration": "D-AIZW",
     "lat": 38.60, "lon": -9.00, "alt": 30000, "vel": 225, "hdg": 270, "vsi": 0,
     "region": "Setubal", "dist": 8.2, "squawk": "2345", "origin": "EDDF", "dest": "LPPT"},

    {"icao24": "3453D1", "callsign": "IBE4567", "origin_country": "Spain", "typecode": "A320", "registration": "EC-ILR",
     "lat": 38.35, "lon": -8.80, "alt": 25000, "vel": 200, "hdg": 340, "vsi": -1000,
     "region": "Sesimbra", "dist": 22.1, "squawk": "4567", "origin": "LEMD", "dest": "LPPT"},

    {"icao24": "484F6D", "callsign": "KLM8910", "origin_country": "Netherlands", "typecode": "B738", "registration": "PH-BXZ",
     "lat": 38.80, "lon": -9.30, "alt": 18000, "vel": 210, "hdg": 180, "vsi": -1500,
     "region": "Lisboa", "dist": 35.4, "squawk": "8910", "origin": "EHAM", "dest": "LPPT"},
]

# Estado atual dos voos demo (para movimento contínuo)
_demo_flight_state = {}

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
            print(f"⏱️ ConnectTimeout (tentativa {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except httpx.ReadTimeout:
            print(f"⏱️ ReadTimeout (tentativa {attempt+1}/{max_retries})")
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
            print(f"🌐 OpenSky: {len(states)} estados")
            return states
        except Exception as e:
            print(f"⚠️ Erro ao parsear OpenSky: {e}")
    return []

async def fetch_adsbexchange():
    try:
        url = "https://api.adsbexchange.com/v2/lat/38.52/lon/-8.89/dist/100/"
        response = await fetch_with_retry(url, timeout=15.0, max_retries=2)
        if response and response.status_code == 200:
            data = response.json()
            ac = data.get("ac", [])
            print(f"📡 ADS-B Exchange: {len(ac)} aeronaves")
            states = []
            for a in ac:
                states.append([
                    a.get("hex", ""),
                    a.get("flight", "").strip(),
                    a.get("country", ""),
                    None, None,
                    a.get("lon"),
                    a.get("lat"),
                    a.get("alt_baro", 0) == 0,
                    a.get("gs", 0) * 0.514444,
                    a.get("track", 0),
                    a.get("baro_rate", 0),
                    None, None,
                    a.get("alt_baro", 0),
                    a.get("squawk", ""),
                    None, None
                ])
            return states
    except Exception as e:
        print(f"⚠️ ADS-B Exchange erro: {e}")
    return []

async def fetch_flightradar24():
    """Tentar FlightRadar24 via proxy CORS (funciona no Render)"""
    try:
        # Usar um proxy CORS público para aceder ao FlightRadar24
        proxies = [
            "https://api.allorigins.win/raw?url=https://data-live.flightradar24.com/zones/fcgi/feed.js?bounds=38.3,38.9,-9.5,-8.5",
            "https://corsproxy.io/?https://data-live.flightradar24.com/zones/fcgi/feed.js?bounds=38.3,38.9,-9.5,-8.5",
        ]
        for proxy_url in proxies:
            response = await fetch_with_retry(proxy_url, timeout=15.0, max_retries=1)
            if response and response.status_code == 200:
                data = response.json()
                # FlightRadar24 retorna um dict com icao24 como keys
                states = []
                for icao, info in data.items():
                    if not isinstance(info, list) or len(info) < 16:
                        continue
                    states.append([
                        icao,                    # icao24
                        info[16] if len(info) > 16 else "",  # callsign
                        info[12] if len(info) > 12 else "",  # origin_country
                        None, None,
                        info[1] if len(info) > 1 else None,  # longitude
                        info[2] if len(info) > 2 else None,  # latitude
                        info[14] if len(info) > 14 else False,  # on_ground
                        info[5] if len(info) > 5 else 0,     # velocity
                        info[3] if len(info) > 3 else 0,     # heading
                        info[15] if len(info) > 15 else 0,   # vertical_rate
                        None, None,
                        info[4] if len(info) > 4 else 0,     # altitude
                        info[6] if len(info) > 6 else "",    # squawk
                        None, None
                    ])
                print(f"📡 FlightRadar24: {len(states)} aeronaves")
                return states
    except Exception as e:
        print(f"⚠️ FlightRadar24 erro: {e}")
    return []

async def fetch_weather(lat, lon):
    cache_key = f"{lat:.1f},{lon:.1f}"
    if cache_key in _weather_cache:
        age = (datetime.utcnow() - _weather_cache[cache_key]["timestamp"]).total_seconds()
        if age < 600:
            return _weather_cache[cache_key]["data"]

    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m&timezone=auto"
        response = await fetch_with_retry(url, timeout=10.0, max_retries=2)
        if response and response.status_code == 200:
            data = response.json()
            current = data.get("current", {})
            weather = {
                "temperature": current.get("temperature_2m"),
                "humidity": current.get("relative_humidity_2m"),
                "pressure": current.get("pressure_msl"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_direction": current.get("wind_direction_10m"),
                "wind_gusts": current.get("wind_gusts_10m"),
                "unit_temp": data.get("current_units", {}).get("temperature_2m", "°C"),
                "unit_wind": data.get("current_units", {}).get("wind_speed_10m", "km/h"),
                "unit_pressure": data.get("current_units", {}).get("pressure_msl", "hPa"),
            }
            _weather_cache[cache_key] = {"data": weather, "timestamp": datetime.utcnow()}
            return weather
    except Exception as e:
        print(f"⚠️ Erro weather: {e}")
    return None

async def fetch_aircraft_info(icao24):
    if icao24 in _aircraft_cache:
        age = (datetime.utcnow() - _aircraft_cache[icao24]["timestamp"]).total_seconds()
        if age < 86400:
            return _aircraft_cache[icao24]["data"]

    try:
        url = f"https://opensky-network.org/api/metadata/aircraft/icao/{icao24.lower()}"
        response = await fetch_with_retry(url, timeout=10.0, max_retries=2)
        if response and response.status_code == 200:
            data = response.json()
            info = {
                "registration": data.get("registration", "N/A"),
                "manufacturer_icao": data.get("manufacturerIcao", "N/A"),
                "model": data.get("model", "N/A"),
                "typecode": data.get("typecode", "N/A"),
                "serial_number": data.get("serialNumber", "N/A"),
                "line_number": data.get("lineNumber", "N/A"),
                "icao_aircraft_class": data.get("icaoAircraftClass", "N/A"),
                "operator": data.get("operator", "N/A"),
                "operator_icao": data.get("operatorIcao", "N/A"),
                "owner": data.get("owner", "N/A"),
                "category_description": data.get("categoryDescription", "N/A"),
            }
            _aircraft_cache[icao24] = {"data": info, "timestamp": datetime.utcnow()}
            return info
    except Exception as e:
        print(f"⚠️ Erro aircraft info: {e}")
    return None

def get_aircraft_specs(typecode):
    if not typecode:
        return None
    typecode_upper = typecode.upper()
    for key, specs in AIRCRAFT_DB.items():
        if key in typecode_upper or typecode_upper in key:
            return specs
    return None

def get_nearest_airport(lat, lon):
    nearest = None
    min_dist = float('inf')
    for code, airport in AIRPORTS.items():
        dist = haversine(lat, lon, airport["lat"], airport["lon"])
        if dist < min_dist:
            min_dist = dist
            nearest = {**airport, "distance_km": round(dist, 1)}
    return nearest

def estimate_route(flight, nearest_airport):
    if not flight or not nearest_airport:
        return {"origin": "Desconhecido", "destination": "Desconhecido", "progress": 0}

    heading = flight.get("heading", 0) or 0
    candidates = []
    for code, airport in AIRPORTS.items():
        if code == nearest_airport["icao"]:
            continue
        dist = haversine(flight["latitude"], flight["longitude"], airport["lat"], airport["lon"])
        candidates.append({**airport, "distance_km": dist})

    candidates.sort(key=lambda x: x["distance_km"])

    origin = nearest_airport if nearest_airport["distance_km"] < 50 else (candidates[0] if candidates else None)
    destination = candidates[0] if candidates else origin

    if origin and destination:
        total_dist = haversine(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
        current_dist_from_origin = haversine(flight["latitude"], flight["longitude"], origin["lat"], origin["lon"])
        progress = min(95, max(5, round((current_dist_from_origin / total_dist) * 100))) if total_dist > 0 else 50
    else:
        progress = 50
        total_dist = 0

    return {
        "origin": origin["name"] if origin else "Desconhecido",
        "origin_icao": origin["icao"] if origin else "",
        "origin_iata": origin.get("iata", "") if origin else "",
        "destination": destination["name"] if destination else "Desconhecido",
        "destination_icao": destination["icao"] if destination else "",
        "destination_iata": destination.get("iata", "") if destination else "",
        "progress": progress,
        "distance_total_km": round(total_dist, 1) if origin and destination else 0,
        "distance_remaining_km": round(haversine(flight["latitude"], flight["longitude"], destination["lat"], destination["lon"]), 1) if destination else 0,
    }

def calculate_mach(velocity_ms, altitude_m):
    if not velocity_ms:
        return None
    speed_of_sound = 295
    mach = velocity_ms / speed_of_sound
    return round(mach, 2)

def move_aircraft(lat, lon, hdg, vel_ms, seconds=30):
    """Mover aeronave com base no rumo e velocidade"""
    # vel_ms = m/s, seconds = tempo desde último update
    # Distância percorrida em km
    distance_km = (vel_ms * seconds) / 1000

    # Converter rumo para radianos (0° = Norte, 90° = Este)
    hdg_rad = math.radians(hdg)

    # 1 grau de latitude ≈ 111 km
    # 1 grau de longitude ≈ 111 km * cos(latitude)
    lat_change = distance_km * math.cos(hdg_rad) / 111.0
    lon_change = distance_km * math.sin(hdg_rad) / (111.0 * math.cos(math.radians(lat)))

    return lat + lat_change, lon + lon_change

def generate_demo_flights():
    """Gerar voos demo em movimento contínuo"""
    global _demo_flight_state

    now = datetime.utcnow()
    flights = []

    for base in _DEMO_FLIGHTS_BASE:
        icao = base["icao24"]

        # Inicializar estado se não existir
        if icao not in _demo_flight_state:
            _demo_flight_state[icao] = {
                "lat": base["lat"],
                "lon": base["lon"],
                "alt": base["alt"],
                "hdg": base["hdg"],
                "vel": base["vel"],
                "vsi": base["vsi"],
                "last_update": now,
            }

        state = _demo_flight_state[icao]

        # Calcular tempo desde último update
        elapsed = (now - state["last_update"]).total_seconds()
        state["last_update"] = now

        # Mover a aeronave
        new_lat, new_lon = move_aircraft(state["lat"], state["lon"], state["hdg"], state["vel"], elapsed)
        state["lat"] = new_lat
        state["lon"] = new_lon

        # Atualizar altitude
        state["alt"] += (state["vsi"] / 60) * elapsed  # ft/min -> ft/s
        state["alt"] = max(0, min(45000, state["alt"]))  # Limitar

        # Pequenas variações aleatórias no rumo (±2°) para parecer real
        import random
        state["hdg"] = (state["hdg"] + random.uniform(-2, 2)) % 360

        # Se sair muito longe da região, inverter rumo (voltar)
        center_lat, center_lon = 38.52, -8.89
        dist_from_center = haversine(new_lat, new_lon, center_lat, center_lon)
        if dist_from_center > 120:
            # Virar para o centro
            dx = center_lon - new_lon
            dy = center_lat - new_lat
            state["hdg"] = (math.degrees(math.atan2(dx, dy)) + 360) % 360

        # Criar o objeto flight
        flight = {
            "icao24": icao,
            "callsign": base["callsign"],
            "origin_country": base["origin_country"],
            "latitude": round(new_lat, 6),
            "longitude": round(new_lon, 6),
            "altitude": round(state["alt"]),
            "altitude_gps": round(state["alt"] + 50),
            "velocity": round(state["vel"]),
            "heading": round(state["hdg"]),
            "vertical_rate": round(state["vsi"]),
            "squawk": base["squawk"],
            "on_ground": False,
            "position_source": 0,
            "region": base["region"],
            "distance_from_center": round(dist_from_center, 1),
            "last_contact": int(now.timestamp()),
            "last_seen": now,
        }

        # Enriquecer
        flight["nearest_airport"] = get_nearest_airport(new_lat, new_lon)
        flight["route"] = estimate_route(flight, flight["nearest_airport"])
        flight["mach"] = calculate_mach(flight["velocity"], flight["altitude"])

        # Aircraft info
        ac_specs = get_aircraft_specs(base["typecode"])
        flight["aircraft_info"] = {
            "typecode": base["typecode"],
            "registration": base["registration"],
            "manufacturer_icao": ac_specs["manufacturer"].upper() if ac_specs else "N/A",
            "model": ac_specs["type"] if ac_specs else "N/A",
        }
        flight["aircraft_specs"] = ac_specs

        # Weather (estático para demo)
        flight["weather"] = {
            "temperature": 22,
            "humidity": 65,
            "pressure": 1013,
            "wind_speed": 15,
            "wind_direction": 270,
            "wind_gusts": 25,
        }

        flights.append(flight)

    return flights

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
        "altitude_gps": state[7],
        "on_ground": state[8],
        "velocity": state[9],
        "heading": state[10],
        "vertical_rate": state[11],
        "squawk": state[14],
        "spi": state[15],
        "position_source": state[16],
    }

def assign_region(lat, lon):
    for region in REGIONS:
        dist = haversine(lat, lon, region["lat"], region["lon"])
        if dist <= region["radius_km"]:
            return region["name"], dist
    return None, None

async def fetch_all_regions():
    states = await fetch_opensky()
    source = "opensky"

    if not states:
        print("🔄 Tentando ADS-B Exchange...")
        states = await fetch_adsbexchange()
        source = "adsbexchange"

    if not states:
        print("🔄 Tentando FlightRadar24...")
        states = await fetch_flightradar24()
        source = "flightradar24"

    if not states:
        print("📊 Usando dados de demonstração com movimento realista...")
        return generate_demo_flights()

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

            parsed["nearest_airport"] = get_nearest_airport(parsed["latitude"], parsed["longitude"])
            parsed["route"] = estimate_route(parsed, parsed["nearest_airport"])
            parsed["mach"] = calculate_mach(parsed.get("velocity"), parsed.get("altitude"))

            try:
                aircraft_info = await fetch_aircraft_info(parsed["icao24"])
                if aircraft_info:
                    parsed["aircraft_info"] = aircraft_info
                    parsed["aircraft_specs"] = get_aircraft_specs(aircraft_info.get("typecode"))
            except:
                pass

            try:
                weather = await fetch_weather(parsed["latitude"], parsed["longitude"])
                if weather:
                    parsed["weather"] = weather
            except:
                pass

            flights.append(parsed)
            print(f"📍 {parsed['callsign'] or parsed['icao24']} -> {region_name} ({dist:.1f}km)")

    print(f"✈️ Voos validos: {valid_count} (fonte: {source})")
    print(f"📍 Voos nas regioes: {len(flights)}/{len(states)}")
    return flights
