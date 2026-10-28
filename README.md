# Cloudless RMV

Home-Assistant-Integration für Abfahrten im **RMV-Gebiet** (Rhein-Main) – mit Verspätungen,
Ausfällen, Störungsmeldungen, **Prüfung, welche Haltestellen angefahren werden**, und einer
**Weiterfahrt-Prüfung** (z. B. fährt die Straßenbahn zur Friedensbrücke?).
Einrichtung komplett grafisch, Lovelace-Karte mit Editor inklusive.

> **Inoffiziell.** Dieses Projekt steht in keiner Verbindung zum RMV und wird nicht vom RMV
> unterstützt oder empfohlen. Datenquelle: RMV Open Data (HAFAS ReST).

## Eigenen API-Schlüssel beantragen (Pflicht)

Dieses Repository enthält **keinen** Schlüssel. Jeder Nutzer braucht einen eigenen, kostenlosen
Schlüssel: **<https://www.rmv.de/s/de/rmv-open-data>**

* Schlüssel vertraulich behandeln – nicht teilen, nicht in Issues/Screenshots/Logs posten.
* Die RMV-Nutzungsbedingungen gelten für dich (u. a. 600 Anfragen/Stunde, 5000/Tag, Quellenangabe
  mit RMV-Logo, Schlüssel verfällt nach 180 Tagen ohne Nutzung). Lies sie vor dem Einsatz.
* Die Integration begrenzt sich selbst auf 85 % dieser Limits (geteilt über alle Einträge mit demselben Schlüssel).

## Installation (HACS)

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/MadisonMedia/cloudless-rmv`, Kategorie *Integration*.
2. „Cloudless RMV“ installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Cloudless RMV*.

## Einrichtung

1. Schlüssel eingeben.
2. Einstiegshaltestelle suchen und auswählen.
3. Optional: Richtung (nur Fahrten Richtung z. B. Frankfurt Hbf).
4. **Haltestellen prüfen**: beliebig viele (z. B. Mühlberg, Konstablerwache, Hauptbahnhof). Es wird angezeigt, ob die Bahn dort hält – und vor allem, **welche nicht** angefahren werden (Ausfall, Umleitung, Halt entfällt, kein Ausstieg).
5. Optional **Weiterfahrt**: Ziel (z. B. Friedensbrücke) und Umstiegshaltestelle. Geprüft wird ab voraussichtlicher Ankunft dort, ob Fahrten zum Ziel laufen oder gestört/ausgefallen sind – ohne genaue Zeiten.

Später unter *Konfigurieren*: Gehzeit, Anzahl Fahrten, Zeitfenster, Umstiegspuffer.
Haltestellen ändern: Eintrag löschen und neu anlegen.

## Karte

```yaml
type: custom:cloudless-rmv-card
entity: sensor.<…>_naechste_abfahrt
```

Alles weitere im visuellen Editor. Die Karte lädt sich selbst (keine Ressource nötig).
Aktualisiert **nur solange sie sichtbar ist** (Standard alle 120 s), Tippen = sofort, zeigt „aktualisiert vor X s“.
Ohne offenes Dashboard fragt die Integration **gar nicht** beim RMV an.

## Entitäten

| Entität | Inhalt |
|---|---|
| `sensor … Nächste Abfahrt` | Zeitstempel; Attribute: alle Fahrten, Meldungen, Haltestellen-Status, Weiterfahrt |
| `sensor … <Haltestelle>` | `ok` / `none` / `unknown` + Anzahl bedienter Fahrten |
| `binary_sensor … Weiterfahrt` | an = keine Fahrt oder gestört (für Automationen/Benachrichtigungen) |

## Datenschutz & Sicherheit

Der Schlüssel liegt nur in deinem HA-Eintrag, wird in Diagnosen geschwärzt und von der Integration
nie geloggt. Details: [SECURITY.md](SECURITY.md). Der Recorder speichert die großen Attribute nicht.

## Entwicklung

```bash
pip install -r requirements_test.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests --ignore=tests/ha
pip install pytest-homeassistant-custom-component && python -m pytest tests/ha
```

## English summary

Unofficial Home Assistant integration for RMV (Rhein-Main) departures: delays, cancellations,
disruption messages, a check which of your chosen stops a train actually serves, and an onward-connection
check. Graphical setup + Lovelace card. **Get your own free key at <https://www.rmv.de/s/de/rmv-open-data>**;
none is included. Not affiliated with the RMV. Please observe the RMV terms of use
(rate limits, attribution).

## RMV-Logo (Quellenangabe)

Die RMV-Nutzungsbedingungen (Abschnitt 5f) verlangen die Quellenangabe **mit Logo**. Das Logo ist
Marke des RMV und liegt deshalb nicht in diesem Repository. Lege die vom RMV bereitgestellte Datei als
`custom_components/cloudless_rmv/www/rmv-logo.png` ab – die Karte zeigt sie dann automatisch im Fuß an
(ohne Datei erscheint nur der Text „Daten: RMV“).
