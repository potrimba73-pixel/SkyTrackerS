# SkyTracker 24/7 - Sesimbra

App de rastreamento de avioes em tempo real com multi-regiao, alertas por email, graficos Chart.js e PWA.

## Funcionalidades

- Mapa interativo com 4 camadas (Escuro, Satelite, Terreno, Padrao)
- Multi-regiao: Sesimbra, Setubal, Lisboa (configuravel)
- Alertas por email quando avioes especificos sao detetados
- Graficos Chart.js: deteccoes por hora, top paises, distribuicao de altitude
- PWA: Instala como app no telemovel
- WebSocket: Atualizacoes em tempo real
- MongoDB: Historico completo de voos
- Limpeza automatica de dados antigos

## Deploy no Render

### 1. MongoDB Atlas (Gratis)
1. Vai a mongodb.com/cloud
2. Cria conta -> cluster Shared/Free Tier
3. Network Access -> adiciona 0.0.0.0/0
4. Copia a connection string

### 2. Render (Gratis)
1. Vai a render.com
2. New -> Blueprint -> conecta o teu GitHub
3. Seleciona o repo com este projeto
4. Render vai ler o render.yaml automaticamente

Ou manualmente:
1. New -> Web Service
2. Conecta GitHub ou faz upload do ZIP
3. Build: pip install -r requirements.txt
4. Start: uvicorn main:app --host 0.0.0.0 --port $PORT
5. Adiciona as variaveis de ambiente

### 3. UptimeRobot (Gratis - mantem acordado 24/7)
1. Vai a uptimerobot.com
2. Add Monitor -> HTTP(s)
3. URL: https://skytracker-xxx.onrender.com/api/health
4. Intervalo: 5 minutos

## Variaveis de Ambiente

| Variavel | Obrigatoria | Descricao |
|----------|-------------|-----------|
| MONGODB_URI | Sim | Connection string do MongoDB Atlas |
| REGIONS | Nao | JSON array com regioes |
| ALERT_AIRCRAFT | Nao | Callsigns separados por virgula |
| SMTP_HOST | Nao | Servidor SMTP |
| SMTP_PORT | Nao | Porta SMTP (default: 587) |
| SMTP_USER | Nao | Email de envio |
| SMTP_PASS | Nao | Password/app password |
| ALERT_EMAIL | Nao | Email que recebe os alertas |
| POLL_INTERVAL | Nao | Segundos entre polls (default: 30) |
| CLEANUP_DAYS | Nao | Dias para manter dados (default: 7) |

## Regioes Pre-configuradas

| Regiao | Centro | Raio |
|--------|--------|------|
| Sesimbra | 38.4435N, 9.1015W | 80km |
| Setubal | 38.5244N, 8.8882W | 60km |
| Lisboa | 38.7223N, 9.1393W | 70km |

## Configurar Email (Gmail)

1. Ativa 2-Step Verification na conta Google
2. Vai a myaccount.google.com/apppasswords
3. Gera uma app password para "Mail"
4. Configura no Render:
   - SMTP_HOST: smtp.gmail.com
   - SMTP_PORT: 587
   - SMTP_USER: teuemail@gmail.com
   - SMTP_PASS: xxxx xxxx xxxx xxxx (app password)
   - ALERT_EMAIL: teuemail@gmail.com

## Instalar como App (PWA)

1. Abre o site no Chrome/Safari no telemovel
2. Clica no menu -> "Adicionar ao ecra inicial"
3. O SkyTracker funciona como app nativa!

## API Endpoints

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| /api/health | GET | Health check |
| /api/flights | GET | Voos ativos |
| /api/flights/refresh | GET | Forca atualizacao |
| /api/regions | GET | Regioes configuradas |
| /api/stats | GET | Estatisticas + graficos |
| /api/alerts | GET | Alertas |
| /api/alerts/{id}/dismiss | POST | Marca alerta como lido |
| /ws | WebSocket | Dados em tempo real |

## Custos

| Servico | Custo |
|---------|-------|
| OpenSky Network | 0 |
| MongoDB Atlas Free Tier | 0 |
| Render Web Service Free | 0 |
| UptimeRobot Free | 0 |
| Total | 0/mes |
