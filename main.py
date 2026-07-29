import os
import asyncio
import json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from database import (
    init_db, get_active_flights, get_stats, get_hourly_stats,
    get_country_stats, get_altitude_distribution, get_pending_alerts,
    get_all_alerts, mark_alert_notified, cleanup_old_data
)
from opensky_client import fetch_all_regions, get_regions
from worker import worker, start_worker

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#0f172a">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="description" content="SkyTracker 24/7 - Rastreamento de avioes em tempo real">
    <title>SkyTracker 24/7 | Sesimbra</title>
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/static/icon-192.png">

    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --accent: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.3);
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #475569;
        }

        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }

        .header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-bottom: 1px solid var(--border);
            padding: 12px 20px;
            position: sticky;
            top: 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
        }

        .header-content {
            max-width: 1600px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }

        .logo { display: flex; align-items: center; gap: 12px; }
        .logo-icon {
            width: 42px; height: 42px;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px;
            box-shadow: 0 0 20px var(--accent-glow);
        }
        .logo-text h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
        .logo-text span { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }

        .header-actions { display: flex; align-items: center; gap: 12px; }

        .alert-badge {
            position: relative;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 8px 14px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex; align-items: center; gap: 8px;
        }
        .alert-badge:hover { background: var(--border); }
        .alert-badge.active { border-color: var(--danger); animation: pulse 2s infinite; }

        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
            50% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
        }

        .alert-count {
            background: var(--danger); color: white;
            font-size: 11px; font-weight: bold;
            padding: 2px 6px; border-radius: 10px;
            min-width: 18px; text-align: center;
        }

        .status-indicator {
            display: flex; align-items: center; gap: 6px;
            font-size: 12px; color: var(--text-secondary);
        }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
            animation: blink 2s infinite;
        }
        .status-dot.offline { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

        .install-btn {
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border: none; color: white;
            padding: 8px 16px; border-radius: 8px;
            font-size: 12px; font-weight: 600;
            cursor: pointer;
            display: none; align-items: center; gap: 6px;
        }
        .install-btn.show { display: flex; }

        .main-layout {
            display: grid;
            grid-template-columns: 1fr 380px;
            max-width: 1600px;
            margin: 0 auto;
            gap: 0;
            min-height: calc(100vh - 70px);
        }
        @media (max-width: 1200px) { .main-layout { grid-template-columns: 1fr; } }

        .map-section { position: relative; height: calc(100vh - 70px); }
        #map { width: 100%; height: 100%; background: #1a1a2e; }

        .map-controls {
            position: absolute; top: 15px; right: 15px;
            z-index: 500;
            display: flex; flex-direction: column; gap: 8px;
        }
        .map-btn {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            width: 40px; height: 40px;
            border-radius: 10px; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
            transition: all 0.2s;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .map-btn:hover { background: var(--bg-card); transform: scale(1.05); }
        .map-btn.active { background: var(--accent); border-color: var(--accent); }

        .layer-menu {
            position: absolute; top: 55px; right: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px; padding: 8px;
            min-width: 160px;
            display: none;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }
        .layer-menu.show { display: block; }
        .layer-option {
            padding: 10px 14px; border-radius: 8px;
            cursor: pointer; font-size: 13px;
            display: flex; align-items: center; gap: 10px;
            transition: all 0.2s;
        }
        .layer-option:hover { background: var(--bg-card); }
        .layer-option.active { background: rgba(59, 130, 246, 0.2); color: var(--accent); }

        .sidebar {
            background: var(--bg-secondary);
            border-left: 1px solid var(--border);
            display: flex; flex-direction: column;
            height: calc(100vh - 70px);
            overflow: hidden;
        }
        .sidebar-tabs {
            display: flex;
            border-bottom: 1px solid var(--border);
            background: var(--bg-primary);
        }
        .sidebar-tab {
            flex: 1; padding: 14px 8px;
            background: none; border: none;
            color: var(--text-secondary);
            font-size: 12px; font-weight: 600;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            transition: all 0.2s;
            display: flex; align-items: center; justify-content: center; gap: 6px;
        }
        .sidebar-tab:hover { color: var(--text-primary); background: rgba(255,255,255,0.03); }
        .sidebar-tab.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

        .sidebar-content {
            flex: 1; overflow-y: auto; padding: 16px;
        }
        .sidebar-content::-webkit-scrollbar { width: 6px; }
        .sidebar-content::-webkit-scrollbar-track { background: transparent; }
        .sidebar-content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

        .stats-grid {
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 10px; margin-bottom: 16px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px; padding: 14px;
            text-align: center;
            transition: all 0.3s;
        }
        .stat-card:hover { border-color: var(--accent); transform: translateY(-2px); }
        .stat-card .value { font-size: 24px; font-weight: 700; color: var(--accent); line-height: 1; }
        .stat-card .label { font-size: 11px; color: var(--text-secondary); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-card .sub { font-size: 10px; color: var(--text-secondary); margin-top: 2px; }

        .flight-list-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 12px;
        }
        .flight-list-header h3 { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
        .flight-count {
            background: var(--accent); color: white;
            font-size: 11px; padding: 2px 8px;
            border-radius: 10px; font-weight: bold;
        }

        .flight-item {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px; padding: 14px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        .flight-item::before {
            content: ''; position: absolute;
            left: 0; top: 0; bottom: 0; width: 3px;
            background: var(--accent);
            opacity: 0; transition: opacity 0.3s;
        }
        .flight-item:hover { border-color: var(--accent); transform: translateX(4px); }
        .flight-item:hover::before { opacity: 1; }
        .flight-item.alert { border-color: var(--danger); }
        .flight-item.alert::before { background: var(--danger); opacity: 1; }

        .flight-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 8px;
        }
        .flight-callsign { font-size: 16px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
        .flight-badge {
            font-size: 10px; padding: 3px 8px;
            border-radius: 6px; font-weight: 600; text-transform: uppercase;
        }
        .badge-sesimbra { background: rgba(239, 68, 68, 0.2); color: #fca5a5; }
        .badge-setubal { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
        .badge-lisboa { background: rgba(34, 197, 94, 0.2); color: #86efac; }
        .badge-alert { background: rgba(239, 68, 68, 0.3); color: #fca5a5; animation: pulse 2s infinite; }

        .flight-details {
            display: grid; grid-template-columns: 1fr 1fr 1fr;
            gap: 8px; font-size: 12px;
        }
        .flight-detail { display: flex; flex-direction: column; gap: 2px; }
        .flight-detail .label { color: var(--text-secondary); font-size: 10px; text-transform: uppercase; }
        .flight-detail .value { color: var(--text-primary); font-weight: 600; }
        .flight-icao { font-size: 10px; color: var(--text-secondary); margin-top: 6px; font-family: monospace; }

        .chart-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px; padding: 16px;
            margin-bottom: 16px;
        }
        .chart-container h4 { font-size: 13px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
        .chart-wrapper { position: relative; height: 200px; }

        .alert-item {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(239, 68, 68, 0.05));
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px; padding: 14px;
            margin-bottom: 10px;
            animation: slideIn 0.3s ease;
        }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        .alert-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .alert-item h4 { font-size: 15px; color: #fca5a5; }
        .alert-time { font-size: 11px; color: var(--text-secondary); }
        .alert-details { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 12px; }
        .alert-detail { display: flex; justify-content: space-between; }
        .alert-detail .label { color: var(--text-secondary); }
        .alert-detail .value { color: var(--text-primary); font-weight: 600; }

        .no-alerts { text-align: center; padding: 40px 20px; color: var(--text-secondary); }
        .no-alerts i { font-size: 48px; margin-bottom: 12px; opacity: 0.5; }

        .region-legend {
            display: flex; gap: 12px; flex-wrap: wrap;
            margin-bottom: 16px; padding: 10px;
            background: var(--bg-card);
            border-radius: 10px; border: 1px solid var(--border);
        }
        .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
        .legend-dot { width: 10px; height: 10px; border-radius: 50%; }

        @media (max-width: 768px) {
            .header-content { padding: 0; }
            .logo-text h1 { font-size: 16px; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .flight-details { grid-template-columns: 1fr 1fr; }
            .sidebar { height: auto; max-height: 50vh; }
            .map-section { height: 50vh; }
            .main-layout { grid-template-columns: 1fr; }
        }

        .loading-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: var(--bg-primary);
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            z-index: 9999;
            transition: opacity 0.5s;
        }
        .loading-overlay.hidden { opacity: 0; pointer-events: none; }
        .spinner {
            width: 50px; height: 50px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-text { margin-top: 16px; color: var(--text-secondary); font-size: 14px; }

        .toast-container {
            position: fixed; bottom: 20px; right: 20px;
            z-index: 9999;
            display: flex; flex-direction: column; gap: 10px;
        }
        .toast {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px; padding: 14px 18px;
            display: flex; align-items: center; gap: 12px;
            animation: toastIn 0.3s ease;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
            max-width: 350px;
        }
        @keyframes toastIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        .toast.alert-toast { border-color: var(--danger); background: linear-gradient(135deg, rgba(239,68,68,0.1), var(--bg-secondary)); }
        .toast i { font-size: 20px; }
        .toast.alert-toast i { color: var(--danger); }

        .leaflet-popup-content-wrapper {
            background: var(--bg-secondary) !important;
            color: var(--text-primary) !important;
            border-radius: 12px !important;
            border: 1px solid var(--border) !important;
        }
        .leaflet-popup-tip { background: var(--bg-secondary) !important; }
        .leaflet-container { background: #1a1a2e !important; }
    </style>
</head>
<body>
    <div class="loading-overlay" id="loading">
        <div class="spinner"></div>
        <div class="loading-text">A inicializar SkyTracker...</div>
    </div>

    <div class="toast-container" id="toastContainer"></div>

    <header class="header">
        <div class="header-content">
            <div class="logo">
                <div class="logo-icon">✈️</div>
                <div class="logo-text">
                    <h1>SkyTracker 24/7</h1>
                    <span>Sesimbra & Regiao</span>
                </div>
            </div>
            <div class="header-actions">
                <div class="alert-badge" id="alertBadge" onclick="showAlertsTab()">
                    <i class="fas fa-bell"></i>
                    <span>Alertas</span>
                    <span class="alert-count" id="alertCount" style="display:none">0</span>
                </div>
                <div class="status-indicator">
                    <div class="status-dot" id="statusDot"></div>
                    <span id="statusText">Ligado</span>
                </div>
                <button class="install-btn" id="installBtn" onclick="installPWA()">
                    <i class="fas fa-download"></i> Instalar App
                </button>
            </div>
        </div>
    </header>

    <div class="main-layout">
        <div class="map-section">
            <div id="map"></div>
            <div class="map-controls">
                <button class="map-btn" id="layerBtn" onclick="toggleLayerMenu()" title="Camadas">
                    <i class="fas fa-layer-group"></i>
                </button>
                <div class="layer-menu" id="layerMenu">
                    <div class="layer-option active" onclick="setMapLayer('dark')" data-layer="dark">
                        <i class="fas fa-moon"></i> Escuro
                    </div>
                    <div class="layer-option" onclick="setMapLayer('satellite')" data-layer="satellite">
                        <i class="fas fa-satellite"></i> Satelite
                    </div>
                    <div class="layer-option" onclick="setMapLayer('terrain')" data-layer="terrain">
                        <i class="fas fa-mountain"></i> Terreno
                    </div>
                    <div class="layer-option" onclick="setMapLayer('standard')" data-layer="standard">
                        <i class="fas fa-map"></i> Padrao
                    </div>
                </div>
                <button class="map-btn" onclick="fitBounds()" title="Centrar">
                    <i class="fas fa-crosshairs"></i>
                </button>
                <button class="map-btn" onclick="toggleRegions()" title="Regioes" id="regionToggle">
                    <i class="fas fa-circle-notch"></i>
                </button>
            </div>
        </div>

        <div class="sidebar">
            <div class="sidebar-tabs">
                <button class="sidebar-tab active" onclick="setTab('flights')" data-tab="flights">
                    <i class="fas fa-plane"></i> Voos
                </button>
                <button class="sidebar-tab" onclick="setTab('stats')" data-tab="stats">
                    <i class="fas fa-chart-bar"></i> Stats
                </button>
                <button class="sidebar-tab" onclick="setTab('alerts')" data-tab="alerts">
                    <i class="fas fa-bell"></i> Alertas
                </button>
            </div>

            <div class="sidebar-content" id="sidebarContent">
                <div id="tab-flights">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="value" id="statTotal">0</div>
                            <div class="label">Voos Ativos</div>
                        </div>
                        <div class="stat-card">
                            <div class="value" id="statAircraft">0</div>
                            <div class="label">Aeronaves 24h</div>
                        </div>
                        <div class="stat-card">
                            <div class="value" id="statCountries">0</div>
                            <div class="label">Paises</div>
                        </div>
                        <div class="stat-card">
                            <div class="value" id="statMaxAlt">0</div>
                            <div class="label">Alt. Max</div>
                            <div class="sub">ft</div>
                        </div>
                    </div>

                    <div class="region-legend" id="regionLegend"></div>

                    <div class="flight-list-header">
                        <h3><i class="fas fa-plane-departure"></i> Voos em Tempo Real</h3>
                        <span class="flight-count" id="flightCount">0</span>
                    </div>
                    <div id="flightList"></div>
                </div>

                <div id="tab-stats" style="display:none">
                    <div class="chart-container">
                        <h4><i class="fas fa-chart-line"></i> Deteccoes por Hora</h4>
                        <div class="chart-wrapper"><canvas id="hourlyChart"></canvas></div>
                    </div>
                    <div class="chart-container">
                        <h4><i class="fas fa-globe"></i> Top Paises</h4>
                        <div class="chart-wrapper"><canvas id="countryChart"></canvas></div>
                    </div>
                    <div class="chart-container">
                        <h4><i class="fas fa-layer-group"></i> Distribuicao de Altitude</h4>
                        <div class="chart-wrapper"><canvas id="altitudeChart"></canvas></div>
                    </div>
                </div>

                <div id="tab-alerts" style="display:none">
                    <div id="alertsList">
                        <div class="no-alerts">
                            <i class="fas fa-bell-slash"></i>
                            <p>Nenhum alerta ativo</p>
                            <p style="font-size:12px; margin-top:8px">Configura ALERT_AIRCRAFT no Render</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <script>
    let map, ws;
    let flights = [];
    let regions = [];
    let alertAircraft = [];
    let markers = {};
    let regionCircles = [];
    let currentLayer = 'dark';
    let showRegions = true;
    let charts = {};
    let installPrompt = null;

    const mapLayers = {
        dark: L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; CARTO', subdomains: 'abcd', maxZoom: 19
        }),
        satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: '&copy; Esri', maxZoom: 19
        }),
        terrain: L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenTopoMap', subdomains: 'abc', maxZoom: 17
        }),
        standard: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap', subdomains: 'abc', maxZoom: 19
        })
    };

    async function init() {
        map = L.map('map', { zoomControl: false, attributionControl: false }).setView([38.5, -8.9], 9);
        mapLayers.dark.addTo(map);
        L.control.zoom({ position: 'bottomright' }).addTo(map);

        await fetchRegions();
        await fetchFlights();
        await fetchStats();
        await fetchAlerts();

        drawRegions();
        connectWebSocket();
        setupPWA();

        setTimeout(() => {
            document.getElementById('loading').classList.add('hidden');
        }, 1000);

        setInterval(fetchStats, 60000);
        setInterval(fetchAlerts, 30000);
    }

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => { updateStatus(true); };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'update' || data.type === 'init') {
                flights = data.flights || [];
                regions = data.regions || regions;
                alertAircraft = data.alert_aircraft || [];
                updateFlightsList();
                updateMapMarkers();
                updateStats(data.stats);
                updateAlertBadge(data.pending_alerts || 0);
            }
        };

        ws.onclose = () => { updateStatus(false); setTimeout(connectWebSocket, 3000); };
        ws.onerror = (err) => { console.error('WebSocket erro:', err); };

        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 30000);
    }

    function updateStatus(online) {
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        if (online) { dot.classList.remove('offline'); text.textContent = 'Em Tempo Real'; }
        else { dot.classList.add('offline'); text.textContent = 'A reconectar...'; }
    }

    async function fetchRegions() {
        try {
            const res = await fetch('/api/regions');
            const data = await res.json();
            regions = data.regions;
            updateRegionLegend();
        } catch (e) { console.error('Erro ao carregar regioes:', e); }
    }

    function drawRegions() {
        regionCircles.forEach(c => map.removeLayer(c));
        regionCircles = [];
        if (!showRegions) return;

        regions.forEach(region => {
            const circle = L.circle([region.lat, region.lon], {
                radius: region.radius_km * 1000,
                color: region.color, fillColor: region.color,
                fillOpacity: 0.08, weight: 2, dashArray: '5, 10'
            }).addTo(map);
            circle.bindPopup(`<div style="font-family:Segoe UI,sans-serif"><strong style="color:${region.color};font-size:16px">${region.name}</strong><br><span style="color:#94a3b8">Raio: ${region.radius_km}km</span></div>`);
            regionCircles.push(circle);

            const label = L.marker([region.lat, region.lon], {
                icon: L.divIcon({
                    className: 'region-label',
                    html: `<div style="background:${region.color};color:white;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:bold;white-space:nowrap;">${region.name}</div>`,
                    iconSize: [80, 20], iconAnchor: [40, 10]
                })
            }).addTo(map);
            regionCircles.push(label);
        });
    }

    function updateRegionLegend() {
        const container = document.getElementById('regionLegend');
        container.innerHTML = regions.map(r => `
            <div class="legend-item">
                <div class="legend-dot" style="background:${r.color}"></div>
                <span>${r.name} (${r.radius_km}km)</span>
            </div>
        `).join('');
    }

    function toggleRegions() {
        showRegions = !showRegions;
        document.getElementById('regionToggle').classList.toggle('active', showRegions);
        drawRegions();
    }

    function updateMapMarkers() {
        const currentIds = new Set(flights.map(f => f.icao24));
        Object.keys(markers).forEach(id => {
            if (!currentIds.has(id)) { map.removeLayer(markers[id]); delete markers[id]; }
        });

        flights.forEach(flight => {
            const isAlert = alertAircraft.some(a => 
                flight.callsign?.toUpperCase().includes(a.toUpperCase()) ||
                flight.icao24?.toUpperCase() === a.toUpperCase()
            );
            const color = flight.region_color || '#3b82f6';
            const size = isAlert ? 24 : 18;

            const iconHtml = `<div style="width:${size}px;height:${size}px;background:${isAlert ? '#ef4444' : color};border:2px solid white;border-radius:50%;box-shadow:0 0 12px ${isAlert ? 'rgba(239,68,68,0.6)' : color + '80'};display:flex;align-items:center;justify-content:center;transform:rotate(${flight.heading || 0}deg);transition:all 0.3s;"><svg width="${size-6}" height="${size-6}" viewBox="0 0 24 24" fill="white"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg></div>`;

            if (markers[flight.icao24]) {
                markers[flight.icao24].setLatLng([flight.latitude, flight.longitude]);
            } else {
                const marker = L.marker([flight.latitude, flight.longitude], {
                    icon: L.divIcon({ className: 'plane-marker', html: iconHtml, iconSize: [size, size], iconAnchor: [size/2, size/2] })
                }).addTo(map);
                marker.bindPopup(createPopupContent(flight));
                markers[flight.icao24] = marker;
            }
        });
    }

    function createPopupContent(flight) {
        const isAlert = alertAircraft.some(a => flight.callsign?.toUpperCase().includes(a.toUpperCase()));
        return `<div style="font-family:Segoe UI,sans-serif;min-width:200px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:16px;color:${isAlert ? '#ef4444' : '#3b82f6'}">${flight.callsign || 'N/A'}</strong>${isAlert ? '<span style="background:#ef4444;color:white;padding:2px 8px;border-radius:10px;font-size:10px">ALERTA</span>' : ''}</div><div style="font-size:12px;color:#94a3b8;margin-bottom:8px">${flight.origin_country || 'Desconhecido'}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px"><div><span style="color:#64748b">Altitude:</span> <strong>${flight.altitude?.toFixed(0) || 0} ft</strong></div><div><span style="color:#64748b">Velocidade:</span> <strong>${flight.velocity?.toFixed(0) || 0} km/h</strong></div><div><span style="color:#64748b">Heading:</span> <strong>${flight.heading?.toFixed(0) || 0}°</strong></div><div><span style="color:#64748b">Regiao:</span> <strong style="color:${flight.region_color || '#3b82f6'}">${flight.region || 'N/A'}</strong></div><div><span style="color:#64748b">Distancia:</span> <strong>${flight.distance_km?.toFixed(1) || 0} km</strong></div><div><span style="color:#64748b">ICAO24:</span> <strong>${flight.icao24?.toUpperCase() || 'N/A'}</strong></div></div></div>`;
    }

    function updateFlightsList() {
        const container = document.getElementById('flightList');
        const count = document.getElementById('flightCount');
        count.textContent = flights.length;

        if (flights.length === 0) {
            container.innerHTML = `<div class="no-alerts"><i class="fas fa-satellite-dish"></i><p>Nenhum aviao detetado</p><p style="font-size:12px;margin-top:8px">A aguardar dados da OpenSky...</p></div>`;
            return;
        }

        container.innerHTML = flights.map(f => {
            const isAlert = alertAircraft.some(a => f.callsign?.toUpperCase().includes(a.toUpperCase()) || f.icao24?.toUpperCase() === a.toUpperCase());
            const regionClass = f.region ? `badge-${f.region.toLowerCase().replace(/[^a-z]/g, '')}` : 'badge-sesimbra';
            return `<div class="flight-item ${isAlert ? 'alert' : ''}" onclick="focusFlight('${f.icao24}')"><div class="flight-header"><div class="flight-callsign"><span>${f.callsign || 'N/A'}</span></div><span class="flight-badge ${isAlert ? 'badge-alert' : regionClass}">${isAlert ? 'ALERTA' : (f.region || 'N/A')}</span></div><div class="flight-details"><div class="flight-detail"><span class="label">Altitude</span><span class="value">${f.altitude?.toFixed(0) || 0} ft</span></div><div class="flight-detail"><span class="label">Velocidade</span><span class="value">${f.velocity?.toFixed(0) || 0} km/h</span></div><div class="flight-detail"><span class="label">Distancia</span><span class="value">${f.distance_km?.toFixed(1) || 0} km</span></div></div><div class="flight-icao">${f.icao24?.toUpperCase() || 'N/A'} | ${f.origin_country || 'Desconhecido'}</div></div>`;
        }).join('');
    }

    function focusFlight(icao24) {
        const flight = flights.find(f => f.icao24 === icao24);
        if (flight && map) {
            map.setView([flight.latitude, flight.longitude], 13);
            if (markers[icao24]) markers[icao24].openPopup();
        }
    }

    function updateStats(stats) {
        if (!stats) return;
        document.getElementById('statTotal').textContent = flights.length;
        document.getElementById('statAircraft').textContent = stats.unique_aircraft || 0;
        document.getElementById('statCountries').textContent = stats.unique_countries || 0;
        document.getElementById('statMaxAlt').textContent = (stats.max_altitude || 0).toLocaleString();
    }

    async function fetchStats() {
        try {
            const res = await fetch('/api/stats?hours=24');
            const data = await res.json();
            updateStats(data.stats);
            updateCharts(data);
        } catch (e) { console.error('Erro ao carregar stats:', e); }
    }

    async function fetchFlights() {
        try {
            const res = await fetch('/api/flights');
            const data = await res.json();
            flights = data.flights;
            updateFlightsList();
            updateMapMarkers();
        } catch (e) { console.error('Erro ao carregar voos:', e); }
    }

    function updateCharts(data) {
        const colors = { primary: '#3b82f6', secondary: '#8b5cf6', success: '#22c55e', warning: '#f59e0b', danger: '#ef4444' };

        const hourlyCtx = document.getElementById('hourlyChart');
        if (hourlyCtx) {
            const hourlyData = data.hourly || [];
            const labels = hourlyData.map(h => `${h._id}:00`);
            const values = hourlyData.map(h => h.count);
            if (charts.hourly) charts.hourly.destroy();
            charts.hourly = new Chart(hourlyCtx, {
                type: 'line',
                data: { labels: labels, datasets: [{ label: 'Deteccoes', data: values, borderColor: colors.primary, backgroundColor: colors.primary + '20', fill: true, tension: 0.4, pointRadius: 3, pointBackgroundColor: colors.primary }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#334155' } }, y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#334155' } } } }
            });
        }

        const countryCtx = document.getElementById('countryChart');
        if (countryCtx) {
            const countryData = data.countries || [];
            const chartColors = [colors.primary, colors.secondary, colors.success, colors.warning, colors.danger, '#ec4899', '#14b8a6', '#f97316'];
            if (charts.country) charts.country.destroy();
            charts.country = new Chart(countryCtx, {
                type: 'doughnut',
                data: { labels: countryData.map(c => c._id), datasets: [{ data: countryData.map(c => c.count), backgroundColor: chartColors, borderWidth: 0 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } } } }
            });
        }

        const altCtx = document.getElementById('altitudeChart');
        if (altCtx) {
            const altData = data.altitude || [];
            const altLabels = ['0-1k', '1-5k', '5-10k', '10-20k', '20-30k', '30-40k', '40k+'];
            const altValues = altLabels.map((_, i) => { const item = altData.find(a => a._id === i); return item ? item.count : 0; });
            if (charts.altitude) charts.altitude.destroy();
            charts.altitude = new Chart(altCtx, {
                type: 'bar',
                data: { labels: altLabels, datasets: [{ label: 'Aeronaves', data: altValues, backgroundColor: colors.secondary + '80', borderColor: colors.secondary, borderWidth: 1, borderRadius: 6 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#334155' } } } }
            });
        }
    }

    async function fetchAlerts() {
        try {
            const res = await fetch('/api/alerts');
            const data = await res.json();
            updateAlertsList(data.alerts);
            updateAlertBadge(data.alerts.filter(a => !a.notified).length);
        } catch (e) { console.error('Erro ao carregar alertas:', e); }
    }

    function updateAlertsList(alerts) {
        const container = document.getElementById('alertsList');
        if (!alerts || alerts.length === 0) {
            container.innerHTML = `<div class="no-alerts"><i class="fas fa-bell-slash"></i><p>Nenhum alerta ativo</p><p style="font-size:12px; margin-top:8px">Configura ALERT_AIRCRAFT no Render</p></div>`;
            return;
        }
        container.innerHTML = alerts.map(a => {
            const time = new Date(a.alert_time).toLocaleString('pt-PT');
            return `<div class="alert-item"><div class="alert-item-header"><h4><i class="fas fa-plane"></i> ${a.callsign || 'N/A'}</h4><span class="alert-time">${time}</span></div><div class="alert-details"><div class="alert-detail"><span class="label">Regiao:</span><span class="value">${a.region || 'N/A'}</span></div><div class="alert-detail"><span class="label">ICAO24:</span><span class="value">${a.icao24?.toUpperCase() || 'N/A'}</span></div><div class="alert-detail"><span class="label">Altitude:</span><span class="value">${a.altitude?.toFixed(0) || 0} ft</span></div><div class="alert-detail"><span class="label">Velocidade:</span><span class="value">${a.velocity?.toFixed(0) || 0} km/h</span></div><div class="alert-detail"><span class="label">Distancia:</span><span class="value">${a.distance_km?.toFixed(1) || 0} km</span></div><div class="alert-detail"><span class="label">Pais:</span><span class="value">${a.origin_country || 'N/A'}</span></div></div></div>`;
        }).join('');
    }

    function updateAlertBadge(count) {
        const badge = document.getElementById('alertCount');
        const alertBadge = document.getElementById('alertBadge');
        if (count > 0) { badge.textContent = count; badge.style.display = 'inline-block'; alertBadge.classList.add('active'); }
        else { badge.style.display = 'none'; alertBadge.classList.remove('active'); }
    }

    function showAlertsTab() { setTab('alerts'); }

    function setTab(tab) {
        document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`.sidebar-tab[data-tab="${tab}"]`).classList.add('active');
        document.getElementById('tab-flights').style.display = tab === 'flights' ? 'block' : 'none';
        document.getElementById('tab-stats').style.display = tab === 'stats' ? 'block' : 'none';
        document.getElementById('tab-alerts').style.display = tab === 'alerts' ? 'block' : 'none';
        if (tab === 'stats') fetchStats();
        if (tab === 'alerts') fetchAlerts();
    }

    function toggleLayerMenu() { document.getElementById('layerMenu').classList.toggle('show'); }

    function setMapLayer(layer) {
        currentLayer = layer;
        Object.values(mapLayers).forEach(l => map.removeLayer(l));
        mapLayers[layer].addTo(map);
        document.querySelectorAll('.layer-option').forEach(opt => opt.classList.remove('active'));
        document.querySelector(`.layer-option[data-layer="${layer}"]`).classList.add('active');
        document.getElementById('layerMenu').classList.remove('show');
    }

    function fitBounds() {
        if (regions.length > 0) {
            const group = new L.featureGroup(regionCircles.filter(c => c.getBounds));
            if (group.getBounds().isValid()) map.fitBounds(group.getBounds().pad(0.2));
            else map.setView([38.5, -8.9], 9);
        }
    }

    function setupPWA() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/service-worker.js')
                .then(reg => console.log('SW registado:', reg))
                .catch(err => console.log('SW erro:', err));
        }
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            installPrompt = e;
            document.getElementById('installBtn').classList.add('show');
        });
        if (window.matchMedia('(display-mode: standalone)').matches) {
            document.getElementById('installBtn').style.display = 'none';
        }
    }

    async function installPWA() {
        if (installPrompt) {
            installPrompt.prompt();
            const result = await installPrompt.userChoice;
            if (result.outcome === 'accepted') {
                showToast('App instalado com sucesso!', 'success');
                document.getElementById('installBtn').classList.remove('show');
            }
            installPrompt = null;
        }
    }

    function showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type === 'alert' ? 'alert-toast' : ''}`;
        toast.innerHTML = `<i class="fas ${type === 'alert' ? 'fa-bell' : 'fa-info-circle'}"></i><span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(100%)'; setTimeout(() => toast.remove(), 300); }, 5000);
    }

    document.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    worker_task = asyncio.create_task(start_worker())
    yield
    worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="SkyTracker 24/7", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

