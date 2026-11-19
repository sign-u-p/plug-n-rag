# Offene Punkte

Stand: 19.11.2026, nach Sprint 1.

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
- [ ] **Cloud-Sitzung** (claude.ai/code) mit einem Vault-Repo:
  - [ ] Lädt das Plugin über `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json`?
  - [ ] Modell-Download hinter der Netzwerkfreigabe: welche Hosts genau? Getestet war hier
        `huggingface.co` → Weiterleitung auf `us.aws.cdn.hf.co`. Je nach Region auch
        `cas-bridge.xethub.hf.co` o. ä. Ohne Freigabe: Meldung + Stichwortsuche (getestet nur
        als Unit-Test mit nicht erreichbarem Provider).
  - [ ] Frische Sitzung sucht ohne neues Embedding (als Unit-Test mit Klon ohne Cache belegt).
  - [ ] Dauer des ersten Starts inkl. `uv`-Installation der Abhängigkeiten und 470-MB-Download.
- [ ] **Windows**: Launcher `bin/plug-n-rag` ist ein POSIX-Shell-Skript. Claude Code nutzt unter
      Windows meist Git Bash; ohne Git Bash ist ein `.cmd`-Gegenstück nötig.
- [ ] **macOS mit Homebrew-Python**: Lässt sich sqlite-vec laden? (Sonst greift der NumPy-Fallback,
      `plug-n-rag status` zeigt es an.)
- [ ] MCP-Wrapper als Server in Claude Code registrieren (siehe README) und prüfen, ob Claude die
      Werkzeuge den Bash-Aufrufen vorzieht.

## Nicht umgesetzt oder nur teilweise

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
- **Sprachumschaltung**: Ausgaben sind nur deutsch.

## Kann-Umfang (Punkt 8 des Auftrags)

Umgesetzt als Skills: `/plug-n-rag:modell-wechseln` und `/plug-n-rag:lernen-zuruecksetzen`
(Kern: `plug-n-rag konfig --setzen …`, `plug-n-rag reindex --ja`, `plug-n-rag lernen --zuruecksetzen`).
Ein vollautomatischer Kostenvoranschlag mit Live-Preisen fehlt (siehe oben).
