# Entscheidungen

Entscheidungen, die SPEC.md offen ließ, und Abweichungen von SPEC.md, jeweils mit Begründung.
Stand: 19.11.2026, Sprint 1.

## Offene Punkte aus SPEC.md, jetzt entschieden

| Thema | Entscheidung | Begründung |
| --- | --- | --- |
| Implementierungssprache | Python ≥ 3.10, ausgeführt über `uv` | Vorgabe des Auftrags, Empfehlung der SPEC. uv bringt bei Bedarf eine Python-Version mit. |
| Lokales Standardmodell | `intfloat/multilingual-e5-small`, gepinnt auf Hugging-Face-Commit `614241f622f53c4eeff9890bdc4f31cfecc418b3`, ONNX-Datei `onnx/model.onnx` | Mehrsprachig mit gutem Deutsch, 384 Dimensionen, auf CPU schnell (18 Abschnitte in unter 1 s nach dem Laden). Ein Vergleichstest mit weiteren Kandidaten steht in OPEN.md. |
| Laufzeit für das lokale Modell | `onnxruntime` + `tokenizers` + NumPy, eigene Mean-Pooling-Implementierung | Kein PyTorch (Gigabytes), keine `sentence-transformers`, läuft auf macOS (ARM/Intel), Linux und Windows. |
| Modell-Download | Direkt per HTTPS von `huggingface.co/<modell>/resolve/<revision>/…` in `~/.cache/plug-n-rag/models` (überschreibbar mit `PLUG_N_RAG_MODEL_DIR`) | Kein `huggingface_hub` als Abhängigkeit; die Revision im Pfad garantiert, dass Gewichte nie unbemerkt wechseln. |
| PDF-Extraktion | `pypdf` (BSD) | PyMuPDF steht unter AGPL und würde die Lizenz des Plugins beeinflussen. pypdf reicht für die Textebene. Rendering von Seitenbildern für die Transkription mit `pypdfium2` (optionales Extra `aufnahme`), Fallback `pdftoppm`. |
| Formate in Version 1 | Markdown, Text, PDF mit Textebene | Empfehlung der SPEC. DOCX, HTML, EPUB später. |
| OCR | Tesseract (falls installiert, Sprachen `deu+eng`), sonst Transkription durch Subagent nur mit Zustimmung | Kostenlos und offline; keine Pflichtabhängigkeit, weil Laien Tesseract selten installiert haben. |
| Schwellen der Qualitätsprüfung | Tesseract-Konfidenz ≥ 70 und ≥ 60 % echte Wörter | Startwerte; an echten Scans zu bestimmen (OPEN.md). |
| Schwellen der Relevanz | e5-small: semantisch relevant ab Kosinus 0,83, „sehr passend“ ab 0,87; Stichwortabdeckung ≥ 50 % | Kalibriert an der Test-Vault: passende Treffer 0,84–0,90, unpassende Fragen 0,80–0,82. Werte stehen pro Modell in `embed/local.py`. |
| Knick-Erkennung | Schnitt am kleinsten Verhältnis aufeinanderfolgender Notiz-Scores, wenn es unter 0,55 (frage), 0,45 (erstellen) bzw. 0,35 (recherche) liegt; Mindestzahl 1/2/3 | `recherche` soll Breite liefern, `frage` Präzision. |
| Lizenz | MIT | Wie die Referenzprojekte; Hinweise in `THIRD_PARTY_NOTICES.md`. |

## Namensanpassungen (Arbeitsnamen mit `vault-`)

| SPEC (Arbeitsname) | Umsetzung | Grund |
| --- | --- | --- |
| CLI `vault <befehl>` | `plug-n-rag <befehl>` (Unterbefehle deutsch wie in der SPEC, englische Aliase `search`, `outline`, `read`, `related`, `map`) | Eindeutig, kollidiert nicht mit anderen Programmen namens `vault` (z. B. HashiCorp Vault). |
| `vault-plugin.yml` | `plug-n-rag.yml` im Wurzelordner | Sichtbar und selbsterklärend für Nutzer:innen. |
| `.vault-index/` | `.plug-n-rag/index/` | Ein einziger versteckter Ordner für alles, was plug-n-rag anlegt. |
| `.vault-cache/` | `.plug-n-rag/cache/` | Wird über `.plug-n-rag/.gitignore` und einen Eintrag in `.gitignore` nie committet. |
| `vault-tuning.json` | `.plug-n-rag/tuning.json` (mit `tuning.commit_learning: true`), sonst `.plug-n-rag/cache/tuning.json` | Siehe oben. |
| Skill `vault-search` | Skill `suche` → `/plug-n-rag:suche` | Plugin-Komponenten werden automatisch mit `plug-n-rag:` benannt. |
| `/vault-setup`, `/vault-status`, `/vault-reindex`, `/vault-aufnehmen`, `/vault-modell-wechseln`, `/vault-lernen-zuruecksetzen` | `/plug-n-rag:setup`, `:status`, `:reindex`, `:aufnehmen`, `:modell-wechseln`, `:lernen-zuruecksetzen` | Namensraum durch das Plugin. |
| Sammlungs-Cache `~/.cache/<plugin>/<pfad-hash>/` | `~/.cache/plug-n-rag/collections/<ordnername>-<hash>/`, Zuordnung in `~/.config/plug-n-rag/collections.json` | Ordnername im Pfad hilft beim Wiederfinden. |