async def broadcast_updates():
    """Envia atualizacoes para todos os clientes WebSocket"""
    while True:
        try:
            if manager.active_connections:
                flights = await get_active_flights()
                regions = get_regions()

                # Stats com fallback para evitar erro
                try:
                    stats = await get_stats(hours=24)
                except Exception as e:
                    print(f"⚠️ Stats erro (usando fallback): {e}")
                    stats = {
                        "total_detections": 0, "unique_aircraft": 0,
                        "unique_countries": 0, "max_altitude": 0,
                        "avg_altitude": 0, "max_speed": 0
                    }

                try:
                    pending_alerts = len(await get_pending_alerts())
                except:
                    pending_alerts = 0

                await manager.broadcast({
                    "type": "update",
                    "flights": flights,
                    "regions": regions,
                    "stats": stats,
                    "pending_alerts": pending_alerts,
                    "timestamp": datetime.utcnow().isoformat()
                })
            await asyncio.sleep(10)
        except Exception as e:
            print(f"WebSocket broadcast erro: {e}")
            await asyncio.sleep(10)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        flights = await get_active_flights()
        regions = get_regions()

        try:
            stats = await get_stats(hours=24)
        except:
            stats = {"total_detections": 0, "unique_aircraft": 0, "unique_countries": 0, "max_altitude": 0, "avg_altitude": 0, "max_speed": 0}

        await websocket.send_json({
            "type": "init",
            "flights": flights,
            "regions": regions,
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        })

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket erro: {e}")
        manager.disconnect(websocket)

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "worker": {
            "running": worker.running,
            "total_polls": worker.stats["total_polls"],
            "last_poll": worker.stats["last_poll_time"]
        }
    }

