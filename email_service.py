import os
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "SkyTracker <noreply@skytracker.pt>")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")

async def send_alert_email(flight_data: dict, region_name: str = "Sesimbra") -> bool:
    """Envia email de alerta quando aviao especifico e detetado"""

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_EMAIL]):
        print("⚠️ Configuracao de email incompleta. Alerta nao enviado.")
        return False

    try:
        callsign = flight_data.get("callsign", "Desconhecido").strip()
        icao24 = flight_data.get("icao24", "N/A")
        altitude = flight_data.get("altitude", 0)
        velocity = flight_data.get("velocity", 0)
        distance = flight_data.get("distance_km", 0)
        lat = flight_data.get("latitude", 0)
        lon = flight_data.get("longitude", 0)
        country = flight_data.get("origin_country", "Desconhecido")

        subject = f"🛫 SkyTracker Alerta: {callsign} detetado em {region_name}!"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 16px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; color: white; font-size: 24px; }}
                .header .icon {{ font-size: 48px; margin-bottom: 10px; }}
                .content {{ padding: 30px; }}
                .flight-card {{ background: #334155; border-radius: 12px; padding: 20px; margin: 15px 0; }}
                .flight-card h2 {{ margin: 0 0 10px 0; color: #60a5fa; font-size: 28px; }}
                .detail {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #475569; }}
                .detail:last-child {{ border-bottom: none; }}
                .label {{ color: #94a3b8; }}
                .value {{ color: #e2e8f0; font-weight: 600; }}
                .badge {{ display: inline-block; background: #ef4444; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
                .map-link {{ display: block; text-align: center; background: #3b82f6; color: white; padding: 15px; border-radius: 8px; text-decoration: none; margin-top: 20px; font-weight: bold; }}
                .map-link:hover {{ background: #2563eb; }}
                .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="icon">✈️</div>
                    <h1>SkyTracker Alerta</h1>
                </div>
                <div class="content">
                    <p>Um aviao da tua lista de alertas foi detetado na regiao de <strong>{region_name}</strong>!</p>

                    <div class="flight-card">
                        <h2>{callsign} <span class="badge">ALERTA</span></h2>
                        <div class="detail">
                            <span class="label">ICAO24</span>
                            <span class="value">{icao24.upper()}</span>
                        </div>
                        <div class="detail">
                            <span class="label">Pais de Origem</span>
                            <span class="value">{country}</span>
                        </div>
                        <div class="detail">
                            <span class="label">Altitude</span>
                            <span class="value">{altitude:,.0f} ft</span>
                        </div>
                        <div class="detail">
                            <span class="label">Velocidade</span>
                            <span class="value">{velocity:,.0f} km/h</span>
                        </div>
                        <div class="detail">
                            <span class="label">Distancia de {region_name}</span>
                            <span class="value">{distance:.1f} km</span>
                        </div>
                        <div class="detail">
                            <span class="label">Coordenadas</span>
                            <span class="value">{lat:.4f}, {lon:.4f}</span>
                        </div>
                        <div class="detail">
                            <span class="label">Hora da Detecao</span>
                            <span class="value">{datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')} UTC</span>
                        </div>
                    </div>

                    <a href="https://www.google.com/maps?q={lat},{lon}" class="map-link" target="_blank">
                        📍 Ver Localizacao no Google Maps
                    </a>
                </div>
                <div class="footer">
                    SkyTracker 24/7 | Sesimbra, Portugal<br>
                    Alerta automatico gerado em {datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')} UTC
                </div>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = ALERT_EMAIL

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=SMTP_USER,
            password=SMTP_PASS
        )

        print(f"📧 Email de alerta enviado para {ALERT_EMAIL}: {callsign}")
        return True

    except Exception as e:
        print(f"❌ Erro ao enviar email: {e}")
        return False
