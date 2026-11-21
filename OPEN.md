# Offene Punkte

Stand: 21.11.2026, Version 0.9.3.

## Checkliste: nur in einer neuen Sitzung prüfbar

In dieser Sitzung wurde plug-n-rag über den lokalen Marketplace installiert
(`claude plugin marketplace add <repo>` + `claude plugin install plug-n-rag@plug-n-rag`), die
Hook-Befehle wurden direkt ausgeführt, und eine nicht-interaktive Sitzung (`claude -p`) in einer
Kopie der Test-Vault hat SessionStart-Hook, Skill `suche`, Gliederung, Abschnitt-Lesen und
Stop-Hook durchlaufen. Offen ist:

- [ ] **Interaktive Sitzung lokal** (Terminal oder Desktop-App) in einer echten Vault:
  - [ ] Erscheint beim ersten Start eine Freigabe-Abfrage für die Hooks? Text im Setup passt?
  - [ ] Kurz-Karte erscheint im Kontext (Frage: „Was weißt du über meine Vault?“).
  - [ ] `/plug-n-rag:setup` von Anfang bis Ende mit einer Vault ohne Git: Inventur, Datenschutz-
        Hinweis, `git init`, GitHub-Repo (privat), Kostenvoranschlag, Indexierung, Karte,
        Testsuche, Abschluss-Commit.
  - [ ] Obsidian Git: Release-Download, `community-plugins.json`, Schlüssel in `data.json`
        gegen `DEFAULT_SETTINGS` geprüft, eingeschränkten Modus in Obsidian ausschalten.
  - [ ] Stop-Hook (asynchron): Notiz in Obsidian ändern, nächste Antwort abwarten, Suche findet
        die Änderung.
  - [ ] Permission-Prompts: Wie oft fragt Claude Code bei `plug-n-rag …`? Ggf. im Setup die
        Regel `Bash(plug-n-rag *)` für `.claude/settings.json` anbieten.
- [ ] **Cloud-Sitzung** (claude.ai/code) mit einem Vault-Repo und einer Umgebung nach
      `plug-n-rag cloud`:
  - [ ] Läuft das Setup-Skript durch (Marketplace hinzufügen, Plugin installieren, Modell laden)?
        Ist `claude` im Setup-Skript auf dem PATH? Reicht `*.hf.co` für alle Download-Hosts?
  - [ ] Wird das Abbild gespeichert (unter etwa fünf Minuten) und startet die nächste Sitzung
        ohne erneuten Download?
  - [ ] Erreicht das Setup-Skript `github.com/sign-u-p/plug-n-rag`, falls das Repo privat ist?
  - [ ] SessionStart-Hook liefert die Kurz-Karte; frische Sitzung sucht ohne neues Embedding
        (als Unit-Test mit Klon ohne Cache belegt).
  - [ ] Voyage mit Netzwerk-Secret: ersetzt der Proxy den Platzhalter `proxy-injected`?
  - [ ] Kann Claude die Umgebung mit eigenen Werkzeugen vorschlagen (Skill `cloud`, Schritt 3)?
  - Korrigiert (21.11.2026, Claude Code 2.1.330): Ein während der Sitzung installiertes Plugin
    lädt erst nach `/reload-plugins`; `plug-n-rag` auf dem PATH ist sofort da (Entscheidung 69).
- [ ] **Suchmodus in einer echten Cloud-Sitzung** (0.9.3): Zeigt die erste Suche „nur Stichwort ·
      Suchmodell lädt (…%)“ mit steigendem Wert, kennzeichnet Claude die Antwort als vorläufig, und
      wartet `suche --warten` bis zum Ende des Downloads? Nennt `status` danach „bereit seit …“?
- [ ] **Selbst-Einrichtung** (`cloud --einbinden`) in einer echten Cloud-Sitzung über claude.ai mit
      einem Vault-Repo, dessen `main` das Start-Skript enthält:
  - [ ] Läuft der Hook, und erreicht er github.com in einer Umgebung mit Netzwerk „Limited“?
  - [ ] Ist `/reload-plugins` in der App (Browser, Handy) verfügbar?
  - [ ] Windows lokal: bleibt der Hook (`sh …`) still, auch ohne Git Bash im PATH?
