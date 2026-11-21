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

## Nachtrag 20.11.2026: Ordneraufbau und Abschriften (0.6.0)

37. **Trennung nach Art der Dateien.** *Teilbar* (Konfiguration, Index, optionale Abschriften) liegt
    in genau einem Ordner `.plug-n-rag/`, auch die Konfiguration (`.plug-n-rag/plug-n-rag.yml`
    statt im Wurzelordner). *Flüchtig* (Suchdatenbank, Protokoll, Zwischenstände, Seitenbilder,
    Extrakte) liegt immer zentral im Cache des Benutzers (`<cache>/plug-n-rag/state/<name>-<hash>/`).
    Grund: iCloud, OneDrive oder Obsidian Sync würden die ständig wechselnde SQLite-Datenbank
    sonst mitsynchronisieren; `.gitignore`-Einträge für den Cache entfallen.
38. **Überall derselbe Name `.plug-n-rag`** (Entscheidung der Auftraggebenden), auch für Sammlungen.
39. **Sammlungen: Ablageort wird gefragt** (im Ordner oder zentral). Empfehlung im Ordner, wenn er
    ein Git-Repo ist oder geteilt bzw. synchronisiert wird; ohne Angabe wählt `init` im Ordner nur
    bei Git-Repos. Der zentrale Ort ist jetzt das **Datenverzeichnis** des Benutzers (Windows
    `%APPDATA%`, macOS `~/Library/Application Support`, Linux `~/.local/share`), nicht mehr der
    Cache, weil Aufräumprogramme Caches leeren und ein Index Geld kosten kann.
40. **Vaults: kein Ablageort-Dialog.** Der Index gehört in die Vault (mehrere Geräte, Cloud).
    `umziehen --nach zentral` verlangt bei Vaults ein ausdrückliches `--trotzdem`.
41. **Abschriften: einmalige Frage, Antwort in `abschriften.ort`.** Vault: `neben_original` oder
    `ordner` (Standard „Abschriften/“, gespiegelte Unterordner). Sammlung: `ordner` (lesbar in
    `.plug-n-rag/abschriften/`) oder `intern`. Abschriften tragen `datei_hash`; fehlt der Cache
    (anderer Rechner, Kopie des Ordners, Cache geleert), stellt plug-n-rag den Seitentext daraus
    wieder her, ohne erneut abzuschreiben.
42. **Bezahlte Abschriften gehen nie verloren.** Ein neuer Extraktor (`pdf-v2`) übernimmt die
    Seitentexte älterer Extrakte mit Transkription. Alte Caches (`.plug-n-rag/cache`, zentrale
    Sammlungen unter dem Cache-Ordner) werden beim ersten Lauf automatisch in den neuen Cache
    kopiert. Behebt einen Fehler aus 0.5.0, durch den Abschriften aus 0.4 als „wartet auf
    Aufnahme“ erschienen wären.
43. **`plug-n-rag umziehen [--nach ordner|zentral]`** stellt auf den neuen Aufbau um bzw. wechselt
    den Ort, ohne neu zu berechnen. Der alte Aufbau wird weiter erkannt; der Sitzungsstart weist
    einmal pro Sitzung darauf hin.
44. **Version 0.6.0.**

## Nachtrag 20.11.2026: Anzeige im Chat als eigener Mod (0.7.0)

45. **Eigenes Plugin `plug-n-rag-anzeige` im selben Marketplace** (Entscheidung der
    Auftraggebenden), unter `plugins/plug-n-rag-anzeige/`. Ein Mod läuft ohne Sandbox und kann von
    Organisationen gesperrt werden; getrennt bleibt plug-n-rag für alle nutzbar, und wer keine
    Anzeige will, installiert sie nicht. Das Anzeige-Plugin listet plug-n-rag als Abhängigkeit.
46. **Daten aus der Werkzeugausgabe, nicht aus einem Feed.** Die Zeile eines Werkzeugaufrufs
    (`ToolUse`) erhält Eingabe und Ausgabe des Bash-Befehls. Der Mod liest die (stabile, deutsche)
    Textausgabe von `plug-n-rag suche`, `lesen` usw. Der im Konzept geplante Aktivitäts-Feed ist
    dadurch unnötig; die Ausgabe an Claude bleibt unverändert.
