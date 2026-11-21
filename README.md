# ForeCast

Desktop-Anwendung zur Analyse von SumUp-Verkaufsberichten (CSV) und zur Erstellung kalenderwochenbasierter Verkaufsprognosen für den Kiosk.

**Repository:** https://github.com/fatih4159/sumup_forecast  
**Technik:** Python 3.10+, PyQt6, pandas, NumPy, Matplotlib und openpyxl.

**Installation & Start**

```bash
python -m pip install -r requirements.txt
python main.py
```

Alternativ sind Startskripte enthalten: `start-linux.sh` (Bazzite/Linux), `start-macos.command` und `start-windows.bat`/`start-windows.ps1`. Die Skripte richten lokal eine `.venv` ein.

**Funktionen**

- CSV-Import, Historie, Verkaufsanalyse mit Balkendiagrammen, saisonale Sortimentsempfehlungen und Öffnungszeitenübersicht.
- Kalenderwochen-Prognosen für Basis, Moderat und Optimistisch: wahlweise mit lokalen Einflussfaktoren oder nur anhand historischer Verkäufe.
- Interaktive Diagramme mit Zoom, Verschieben, Punktinspektion und Szenariofokus.
- Optionaler Umsatzziel-Vergleich, Ausschluss ganzer Transaktionen anhand FF001-Barcode, Excel-Export.
- Lokale Verarbeitung ohne Cloud-Zwang.

**Hinweise zur Prognose**

Bei wenigen vollständigen Kalenderwochen sind besonders langfristige Prognosen sehr unsicher. Die Szenarien sind Planungsannahmen, keine statistisch validierten Garantieintervalle. Der rein historische Modus bezieht keine Feiertage, Ferien oder Weihnachtsmärkte ein.

**Umbenennung**

Die Benutzeroberfläche trägt den Namen **ForeCast**. Der bestehende `QSettings('Floesser Laedle','Forecast')`-Speicherbereich bleibt aus Gründen der Kompatibilität erhalten, damit Benutzereinstellungen und der letzte CSV-Pfad bei der Umstellung nicht verlorengehen.

## FF001-Filter
Die Checkbox **FF001-Verkäufe vollständig ignorieren** ist standardmäßig aktiv. Die Erkennung prüft den exakten Barcode `FF001` in Artikelnummer, Barcode, EAN, SKU oder GTIN. Alle Positionen mit derselben Transaktionsnummer werden ausgeschlossen, bevor Statistiken, Prognosen und Exportdaten berechnet werden. Eine Filter-Zusammenfassung wird angezeigt und in Excel dokumentiert. Der mitgelieferte Beispielexport enthält keine FF001-Position.

## Neues Wachstumsmodell
Im Bereich **Wachstum & Anlaufphase** kannst du drei Trendquellen wählen:
- **Hybrid**: Mischt ein angenommenes Anlaufwachstum mit dem gemessenen Trend. Je mehr vollständige KW vorhanden sind (ab 3), desto höher wird das Gewicht des Ist-Trends; ab 12 vollständigen KW vollständig Ist-Trend.
- **Annahme**: Verwendet die von dir eingestellte Wachstumsrate pro KW.
- **Nur Ist-Trend**: Verwendet ausschließlich den gemessenen Trend (bei weniger als 3 vollständigen KW: 0 %).

Die Wachstumsrate flacht über die einstellbare Sättigungsdauer ab; ein relativer Umsatzdeckel begrenzt die modellierte Steigerung. Drei Szenarien haben eigene Wachstumspfade. Saisonfaktoren werden zusätzlich berücksichtigt. Das Modell bleibt eine heuristische Planung und ist keine Garantie.

Der Bereich zeigt die Zahl vollständiger KW sowie gemessenen und verwendeten Trend. Der Excel-Export enthält das Tabellenblatt **Wachstumsmodell** und die KW-Prognose enthält Trend- und Wachstumsfaktor-Spalten.

**FF001-Filter bleibt erhalten**, ebenso die Startskripte für Linux/Bazzite, macOS und Windows.