- [ ] **Einrichtung direkt in der Cloud** mit dem Startsatz aus der README in einer frischen
      Sitzung auf einem Vault-Repo ohne plug-n-rag:
  - [ ] Installiert Claude das Plugin auf den Startsatz hin ohne Rückfragen-Schleife, und findet es
        `/plug-n-rag:setup` im selben oder nächsten Zug?
  - [ ] Netzwerkfreigabe über die Umgebungswerkzeuge mit Hosts aus `plug-n-rag cloud --hosts`.
  - [ ] Setup-Skript über die Umgebungswerkzeuge sichern; nächste Sitzung hat plug-n-rag.
- [ ] **`/plug-n-rag:nach-main` aus einer Cloud-Sitzung**: Akzeptiert die Sitzung die Aufforderung
      im Chat als Erlaubnis für den Push nach `main`? Verhalten bei geschütztem `main` prüfen.
- [ ] **Windows**: Launcher `scripts/plug-n-rag` ist ein POSIX-Shell-Skript. Claude Code nutzt unter
      Windows meist Git Bash; ohne Git Bash ist ein `.cmd`-Gegenstück nötig.
- [ ] **macOS mit Homebrew-Python**: Lässt sich sqlite-vec laden? (Sonst greift der NumPy-Fallback,
      `plug-n-rag status` zeigt es an.)
- [ ] MCP-Wrapper als Server in Claude Code registrieren (siehe README) und prüfen, ob Claude die
      Werkzeuge den Bash-Aufrufen vorzieht.

- [ ] **Installation über die Plugin-Seite** (Desktop-App → Einstellungen → Plugins → Hinzufügen →
      Marketplace hinzufügen → `sign-u-p/plug-n-rag`):
  - [ ] Nimmt claude.ai den Marketplace an (öffentliches Repo, Plugin-Quelle `./`)?
  - [ ] Erscheint plug-n-rag danach in lokalen Claude-Code-Sitzungen (synced plugin), laufen die Hooks,
        und landet `plug-n-rag` über `CLAUDE_ENV_FILE` auf dem PATH?
  - [ ] Was passiert in Cowork (Hooks laufen dort ggf. ohne uv; sollte still bleiben)?
  - [x] Kommt ein über das Konto hinzugefügtes Plugin auch in Cloud-Sitzungen an? Nein (21.11.2026:
        Ordner für Konto-Plugins im Container leer, `/plug-n-rag:setup` unbekannt). Antwort darauf:
        Selbst-Einrichtung der Vault (Entscheidung 69).

- [ ] **Windows** nach 0.5.0 erneut: Umlaute in `sync --fortschritt`, Seitenbilder für `aufnehmen`
      ohne Poppler (pypdfium2 + Pillow), Wechsel von einer alten 3.10-Umgebung auf ≥ 3.11.
- [ ] **Gedruckte Seitenzahlen** an echten Büchern prüfen (Erkennung über Kopf-/Fußzeilen ist eine
      Heuristik; bei Auszügen mit fehlenden Seiten kann der Versatz springen).
- [ ] **Literaturlisten-Erkennung** an echten Fachbüchern prüfen (Schwelle 3,5 Jahreszahlen pro 100 Wörter).

- [ ] **Umzug einer echten 0.4/0.5-Installation** (Windows, zentrale Sammlung mit Haiku-Abschriften):
      Erscheinen nach dem Update keine Seiten als „wartet auf Aufnahme“? `plug-n-rag umziehen`
      verschiebt den zentralen Index aus dem Cache- in den Datenordner (`%APPDATA%\plug-n-rag\data`).
- [ ] **Sammlung im Ordner auf einem Netzlaufwerk/Nextcloud** mit zwei Rechnern: Index und Abschriften
      werden übernommen, nichts wird neu berechnet (als Unit-Test mit Kopie des Ordners belegt).

- [ ] **plug-n-rag Display in der Desktop-App** (Code-Tab, lokale Sitzung): Getestet sind die Hooks
      mit dem Test-Kit der Engine (Desktop, Terminal, Handy) und `claude plugin validate`; noch
      nicht gesehen in der echten App:
  - [ ] Wirkt die kompakte Zeile ruhig genug? Passt „Details“ als Bedienung, oder lieber nur der Pfeil?
  - [ ] Findet der Mod den Starter von plug-n-rag (Cache-Layout `…/plug-n-rag/plug-n-rag/<version>/`)
        und läuft `sh <starter> anzeige-daten` unter Windows (Git Bash)?
  - [ ] Band mit Fortschritt während einer langen Indexierung; Ausblenden hält für die Sitzung.
  - [ ] Seitenleiste: Breite, Lesbarkeit, Tastenbedienung, Bildschirmleser.
  - [ ] Handy-App: erscheint die ruhige Zeile unter dem Schritt?
  - [x] Nimmt die Plugin-Seite ein Plugin mit Mod an? Ja: Desktop-App (Windows) zeigt beide Plugins
        unter „Entdecken“ und installiert sie (20.11.2026).