47. **`plug-n-rag anzeige-daten`** liefert JSON für Seitenleiste und Band (Dateien, Indexierung mit
    Fortschritt, wartende Scans, Ersparnis, Karte), lokal und ohne Modell, ohne Notizinhalte und
    Suchanfragen. Der Abgleich schreibt dafür bei langen Läufen alle 2 s eine Fortschrittsdatei.
    Der Mod findet den Starter von plug-n-rag als Nachbar-Plugin (Ordner- oder Cache-Layout), sonst
    über den stabilen Starter im Benutzer-Cache oder den PATH.
48. **Unaufdringlich nach den Mustern der App:** kompakte Zeile statt des Bash-Befehls (Strg+O zeigt
    das Original), Details nur auf Klick, Band nur bei laufender Indexierung oder offenen Aufgaben
    und ausblendbar, Seitenleiste nur auf Wunsch (`/pnr`). In der Handy-App bleibt die native Zeile
    mit einer ruhigen Zusatzzeile. Kein Button handelt selbst: Vorschläge landen über
    `$.prompt.fill` im Eingabefeld.
49. **Barrierefreiheit:** Relevanz als Wort plus Form (●●●/●●○/●○○), keine Farbe als einzige
    Information, Farben aus dem Theme der App, alle Buttons mit Beschriftung und Tasten (1–3, R),
    keine Animation.
50. **Cloud-Sitzungen** zeichnen nichts. Dort bittet der Sitzungsstart Claude um eine Quellenzeile
    unter Antworten aus der Vault (`anzeige: kompakt`, abschaltbar mit `aus`).
51. **Version 0.7.0** (plug-n-rag), **0.1.0** (plug-n-rag-anzeige).

## Nachtrag 20.11.2026: Nichts tun, wo nichts zu tun ist (0.7.1 / Anzeige 0.1.1)

52. **Der Starter prüft selbst, ob ein Hook gebraucht wird.** Bei `session-start` und `stop` sucht
    er im Projektordner und darüber nach `.obsidian/`, `.plug-n-rag/plug-n-rag.yml` oder dem alten
    `plug-n-rag.yml` und in der Liste zentral gespeicherter Sammlungen. Ohne Treffer endet er sofort,
    ohne uv oder Python zu starten. Das spart in fremden Projekten den Programmstart und vor allem
    den einmaligen Paket-Download beim ersten Start nach der Installation. Unter Windows entscheidet
    bei vorhandener Sammlungsliste weiterhin Python (Pfade sind dort anders geschrieben).
53. **Der Anzeige-Mod fragt beim Sitzungsstart nur in der Nähe einer Vault oder Sammlung Daten ab**
    (gleiche Merkmale, über `$.fs.exists` und die Sammlungsliste). Nach jedem tatsächlichen
    plug-n-rag-Aufruf und bei `/pnr` fragt er weiterhin.

## Nachtrag 20.11.2026: Repo als Marketplace mit mehreren Plugins (0.8.0 / Anzeige 0.1.2)

54. **Jedes Plugin in `plugins/<name>/`**, auch plug-n-rag selbst (vorher Quelle `./`, das ganze Repo).
    Grund: Mit `./` steckte jedes weitere Plugin im Paket von plug-n-rag mit drin, und Dokumente des
    Repos (SPEC, DECISIONS) wurden mitinstalliert. Jetzt enthält jedes Plugin nur sich selbst. Im
    Plugin-Cache ändert sich nichts (`…/<marketplace>/plug-n-rag/<version>/scripts/plug-n-rag`),
    deshalb funktionieren Setup-Skripte für Cloud-Umgebungen und der stabile Starter unverändert.
    Repo-Ebene: Katalog, Anleitung, Spezifikation, Entscheidungen, Lizenz, `tools/check.sh`,
    `CONTRIBUTING.md`.
55. **`tools/check.sh`** prüft den Katalog und jedes Plugin unter `plugins/` (validate, pytest bei
    `pyproject.toml`, Mod-Tests bei `*.test.ts(x)`) und findet neue Plugins von selbst. Eine
    GitHub-Action dafür ist bewusst noch nicht angelegt (siehe OPEN.md).
56. **Lizenz und Hinweise in jedem Plugin-Ordner**, weil installierte Plugins nur ihren eigenen
    Ordner bekommen.
57. **Anzeige 0.1.2** sucht den Starter zuerst unter `plugins/plug-n-rag/` (Ordner-Marketplace),
    dann wie bisher im Plugin-Cache und im alten Aufbau.

## Nachtrag 20.11.2026: Zweisprachig, Englisch und Deutsch (0.9.0 / Anzeige 0.2.0)