## Abweichungen von SPEC.md

1. **Slash-Befehle als Skills statt `commands/`.** Die aktuelle Plugin-Dokumentation empfiehlt
   `skills/` für neue Plugins; Skills erscheinen ebenfalls als `/plug-n-rag:<name>`.
   `status`, `reindex`, `modell-wechseln` und `lernen-zuruecksetzen` sind mit
   `disable-model-invocation: true` markiert: Sie kosten so keinen Kontext in jeder Sitzung
   (gemessen: rund 430 Tokens weniger), Nutzer:innen rufen sie selbst auf.
2. ~~**Ausführbares Programm in `bin/`.**~~ (ersetzt durch Punkt 26) Claude Code legt `bin/` eines aktiven Plugins auf den PATH
   des Bash-Werkzeugs, deshalb heißt der Aufruf überall einfach `plug-n-rag …`. Nachteil laut
   Dokumentation: claude.ai und Cowork installieren Plugins mit `bin/` nicht. Für den späteren
   Konnektor in der Claude-App ist ohnehin der MCP-Wrapper vorgesehen.
3. **Chunk-Hash ohne Dateinamen-Titel.** SPEC: Hash über „Titel + heading_path + Text“. Fällt der
   Titel auf den Dateinamen zurück, würde Umbenennen neu einbetten. Deshalb geht nur ein
   *ausdrücklicher* Titel (Frontmatter `title`/`titel` oder erste H1) in den Hash ein. Der
   Breadcrumb im Embedding-Text enthält weiterhin den Dateinamen; nach einem Umbenennen bleibt
   der alte Vektor (mit altem Namen im Breadcrumb) in Gebrauch. Das ist gewollt (Akzeptanzkriterium).
4. **Hydrate liest Text durch erneutes Chunking**, nicht durch Ausschneiden von Zeilen. Die
   Abschnitte werden deterministisch neu berechnet und über den Hash den Vektoren zugeordnet.
   Vorteil: auch veraltete Index-Dateien liefern Vektoren für alle unveränderten Abschnitte, und
   Dateien ohne Index-Datei sind trotzdem per Stichwort auffindbar.
5. **PDF-Abschnitte überschreiten nie eine Seitengrenze**, damit Belege immer genau eine Seite
   (oder einen Seitenbereich bei Lesezeichen) nennen.
6. **Vault-Modus indexiert standardmäßig nur Markdown.** PDFs in einer Vault werden über
   `/plug-n-rag:aufnehmen` zu Notizen (SPEC-Ablauf). Mit `formats: [markdown, pdf]` lassen sich
   PDFs auch direkt indexieren.
7. **Zusätzliche Git-Einstellung `git.auto_commit: off | index | all` und `git.auto_push`.** Die SPEC
   beschreibt „Änderungen werden beim nächsten Start erfasst und committet“ für den Weg ohne
   Obsidian Git. Standard ist `off`; das Setup fragt nach.
8. **Stop-Hook läuft asynchron** (`async: true`). So blockiert er nie die nächste Eingabe, auch wenn
   ein geänderter Text eingebettet werden muss.
9. **SessionStart mit Zeitbudget** (6 s): Was nicht fertig wird, indexiert ein Hintergrundprozess
   weiter; ist das Modell noch nicht heruntergeladen, wird im Hook gar nicht eingebettet. Die
   Stichwortsuche funktioniert sofort.
10. **Relevanz in Worten mit drei Stufen**: „sehr passend“, „passend“, „am Rande“.
11. **Suchausgabe endet mit einem `Lesen:`-Hinweis** auf den besten Abschnitt. Im End-to-End-Test
    hat Claude ohne diesen Hinweis ganze Dateien gelesen; mit ihm liest es gezielt Abschnitte.