## UI-Neugestaltung (Version 2)
- Neue, vollständig strukturierte Desktop-Oberfläche mit dunkler Seitennavigation und sechs Arbeitsbereichen: Übersicht, KW-Prognose, Verkaufsanalyse, Sortiment, Öffnungszeiten und Modell & Faktoren.
- Übersicht mit vier Kennzahlen und durchgängiger Ist-/Prognose-Liniengrafik.
- Einheitliche, kontrastreiche Gestaltung mit konsistenten Abständen, Tabellen und Fokuszuständen.
- Einstellungen und FF001-Filter auf einer eigenen scrollbaren Seite; keine überfüllte Seitenleiste mehr.
- CSV-Import und Excel-Export sind auf jeder Seite verfügbar. Der letzte CSV-Pfad wird lokal gespeichert und beim Neustart automatisch erneut eingelesen, sofern vorhanden.
- Die vorherige Prognoselogik, die Szenarien, der FF001-Filter und die plattformübergreifenden Startskripte bleiben erhalten.

### Teststatus
Die Python-Syntax wurde geprüft. Ein tatsächlicher Qt-GUI-Test war in der Erstellungsumgebung nicht möglich, weil PyQt6 dort nicht installiert ist und der Paketindex nicht erreichbar war.

## Optionales Umsatzziel (neu)
Unter **Modell & Faktoren → Optionales Umsatzziel** kannst du ein Umsatzziel pro Kalenderwoche aktivieren und den Betrag in Euro eingeben. Der Zielwert ist standardmäßig deaktiviert und wird lokal in den App-Einstellungen gespeichert.

Bei aktivem Ziel erscheint eine **rote gestrichelte Referenzlinie** im Dashboard und im KW-Prognose-Diagramm. Die KW-Tabelle zeigt Zielumsatz, Abweichung in Euro und Zielerreichung in Prozent. Im Excel-Export gibt es ein Blatt `Umsatzziel`, zusätzliche Spalten in `Historische KW` und `KW-Prognose` sowie die Zielreihe in beiden Liniendiagrammen.

Das Ziel ist **keine Eingangsgröße der Prognose**. Ein Ziel von 2.000 €/KW erhöht nicht automatisch die prognostizierten Verkäufe. Die Ist-KW werden mit den tatsächlich erfassten Umsätzen verglichen; unvollständige KW sind daher nicht direkt mit vollen KW vergleichbar.

### Teststatus
Python-Syntax und Klassenstruktur wurden geprüft. Ein grafischer Laufzeittest ist in dieser Umgebung nicht möglich, da PyQt6 nicht installiert ist.

## Prognose ausschließlich aus historischen Verkaufsdaten

Unter **Modell & Faktoren → Prognoseverfahren** die Option **„Nur historische Verkaufsdaten verwenden“** aktivieren. Die Einstellung wird gespeichert und beim Wechsel sofort neu berechnet.

- Nutzt ausschließlich die bereits importierten, nach dem FF001-Filter bereinigten historischen Umsätze pro Kalenderwoche.
- **Keine** Feiertage, Ferien, Weihnachtsmarkt- oder Pendlerfaktoren; **keine** angenommene Anlauf-Wachstumsrate oder Wachstumsdeckel.
- Ab drei vollständigen Kalenderwochen wird ein begrenzter empirischer Trend aus den letzten bis zu acht vollständigen KW berechnet. Die moderate und optimistische Kurve wird aus der beobachteten Schwankung abgeleitet.
- Bei weniger als drei vollständigen KW wird ein konstanter Basiswert aus vollständigen KW fortgeschrieben; Szenarien fallen zusammen, weil die Daten für Trend und Streuung nicht ausreichen.
- Umsatzziel, FF001-Filter, alle Diagramme und XLSX-Export bleiben verfügbar. Das Excel-Blatt **Prognoseverfahren** dokumentiert den Modus.
- **Grenze:** Die Normalisierung unvollständiger KW nutzt die Kalendertage der Datei, nicht nachgewiesene Öffnungstage.

## Fehlerbehebung: Historische Prognose mit nur zwei vollständigen KW
Die rein historische Prognose berechnet jetzt bereits ab zwei vollständigen KW einen **gedämpften Ist-Trend**. Die Projektion flacht über längere Horizonte ab. Die Szenariobreite basiert auf der beobachteten täglichen Umsatzstreuung und wächst mit dem Prognosehorizont. Bei nur einer vollständigen KW bleibt die mittlere Prognose konstant; die Szenarien können trotzdem auseinanderlaufen. Es werden **keine** Feiertage, Ferien, Pendlerannahmen oder Wachstumsannahmen verwendet. Die Szenariobänder sind heuristisch und **keine statistisch kalibrierten Konfidenzintervalle**.