58. **Werkzeug und Anleitung in beiden Sprachen.** plug-n-rag spart Tokens und damit Rechenleistung;
    das soll nicht an einer Sprachgrenze enden. Das Suchmodell bleibt multilingual-e5-small: gezielt
    gewählt wegen seiner Stärke im Deutschen, im Englischen genauso gut (an einer englischen
    Beispiel-Vault belegt: Umschreibungen ohne gemeinsame Wörter treffen, Fremdthemen ergeben
    „Nothing relevant found“, eine deutsche Frage findet eine englische Notiz; `tests/test_english.py`).
    Über Sprachgrenzen hinweg trifft die Suche seltener als innerhalb einer Sprache; die Skill-Anleitung
    rät deshalb, bei mageren Treffern zusätzlich in der Sprache der Notizen zu fragen.
59. **Texte nebeneinander im Code**, `tr("Deutsch", "English")` (`i18n.py`), statt Übersetzungsdateien:
    Beide Fassungen stehen an der Stelle, an der sie gebraucht werden, und können nicht
    auseinanderlaufen. Zwei Sprachen rechtfertigen kein gettext.
60. **Welche Sprache gilt:** `PLUG_N_RAG_LANG` > `language` in der Konfiguration (vom Setup in der
    Sprache des Gesprächs gesetzt, `init --sprache/--language`) > Deutsch für Konfigurationen ohne
    diesen Schlüssel (alle vor 0.9 waren deutsch; bestehende Vaults ändern sich also nicht) >
    Systemsprache (`LC_ALL`, `LC_MESSAGES`, `LANG`; Deutsch nur bei `de…`). Claude antwortet immer
    in der Sprache der Nutzer:in; die Einstellung betrifft nur die festen Texte.
61. **Befehle, Optionen und Werte haben deutsche und englische Namen** (`suche`/`search`,
    `--zweck frage`/`--purpose question`, `--ablage ordner`/`--place folder` …). Gespeichert wird
    intern weiter der deutsche Wert, damit ältere Konfigurationen und Lernstände gültig bleiben. Die
    Hilfe (`--help`) nennt zuerst den Namen in der aktuellen Sprache.
62. **Skills:** deutsche Skills bleiben (bestehende Aufrufe funktionieren), Beschreibungen tragen einen
    englischen Satz, damit Claude sie auch bei englischen Anfragen auswählt. Für die von Hand
    aufgerufenen Skills gibt es englische Namen (`ingest`, `to-main`, `switch-model`,
    `reset-learning`), die über `plug-n-rag guide <name>` dieselbe Anleitung laden, mit denselben
    Werkzeugfreigaben. So gibt es eine Anleitung, nicht zwei.
63. **Anzeige 0.2.0** erkennt beide Ausgabeformate und spricht die Sprache, die `anzeige-daten`
    meldet (neues Feld `language`) oder die eine Ausgabe erkennen lässt.
64. **README:** Englisch als Hauptseite (`README.md`), Deutsch als `README.de.md`, gegenseitig verlinkt.
    DECISIONS, OPEN, SPEC und CONTRIBUTING bleiben deutsch (Arbeitsdokumente).
65. **Texterkennung mit den vorhandenen Sprachpaketen.** plug-n-rag fragt Tesseract einmal nach den
    installierten Paketen (`--list-langs`) und nutzt Deutsch und Englisch, soweit vorhanden, die
    Sprache der Vault zuerst. Vorher wurde immer `deu+eng` verlangt; fehlte ein Paket, lief die
    Erkennung ohne Sprachangabe (nur Englisch) neu, und deutsche Scans wurden schlechter erkannt.
    Fehlt ein Paket, sagt `aufnehmen` das, und der Skill bietet die Nachinstallation an.
66. **Neutrale Beispiel-Vault für die Tests** (Wohnen, Sanierung, Projekte, Umfragen) vor der
    Veröffentlichung. Sie bildet nach, was die alte Vault prüfte: eine Wortzusammensetzung, die nur
    als Teil vorkommt („Dachsanierung“ in „Dachsanierungsbedarf“), einen langen Abschnitt, der
    geteilt wird, Links und Backlinks, Umlaute in Dateinamen, eine private Notiz, einen privaten
    Ordner, eine Vorlage und ein PDF mit zwei Seiten. Die Relevanzschwellen bestehen auch an der
    neuen Vault (Umschreibungen treffen, Fremdthemen ergeben „Nichts Passendes gefunden“).
67. **Sichtbarer Name „plug-n-rag Display“** statt „plug-n-rag Anzeige (display)“: In der englischen
    Plugin-Liste wirkte das deutsche Wort verwirrend. Die Kennung `plug-n-rag-anzeige` bleibt, damit
    bestehende Installationen und Befehle gültig bleiben (Anzeige 0.2.1).
