# ForeCast — Webanwendung

ForeCast ist eine **mobile-first** Webanwendung für SumUp-Verkaufsanalysen und kalenderwochenbasierte Umsatzprognosen. Die Anwendung verwendet **Django + FastAPI** mit **PostgreSQL** (Produktion) oder **SQLite** (lokale Entwicklung). Es gibt keine Desktop-GUI oder plattformspezifischen Startskripte.

## Funktionen
- Django-Login, Registrierung und Benutzerverwaltung
- Mehrere Mandanten pro Benutzer, rollenbasierte Mitgliedschaften (Inhaber, Administrator, Mitglied, Leser)
- Mandantenisolierte SumUp-CSV-Importe, automatische Dublettenprüfung, Importhistorie
- Umsatzanalyse nach Tagen, Stunden, Kategorien und Artikeln
- KW-Prognosen: Basis, Moderat und Optimistisch; Wachstum, Saisonfaktoren und Historienmodus
- Responsive mobile-first Dashboard mit touchfreundlichen Eingaben und Diagrammen
- Excel-Export, mandantenbezogene Einstellungen und Reset auf Standardwerte

## EasyPanel (Nixpacks)
1. GitHub-Repository als EasyPanel-App mit **Nixpacks** verbinden.
2. PostgreSQL mit persistentem Speicher anlegen.
3. Umgebungsvariablen konfigurieren:
   ```env
   DJANGO_SECRET_KEY=<langes-zufaelliges-secret>
   DJANGO_DEBUG=false
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
   ALLOWED_HOSTS=forecast.example.com
   CSRF_TRUSTED_ORIGINS=https://forecast.example.com
   SESSION_COOKIE_SECURE=true
   CSRF_COOKIE_SECURE=true
   PORT=8000
   ```
4. App-Port `8000`, Domain und HTTPS im EasyPanel konfigurieren.
5. Das `nixpacks.toml` installiert `requirements-web.txt`; `start-web.sh` führt Migrationen und `collectstatic` aus und startet den ASGI-Server.
6. Über `/register/` einen ersten Benutzer mit eigenem Mandanten registrieren.

## Lokal starten
```bash
python -m pip install -r requirements-web.txt
export DJANGO_SECRET_KEY=development-only-secret
export DJANGO_DEBUG=true
python manage.py migrate
uvicorn webapp.asgi:application --reload --port 8000
```
Ohne `DATABASE_URL` wird SQLite verwendet. **SQLite-Dateien im Container benötigen ein persistentes Volume.**

## Struktur
- `forecast_engine.py`: reine pandas-/NumPy-Berechnung ohne Desktop-Abhängigkeiten
- `forecast/`: Django-Datenmodelle, Authentifizierung, API und Import-/Dedup-Logik
- `webapp/`: Django-/ASGI-Konfiguration und FastAPI-Mount
- `templates/`, `static/`: responsive Weboberfläche
- `start-web.sh`, `nixpacks.toml`: EasyPanel-Deployment

## Sicherheit und Validierung
Mandantenzugriff wird über Django-Mitgliedschaften geprüft. Für jede CSV-Zeile wird ein stabiler Hash mit Vorkommensindex erzeugt, der pro Mandant eindeutig ist. Exakt gleiche, bereits importierte Zeilen werden übersprungen. Bei überlappenden Exporten mit vollständig identischen, aber tatsächlich verschiedenen Transaktionen ist eine eindeutige SumUp-Positions-ID für perfekte Deduplizierung erforderlich.

**Vor produktivem Einsatz** sind vollständige Tests der Migrationen, CSV-Verarbeitung, Session-Authentifizierung, Mandantentrennung und des EasyPanel-Deployments notwendig.