12. **MCP-Wrapper ist vorhanden, aber nicht automatisch registriert.** Ein automatisch gestarteter
    MCP-Server würde in jedem Projekt (auch ohne Vault) starten und seine Abhängigkeiten
    installieren. Aktivierung beschreibt die README. Die MCP-Werkzeuge liefern dieselben Texte
    wie die CLI (kein eigenes JSON-Format).
13. **Kein `vault --json`** für die Suche: Der MCP-Wrapper gibt Text zurück, wie die CLI.
    `plug-n-rag inventur --json` gibt es für das Setup.
14. **Voyage-Standardmodell `voyage-3.5-lite` mit 1.024 Dimensionen**, Key aus `VOYAGE_API_KEY` oder
    `~/.config/plug-n-rag/voyage_api_key`. Voyage hat keine Revisionen; der Modellbezeichner ist
    `voyage:<modell>@d<dimensionen>`.
15. **Token-Schätzung** pauschal mit etwa 3,8 Zeichen pro Token. Nur für Größenangaben und die
    Ersparnis-Schätzung, nie für harte Grenzen.
16. **Lernen läuft beim Sitzungsstart** (`tuning.learn`), höchstens ein Schritt pro Sitzung
    (gleitender Mittelwert mit α = 0,15, aufgerundet auf eine Einheit). Gelernte Werte gelten
    erst ab 5 Beobachtungen pro Zweck.

## Nachtrag 19.11.2026: Cloud-Sitzungen

17. **Cloud-Sitzungen über ein Setup-Skript der Cloud-Umgebung, nicht über das Vault-Repo.**
    Laut Dokumentation installieren Cloud-Sitzungen keine Plugins aus `enabledPlugins` oder
    `extraKnownMarketplaces` in `.claude/settings.json` eines Repos (die erste Fassung von README und
    Setup-Skill hatte das falsch empfohlen). Stattdessen installiert ein Setup-Skript plug-n-rag
    im Container mit `claude plugin install` (Nutzerebene) und lädt das Modell mit
    `plug-n-rag modell-laden` vorab. Die Umgebung wird danach als Abbild gespeichert, sodass
    Plugin, Python-Pakete und Modell in späteren Sitzungen schon da sind. Belegt in dieser
    Cloud-Sitzung: Ein so installiertes Plugin wurde von der laufenden Sitzung geladen
    (Skills und Agent erschienen).
18. **Netzwerkfreigabe `huggingface.co` und `*.hf.co`.** Hugging Face leitet Downloads auf
    wechselnde CDN-Hosts unter `hf.co` um (z. B. `us.aws.cdn.hf.co`); Cloud-Umgebungen erlauben
    Platzhalter mit `*.`.
19. **Voyage in der Cloud über ein Netzwerk-Secret.** Ist kein Key sichtbar und läuft plug-n-rag in
    einer Cloud-Sitzung (`CLAUDE_CODE_REMOTE=true`), sendet es den Platzhalter `proxy-injected`;
    der Netzwerk-Proxy setzt den echten Key ein. Der Key gelangt so nie in die Sitzung.
20. **Neue Befehle** `plug-n-rag cloud` (Anleitung, `--skript`, `--pruefen`) und
    `plug-n-rag modell-laden`, neuer Skill `/plug-n-rag:cloud`. Die Anleitung kommt aus dem Kern,
    damit Hosts und Skript zur Konfiguration der Vault passen (lokal oder Voyage).
21. **Version 0.2.0**: Die Version in `plugin.json` ist gesetzt, deshalb bekommen installierte
    Plugins Änderungen erst mit einer neuen Versionsnummer.

## Nachtrag 19.11.2026: Einrichtung in der Cloud, Übernahme nach main

22. **Einrichtung komplett in einer Cloud-Sitzung.** Claude installiert das Plugin auf Wunsch der
    Nutzer:in mit `claude plugin marketplace add` / `install` in der laufenden Sitzung. Belegt in
    dieser Cloud-Sitzung: Skills, Agent und der Befehl `plug-n-rag` (über `bin/` auf dem PATH)
    standen danach sofort bereit. Die README gibt einen Startsatz zum Kopieren vor; der
    Setup-Leitfaden hat einen eigenen Abschnitt „Cloud-Weg“ (lokale Schritte überspringen,
    Netzwerkfreigabe vor der Indexierung, Setup-Skript für künftige Sitzungen sichern).
23. **`plug-n-rag cloud --hosts`** ermittelt die exakten Download-Hosts (Weiterleitung von
    huggingface.co). Werkzeuge zum Ändern der Cloud-Umgebung akzeptieren oft keine Platzhalter
    wie `*.hf.co`; von Hand eingetragen ist `*.hf.co` robuster, weil der CDN-Host je nach Region
    wechselt.