68. **Rückmeldung aus dem Alltag (0.9.1 / Display 0.2.2).**
    - Unter Windows rief Claude `plug-n-rag` einmal im PowerShell-Werkzeug auf und bekam
      „nicht erkannt“: Der Starter liegt über `CLAUDE_ENV_FILE` nur für das Bash-Werkzeug auf dem
      PATH. Jeder Skill sagt jetzt ausdrücklich „mit dem Bash-Werkzeug“, und der Sitzungsstart
      erinnert unter Windows daran.
    - Bis zur ersten Antwort verging bis zu einer Minute ohne Rückmeldung (Anleitung laden,
      mehrere Suchen; die Suche selbst dauert wenige Sekunden). Der Skill `suche` lässt Claude vorher
      einen Satz schreiben („Ich schaue nach, was in deinen Notizen dazu steht. Einen kleinen
      Moment.“).
    - Das Display fasst Lese-Befehle mit mehreren Abschnitten zusammen („Gelesen: 3 Abschnitte aus
      2 Notizen“) und nimmt nie eine Trennlinie wie `====` als Zusammenfassung.

## Nachtrag 21.11.2026: Selbst-Einrichtung der Vault für Cloud-Sitzungen

69. **Die Vault installiert plug-n-rag in Cloud-Sitzungen selbst** (`plug-n-rag cloud --einbinden`,
    0.9.2). Ergänzt Entscheidung 17, statt sie aufzuheben. Anlass: In einer Cloud-Sitzung mit
    Vault-Repo war `/plug-n-rag:setup` unbekannt. Das über die Plugin-Seite hinzugefügte Plugin kam
    dort nicht an (der Ordner für Konto-Plugins im Container war leer), und das Setup-Skript gehört
    zu einer einzelnen Umgebung. Beobachtet in einer Cloud-Sitzung mit Claude Code 2.1.330:
    - Start-Hooks aus `.claude/settings.json` des Repos laufen; nur `enabledPlugins` wird übergangen.
    - Ein Plugin, das ein solcher Hook installiert, ist in der Sitzung **nicht** geladen, auch nicht
      ab der zweiten Eingabe: Claude Code legt die Plugin-Liste vor dem Ende der Hooks fest. Nach
      `/reload-plugins` sind alle Skills da. Der Befehl `plug-n-rag` (PATH über `CLAUDE_ENV_FILE`)
      und die Startmeldung kommen dagegen sofort an.
    Daraus: `.plug-n-rag/cloud-start.sh` als Start-Hook. Es tut lokal nichts, tut nichts, wenn das
    Plugin beim Start schon da war (dann läuft dessen eigener Hook, keine doppelte Kurz-Karte),
    installiert sonst aus dem Marketplace und startet den Sitzungsstart von plug-n-rag selbst. Seine
    Meldung sagt Claude, `/plug-n-rag:…` bis zum `/reload-plugins` über `plug-n-rag anleitung`
    zu bedienen, statt den Befehl für unbekannt zu erklären. Belegt mit einer echten Sitzung, deren
    erste Eingabe `/plug-n-rag:status` war. Bestehende Einträge in `.claude/settings.json` bleiben
    erhalten; ungültiges JSON wird nie überschrieben; `--ausbinden` nimmt alles zurück. Eine Vault
    im Unterordner eines Repos wird abgelehnt, weil Cloud-Sitzungen im Hauptordner starten.
    Das Setup-Skript der Umgebung bleibt als Weg B (Modell vorab, alle Befehle ohne Nachladen) und
    meldet jetzt, wenn die Installation scheitert, statt Fehler stumm zu schlucken.

## Nachtrag 21.11.2026: Suchmodus in jeder Ausgabe (0.9.3)