## Interaktive Diagramme
Klicke in einem Liniendiagramm auf einen Punkt bzw. bis zu 35 Pixel neben einen Punkt. Ein dauerhaft sichtbarer Infokasten zeigt die X-Achsen-Beschriftung und die Werte **aller** vorhandenen Reihen an dieser Position. Die ausgewählte Position erhält eine vertikale Hilfslinie. Ein weiterer Klick wählt einen anderen Datenpunkt. Die Funktion gilt für Dashboard, KW-Prognose, Tages-, Stunden-, Kategorie- und Artikeldiagramme. Auch das optionale Umsatzziel wird im Infokasten angezeigt.

## Interaktive Diagramme: Zoom, Scrollen, Verschieben
Alle sechs Matplotlib-Diagramme besitzen eine Werkzeugleiste und Mausnavigation:
- **Mausrad:** beide Achsen am Mauszeiger zoomen
- **Shift + Mausrad:** nur horizontal zoomen
- **Strg + Mausrad:** nur vertikal zoomen
- **Linke Maustaste ziehen:** Diagramm horizontal und vertikal verschieben
- **Einfacher Linksklick auf Datenpunkt:** Werte aller sichtbaren Reihen der gewählten KW anzeigen
- **＋ / －:** hinein- oder herauszoomen
- **Zurücksetzen:** vollständigen Diagrammausschnitt wiederherstellen
- **Skalierung:** automatisch, linear oder komprimiert (symmetrisch logarithmisch)

Bei starken Abweichungen zwischen moderater, Basis- und optimistischer Prognose wird automatisch eine **komprimierte Y-Achse** gewählt. Dadurch bleiben auch kleine Werte sichtbar, selbst wenn das optimistische Szenario um ein Vielfaches größer ist. Die echten Zahlen bleiben unverändert; nur die visuelle Achsenskalierung ändert sich. Bei Bedarf lässt sich jederzeit wieder die lineare Darstellung wählen.

**Achtung:** Die große optimistische Prognose im Screenshot ist ein Effekt der aus wenigen Beobachtungen extrapolierten historischen Wachstumsraten. Die neue Diagrammsteuerung verbessert die Lesbarkeit, ersetzt aber keine zusätzliche Modellkalibrierung.

**Teststatus:** Python-AST/Syntaxprüfung erfolgreich. Ein echter PyQt6-GUI-Test war in der Ausführungsumgebung mangels PyQt6 nicht möglich.

## Diagrammkorrektur – Y-Achse und Szenarien
- Behebt das Hochlaufen der Y-Achse auf absurde Werte (z. B. 10^29) beim wiederholten Umschalten zwischen linearer, automatischer und komprimierter Skalierung.
- Jeder Modus berechnet seine Achsengrenzen **aus den tatsächlich sichtbaren Zahlenreihen** vollständig neu. Zoom- und Pan-Zustände werden beim Wechsel zurückgesetzt.
- Neuer Auswahlmodus **Fokus: Basis & Moderat**: Die extreme optimistische Reihe wird vorübergehend ausgeblendet, damit die beiden anderen Kurven gut lesbar bleiben. Die zugrunde liegenden Prognosewerte werden nicht geändert.
- Im Modus **Alle Szenarien** bleibt die optimistische Kurve verfügbar. Das Basisszenario wird dicker gezeichnet.
- Bei extrem unterschiedlichen Szenarien wird die automatische Achse sinnvoll komprimiert; im Gegensatz zur alten Version wird der Kompressionsbereich dynamisch aus den Umsätzen abgeleitet.

Test: 30 vollständige Wechselzyklen der Achsenskalierung und des Szenariofokus mit Matplotlib ohne Achsenexplosion erfolgreich. Die PyQt6-Oberfläche wurde mangels PyQt6 in der Testumgebung nicht ausgeführt.

## Korrektur: getrennte historische Szenarien

Das historische Prognosemodell verwendet jetzt die mediane Veränderung vollständiger KW für die **Basis**. Die beobachtete Streuung der Veränderungen zwischen gleichen Wochentagen dient zur Berechnung einer **symmetrischen unteren und oberen Szenariorate** um die Basis. Bei nur einem Vergleich wird die beobachtete absolute Veränderung als vorläufige Streuungs-Näherung genutzt. Die Trendraten werden bei kurzer Historie gedämpft und über den Prognosehorizont abflachend fortgeschrieben. Das sind **Szenarien, keine statistisch kalibrierten Konfidenzintervalle**.

