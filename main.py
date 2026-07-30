import os
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, get_db, get_active_flights, get_stats
from worker import start_worker, stop_worker

# HTML Dashboard inline
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SkyTracker - Sesimbra</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0f172a">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;overflow-x:hidden}
.header{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);padding:12px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;position:sticky;top:0;z-index:1000}
.header h1{font-size:1.4rem;color:#38bdf8;display:flex;align-items:center;gap:8px}
.header .status{display:flex;align-items:center;gap:15px;font-size:.85rem}
.status-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.alert-badge{background:#ef4444;color:white;padding:4px 10px;border-radius:12px;font-size:.75rem;font-weight:600;cursor:pointer;display:none}
.alert-badge.show{display:block}
.main-container{display:grid;grid-template-columns:1fr 380px;height:calc(100vh - 60px)}
@media(max-width:1024px){.main-container{grid-template-columns:1fr}}
#map{height:100%;width:100%}
.sidebar{background:#1e293b;border-left:1px solid #334155;display:flex;flex-direction:column;overflow:hidden}
.tabs{display:flex;background:#0f172a;border-bottom:1px solid #334155}
.tab{flex:1;padding:12px;text-align:center;cursor:pointer;font-size:.85rem;font-weight:500;transition:all .2s;border-bottom:2px solid transparent}
.tab:hover{background:#334155}
.tab.active{border-bottom-color:#38bdf8;color:#38bdf8;background:#1e293b}
.tab-content{flex:1;overflow-y:auto;padding:15px;display:none}
.tab-content.active{display:block}
.flight-card{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:12px;margin-bottom:10px;cursor:pointer;transition:all .2s}
.flight-card:hover{border-color:#38bdf8;transform:translateX(4px)}
.flight-card .airline{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.flight-card .airline-flag{font-size:1.2rem}
.flight-card .airline-name{font-size:.75rem;color:#94a3b8}
.flight-card .callsign{font-size:1.1rem;font-weight:700;color:#f8fafc}
.flight-card .details{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px;font-size:.8rem;color:#cbd5e1}
.flight-card .detail-item{display:flex;align-items:center;gap:5px}
.flight-card .detail-item i{color:#38bdf8;width:14px}
.flight-card .region-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:600;margin-top:6px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.stat-card{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:15px;text-align:center}
.stat-card .value{font-size:1.8rem;font-weight:700;color:#38bdf8}
.stat-card .label{font-size:.75rem;color:#94a3b8;margin-top:4px}
.chart-container{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:15px;margin-bottom:15px}
.chart-container h3{font-size:.9rem;margin-bottom:10px;color:#e2e8f0}
.alert-item{background:#0f172a;border-left:3px solid #ef4444;border-radius:0 8px 8px 0;padding:12px;margin-bottom:10px}
.alert-item .time{font-size:.7rem;color:#94a3b8}
.alert-item .message{font-size:.85rem;margin-top:4px}
.layer-control{position:absolute;top:70px;right:10px;z-index:1000;background:#1e293b;border:1px solid #334155;border-radius:8px;padding:8px;box-shadow:0 4px 12px rgba(0,0,0,.3)}
.layer-btn{display:block;width:100%;padding:8px 12px;margin-bottom:4px;background:transparent;border:1px solid #475569;border-radius:6px;color:#e2e8f0;cursor:pointer;font-size:.8rem;transition:all .2s}
.layer-btn:hover{background:#334155}
.layer-btn.active{background:#38bdf8;color:#0f172a;border-color:#38bdf8}
.loading{text-align:center;padding:40px;color:#94a3b8}
.loading i{font-size:2rem;animation:spin 1s linear infinite}
@keyframes spin{100%{transform:rotate(360deg)}}
.leaflet-popup-content-wrapper{background:#1e293b;color:#e2e8f0;border-radius:10px}
.leaflet-popup-tip{background:#1e293b}
.popup-content{min-width:240px}
.popup-content .popup-header{display:flex;align-items:center;gap:8px;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:8px}
.popup-content .popup-flag{font-size:1.5rem}
.popup-content .popup-callsign{font-size:1.2rem;font-weight:700}
.popup-content .popup-airline{font-size:.8rem;color:#94a3b8}
.popup-content .popup-details{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.8rem}
.popup-content .popup-detail{display:flex;align-items:center;gap:5px}
.popup-content .popup-detail i{color:#38bdf8;width:14px}
.popup-content .popup-route{margin-top:8px;padding-top:8px;border-top:1px solid #334155;font-size:.8rem;color:#94a3b8}
.popup-content .popup-route strong{color:#e2e8f0}
@media(max-width:768px){.main-container{grid-template-columns:1fr}.sidebar{height:50vh}.header h1{font-size:1.1rem}}
</style>
</head>
<body>
<div class="header">
<h1><i class="fas fa-plane"></i> SkyTracker <span style="color:#94a3b8;font-size:.9rem">Sesimbra 24/7</span></h1>
<div class="status">
<div style="display:flex;align-items:center;gap:6px"><div class="status-dot"></div><span id="conn-status">Online</span></div>
<span id="flight-count">0 voos</span>
<div class="alert-badge" id="alert-badge" onclick="showAlerts()"><i class="fas fa-bell"></i> <span id="alert-count">0</span></div>
</div>
</div>
<div class="main-container">
<div id="map"></div>
<div class="layer-control">
<button class="layer-btn active" onclick="setLayer('dark')">🌑 Escuro</button>
<button class="layer-btn" onclick="setLayer('satellite')">🛰️ Satélite</button>
<button class="layer-btn" onclick="setLayer('terrain')">⛰️ Terreno</button>
<button class="layer-btn" onclick="setLayer('standard')">🗺️ Padrão</button>
</div>
<div class="sidebar">
<div class="tabs">
<div class="tab active" onclick="switchTab('flights')"><i class="fas fa-plane"></i> Voos</div>
<div class="tab" onclick="switchTab('stats')"><i class="fas fa-chart-bar"></i> Stats</div>
<div class="tab" onclick="switchTab('alerts')"><i class="fas fa-bell"></i> Alertas</div>
</div>
<div class="tab-content active" id="tab-flights">
<div class="loading" id="flights-loading"><i class="fas fa-circle-notch"></i><p>A carregar voos...</p></div>
<div id="flights-list"></div>
</div>
<div class="tab-content" id="tab-stats">
<div class="stats-grid">
<div class="stat-card"><div class="value" id="stat-total">0</div><div class="label">Voos 24h</div></div>
<div class="stat-card"><div class="value" id="stat-active">0</div><div class="label">Ativos</div></div>
<div class="stat-card"><div class="value" id="stat-countries">0</div><div class="label">Países</div></div>
<div class="stat-card"><div class="value" id="stat-max-alt">0</div><div class="label">Alt. Max (ft)</div></div>
</div>
<div class="chart-container"><h3>📈 Detecoes por Hora</h3><canvas id="hourlyChart"></canvas></div>
<div class="chart-container"><h3>🌍 Top Paises</h3><canvas id="countriesChart"></canvas></div>
<div class="chart-container"><h3>📏 Distribuicao de Altitude</h3><canvas id="altitudeChart"></canvas></div>
</div>
<div class="tab-content" id="tab-alerts">
<div id="alerts-list"><p style="color:#94a3b8;text-align:center;padding:20px">Nenhum alerta configurado</p></div>
</div>
</div>
</div>
<script>
const AIRLINES={"TAP":{name:"TAP Air Portugal",country:"Portugal",flag:"🇵🇹"},"RYR":{name:"Ryanair",country:"Ireland",flag:"🇮🇪"},"EZY":{name:"easyJet",country:"UK",flag:"🇬🇧"},"BAW":{name:"British Airways",country:"UK",flag:"🇬🇧"},"AFR":{name:"Air France",country:"France",flag:"🇫🇷"},"DLH":{name:"Lufthansa",country:"Germany",flag:"🇩🇪"},"IBE":{name:"Iberia",country:"Spain",flag:"🇪🇸"},"VLG":{name:"Vueling",country:"Spain",flag:"🇪🇸"},"EIN":{name:"Aer Lingus",country:"Ireland",flag:"🇮🇪"},"SWR":{name:"Swiss",country:"Switzerland",flag:"🇨🇭"},"KLM":{name:"KLM",country:"Netherlands",flag:"🇳🇱"},"SAS":{name:"SAS",country:"Sweden",flag:"🇸🇪"},"NAX":{name:"Norwegian",country:"Norway",flag:"🇳🇴"},"WZZ":{name:"Wizz Air",country:"Hungary",flag:"🇭🇺"},"TRA":{name:"Transavia",country:"Netherlands",flag:"🇳🇱"},"EWG":{name:"Eurowings",country:"Germany",flag:"🇩🇪"},"TOM":{name:"TUI Airways",country:"UK",flag:"🇬🇧"},"FIN":{name:"Finnair",country:"Finland",flag:"🇫🇮"},"LOT":{name:"LOT Polish",country:"Poland",flag:"🇵🇱"},"AUA":{name:"Austrian",country:"Austria",flag:"🇦🇹"},"OS":{name:"Austrian",country:"Austria",flag:"🇦🇹"},"LX":{name:"Swiss",country:"Switzerland",flag:"🇨🇭"},"AF":{name:"Air France",country:"France",flag:"🇫🇷"},"KL":{name:"KLM",country:"Netherlands",flag:"🇳🇱"},"LH":{name:"Lufthansa",country:"Germany",flag:"🇩🇪"},"BA":{name:"British Airways",country:"UK",flag:"🇬🇧"},"IB":{name:"Iberia",country:"Spain",flag:"🇪🇸"},"VY":{name:"Vueling",country:"Spain",flag:"🇪🇸"},"FR":{name:"Ryanair",country:"Ireland",flag:"🇮🇪"},"U2":{name:"easyJet",country:"UK",flag:"🇬🇧"},"TP":{name:"TAP Air Portugal",country:"Portugal",flag:"🇵🇹"}};
function getAirlineInfo(callsign){if(!callsign)return{name:"Desconhecida",country:"Desconhecido",flag:"✈️"};const cs=callsign.toUpperCase();for(let prefix of Object.keys(AIRLINES).sort((a,b)=>b.length-a.length)){if(cs.startsWith(prefix))return AIRLINES[prefix]}return{name:"Desconhecida",country:"Desconhecido",flag:"✈️"}}
const map=L.map('map').setView([38.5244,-8.8882],9);
const layers={dark:L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; CARTO'}),satellite:L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'&copy; Esri'}),terrain:L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenTopoMap'}),standard:L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OSM'})};
layers.dark.addTo(map);
function setLayer(name){Object.values(layers).forEach(l=>map.removeLayer(l));layers[name].addTo(map);document.querySelectorAll('.layer-btn').forEach(b=>b.classList.remove('active'));event.target.classList.add('active')}
function createAircraftIcon(heading,color,callsign){const airline=getAirlineInfo(callsign);const svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="36" height="36"><g transform="rotate('+(heading||0)+',50,50)"><path d="M50 10 L20 50 L30 55 L50 45 L70 55 L80 50 Z" fill="'+color+'" stroke="white" stroke-width="1.5"/><ellipse cx="50" cy="50" rx="6" ry="35" fill="'+color+'" stroke="white" stroke-width="1.5"/><path d="M50 80 L35 95 L50 90 L65 95 Z" fill="'+color+'" stroke="white" stroke-width="1.5"/><ellipse cx="50" cy="22" rx="4" ry="6" fill="#1e293b" stroke="white" stroke-width="0.5"/><line x1="50" y1="30" x2="50" y2="70" stroke="white" stroke-width="0.8" stroke-dasharray="3,3"/></g></svg>';return L.divIcon({html:svg,className:'aircraft-icon',iconSize:[36,36],iconAnchor:[18,18],popupAnchor:[0,-18]})}
let flights=[],markers={},regions=[],ws=null,charts={};
async function loadRegions(){try{const res=await fetch('/api/regions');regions=await res.json();regions.forEach(r=>{L.circle([r.lat,r.lon],{radius:r.radius_km*1000,color:r.color,fillColor:r.color,fillOpacity:.08,weight:2}).addTo(map).bindPopup('<b>'+r.name+'</b><br>Raio: '+r.radius_km+'km');L.marker([r.lat,r.lon],{icon:L.divIcon({html:'<div style="background:'+r.color+';color:white;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:600;">'+r.name+'</div>',className:'region-label'})}).addTo(map)})}catch(e){console.error('Erro regioes:',e)}}
async function loadFlights(){try{const res=await fetch('/api/flights');const data=await res.json();updateFlights(data.flights||[])}catch(e){console.error('Erro voos:',e)}}
function updateFlights(newFlights){flights=newFlights;document.getElementById('flight-count').textContent=flights.length+' voos';document.getElementById('flights-loading').style.display='none';const currentIds=new Set(flights.map(f=>f.icao24));Object.keys(markers).forEach(id=>{if(!currentIds.has(id)){map.removeLayer(markers[id]);delete markers[id]}});flights.forEach(f=>{const airline=getAirlineInfo(f.callsign);const region=regions.find(r=>r.name===f.region)||{color:'#38bdf8'};if(markers[f.icao24]){markers[f.icao24].setLatLng([f.latitude,f.longitude]);markers[f.icao24].setIcon(createAircraftIcon(f.heading,region.color,f.callsign))}else{const marker=L.marker([f.latitude,f.longitude],{icon:createAircraftIcon(f.heading,region.color,f.callsign)}).addTo(map);const flightTime=f.last_contact?Math.round((Date.now()/1000-f.last_contact)/60):'?';const popupContent='<div class="popup-content"><div class="popup-header"><span class="popup-flag">'+airline.flag+'</span><div><div class="popup-callsign">'+(f.callsign||'N/A')+'</div><div class="popup-airline">'+airline.name+'</div></div></div><div class="popup-details"><div class="popup-detail"><i class="fas fa-arrows-alt-v"></i> '+Math.round(f.altitude||0).toLocaleString()+' ft</div><div class="popup-detail"><i class="fas fa-tachometer-alt"></i> '+Math.round((f.velocity||0)*3.6)+' km/h</div><div class="popup-detail"><i class="fas fa-compass"></i> '+Math.round(f.heading||0)+'°</div><div class="popup-detail"><i class="fas fa-clock"></i> '+flightTime+' min</div><div class="popup-detail"><i class="fas fa-fingerprint"></i> '+(f.icao24||'N/A')+'</div><div class="popup-detail"><i class="fas fa-globe"></i> '+(f.origin_country||'N/A')+'</div></div><div class="popup-route"><div><strong>📍 Regiao:</strong> '+(f.region||'N/A')+' ('+(f.distance_from_center?f.distance_from_center.toFixed(1):'?')+' km)</div><div><strong>⏱️ Ultimo contacto:</strong> '+(f.last_contact?new Date(f.last_contact*1000).toLocaleTimeString('pt-PT'):'N/A')+'</div><div><strong>📡 Transponder:</strong> '+(f.squawk||'N/A')+'</div><div><strong>🏢 Companhia:</strong> '+airline.name+' ('+airline.country+')</div></div></div>';marker.bindPopup(popupContent);markers[f.icao24]=marker}});renderFlightList()}
function renderFlightList(){const container=document.getElementById('flights-list');if(!flights.length){container.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">Nenhum voo ativo</p>';return}container.innerHTML=flights.map(f=>{const airline=getAirlineInfo(f.callsign);const region=regions.find(r=>r.name===f.region)||{color:'#38bdf8'};const flightTime=f.last_contact?Math.round((Date.now()/1000-f.last_contact)/60):'?';return'<div class="flight-card" onclick="focusFlight(\''+f.icao24+'\')"><div class="airline"><span class="airline-flag">'+airline.flag+'</span><div><div class="callsign">'+(f.callsign||'N/A')+'</div><div class="airline-name">'+airline.name+'</div></div></div><div class="details"><div class="detail-item"><i class="fas fa-arrows-alt-v"></i> '+Math.round(f.altitude||0).toLocaleString()+' ft</div><div class="detail-item"><i class="fas fa-tachometer-alt"></i> '+Math.round((f.velocity||0)*3.6)+' km/h</div><div class="detail-item"><i class="fas fa-compass"></i> '+Math.round(f.heading||0)+'°</div><div class="detail-item"><i class="fas fa-clock"></i> '+flightTime+' min</div></div><span class="region-tag" style="background:'+region.color+'22;color:'+region.color+';border:1px solid '+region.color+'44">📍 '+(f.region||'N/A')+' ('+(f.distance_from_center?f.distance_from_center.toFixed(1):'?')+' km)</span></div>'}).join('')}
function focusFlight(icao24){const f=flights.find(x=>x.icao24===icao24);if(f){map.setView([f.latitude,f.longitude],13);if(markers[icao24])markers[icao24].openPopup()}}
async function loadStats(){try{const res=await fetch('/api/stats?hours=24');const data=await res.json();const s=data.stats||{};document.getElementById('stat-total').textContent=s.total_flights||0;document.getElementById('stat-active').textContent=s.active_flights||0;document.getElementById('stat-countries').textContent=s.unique_countries||0;document.getElementById('stat-max-alt').textContent=s.max_altitude?Math.round(s.max_altitude).toLocaleString():0;renderCharts(s)}catch(e){console.error('Erro stats:',e)}}
function renderCharts(s){if(charts.hourly)charts.hourly.destroy();if(charts.countries)charts.countries.destroy();if(charts.altitude)charts.altitude.destroy();const hourly=s.hourly||[];charts.hourly=new Chart(document.getElementById('hourlyChart'),{type:'line',data:{labels:hourly.map(h=>h.hour+':00'),datasets:[{label:'Voos',data:hourly.map(h=>h.count),borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.1)',fill:true,tension:.4}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'}}}}});const countries=s.countries||[];charts.countries=new Chart(document.getElementById('countriesChart'),{type:'doughnut',data:{labels:countries.map(c=>c.country),datasets:[{data:countries.map(c=>c.count),backgroundColor:['#38bdf8','#22c55e','#f59e0b','#ef4444','#a855f7','#ec4899']}]},options:{responsive:true,plugins:{legend:{position:'right',labels:{color:'#e2e8f0'}}}}});const altRanges=s.altitude_distribution||[];charts.altitude=new Chart(document.getElementById('altitudeChart'),{type:'bar',data:{labels:altRanges.map(a=>a.range),datasets:[{label:'Avioes',data:altRanges.map(a=>a.count),backgroundColor:'#38bdf8'}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'}}}}})}
async function loadAlerts(){try{const res=await fetch('/api/alerts');const data=await res.json();const alerts=data.alerts||[];document.getElementById('alert-count').textContent=alerts.length;document.getElementById('alert-badge').classList.toggle('show',alerts.length>0);const container=document.getElementById('alerts-list');if(!alerts.length){container.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">Nenhum alerta</p>';return}container.innerHTML=alerts.map(a=>'<div class="alert-item"><div class="time">'+new Date(a.timestamp).toLocaleString('pt-PT')+'</div><div class="message">🔔 <strong>'+a.callsign+'</strong> detetado em '+a.region+' — '+(a.distance_km?a.distance_km.toFixed(1):'?')+' km de distancia</div></div>').join('')}catch(e){console.error('Erro alerts:',e)}}
function showAlerts(){switchTab('alerts')}
function switchTab(name){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));event.target.closest('.tab').classList.add('active');document.getElementById('tab-'+name).classList.add('active');if(name==='stats')loadStats();if(name==='alerts')loadAlerts()}
function connectWS(){const protocol=window.location.protocol==='https:'?'wss:':'ws:';ws=new WebSocket(protocol+'//'+window.location.host+'/ws');ws.onopen=()=>{document.getElementById('conn-status').textContent='Online';document.querySelector('.status-dot').style.background='#22c55e'};ws.onmessage=(e)=>{try{const data=JSON.parse(e.data);if(data.type==='init'||data.type==='update'){updateFlights(data.flights||[])}}catch(err){console.error('WS parse error:',err)}};ws.onclose=()=>{document.getElementById('conn-status').textContent='Offline';document.querySelector('.status-dot').style.background='#ef4444';setTimeout(connectWS,5000)};ws.onerror=(e)=>{console.error('WS error:',e);ws.close()}}
loadRegions();loadFlights();loadStats();loadAlerts();connectWS();
setInterval(()=>{if(!ws||ws.readyState!==WebSocket.OPEN)loadFlights()},30000);setInterval(loadAlerts,60000);
if('serviceWorker'in navigator){navigator.serviceWorker.register('/service-worker.js').catch(e=>console.log('SW error:',e))}
</script>
</body>
</html>"""

# Service Worker
SW_JS = """self.addEventListener('install', e => {
    e.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', e => {
    e.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', e => {
    e.respondWith(fetch(e.request).catch(() => new Response('Offline')));
});"""

# Manifest
MANIFEST_JSON = """{
    "name": "SkyTracker - Sesimbra",
    "short_name": "SkyTracker",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0f172a",
    "theme_color": "#0f172a",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
    ]
}"""

# Config
REGIONS = json.loads(os.getenv("REGIONS", '[{"name":"Sesimbra","lat":38.4435,"lon":-9.1015,"radius_km":80,"color":"#ef4444"},{"name":"Setubal","lat":38.5244,"lon":-8.8882,"radius_km":60,"color":"#3b82f6"},{"name":"Lisboa","lat":38.7223,"lon":-9.1393,"radius_km":70,"color":"#22c55e"}]'))
ALERT_AIRCRAFT = [a.strip() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]

# WebSocket Manager
class WSManager:
    def __init__(self):
        self.connections = []
    async def connect(self, ws):
        self.connections.append(ws)
    async def disconnect(self, ws):
        if ws in self.connections:
            self.connections.remove(ws)
    async def broadcast(self, message):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

manager = WSManager()

def serialize_for_json(obj):
    """Converte objetos nao serializaveis para JSON"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    return obj

async def broadcast_updates():
    try:
        db = await get_db()
        flights_col = db["flights"]
        cursor = flights_col.find({"last_seen": {"$gte": datetime.utcnow() - timedelta(minutes=5)}})
        flights = []
        async for doc in cursor:
            doc.pop("_id", None)
            # Converter todos os datetimes para strings
            for key, value in list(doc.items()):
                if isinstance(value, datetime):
                    doc[key] = value.isoformat()
            flights.append(doc)

        message = json.dumps({"type": "update", "flights": flights, "timestamp": datetime.utcnow().isoformat()})
        await manager.broadcast(message)
    except Exception as e:
        print(f"Broadcast error: {e}")
        traceback.print_exc()

# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("✅ Base de dados inicializada")
    worker_task = asyncio.create_task(start_worker(broadcast_updates))
    print("🚀 SkyTracker Worker iniciado!")
    print(f"📍 Regioes: {[r['name'] for r in REGIONS]}")
    print(f"🔔 Alertas: {', '.join(ALERT_AIRCRAFT) if ALERT_AIRCRAFT else 'Nenhum configurado'}")
    yield
    stop_worker()
    worker_task.cancel()
    print("🛑 Worker parado")

app = FastAPI(title="SkyTracker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content=json.loads(MANIFEST_JSON))

@app.get("/service-worker.js")
async def service_worker():
    return HTMLResponse(content=SW_JS, media_type="application/javascript")

@app.get("/icon-192.png")
@app.get("/icon-512.png")
async def icon():
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    return HTMLResponse(content=png, media_type="image/png")

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/regions")
async def get_regions():
    return REGIONS

@app.get("/api/flights")
async def get_flights_api():
    try:
        flights = await get_active_flights()
        return {"flights": flights, "count": len(flights)}
    except Exception as e:
        return {"flights": [], "count": 0, "error": str(e)}

@app.get("/api/stats")
async def get_stats_api(hours: int = Query(24, ge=1, le=168)):
    try:
        stats = await get_stats(hours=hours)
        return {"stats": stats}
    except Exception as e:
        return {"stats": {}}

@app.get("/api/alerts")
async def get_alerts_api():
    try:
        db = await get_db()
        alerts_col = db["alerts"]
        cursor = alerts_col.find().sort("timestamp", -1).limit(50)
        alerts = []
        async for doc in cursor:
            doc.pop("_id", None)
            for key, value in list(doc.items()):
                if isinstance(value, datetime):
                    doc[key] = value.isoformat()
            alerts.append(doc)
        return {"alerts": alerts}
    except Exception as e:
        return {"alerts": []}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket)
    try:
        flights = await get_active_flights()
        await websocket.send_text(json.dumps({"type": "init", "flights": flights}))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket erro: {e}")
        await manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