70. **Jede Suche sagt, wie vollständig sie war.** Anlass: Rückmeldung aus einer Cloud-Sitzung
    (Vault mit 32 Dateien). Beim Start hieß es „Modell lädt im Hintergrund, bis dahin
    Stichwortsuche“, die Ausgabe von `suche` sagte danach aber nicht, in welchem Modus sie lief.
    Claude behandelte frühe Ergebnisse als vollständig; dieselbe Frage lieferte später andere
    Reihenfolge und zusätzliche Notizen. Dabei zeigte sich ein Fehler: War der Index aus dem Repo
    vollständig, gab es nichts einzubetten, also startete auch kein Hintergrund-Abgleich, und das
    angekündigte Modell lud niemand. Die erste Suche hätte dann selbst 470 MB geladen, mit einer
    zweiten Kopie parallel zu einem laufenden Download in dieselbe Datei. Daraus:
    - Erste Zeile jeder Suche: „Suchmodus: semantisch + Stichwort · Index vollständig“, „nur
      Stichwort · Suchmodell lädt (60 %)“ (Fortschritt aus `.download.json` im Modellordner),
      „… aber erst 20 von 32 Dateien semantisch indexiert“, „Index passt nicht zum Modell“.
    - Ist das Ergebnis unvollständig, steht „⚠ Vorläufiges Ergebnis“ **beim Ergebnis**, nicht nur
      beim Sitzungsstart, mit dem Auftrag, die Antwort als vorläufig zu kennzeichnen. „Nichts
      gefunden“ gilt dann nicht als „steht nicht in den Notizen“.
    - `suche --warten [sek]` blockiert, bis Modell und Index bereit sind, und erledigt die Arbeit
      selbst, wenn niemand sonst sie tut. Es bricht ab, wenn Warten nicht hilft.
    - Die Suche lädt das Modell nie selbst; sie startet höchstens den Hintergrund-Download. Der
      Sitzungsstart startet ihn jetzt auch bei vollständigem Index (`sync --modell-vorab`). Jeder
      Prozess lädt in eine eigene `.part`-Datei.
    - `status` nennt, seit wann die semantische Suche vollständig ist (`complete_at` in
      `pending.json`, bleibt erhalten, solange der Index vollständig bleibt; dazu der Zeitpunkt, an
      dem das Modell fertig geladen war).
    - Vorläufige Suchen zählen nicht für die Token-Steuerung: Tieferes Lesen gleicht dann fehlende
      Treffer aus und sagt nichts über die richtige Tiefe.

71. **Chronologie als eigener Weg, nicht als Relevanz.** Aus derselben Sitzung: „Was passierte
    danach?“ ließ sich mit der Relevanzsuche nicht beantworten, Claude wich auf `ls`/`cat` aus, und
    die Wochennotiz `2024-W07.md` tauchte in keiner Suche auf. `suche --chronologisch` listet
    Notizen nach ihrem eigenen Datum (Dateiname `2024-02-12`, `2024-W07`, `2024-02` oder
    Frontmatter `date`/`datum`), mit `--in`, `--tag` und `--seit` (hier: Datum der Notiz) und
    optional einer Frage, die auf passende Notizen einschränkt. Eine Wochennotiz zählt ab ihrem
    Montag und erscheint auch, wenn `--seit` mitten in ihrer Woche liegt. Die Änderungszeit dient
    bewusst nicht als Datum: In einem Git-Klon (Cloud) tragen alle Dateien die Zeit des Auscheckens.
    `verwandt` nennt bei datierten Notizen den Tag davor und danach im selben Ordner sowie die
    Wochennotiz (bzw. bei einer Wochennotiz die Tage der Woche).

72. **Beim Sitzungsstart nach einer neueren Version sehen** (0.9.3). Wunsch aus derselben
    Rückmeldung. Quelle ist `plugin.json` auf `main` im Marketplace-Repo, erst über
    raw.githubusercontent.com (3 s), sonst über `git fetch --depth 1` (Cloud-Umgebungen lassen
    github.com oft nur für Git durch). Ein Ergebnis gilt sechs Stunden, ein Fehlschlag eine Stunde
    lang: ohne Netz bleibt der Start schnell und still. Einstellung `updates` in der Konfiguration
    der Vault (nicht im Benutzerordner, weil Cloud-Container ihn vergessen): `fragen` (Standard,
    Claude fragt einmal), `automatisch` (Aktualisierung im Hintergrund), `aus`. `plug-n-rag
    aktualisieren --spaeter` merkt die abgelehnte Version in `updates_skip`; erst eine neuere wird
    wieder angeboten. Aktualisiert wird ausschließlich über Claude Codes eigene Befehle
    (`claude plugin marketplace update`, `claude plugin update`, mit dem installierten Scope, und
    plug-n-rag Display mit, falls installiert); plug-n-rag schreibt nie selbst in die Plugin-Ordner.
    Danach zeigt der Starter `plug-n-rag` auf die neue Version, Skills und Hooks gelten nach
    `/reload-plugins` oder ab der nächsten Sitzung. Läuft das Plugin aus einem Ordner (Entwicklung),
    gibt es nur den Hinweis auf `git pull`. Geprüft mit einer echten Installation über einen lokalen
    Marketplace: 0.9.3 → 0.9.4, Starter umgestellt.
