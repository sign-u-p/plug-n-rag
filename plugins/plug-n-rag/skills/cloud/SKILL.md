---
name: cloud
description: Richtet plug-n-rag für Cloud-Sitzungen ein (Claude Code im Browser, in der Desktop- oder Handy-App mit einer Vault auf GitHub) und prüft, ob alles bereit ist. Verwenden, wenn jemand die Vault in Cloud-Sitzungen nutzen möchte, wenn in einer Cloud-Sitzung das Suchmodell nicht geladen werden kann oder wenn das Setup bei Schritt „Cloud-Sitzungen“ ankommt. English: sets up plug-n-rag for cloud sessions and checks that everything is ready.
allowed-tools: Bash(plug-n-rag cloud*) Bash(plug-n-rag modell-laden*) Bash(plug-n-rag status*) Bash(plug-n-rag load-model*)
---

> **Sprache / language:** Antworte in der Sprache, in der die Nutzer:in schreibt; auf Deutsch
> gendergerecht mit Doppelpunkt. If the user writes in English, answer in English. Alle Befehle
> gibt es auch englisch (`search`, `read`, `outline`, `--purpose question`, …); die festen Texte
> von plug-n-rag folgen der Sprache der Vault (`language` in der Konfiguration).
>
> **Werkzeug / tool:** `plug-n-rag` immer mit dem **Bash**-Werkzeug ausführen, nie mit PowerShell
> (unter Windows kennt PowerShell den Befehl nicht). Always run `plug-n-rag` with the Bash tool.

# plug-n-rag in Cloud-Sitzungen

Erkläre ohne Fachjargon. Die Nutzer:in muss keine Begriffe wie „Container“ kennen; sag
„Cloud-Umgebung“ (so heißt es in der App) und „Setup-Skript“.

## Das Wichtigste vorweg

- Cloud-Sitzungen installieren **keine** Plugins, die ein Repo unter `enabledPlugins` in
  `.claude/settings.json` einträgt. Ein solcher Eintrag hilft nur auf dem eigenen Rechner. Plugins,
  die über die Plugin-Seite zum Konto hinzugefügt wurden, kommen ebenfalls nicht in Cloud-Sitzungen.
- Cloud-Sitzungen führen aber die **Start-Hooks des Repos** aus. Darauf baut **Weg A, die
  Selbst-Einrichtung** (empfohlen): `plug-n-rag cloud --einbinden` legt `.plug-n-rag/cloud-start.sh`
  an und trägt es als Start-Hook ein. Fehlt plug-n-rag in einer Cloud-Sitzung, installiert das
  Skript es. Funktioniert in **jeder** Cloud-Umgebung, ohne Einstellungen. Der Befehl `plug-n-rag`
  geht sofort; die `/plug-n-rag:…`-Befehle erscheinen nach einmal `/reload-plugins`.
- **Weg B, Setup-Skript der Cloud-Umgebung** (zusätzlich oder statt A): installiert das Plugin vor
  dem Start und lädt das Suchmodell vorab. Die Umgebung wird als Abbild gespeichert; Sitzungen
  starten sofort suchbereit, mit allen Befehlen.
- Für die semantische Suche braucht die Umgebung in beiden Fällen eine **Netzwerkfreigabe** für
  Hugging Face (lokales Modell) bzw. ein **Netzwerk-Secret** für Voyage. Ohne geht die Stichwortsuche.
- Die Index-Dateien kommen aus dem Vault-Repo. Deshalb müssen sie committet und gepusht sein.

## Zwei Ausgangslagen

- **Lokal eingerichtet, jetzt auch in der Cloud**: Ablauf unten ab Schritt 1.
- **Alles direkt in der Cloud**: Die Nutzer:in hat eine Cloud-Sitzung mit ihrem Vault-Repo
  gestartet und plug-n-rag darin installieren lassen (meist mit dem Satz „Richte dieses Repo für
  plug-n-rag ein: github.com/sign-u-p/plug-n-rag“, Ablauf in `AGENTS.md` des Plugin-Repos) (`claude plugin marketplace add
  sign-u-p/plug-n-rag`, `claude plugin install plug-n-rag@plug-n-rag`). Dann zuerst
  `/plug-n-rag:setup` (Abschnitt „Cloud-Weg“), danach Schritt 3 unten, damit künftige Sitzungen
  das Plugin automatisch haben.
- **Plugin gerade erst von der Selbst-Einrichtung installiert**: Die Startmeldung sagt es. Dann gibt
  es `/plug-n-rag:…` erst nach `/reload-plugins`; bis dahin `plug-n-rag anleitung <name>` lesen.

## Ablauf

