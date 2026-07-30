import os
import json
import math
import traceback
import asyncio
from datetime import datetime

import httpx

REGIONS = json.loads(os.getenv("REGIONS", '[{"name":"Sesimbra","lat":38.4435,"lon":-9.1015,"radius_km":80,"color":"#ef4444"},{"name":"Setubal","lat":38.5244,"lon":-8.8882,"radius_km":60,"color":"#3b82f6"},{"name":"Lisboa","lat":38.7223,"lon":-9.1393,"radius_km":70,"color":"#22c55e"}]'))

# Cache para dados de aeronaves e aeroportos
_aircraft_cache = {}
_airport_cache = {}
_weather_cache = {}

# Dados de aeronaves comuns (fallback)
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

# Aeroportos da região (fallback)
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

async def fetch_weather(lat, lon):
    """Buscar dados meteorológicos do Open-Meteo (gratuito)"""
    cache_key = f"{lat:.1f},{lon:.1f}"
    if cache_key in _weather_cache:
        age = (datetime.utcnow() - _weather_cache[cache_key]["timestamp"]).total_seconds()
        if age < 600:  # Cache 10 minutos
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
    """Buscar informações da aeronave (gratuito via OpenSky)"""
    if icao24 in _aircraft_cache:
        age = (datetime.utcnow() - _aircraft_cache[icao24]["timestamp"]).total_seconds()
        if age < 86400:  # Cache 24h
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
    """Obter especificações da aeronave da base de dados local"""
    if not typecode:
        return None
    typecode_upper = typecode.upper()
    # Procurar match parcial
    for key, specs in AIRCRAFT_DB.items():
        if key in typecode_upper or typecode_upper in key:
            return specs
    return None

def get_nearest_airport(lat, lon):
    """Encontrar o aeroporto mais próximo"""
    nearest = None
    min_dist = float('inf')
    for code, airport in AIRPORTS.items():
        dist = haversine(lat, lon, airport["lat"], airport["lon"])
        if dist < min_dist:
            min_dist = dist
            nearest = {**airport, "distance_km": round(dist, 1)}
    return nearest

def estimate_route(flight, nearest_airport):
    """Estimar origem/destino com base na posição e rumo"""
    if not flight or not nearest_airport:
        return {"origin": "Desconhecido", "destination": "Desconhecido", "progress": 0}

    heading = flight.get("heading", 0) or 0

    # Aeroportos prováveis de origem/destino na região
    candidates = []
    for code, airport in AIRPORTS.items():
        if code == nearest_airport["icao"]:
            continue
        dist = haversine(flight["latitude"], flight["longitude"], airport["lat"], airport["lon"])
        candidates.append({**airport, "distance_km": dist})

    candidates.sort(key=lambda x: x["distance_km"])

    # Estimar origem (aeroporto atrás) e destino (aeroporto à frente)
    origin = nearest_airport if nearest_airport["distance_km"] < 50 else (candidates[0] if candidates else None)
    destination = candidates[0] if candidates else origin

    # Calcular progresso aproximado
    if origin and destination:
        total_dist = haversine(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
        current_dist_from_origin = haversine(flight["latitude"], flight["longitude"], origin["lat"], origin["lon"])
        progress = min(95, max(5, round((current_dist_from_origin / total_dist) * 100))) if total_dist > 0 else 50
    else:
        progress = 50

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
    """Estimar número Mach (simplificado)"""
    if not velocity_ms:
        return None
    # Velocidade do som aproximada em m/s a diferentes altitudes
    # A 30000ft (~9144m): ~295 m/s
    # A 35000ft (~10668m): ~295 m/s
    # A 40000ft (~12192m): ~295 m/s
    speed_of_sound = 295  # m/s a altitude de cruzeiro
    mach = velocity_ms / speed_of_sound
    return round(mach, 2)

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
        print("📊 Usando dados de demonstração...")
        demo_flights = [
            {"icao24": "ABC123", "callsign": "TAP1923", "origin_country": "Portugal", "latitude": 38.72, "longitude": -9.14, "altitude": 15000, "altitude_gps": 15100, "velocity": 220, "heading": 45, "vertical_rate": 1500, "region": "Lisboa", "distance_from_center": 0.3, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "1234", "on_ground": False, "position_source": 0},
            {"icao24": "DEF456", "callsign": "RYR5678", "origin_country": "Ireland", "latitude": 38.52, "longitude": -8.89, "altitude": 28000, "altitude_gps": 28100, "velocity": 230, "heading": 120, "vertical_rate": 0, "region": "Setubal", "distance_from_center": 0.5, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "5678", "on_ground": False, "position_source": 0},
            {"icao24": "GHI789", "callsign": "EZY9012", "origin_country": "United Kingdom", "latitude": 38.44, "longitude": -9.10, "altitude": 32000, "altitude_gps": 32100, "velocity": 210, "heading": 200, "vertical_rate": -500, "region": "Sesimbra", "distance_from_center": 0.4, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "9012", "on_ground": False, "position_source": 0},
            {"icao24": "JKL012", "callsign": "BAW3456", "origin_country": "United Kingdom", "latitude": 38.65, "longitude": -9.25, "altitude": 12000, "altitude_gps": 12100, "velocity": 180, "heading": 315, "vertical_rate": -2000, "region": "Lisboa", "distance_from_center": 14.5, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "3456", "on_ground": False, "position_source": 0},
            {"icao24": "MNO345", "callsign": "AFR7890", "origin_country": "France", "latitude": 38.40, "longitude": -8.95, "altitude": 35000, "altitude_gps": 35100, "velocity": 240, "heading": 90, "vertical_rate": 0, "region": "Setubal", "distance_from_center": 16.6, "last_contact": int(datetime.utcnow().timestamp()), "squawk": "7890", "on_ground": False, "position_source": 0},
        ]
        for f in demo_flights:
            f["last_seen"] = datetime.utcnow()
            # Adicionar dados enriquecidos
            f["weather"] = {"temperature": 22, "wind_speed": 15, "wind_direction": 270, "pressure": 1013}
            f["aircraft_info"] = {"typecode": "A320", "registration": "CS-T" + f["icao24"][-2:], "manufacturer_icao": "AIRBUS", "model": "A320-214"}
            f["aircraft_specs"] = AIRCRAFT_DB.get("A320")
            f["nearest_airport"] = get_nearest_airport(f["latitude"], f["longitude"])
            f["route"] = estimate_route(f, f["nearest_airport"])
            f["mach"] = calculate_mach(f["velocity"], f["altitude"])
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

            # Enriquecer com dados adicionais
            parsed["nearest_airport"] = get_nearest_airport(parsed["latitude"], parsed["longitude"])
            parsed["route"] = estimate_route(parsed, parsed["nearest_airport"])
            parsed["mach"] = calculate_mach(parsed.get("velocity"), parsed.get("altitude"))

            # Tentar buscar info da aeronave (não bloqueante)
            try:
                aircraft_info = await fetch_aircraft_info(parsed["icao24"])
                if aircraft_info:
                    parsed["aircraft_info"] = aircraft_info
                    parsed["aircraft_specs"] = get_aircraft_specs(aircraft_info.get("typecode"))
            except:
                pass

            # Tentar buscar weather (não bloqueante)
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