Geprüft mit dem Verkaufsbericht vom 12.10.–21.11.2026: Zwei vollständige KW, sieben passende Tagesvergleiche, drei voneinander verschiedene Szenariokurven. Zusätzlicher Test: Externe Saison- und Wachstumsparameter ändern die rein historische Prognose nicht. Python-Syntax geprüft; grafischer PyQt-Laufzeittest steht noch aus.

## Szenarioreihenfolge (aktualisiert)
Die Szenarien sind nun **Basis ≤ Moderat ≤ Optimistisch**. „Moderat“ ist das mittlere, moderat positive Szenario zwischen Basis und Optimistisch, kein pessimistisches Szenario. Im historischen Modus wird zunächst die beobachtete Wachstumsstreuung berechnet; Basis ist mindestens 0 % Wachstum, Optimistisch der höhere empirisch abgeleitete Wachstumspfad, und Moderat liegt exakt auf halbem Weg zwischen beiden **Wachstumsraten**. Im saisonalen Modus liegt Moderat zwischen Basis und Optimistisch auf halbem Weg im Eurobetrag. Wenn die historischen Daten keine positive Bandbreite ergeben, können Szenarien zusammenfallen; die App erfindet keine zusätzliche Steigerung. Negative tatsächliche Ist-Werte werden nicht verändert.


Hinweis: Die Anzeige heißt nun „Moderat“; interne Feldnamen `vorsichtig` bleiben zur Abwärtskompatibilität erhalten.

## Korrektur: Prognose startet an der aktuellen KW
Die drei Prognoselinien werden jetzt am **geschätzten Gesamtumsatz der aktuellen Kalenderwoche** verankert, nicht am Median älterer KW. Wenn die aktuelle KW noch läuft, bleibt der bereits erfasste Ist-Umsatz unverändert; die fehlenden Wochentage werden aus den historischen Umsätzen der gleichen Wochentage ergänzt. Die erste zukünftige KW ist die Folgewoche. Im Diagramm ist der Punkt in der aktuellen KW eine Hochrechnung, während die Ist-Linie den tatsächlich erfassten Umsatz zeigt. Der Prognoseanker wird im Dashboard-Infotext und im Excel-Blatt `Prognose-Anker` dokumentiert. Im Modus „Nur historische Verkaufsdaten“ werden hierfür keine Feiertags-, Ferien-, Markt- oder Pendlerfaktoren verwendet.

**Hinweis:** Wenn für einen fehlenden Wochentag keine Vergleichsdaten vorliegen, kann die Hochrechnung zu niedrig ausfallen. Mit nur zwei vollständigen KW sind Wachstumsraten und Schätzungen weiterhin unsicher.

## Verkaufsanalyse als Balkendiagramme
Die vier Diagramme unter **Verkaufsanalyse** (Tagesverlauf, Stundenverlauf, Kategorien und Topartikel) werden jetzt als Balkendiagramme angezeigt. Klick auf einen Balken zeigt den exakten Wert. Mausrad-Zoom, Verschieben, Achsenskalierung und Zurücksetzen bleiben verfügbar. **Übersicht** und **KW-Prognose** bleiben Liniendiagramme. Die Berechnungen und Prognosewerte wurden nicht verändert.

## Historisches Wachstum – Überarbeitung
Die rein historische Prognose verwendet jetzt auch die hochgerechnete aktuelle Kalenderwoche als vorläufigen Trendhinweis, sofern sie noch nicht abgeschlossen ist. Der Ausgangswert bleibt der geschätzte Gesamtumsatz der aktuellen KW. Die Raten für **Basis**, **Moderat** und **Optimistisch** werden aus den Veränderungen zwischen historischen KW ermittelt; bei wenig Daten werden sie statistisch gedämpft.

Die Fortschreibung verwendet `8 * log(1 + Prognose-KW / 8)` statt eines asymptotisch gedeckelten Horizonts. Dadurch nimmt die Wachstumsrate langfristig ab, die Prognose wird bei positivem Wachstum aber nicht künstlich auf einen festen Umsatzdeckel begrenzt. Bei fehlendem positivem historischem Signal bleibt die Basisprognose weiterhin konstant – die App erfindet kein Wachstum.

**Achtung:** Die aktuelle KW ist eine Schätzung, keine abgeschlossene historische Beobachtung. Die Werte für 50 KW sind bei nur zwei vollständigen KW hochgradig unsicher und keine Umsatzgarantie.