1. **Ausgangslage klären**
   - Lokal (im Ordner der Vault): `plug-n-rag cloud --pruefen`. Fehlt ein GitHub-Repo oder sind die
     Index-Dateien nicht gepusht, das zuerst erledigen (Commit „Vault-Index aktualisiert“, Push nur
     nach Rückfrage, nie `--force`). Ist das Repo öffentlich: deutlich warnen und Hilfe anbieten,
     es auf privat zu stellen.
   - In einer Cloud-Sitzung, in der plug-n-rag schon läuft: ebenfalls `plug-n-rag cloud --pruefen`
     und nur die ⚠-Punkte bearbeiten.
2. **Anleitung erzeugen**: `plug-n-rag cloud`. Die Ausgabe enthält die Hosts für „Allowed domains“
   und das Setup-Skript, passend zum Modell dieser Vault (`plug-n-rag cloud --skript` gibt nur das
   Skript aus). Gib beides **unverändert** weiter, in Codeblöcken zum Kopieren.
3. **Selbst-Einrichtung einbinden (Weg A)**: Kurz erklären, was sie tut, fragen, dann
   `plug-n-rag cloud --einbinden`. Committen und nach `main` übernehmen (`/plug-n-rag:nach-main`),
   denn Cloud-Sitzungen starten vom Hauptstand. Entfernen geht mit `plug-n-rag cloud --ausbinden`.
   Danach weiter mit Schritt 4 für das Netzwerk; das Setup-Skript dort ist optional.
4. **Umgebung einrichten**
   - Stehen dir in dieser Sitzung Werkzeuge zum Anlegen oder Bearbeiten von Cloud-Umgebungen zur
     Verfügung, biete an, das selbst vorzuschlagen (Name z. B. „Vault“, Netzwerk „Limited“ mit
     Paketquellen, die Hosts, das Setup-Skript). Die Nutzer:in bestätigt den Vorschlag; ohne
     Bestätigung nichts ändern. Erlauben die Werkzeuge keine Platzhalter wie `*.hf.co`, nimm die
     exakten Hosts aus `plug-n-rag cloud --hosts`. Verlangen sie, dass ein Setup-Skript vorher in
     der Sitzung lief, führe `plug-n-rag cloud --skript > /tmp/pnr-setup.sh && bash /tmp/pnr-setup.sh`
     aus und prüfe das Ergebnis, bevor du es vorschlägst.
   - Sonst Schritt für Schritt anleiten: In der Sitzungsleiste auf den Namen der Umgebung tippen,
     „Bearbeiten“ (oder „Hinzufügen“ für eine eigene Vault-Umgebung). Dort:
     **Network access** → „Limited“, „Allow package managers“ angehakt lassen, unter
     **Allowed domains** die Hosts eintragen. **Setup script** → Skript einfügen. Speichern.
     Doku: https://code.claude.com/docs/en/cloud-environments
   - **Voyage**: Den Key als **Netzwerk-Secret** der Umgebung für den Host `api.voyageai.com`
     hinterlegen lassen (nie als Umgebungsvariable, nie ins Repo, nie in den Chat). plug-n-rag
     erkennt die Cloud-Sitzung und lässt den Key vom Netzwerk-Proxy einsetzen. Gibt es ein Werkzeug,
     mit dem die Nutzer:in ein Secret sicher eingibt, nutze es.
5. **Testen**: Eine neue Sitzung mit dem Vault-Repo in dieser Umgebung starten. Der erste Start
   dauert einige Minuten (Modell etwa 470 MB). Dort `plug-n-rag cloud --pruefen` und eine
   Testsuche, z. B. `plug-n-rag suche "<Thema aus der Vault>" --zweck frage`.
6. **Erklären, was anders ist als lokal**
   - Cloud-Sitzungen arbeiten auf einem eigenen Branch (`claude/…`). Änderungen an Notizen landen
     erst nach dem Zusammenführen auf GitHub im Hauptstand und damit in Obsidian.
   - Ein Update von plug-n-rag kommt in die Cloud-Umgebung, wenn sie neu gebaut wird (spätestens
     nach etwa sieben Tagen oder nach einer Änderung am Setup-Skript).

## Wenn etwas nicht klappt

- **„Suchmodell konnte nicht geladen werden“ / Hugging Face blockiert**: Hosts aus `plug-n-rag cloud`
  fehlen in „Allowed domains“. Bis dahin funktioniert die Stichwortsuche.
- **plug-n-rag fehlt in der Cloud-Sitzung** (Befehl unbekannt, keine Kurz-Karte beim Start): Die
  Selbst-Einrichtung ist nicht eingebunden oder noch nicht auf `main`; ohne sie fehlt das
  Setup-Skript oder die Sitzung lief in einer anderen Umgebung; oder das Repo `sign-u-p/plug-n-rag`
  ist für die Umgebung nicht erreichbar (die Startmeldung der Selbst-Einrichtung sagt das).
- **`/plug-n-rag:…` unbekannt, `plug-n-rag` geht aber**: Das Plugin wurde während der Sitzung
  installiert. Die Nutzer:in tippt einmal `/reload-plugins`.
- **Alles wird neu berechnet**: Index-Dateien waren nicht gepusht.
