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
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E&#9992;%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0b1120;color:#e2e8f0;overflow-x:hidden}
.header{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);padding:12px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #334155;position:sticky;top:0;z-index:1000}
.header h1{font-size:1.3rem;color:#38bdf8;display:flex;align-items:center;gap:8px}
.header .status{display:flex;align-items:center;gap:15px;font-size:.85rem}
.status-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.alert-badge{background:#ef4444;color:white;padding:4px 10px;border-radius:12px;font-size:.75rem;font-weight:600;cursor:pointer;display:none}
.alert-badge.show{display:block}
.main-container{display:grid;grid-template-columns:1fr 420px;height:calc(100vh - 56px)}
@media(max-width:1200px){.main-container{grid-template-columns:1fr}}
#map{height:100%;width:100%;z-index:1}
.layer-control{position:absolute;top:70px;right:10px;z-index:1000;background:#1e293b;border:1px solid #334155;border-radius:10px;padding:8px;box-shadow:0 4px 20px rgba(0,0,0,.5)}
.layer-btn{display:block;width:100%;padding:8px 12px;margin-bottom:4px;background:transparent;border:1px solid #475569;border-radius:6px;color:#e2e8f0;cursor:pointer;font-size:.8rem;transition:all .2s}
.layer-btn:hover{background:#334155}
.layer-btn.active{background:#38bdf8;color:#0f172a;border-color:#38bdf8}
.sidebar{background:#0f172a;border-left:1px solid #334155;display:flex;flex-direction:column;overflow:hidden}
@media(max-width:1200px){.sidebar{height:50vh;border-left:none;border-top:1px solid #334155}}
.tabs{display:flex;background:#0f172a;border-bottom:1px solid #334155}
.tab{flex:1;padding:12px;text-align:center;cursor:pointer;font-size:.8rem;font-weight:500;transition:all .2s;border-bottom:2px solid transparent}
.tab:hover{background:#1e293b}
.tab.active{border-bottom-color:#38bdf8;color:#38bdf8;background:#1e293b}
.tab-content{flex:1;overflow-y:auto;padding:15px;display:none}
.tab-content.active{display:block}
.flight-card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:14px;margin-bottom:10px;cursor:pointer;transition:all .2s}
.flight-card:hover{border-color:#38bdf8;transform:translateX(4px)}
.flight-card .airline{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.flight-card .airline-flag{font-size:1.3rem}
.flight-card .airline-name{font-size:.75rem;color:#94a3b8}
.flight-card .callsign{font-size:1.1rem;font-weight:700;color:#f8fafc}
.flight-card .details{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px;font-size:.78rem;color:#cbd5e1}
.flight-card .detail-item{display:flex;align-items:center;gap:5px}
.flight-card .detail-item i{color:#38bdf8;width:14px}
.flight-card .region-tag{display:inline-block;padding:3px 10px;border-radius:6px;font-size:.7rem;font-weight:600;margin-top:8px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.stat-card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:15px;text-align:center}
.stat-card .value{font-size:1.6rem;font-weight:700;color:#38bdf8}
.stat-card .label{font-size:.75rem;color:#94a3b8;margin-top:4px}
.chart-container{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:15px;margin-bottom:15px}
.chart-container h3{font-size:.85rem;margin-bottom:10px;color:#e2e8f0}
.chart-wrapper{position:relative;height:180px}
.alert-item{background:#1e293b;border-left:3px solid #ef4444;border-radius:0 10px 10px 0;padding:12px;margin-bottom:10px}
.alert-item .time{font-size:.7rem;color:#94a3b8}
.alert-item .message{font-size:.82rem;margin-top:4px}
.loading{text-align:center;padding:40px;color:#94a3b8}
.loading i{font-size:2rem;animation:spin 1s linear infinite}
@keyframes spin{100%{transform:rotate(360deg)}}
.leaflet-popup-content-wrapper{background:#1e293b;color:#e2e8f0;border-radius:12px;border:1px solid #334155}
.leaflet-popup-tip{background:#1e293b}
.detail-panel{position:fixed;top:0;right:-450px;width:420px;height:100vh;background:#0f172a;border-left:1px solid #334155;z-index:2000;transition:right .3s ease;overflow-y:auto;padding:0}
.detail-panel.open{right:0}
.detail-panel-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:1999;display:none}
.detail-panel-overlay.show{display:block}
.detail-header{background:linear-gradient(135deg,#1e293b,#0f172a);padding:20px;border-bottom:1px solid #334155;position:sticky;top:0;z-index:10}
.detail-header .close-btn{position:absolute;top:15px;right:15px;background:none;border:none;color:#94a3b8;font-size:1.2rem;cursor:pointer;padding:5px}
.detail-header .close-btn:hover{color:#fff}
.detail-header .flight-number{font-size:1.5rem;font-weight:700;color:#38bdf8}
.detail-header .airline-info{display:flex;align-items:center;gap:10px;margin-top:8px}
.detail-header .airline-flag{font-size:1.8rem}
.detail-header .airline-name{font-size:.9rem;color:#94a3b8}
.detail-section{padding:18px 20px;border-bottom:1px solid #1e293b}
.detail-section h3{font-size:.8rem;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.detail-section h3 i{color:#38bdf8}
.route-visual{display:flex;align-items:center;gap:10px;margin:15px 0}
.route-point{text-align:center;flex:1}
.route-point .code{font-size:1.2rem;font-weight:700;color:#38bdf8}
.route-point .name{font-size:.7rem;color:#94a3b8;margin-top:2px}
.route-line{flex:2;height:4px;background:#334155;border-radius:2px;position:relative}
.route-progress{height:100%;background:linear-gradient(90deg,#38bdf8,#22c55e);border-radius:2px;transition:width .5s ease}
.route-plane{position:absolute;top:50%;transform:translate(-50%,-50%);font-size:1.2rem;transition:left .5s ease}
.route-info{display:flex;justify-content:space-between;font-size:.75rem;color:#94a3b8;margin-top:8px}
.data-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.data-item{background:#1e293b;border-radius:8px;padding:10px}
.data-item .label{font-size:.7rem;color:#64748b;text-transform:uppercase}
.data-item .value{font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:2px}
.data-item .value.highlight{color:#38bdf8}
.aircraft-image{width:100%;height:160px;background:#1e293b;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:15px}
.weather-widget{display:flex;align-items:center;gap:15px;background:#1e293b;border-radius:10px;padding:12px}
.weather-widget .temp{font-size:1.8rem;font-weight:700;color:#38bdf8}
.weather-widget .details{font-size:.75rem;color:#94a3b8}
.playback-controls{display:flex;align-items:center;gap:10px;margin-top:15px}
.playback-btn{background:#38bdf8;color:#0f172a;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-weight:600;font-size:.8rem}
.playback-btn:hover{background:#0ea5e9}
.playback-slider{flex:1;height:6px;background:#334155;border-radius:3px;cursor:pointer;position:relative}
.playback-progress{height:100%;background:#38bdf8;border-radius:3px;width:0%}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:#0f172a}
::-webkit-scrollbar-thumb{background:#334155;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:#475569}
@media(max-width:768px){
    .main-container{grid-template-columns:1fr}
    .sidebar{height:45vh}
    .header h1{font-size:1.1rem}
    .detail-panel{width:100%;right:-100%}
}
</style>
</head>
<body>
<div class="header">
    <h1><i class="fas fa-plane"></i> SkyTracker <span style="color:#94a3b8;font-size:.85rem">Sesimbra 24/7</span></h1>
    <div class="status">
        <div style="display:flex;align-items:center;gap:6px"><div class="status-dot"></div><span id="conn-status">Online</span></div>
        <span id="flight-count">0 voos</span>
        <div class="alert-badge" id="alert-badge" onclick="showAlerts()"><i class="fas fa-bell"></i> <span id="alert-count">0</span></div>
    </div>
</div>
<div class="main-container">
    <div id="map"></div>
    <div class="layer-control">
        <button class="layer-btn active" onclick="setLayer('dark')">&#127769; Escuro</button>
        <button class="layer-btn" onclick="setLayer('satellite')">&#127757; Satelite</button>
        <button class="layer-btn" onclick="setLayer('terrain')">&#9968;&#65039; Terreno</button>
        <button class="layer-btn" onclick="setLayer('standard')">&#128506;&#65039; Padrao</button>
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
                <div class="stat-card"><div class="value" id="stat-countries">0</div><div class="label">Paises</div></div>
                <div class="stat-card"><div class="value" id="stat-max-alt">0</div><div class="label">Alt. Max (ft)</div></div>
            </div>
            <div class="chart-container"><h3>&#128202; Detecoes por Hora</h3><div class="chart-wrapper"><canvas id="hourlyChart"></canvas></div></div>
            <div class="chart-container"><h3>&#127757; Top Paises</h3><div class="chart-wrapper"><canvas id="countriesChart"></canvas></div></div>
            <div class="chart-container"><h3>&#128207; Distribuicao de Altitude</h3><div class="chart-wrapper"><canvas id="altitudeChart"></canvas></div></div>
        </div>
        <div class="tab-content" id="tab-alerts">
            <div id="alerts-list"><p style="color:#94a3b8;text-align:center;padding:20px">Nenhum alerta configurado</p></div>
        </div>
    </div>
</div>
<div class="detail-panel-overlay" id="detail-overlay" onclick="closeDetailPanel()"></div>
<div class="detail-panel" id="detail-panel">
    <div class="detail-header">
        <button class="close-btn" onclick="closeDetailPanel()"><i class="fas fa-times"></i></button>
        <div class="flight-number" id="detail-callsign">---</div>
        <div class="airline-info">
            <span class="airline-flag" id="detail-flag">&#9992;&#65039;</span>
            <span class="airline-name" id="detail-airline">---</span>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-route"></i> Trajeto</h3>
        <div class="route-visual">
            <div class="route-point">
                <div class="code" id="detail-origin-code">---</div>
                <div class="name" id="detail-origin-name">---</div>
            </div>
            <div class="route-line">
                <div class="route-progress" id="route-progress-bar" style="width:0%"></div>
                <div class="route-plane" id="route-plane-icon" style="left:0%">&#9992;&#65039;</div>
            </div>
            <div class="route-point">
                <div class="code" id="detail-dest-code">---</div>
                <div class="name" id="detail-dest-name">---</div>
            </div>
        </div>
        <div class="route-info">
            <span id="route-progress-text">Progresso: 0%</span>
            <span id="route-distance">Distancia: --- km</span>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-location-arrow"></i> Posicao e Movimento</h3>
        <div class="data-grid">
            <div class="data-item"><div class="label">Latitude</div><div class="value" id="detail-lat">---</div></div>
            <div class="data-item"><div class="label">Longitude</div><div class="value" id="detail-lon">---</div></div>
            <div class="data-item"><div class="label">Altitude (Baro)</div><div class="value highlight" id="detail-alt">---</div></div>
            <div class="data-item"><div class="label">Altitude (GPS)</div><div class="value" id="detail-alt-gps">---</div></div>
            <div class="data-item"><div class="label">Velocidade Solo</div><div class="value highlight" id="detail-gs">---</div></div>
            <div class="data-item"><div class="label">Velocidade Indicada</div><div class="value" id="detail-ias">---</div></div>
            <div class="data-item"><div class="label">Razao Vertical</div><div class="value" id="detail-vsi">---</div></div>
            <div class="data-item"><div class="label">Rumo (Track)</div><div class="value" id="detail-track">---</div></div>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-sliders-h"></i> Parametros de Voo</h3>
        <div class="data-grid">
            <div class="data-item"><div class="label">Squawk</div><div class="value highlight" id="detail-squawk">---</div></div>
            <div class="data-item"><div class="label">Numero Mach</div><div class="value" id="detail-mach">---</div></div>
            <div class="data-item"><div class="label">Temperatura</div><div class="value" id="detail-temp">---</div></div>
            <div class="data-item"><div class="label">Vento</div><div class="value" id="detail-wind">---</div></div>
            <div class="data-item"><div class="label">Pressao</div><div class="value" id="detail-pressure">---</div></div>
            <div class="data-item"><div class="label">No Solo</div><div class="value" id="detail-ground">---</div></div>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-plane"></i> Aeronave</h3>
        <div class="aircraft-image" id="aircraft-img">&#9992;&#65039;</div>
        <div class="data-grid">
            <div class="data-item"><div class="label">Tipo</div><div class="value highlight" id="detail-type">---</div></div>
            <div class="data-item"><div class="label">Matricula</div><div class="value" id="detail-reg">---</div></div>
            <div class="data-item"><div class="label">Fabricante</div><div class="value" id="detail-manuf">---</div></div>
            <div class="data-item"><div class="label">Modelo</div><div class="value" id="detail-model">---</div></div>
            <div class="data-item"><div class="label">Envergadura</div><div class="value" id="detail-wingspan">---</div></div>
            <div class="data-item"><div class="label">Passageiros</div><div class="value" id="detail-pax">---</div></div>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-warehouse"></i> Aeroporto Mais Proximo</h3>
        <div class="data-grid">
            <div class="data-item"><div class="label">Nome</div><div class="value highlight" id="detail-airport-name">---</div></div>
            <div class="data-item"><div class="label">Distancia</div><div class="value" id="detail-airport-dist">---</div></div>
            <div class="data-item"><div class="label">Cidade</div><div class="value" id="detail-airport-city">---</div></div>
            <div class="data-item"><div class="label">Pais</div><div class="value" id="detail-airport-country">---</div></div>
        </div>
    </div>
    <div class="detail-section">
        <h3><i class="fas fa-history"></i> Historico / Playback</h3>
        <p style="color:#64748b;font-size:.8rem;margin-bottom:10px">Reproducao da rota do voo</p>
        <div class="playback-controls">
            <button class="playback-btn" onclick="playPlayback()"><i class="fas fa-play"></i></button>
            <div class="playback-slider" onclick="seekPlayback(event)">
                <div class="playback-progress" id="playback-progress"></div>
            </div>
        </div>
    </div>
</div>
<script>
const AIRLINES={"TAP":{name:"TAP Air Portugal",country:"Portugal",flag:"&#127477;&#127481;"},"RYR":{name:"Ryanair",country:"Ireland",flag:"&#127470;&#127466;"},"EZY":{name:"easyJet",country:"UK",flag:"&#127468;&#127463;"},"BAW":{name:"British Airways",country:"UK",flag:"&#127468;&#127463;"},"AFR":{name:"Air France",country:"France",flag:"&#127467;&#127479;"},"DLH":{name:"Lufthansa",country:"Germany",flag:"&#127465;&#127466;"},"IBE":{name:"Iberia",country:"Spain",flag:"&#127466;&#127480;"},"VLG":{name:"Vueling",country:"Spain",flag:"&#127466;&#127480;"},"EIN":{name:"Aer Lingus",country:"Ireland",flag:"&#127470;&#127466;"},"SWR":{name:"Swiss",country:"Switzerland",flag:"&#127464;&#127469;"},"KLM":{name:"KLM",country:"Netherlands",flag:"&#127475;&#127473;"},"SAS":{name:"SAS",country:"Sweden",flag:"&#127480;&#127466;"},"NAX":{name:"Norwegian",country:"Norway",flag:"&#127475;&#127472;"},"WZZ":{name:"Wizz Air",country:"Hungary",flag:"&#127469;&#127482;"},"TRA":{name:"Transavia",country:"Netherlands",flag:"&#127475;&#127473;"},"EWG":{name:"Eurowings",country:"Germany",flag:"&#127465;&#127466;"},"TOM":{name:"TUI Airways",country:"UK",flag:"&#127468;&#127463;"},"FIN":{name:"Finnair",country:"Finland",flag:"&#127467;&#127470;"},"LOT":{name:"LOT Polish",country:"Poland",flag:"&#127477;&#127473;"},"AUA":{name:"Austrian",country:"Austria",flag:"&#127462;&#127481;"},"OS":{name:"Austrian",country:"Austria",flag:"&#127462;&#127481;"},"LX":{name:"Swiss",country:"Switzerland",flag:"&#127464;&#127469;"},"AF":{name:"Air France",country:"France",flag:"&#127467;&#127479;"},"KL":{name:"KLM",country:"Netherlands",flag:"&#127475;&#127473;"},"LH":{name:"Lufthansa",country:"Germany",flag:"&#127465;&#127466;"},"BA":{name:"British Airways",country:"UK",flag:"&#127468;&#127463;"},"IB":{name:"Iberia",country:"Spain",flag:"&#127466;&#127480;"},"VY":{name:"Vueling",country:"Spain",flag:"&#127466;&#127480;"},"FR":{name:"Ryanair",country:"Ireland",flag:"&#127470;&#127466;"},"U2":{name:"easyJet",country:"UK",flag:"&#127468;&#127463;"},"TP":{name:"TAP Air Portugal",country:"Portugal",flag:"&#127477;&#127481;"}};
function getAirlineInfo(callsign){if(!callsign)return{name:"Desconhecida",country:"Desconhecido",flag:"&#9992;&#65039;"};const cs=callsign.toUpperCase();for(let prefix of Object.keys(AIRLINES).sort((a,b)=>b.length-a.length)){if(cs.startsWith(prefix))return AIRLINES[prefix]}return{name:"Desconhecida",country:"Desconhecido",flag:"&#9992;&#65039;"}}
let map,layers;
document.addEventListener('DOMContentLoaded',function(){
    const mapContainer=document.getElementById('map');
    if(!mapContainer){console.error('Container do mapa nao encontrado!');return;}
    map=L.map('map').setView([38.5244,-8.8882],9);
    layers={
        dark:L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; CARTO'}),
        satellite:L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'&copy; Esri'}),
        terrain:L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenTopoMap'}),
        standard:L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OSM'})
    };
    layers.dark.addTo(map);
    loadRegions();loadFlights();loadStats();loadAlerts();connectWS();
});
function setLayer(name){Object.values(layers).forEach(l=>map.removeLayer(l));layers[name].addTo(map);document.querySelectorAll('.layer-btn').forEach(b=>b.classList.remove('active'));event.target.classList.add('active')}
function createAircraftIcon(heading,color,callsign){const airline=getAirlineInfo(callsign);const svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="36" height="36"><g transform="rotate('+(heading||0)+',50,50)"><path d="M50 10 L20 50 L30 55 L50 45 L70 55 L80 50 Z" fill="'+color+'" stroke="white" stroke-width="1.5"/><ellipse cx="50" cy="50" rx="6" ry="35" fill="'+color+'" stroke="white" stroke-width="1.5"/><path d="M50 80 L35 95 L50 90 L65 95 Z" fill="'+color+'" stroke="white" stroke-width="1.5"/><ellipse cx="50" cy="22" rx="4" ry="6" fill="#1e293b" stroke="white" stroke-width="0.5"/><line x1="50" y1="30" x2="50" y2="70" stroke="white" stroke-width="0.8" stroke-dasharray="3,3"/></g></svg>';return L.divIcon({html:svg,className:'aircraft-icon',iconSize:[36,36],iconAnchor:[18,18],popupAnchor:[0,-18]})}
let flights=[],markers={},regions=[],ws=null,charts={},selectedFlight=null;
async function loadRegions(){try{const res=await fetch('/api/regions');regions=await res.json();regions.forEach(r=>{L.circle([r.lat,r.lon],{radius:r.radius_km*1000,color:r.color,fillColor:r.color,fillOpacity:.08,weight:2}).addTo(map).bindPopup('<b>'+r.name+'</b><br>Raio: '+r.radius_km+'km');L.marker([r.lat,r.lon],{icon:L.divIcon({html:'<div style="background:'+r.color+';color:white;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:600;">'+r.name+'</div>',className:'region-label'})}).addTo(map)})}catch(e){console.error('Erro regioes:',e)}}
async function loadFlights(){try{const res=await fetch('/api/flights');const data=await res.json();updateFlights(data.flights||[])}catch(e){console.error('Erro voos:',e)}}
function updateFlights(newFlights){flights=newFlights;document.getElementById('flight-count').textContent=flights.length+' voos';document.getElementById('flights-loading').style.display='none';const currentIds=new Set(flights.map(f=>f.icao24));Object.keys(markers).forEach(id=>{if(!currentIds.has(id)){map.removeLayer(markers[id]);delete markers[id]}});flights.forEach(f=>{const airline=getAirlineInfo(f.callsign);const region=regions.find(r=>r.name===f.region)||{color:'#38bdf8'};if(markers[f.icao24]){markers[f.icao24].setLatLng([f.latitude,f.longitude]);markers[f.icao24].setIcon(createAircraftIcon(f.heading,region.color,f.callsign))}else{const marker=L.marker([f.latitude,f.longitude],{icon:createAircraftIcon(f.heading,region.color,f.callsign)}).addTo(map);marker.on('click',()=>openDetailPanel(f));const flightTime=f.last_contact?Math.round((Date.now()/1000-f.last_contact)/60):'?';const popupContent='<div style="min-width:220px;font-family:system-ui"><div style="display:flex;align-items:center;gap:8px;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:8px"><span style="font-size:1.4rem">'+airline.flag+'</span><div><div style="font-size:1.1rem;font-weight:700">'+(f.callsign||'N/A')+'</div><div style="font-size:.75rem;color:#94a3b8">'+airline.name+'</div></div></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.78rem"><div><i class="fas fa-arrows-alt-v" style="color:#38bdf8"></i> '+Math.round(f.altitude||0).toLocaleString()+' ft</div><div><i class="fas fa-tachometer-alt" style="color:#38bdf8"></i> '+Math.round((f.velocity||0)*3.6)+' km/h</div><div><i class="fas fa-compass" style="color:#38bdf8"></i> '+Math.round(f.heading||0)+'°</div><div><i class="fas fa-clock" style="color:#38bdf8"></i> '+flightTime+' min</div></div><div style="margin-top:8px;padding-top:8px;border-top:1px solid #334155;font-size:.75rem;color:#94a3b8"><div><strong style="color:#e2e8f0">&#127759; Regiao:</strong> '+(f.region||'N/A')+'</div><div><strong style="color:#e2e8f0">&#128226; Squawk:</strong> '+(f.squawk||'N/A')+'</div></div></div>';marker.bindPopup(popupContent);markers[f.icao24]=marker}});renderFlightList();if(selectedFlight)updateDetailPanel(selectedFlight)}
function renderFlightList(){const container=document.getElementById('flights-list');if(!flights.length){container.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">Nenhum voo ativo</p>';return}container.innerHTML=flights.map(f=>{const airline=getAirlineInfo(f.callsign);const region=regions.find(r=>r.name===f.region)||{color:'#38bdf8'};const flightTime=f.last_contact?Math.round((Date.now()/1000-f.last_contact)/60):'?';return'<div class="flight-card" onclick="openDetailPanel(flights.find(x=>x.icao24===\''+f.icao24+'\'))"><div class="airline"><span class="airline-flag">'+airline.flag+'</span><div><div class="callsign">'+(f.callsign||'N/A')+'</div><div class="airline-name">'+airline.name+'</div></div></div><div class="details"><div class="detail-item"><i class="fas fa-arrows-alt-v"></i> '+Math.round(f.altitude||0).toLocaleString()+' ft</div><div class="detail-item"><i class="fas fa-tachometer-alt"></i> '+Math.round((f.velocity||0)*3.6)+' km/h</div><div class="detail-item"><i class="fas fa-compass"></i> '+Math.round(f.heading||0)+'°</div><div class="detail-item"><i class="fas fa-clock"></i> '+flightTime+' min</div></div><span class="region-tag" style="background:'+region.color+'22;color:'+region.color+'">&#127759; '+(f.region||'N/A')+' ('+(f.distance_from_center?f.distance_from_center.toFixed(1):'?')+' km)</span></div>'}).join('')}
function focusFlight(icao24){const f=flights.find(x=>x.icao24===icao24);if(f){map.setView([f.latitude,f.longitude],13);if(markers[icao24])markers[icao24].openPopup()}}
function openDetailPanel(flight){if(!flight)return;selectedFlight=flight;updateDetailPanel(flight);document.getElementById('detail-panel').classList.add('open');document.getElementById('detail-overlay').classList.add('show');}
function closeDetailPanel(){document.getElementById('detail-panel').classList.remove('open');document.getElementById('detail-overlay').classList.remove('show');selectedFlight=null;}
function updateDetailPanel(f){const airline=getAirlineInfo(f.callsign);document.getElementById('detail-callsign').textContent=f.callsign||'N/A';document.getElementById('detail-flag').innerHTML=airline.flag;document.getElementById('detail-airline').textContent=airline.name+' | '+airline.country;const route=f.route||{};document.getElementById('detail-origin-code').textContent=route.origin_icao||'???';document.getElementById('detail-origin-name').textContent=(route.origin||'Desconhecido').substring(0,15);document.getElementById('detail-dest-code').textContent=route.destination_icao||'???';document.getElementById('detail-dest-name').textContent=(route.destination||'Desconhecido').substring(0,15);const progress=route.progress||0;document.getElementById('route-progress-bar').style.width=progress+'%';document.getElementById('route-plane-icon').style.left=progress+'%';document.getElementById('route-progress-text').textContent='Progresso: '+progress+'%';document.getElementById('route-distance').textContent='Distancia: '+(route.distance_total_km||0)+' km ('+(route.distance_remaining_km||0)+' km restantes)';document.getElementById('detail-lat').textContent=f.latitude?f.latitude.toFixed(4):'---';document.getElementById('detail-lon').textContent=f.longitude?f.longitude.toFixed(4):'---';document.getElementById('detail-alt').textContent=f.altitude?Math.round(f.altitude).toLocaleString()+' ft':'---';document.getElementById('detail-alt-gps').textContent=f.altitude_gps?Math.round(f.altitude_gps).toLocaleString()+' ft':'---';document.getElementById('detail-gs').textContent=f.velocity?Math.round(f.velocity*3.6)+' km/h':'---';document.getElementById('detail-ias').textContent=f.velocity?Math.round(f.velocity*1.94384)+' kts':'---';document.getElementById('detail-vsi').textContent=f.vertical_rate?Math.round(f.vertical_rate)+' ft/min':'---';document.getElementById('detail-track').textContent=f.heading?Math.round(f.heading)+'°':'---';document.getElementById('detail-squawk').textContent=f.squawk||'---';document.getElementById('detail-mach').textContent=f.mach?'M'+f.mach:'---';const weather=f.weather||{};document.getElementById('detail-temp').textContent=weather.temperature?weather.temperature+'°C':'---';document.getElementById('detail-wind').textContent=(weather.wind_speed&&weather.wind_direction)?weather.wind_direction+'° / '+weather.wind_speed+' km/h':'---';document.getElementById('detail-pressure').textContent=weather.pressure?weather.pressure+' hPa':'---';document.getElementById('detail-ground').textContent=f.on_ground?'Sim':'Nao';const acInfo=f.aircraft_info||{};const acSpecs=f.aircraft_specs||{};document.getElementById('detail-type').textContent=acInfo.typecode||'---';document.getElementById('detail-reg').textContent=acInfo.registration||'---';document.getElementById('detail-manuf').textContent=acInfo.manufacturer_icao||'---';document.getElementById('detail-model').textContent=acInfo.model||'---';document.getElementById('detail-wingspan').textContent=acSpecs.wingspan?acSpecs.wingspan+' m':'---';document.getElementById('detail-pax').textContent=acSpecs.passengers?acSpecs.passengers:'---';const airport=f.nearest_airport||{};document.getElementById('detail-airport-name').textContent=airport.name||'---';document.getElementById('detail-airport-dist').textContent=airport.distance_km?airport.distance_km+' km':'---';document.getElementById('detail-airport-city').textContent=airport.city||'---';document.getElementById('detail-airport-country').textContent=airport.country||'---';}
let playbackInterval=null;function playPlayback(){if(playbackInterval){clearInterval(playbackInterval);playbackInterval=null;return;}let progress=0;playbackInterval=setInterval(()=>{progress+=1;if(progress>100){progress=0;}document.getElementById('playback-progress').style.width=progress+'%';},100);}
function seekPlayback(e){const rect=e.target.getBoundingClientRect();const pct=((e.clientX-rect.left)/rect.width)*100;document.getElementById('playback-progress').style.width=pct+'%';}
async function loadStats(){try{const res=await fetch('/api/stats?hours=24');const data=await res.json();const s=data.stats||{};document.getElementById('stat-total').textContent=s.total_flights||0;document.getElementById('stat-active').textContent=s.active_flights||0;document.getElementById('stat-countries').textContent=s.unique_countries||0;document.getElementById('stat-max-alt').textContent=s.max_altitude?Math.round(s.max_altitude).toLocaleString():0;renderCharts(s)}catch(e){console.error('Erro stats:',e)}}
function renderCharts(s){if(!s||typeof s!=='object'){console.log('Stats vazias');return}const hourlyCanvas=document.getElementById('hourlyChart');const countriesCanvas=document.getElementById('countriesChart');const altitudeCanvas=document.getElementById('altitudeChart');if(!hourlyCanvas||!countriesCanvas||!altitudeCanvas){return}const container=hourlyCanvas.parentElement;if(!container||container.clientHeight===0||container.clientWidth===0){return}try{if(charts.hourly)charts.hourly.destroy()}catch(e){}try{if(charts.countries)charts.countries.destroy()}catch(e){}try{if(charts.altitude)charts.altitude.destroy()}catch(e){}const hourly=s.hourly||[];if(hourly.length>0){try{charts.hourly=new Chart(hourlyCanvas,{type:'line',data:{labels:hourly.map(h=>h.hour+':00'),datasets:[{label:'Voos',data:hourly.map(h=>h.count),borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,0.1)',fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#94a3b8'},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8'},grid:{color:'#334155'},beginAtZero:true}}}})}catch(e){}}const countries=s.countries||[];if(countries.length>0){try{charts.countries=new Chart(countriesCanvas,{type:'doughnut',data:{labels:countries.map(c=>c.country),datasets:[{data:countries.map(c=>c.count),backgroundColor:['#38bdf8','#22c55e','#f59e0b','#ef4444','#a855f7','#ec4899','#14b8a6','#f97316']}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:'#e2e8f0',font:{size:10}}}}}})}catch(e){}}const altRanges=s.altitude_distribution||[];if(altRanges.length>0){try{charts.altitude=new Chart(altitudeCanvas,{type:'bar',data:{labels:altRanges.map(a=>a.range),datasets:[{label:'Avioes',data:altRanges.map(a=>a.count),backgroundColor:'#38bdf8',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#94a3b8',font:{size:10}},grid:{color:'#334155'}},y:{ticks:{color:'#94a3b8'},grid:{color:'#334155'},beginAtZero:true}}}})}catch(e){}}}
async function loadAlerts(){try{const res=await fetch('/api/alerts');const data=await res.json();const alerts=data.alerts||[];document.getElementById('alert-count').textContent=alerts.length;document.getElementById('alert-badge').classList.toggle('show',alerts.length>0);const container=document.getElementById('alerts-list');if(!alerts.length){container.innerHTML='<p style="color:#94a3b8;text-align:center;padding:20px">Nenhum alerta</p>';return}container.innerHTML=alerts.map(a=>'<div class="alert-item"><div class="time">'+new Date(a.timestamp).toLocaleString('pt-PT')+'</div><div class="message">&#128680; <strong>'+a.callsign+'</strong> detetado em '+a.region+' &mdash; '+(a.distance_km?a.distance_km.toFixed(1):'?')+' km</div></div>').join('')}catch(e){console.error('Erro alerts:',e)}}
function showAlerts(){switchTab('alerts')}
function switchTab(name){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));event.target.closest('.tab').classList.add('active');document.getElementById('tab-'+name).classList.add('active');if(name==='stats')loadStats();if(name==='alerts')loadAlerts()}
function connectWS(){const protocol=window.location.protocol==='https:'?'wss:':'ws:';ws=new WebSocket(protocol+'//'+window.location.host+'/ws');ws.onopen=()=>{document.getElementById('conn-status').textContent='Online';document.querySelector('.status-dot').style.background='#22c55e'};ws.onmessage=(e)=>{try{const data=JSON.parse(e.data);if(data.type==='init'||data.type==='update'){updateFlights(data.flights||[])}}catch(err){console.error('WS parse error:',err)}};ws.onclose=()=>{document.getElementById('conn-status').textContent='Offline';document.querySelector('.status-dot').style.background='#ef4444';setTimeout(connectWS,5000)};ws.onerror=(e)=>{console.error('WS error:',e);ws.close()}}
setInterval(()=>{if(!ws||ws.readyState!==WebSocket.OPEN)loadFlights()},30000);
setInterval(loadAlerts,60000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/service-worker.js').catch(e=>console.log('SW error:',e))}
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

async def broadcast_updates():
    try:
        db = await get_db()
        flights_col = db["flights"]
        cursor = flights_col.find({"last_seen": {"$gte": datetime.utcnow() - timedelta(minutes=5)}})
        flights = []
        async for doc in cursor:
            doc.pop("_id", None)
            for key, value in list(doc.items()):
                if isinstance(value, datetime):
                    doc[key] = value.isoformat()
            flights.append(doc)
        message = json.dumps({"type": "update", "flights": flights, "timestamp": datetime.utcnow().isoformat()})
        await manager.broadcast(message)
    except Exception as e:
        print(f"Broadcast error: {e}")
        traceback.print_exc()

# Lifespan - ROBUSTO
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("✅ Base de dados inicializada")

    worker_task = asyncio.create_task(start_worker(broadcast_updates))
    print("🚀 SkyTracker Worker iniciado!")
    print(f"📍 Regioes: {[r['name'] for r in REGIONS]}")
    print(f"🔔 Alertas: {', '.join(ALERT_AIRCRAFT) if ALERT_AIRCRAFT else 'Nenhum configurado'}")

    yield

    # Graceful shutdown
    print("🛑 A parar worker...")
    stop_worker()
    try:
        worker_task.cancel()
        await asyncio.wait_for(asyncio.shield(worker_task), timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    print("🛑 Worker parado")

app = FastAPI(title="SkyTracker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ROTA / com suporte a GET e HEAD (para health checks do Render)
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.head("/")
async def dashboard_head():
    return HTMLResponse(content="", status_code=200)

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content=json.loads(MANIFEST_JSON))

@app.get("/service-worker.js")
async def service_worker():
    return HTMLResponse(content=SW_JS, media_type="application/javascript")

@app.get("/icon-192.png")
async def icon_192():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" width="192" height="192"><rect fill="#0f172a" width="192" height="192"/><text x="96" y="130" font-size="120" text-anchor="middle">&#9992;&#65039;</text></svg>'
    return HTMLResponse(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512"><rect fill="#0f172a" width="512" height="512"/><text x="256" y="360" font-size="320" text-anchor="middle">&#9992;&#65039;</text></svg>'
    return HTMLResponse(content=svg, media_type="image/svg+xml")

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
        print(f"WebSocket error: {e}")
        await manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