24. **`plug-n-rag nach-main` und Skill `/plug-n-rag:nach-main`.** Cloud-Sitzungen arbeiten auf
    eigenen Branches; die Nutzer:in soll trotzdem aus dem Chat heraus alles in den Hauptstand legen
    können. Der Befehl committet Notizen und Index, holt `main`, **führt zusammen statt zu
    rebasen**, pusht nach `main` (nie `--force`) und zusätzlich auf den Sitzungs-Branch.
    Index-Konflikte werden neu berechnet, Notiz-Konflikte brechen ohne Änderung ab, ein
    API-Key-ähnlicher Inhalt verhindert den Commit. Der Skill verlangt die ausdrückliche
    Aufforderung im Chat; sie gilt als Erlaubnis für diesen einen Push.
25. **Version 0.3.0.**

## Nachtrag 19.11.2026: Installation über die Plugin-Seite

26. **Starter in `scripts/` statt `bin/`.** claude.ai lehnt Plugins mit einem `bin/`-Ordner auf
    oberster Ebene ab. Damit Nutzer:innen plug-n-rag über die Plugin-Seite der Desktop-App bzw.
    von claude.ai hinzufügen können („Hinzufügen → Marketplace hinzufügen → sign-u-p/plug-n-rag“),
    liegt der Starter jetzt in `scripts/plug-n-rag`. Der SessionStart-Hook schreibt
    `export PATH="<plugin>/scripts:$PATH"` in `CLAUDE_ENV_FILE`, sodass `plug-n-rag …` im
    Bash-Werkzeug weiter als einfacher Befehl funktioniert. Skills nennen zusätzlich den vollen Pfad
    über `${CLAUDE_PLUGIN_ROOT}`. Weg A der README ist damit die Plugin-Seite; Terminal und
    „Claude erledigt es“ bleiben als Wege B und C.
27. **Version 0.4.0.**

## Nachtrag 20.11.2026: Rückmeldung aus der ersten echten Einrichtung (Windows 11, Sammlungs-Modus)

28. **Python ≥ 3.11.** `onnxruntime` hat keine Pakete mehr für Python 3.10; uv wählte eine
    vorhandene 3.10 und die Installation scheiterte. `requires-python = ">=3.11"`, Lockfile neu.
    uv legt eine bestehende, unpassende Umgebung beim nächsten Aufruf selbst neu an.
29. **Pillow im Extra `aufnahme`** (pypdfium2 braucht es für `to_pil()`). Seitenbilder, die sich
    nicht erzeugen lassen, führen zu einer klaren Fehlermeldung mit Grund, statt still einen
    leeren Plan auszugeben.
30. **Inventur zählt PDFs mit Textebene und Textdateien.** Stichprobe von bis zu sechs Seiten pro
    PDF, hochgerechnet; PDF-Abschnitte mindestens einer pro Seite. Ausgegeben werden getrennte
    Schätzungen für Vault- und Sammlungs-Modus.
31. **pypdf-Warnungen auf ERROR** (die „fontTools is required…“-Flut kostete Kontext). Kein
    zusätzliches fonttools, weil die Textextraktion auch ohne es funktioniert.
32. **Literaturlisten abwerten.** Erkennung über die Überschrift (Literatur, Quellen, References …)
    oder den Text (viele Jahreszahlen pro 100 Wörter plus Verlags-/DOI-/Initialen-Muster).
    Solche Abschnitte bekommen 40 % der Stärke und 50 % des RRF-Werts und sind als
    „Literaturliste“ markiert, außer die Frage zielt erkennbar auf Literatur oder Quellen.
33. **Gedruckte Seitenzahlen.** Aus den Seitenbezeichnungen des PDFs (/PageLabels), sonst aus einer
    alleinstehenden Zahl in der ersten oder letzten Zeile, wenn die Mehrheit auf denselben Versatz
    kommt. Angezeigt als „S. 1 (gedruckt S. 11)“. Extraktionsversion `pdf-v2`: PDFs werden neu
    gelesen, Vektoren über den Hash-Pool wiederverwendet (kein neues Embedding).
34. **UTF-8 auch für die Fehler- und Fortschrittsausgabe** (Windows-Konsolen zeigten „St�rung“).
35. **Scans sind kein Fehler.** Eingescannte PDFs ohne Textebene heißen jetzt „wartet auf Aufnahme“
    und stehen als Hinweis in Abgleich, Status und Sitzungsstart, nicht unter „Fehler“.
36. **Version 0.5.0.**
