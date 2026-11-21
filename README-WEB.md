# ForeCast Web · Django + FastAPI

Mandantenfähige Webumsetzung der ursprünglichen PyQt6-Anwendung. Die desktopunabhängige Prognoselogik steht in `forecast_engine.py` (aus `main.py` extrahiert). Die Desktop-Anwendung bleibt vorerst erhalten.

## Architektur

- Django: Registrierung, Session-Login, CSRF, Benutzer, Rollen, Mandanten und Admin.
- FastAPI: `GET /api/dashboard` (Session-basiert), `GET /api/health`. Derselbe ASGI-Prozess bedient die Oberfläche.
- Django ORM: PostgreSQL über `DATABASE_URL`, sonst SQLite.
- Jede Verkaufsposition hat eine mandantenlokale Eindeutigkeitskennung. Rollen: Owner/Admin (Import, Einstellungen, Mitglieder), Member (Import), Viewer (Lesen).
- CSV Import: Pflichtspalten wie im Desktop, FF001-Markierung und weitere Prognosefilter bleiben erhalten.
- Import-Historie zeigt Datensatzanzahl, neue Positionen und automatisch ausgeschlossene Dubletten.

### Wie Dubletten erkannt werden

Für jede Quellzeile wird ein kanonischer SHA-256-Fingerprint über alle CSV-Spalten gebildet, unabhängig von Spaltenreihenfolge und Dateiname. Identische Zeilen werden mit laufender Vorkommensnummer versehen, damit mehrere vollständig identische Verkaufspositionen *innerhalb derselben Datei* nicht versehentlich zusammenfallen. Bei erneutem Upload derselben Datei werden dieselben Vorkommensschlüssel generiert und verworfen. Ein Unique-Constraint auf `(tenant, fingerprint)` schützt vor parallelen identischen Imports. Ein Überschneiden zweier Exporte mit unterschiedlich abgeschnittenen identischen Positionen kann ohne stabile Positions-ID nicht in jedem Fall perfekt aufgelöst werden; für SumUp-Exporte mit stabilen eindeutigen Zeilenfeldern ist die Zuordnung belastbarer.

## EasyPanel / Nixpacks

1. PostgreSQL-Datenbank in EasyPanel erstellen, ihr persistentes Volume nutzen.
2. Web-Service aus GitHub-Repository mit Buildtyp **Nixpacks**, Port **8000**, Startkommando `bash ./start-web.sh` anlegen.
3. Umgebungsvariablen nach `.env.example` setzen:
   - `DJANGO_SECRET_KEY` mit kryptografisch zufälligem Wert (mindestens 32 Bytes)
   - `DATABASE_URL=postgresql://USER:PASS@HOST:5432/DB`
   - `ALLOWED_HOSTS=forecast.example.com`
   - `CSRF_TRUSTED_ORIGINS=https://forecast.example.com`
   - `SESSION_COOKIE_SECURE=true` und `CSRF_COOKIE_SECURE=true`
   - `PORT=8000`
4. HTTPS in EasyPanel aktivieren. Das Startskript führt `migrate` und `collectstatic` aus, dann startet Uvicorn.
5. Erste Person registriert sich über `/register/` und legt einen eigenen Mandanten an.
6. Django-Superuser optional über EasyPanel-Terminal: `python manage.py createsuperuser` (Admin: `/admin/`).

Für eine lokale Testumgebung:
```sh
python -m pip install -r requirements-web.txt
DJANGO_SECRET_KEY=local-secret DJANGO_DEBUG=true python manage.py migrate
DJANGO_SECRET_KEY=local-secret DJANGO_DEBUG=true uvicorn webapp.asgi:application --reload --port 8000
```
SQLite funktioniert lokal ohne `DATABASE_URL`; bei containerisiertem SQLite unbedingt persistentes Volume bereitstellen.

## Sicherheit

- Normale Nutzer dürfen Mandanten nur über Mitgliedschaft betreten; Benutzer dürfen nur Daten ihrer aktiven Organisation abrufen.
- Imports und Einstellungen prüfen die Rolle serverseitig. Datenbank-Unique-Constraint wirkt nur innerhalb des Mandanten.
- Registrieren ist derzeit offen. Für geschlossene Installationen sollte Self-Signup deaktiviert oder um Einladungen ergänzt werden.
- Vor öffentlichem Produktionsbetrieb: CSRF-/Session-/Rollenintegration, FastAPI-Endpunkte und Deployment mit einer realen Postgres-Instanz testen, HTTPS und Backups einrichten.