@app.get("/api/flights")
async def get_flights(region: str = Query(None)):
    region_filter = {"name": region} if region else None
    flights = await get_active_flights(region_filter)
    return {"flights": flights, "count": len(flights), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/flights/refresh")
async def refresh_flights():
    flights = await fetch_all_regions()
    from worker import SkyTrackerWorker
    temp_worker = SkyTrackerWorker()
    await temp_worker.process_flights(flights)
    return {"flights": flights, "count": len(flights), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/regions")
async def get_regions_api():
    return {"regions": get_regions()}

@app.get("/api/stats")
async def get_stats_api(hours: int = Query(24, ge=1, le=168)):
    try:
        stats = await get_stats(hours=hours)
        hourly = await get_hourly_stats(hours=hours)
        countries = await get_country_stats(hours=hours)
        altitude = await get_altitude_distribution(hours=hours)
    except Exception as e:
        print(f"Stats API erro: {e}")
        stats = {"total_detections": 0, "unique_aircraft": 0, "unique_countries": 0, "max_altitude": 0, "avg_altitude": 0, "max_speed": 0}
        hourly = []
        countries = []
        altitude = []

    return {"stats": stats, "hourly": hourly, "countries": countries, "altitude": altitude, "hours": hours}

@app.get("/api/alerts")
async def get_alerts(pending_only: bool = Query(False)):
    if pending_only:
        alerts = await get_pending_alerts()
    else:
        alerts = await get_all_alerts()
    return {"alerts": alerts, "count": len(alerts)}

@app.post("/api/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    await mark_alert_notified(alert_id)
    return {"status": "ok", "message": "Alerta marcado como lido"}

@app.post("/api/cleanup")
async def trigger_cleanup(days: int = Query(7, ge=1, le=30)):
    result = await cleanup_old_data(days=days)
    return {"status": "ok", "result": result}

@app.get("/api/worker/stats")
async def get_worker_stats():
    return {
        "running": worker.running,
        "stats": worker.stats,
        "regions": get_regions(),
        "alert_aircraft": [a.strip() for a in os.getenv("ALERT_AIRCRAFT", "").split(",") if a.strip()]
    }

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/manifest.json")
async def get_manifest():
    return {
        "name": "SkyTracker 24/7",
        "short_name": "SkyTracker",
        "description": "Rastreamento de avioes em tempo real - Sesimbra, Portugal",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#3b82f6",
        "orientation": "any",
        "icons": [
            {"src": "/icon-72.png", "sizes": "72x72", "type": "image/png"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }

@app.get("/service-worker.js", response_class=HTMLResponse)
async def get_service_worker():
    content = """
const CACHE_NAME = 'skytracker-v1';
const urlsToCache = ['/'];
self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
    self.skipWaiting();
});
self.addEventListener('fetch', event => {
    event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});
"""
    return HTMLResponse(content=content, media_type="application/javascript")

@app.on_event("startup")
async def startup_broadcast():
    asyncio.create_task(broadcast_updates())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