## Nicht umgesetzt oder nur teilweise

- **GitHub-Action**, die `tools/check.sh --schnell` bei jedem Pull Request ausführt (braucht Node für
  die Claude-Code-CLI und uv). Nicht angelegt, weil Änderungen an Workflows besondere
  GitHub-Rechte brauchen; bei Bedarf über die GitHub-Weboberfläche ergänzen.

- **Modellvergleich** (SPEC Schritt 2): drei lokale Kandidaten (e5-small, EmbeddingGemma 300M,
  Model2Vec) und Voyage an zehn typischen Fragen einer echten deutschen Vault, Trefferqualität
  und CPU-Laufzeit dokumentieren. Bisher nur e5-small, kalibriert an der kleinen Test-Vault.
- **Relevanzschwellen an einer echten Vault nachkalibrieren** (`min_similarity`, `strong_similarity`
  in `src/plug_n_rag/embed/local.py`; Knick-Schwellen in `tuning.py`). Die Test-Vault hat nur
  sieben Notizen; IDF-Gewichte sind dort wenig aussagekräftig.
- **Voyage gegen die echte API**: In dieser Sitzung war kein `VOYAGE_API_KEY` gesetzt; getestet
  wurde gegen einen lokalen Fake-Server. `pytest -m voyage` mit gesetztem Key nachholen und die
  Schwellen für Voyage (`min_similarity` 0,35 / `strong_similarity` 0,55 sind Schätzwerte) prüfen.
- **Preisabfrage zur Laufzeit**: Die Skills weisen Claude an, den aktuellen Voyage-Preis auf
  voyageai.com/pricing nachzusehen. Ein Kern-Befehl, der Preise selbst ermittelt, fehlt.
- **OCR mit Tesseract** ist implementiert, aber hier nicht installiert und deshalb ungetestet.
  Schwellen (Konfidenz 70, 60 % echte Wörter) an echten Scans bestimmen. Docling als Alternative
  prüfen; Marker nur nach Lizenzprüfung.
- **DOCX, HTML, EPUB** im Sammlungs-Modus (Positionsangabe „Absätze“ ist im Modell vorgesehen).
- **Gemeinsame Suche über mehrere Sammlungen** (SPEC: nicht Version 1).
- **Schwerpunkte der Karte**: einfaches k-Means mit Benennung über Tags und Überschriftenwörter.
  Bei großen Vaults prüfen, ob die Namen hilfreich sind.
- **Modell kleiner machen**: ONNX-Datei ist 470 MB (fp32). Eine int8-Quantisierung (~120 MB) würde
  Download und Cloud-Start beschleunigen; braucht eigenen Modellbezeichner und Vergleichstest.
- **GitHub Actions als Sicherheitsnetz** (SPEC: später).
- **„weitergelesen zählt nur, wenn danach zitiert wurde“** (Leitplanke der SPEC): Das Protokoll
  sieht Lese-Aufrufe (`lesen`, `gliederung`), aber keine Zitate in Antworten. Gezählt werden
  daher nur tatsächliche Lese-Aufrufe auf Treffer, nicht bloßes Weiterblättern.
- **Read-Werkzeug im Lernprotokoll**: Liest Claude Abschnitte mit dem eingebauten Read statt mit
  `plug-n-rag lesen`, sieht das Lernprotokoll das nicht. Möglich wäre ein PostToolUse-Hook.
- **Weitere Sprachen**: Ausgaben gibt es auf Deutsch und Englisch (0.9). Das Modell kann rund 100
  Sprachen; für weitere Ausgabesprachen müsste `tr()` zu einer Tabelle werden.
- **Englisch an einer echten englischen Vault prüfen** (Schwellen `min_similarity`/`strong_similarity`
  sind an deutschen Texten kalibriert; an der englischen Beispiel-Vault passten sie). Ebenso die
  Suche über Sprachgrenzen hinweg in gemischten Vaults.

## Kann-Umfang (Punkt 8 des Auftrags)

Umgesetzt als Skills: `/plug-n-rag:modell-wechseln` und `/plug-n-rag:lernen-zuruecksetzen`
(Kern: `plug-n-rag konfig --setzen …`, `plug-n-rag reindex --ja`, `plug-n-rag lernen --zuruecksetzen`).
Ein vollautomatischer Kostenvoranschlag mit Live-Preisen fehlt (siehe oben).
