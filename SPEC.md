# plug-n-rag – Technische Spezifikation

Nov 18, 2026

## Zweck dieses Dokuments

Dieses Dokument ist die verbindliche Spezifikation für die Umsetzung von plug-n-rag. Es richtet sich an Agenten und Entwickler:innen ohne Vorwissen aus den Planungsgesprächen.

**Projekt:** plug-n-rag · Repository: [github.com/sign-u-p/plug-n-rag](https://github.com/sign-u-p/plug-n-rag). Dateinamen, Befehle und Pfade mit dem Präfix `vault-` in diesem Dokument sind Arbeitsnamen. Bei der Umsetzung dürfen sie an den Projektnamen angepasst werden, die Entscheidung kommt in DECISIONS.md.

**Stand:** Konzept. Es existiert noch kein Code. Alle Entscheidungen hier sind abgestimmt. Abweichungen nur nach Rückfrage.

**Kurzfassung:** Ein Claude-Code-Plugin, das eine Obsidian-Vault in einem Git-Repo semantisch durchsuchbar macht, auf ausdrücklichen Wunsch auch andere lokale Ordner wie Dokumentensammlungen oder Bibliotheken. Embeddings werden pro Notiz als Datei im Repo versioniert. In jeder Sitzung wird daraus eine lokale SQLite-Datenbank (FTS5 + sqlite-vec) gebaut. Hooks halten Vault und Index per Hash-Abgleich synchron. Ein Skill steuert, wie Claude sucht und liest, mit dem Ziel, Tokens zu sparen.

**Lesereihenfolge für Agenten:** Ziele → Architektur → Datenmodell → Abgleich → Suche. Die restlichen Abschnitte bei Bedarf.

**Sprache:** Nutzerseitige Texte (Befehle, Meldungen, Skill-Ausgaben an Nutzer:innen) auf Deutsch, Code und Bezeichner auf Englisch. Gendergerechte Sprache mit Doppelpunkt (Nutzer:innen).

## Ziele, Nicht-Ziele, Zielgruppe

**Zielgruppe:** Obsidian-Nutzer:innen ohne Entwicklungshintergrund, die mit Claude Code über ihre Vault arbeiten. Kein Git-, Terminal- oder Datenbankwissen voraussetzen. Deutschsprachige Vaults sind ein Primärfall. Sekundär: Menschen mit losen Dokumentensammlungen, Bibliotheken oder Projektordnern ohne Obsidian.

**Ziele**

1. Token-Verbrauch beim Arbeiten mit der Vault spürbar senken, durch gezielte Suche und stufenweises Lesen.
2. Bessere Trefferqualität als grep: semantisch, mit Teilwortsuche für deutsche Komposita.
3. Null Infrastruktur: kein Server, kein Docker, kein Datenbank-Hosting.
4. Identisches Verhalten lokal und in Claude-Code-Cloud-Sitzungen.
5. Vault und Index synchronisieren sich automatisch, über alle Änderungswege (Claude, Obsidian, GitHub-Web).
6. Vollständig begleitete Einrichtung, auch ohne bestehendes Repo.

**Nicht-Ziele (Version 1)**

- Kein MCP-Konnektor für die Claude-App. Kommt später, die Architektur soll ihn aber ermöglichen.
- Keine Suchoberfläche für Menschen. Das Plugin ist ein Werkzeug für den Agenten.
- Kein Erzeugen von Lerntools oder anderen Inhalten. Das Plugin verwaltet nur Daten.
- Keine Änderung bestehender Notizen ohne ausdrückliche Zustimmung.
- Kein Orphan-Branch und keine Git-Notes: zu komplex für die Zielgruppe.
- Keine Echtzeit-Dateiüberwachung.

## Geltungsbereich: Vaults und andere Ordner

Das Plugin kennt zwei Modi. Der **Vault-Modus** ist der Hauptfall und wird automatisch erkannt. Der **Sammlungs-Modus** gilt für beliebige lokale Ordner und wird nur auf ausdrücklichen Wunsch aktiviert, z. B. „Mach meinen Ordner Fachliteratur durchsuchbar“ oder `/vault-setup <pfad>`. Kern, Abgleich und Suche sind in beiden Modi identisch. Unterschiede betreffen nur Eingabe, Metadaten und Speicherort.

|  | Vault-Modus | Sammlungs-Modus |
| --- | --- | --- |
| Aktivierung | Automatisch erkannt am Ordner `.obsidian/`, Einrichtung angeboten | Nur auf ausdrücklichen Wunsch. Kein SessionStart-Hinweis in fremden Ordnern |
| Dateitypen | Markdown | Markdown, Text, PDF; später DOCX, HTML, EPUB |
| Metadaten | Frontmatter, Tags, Wikilinks, Obsidian-Vorlagen | Dokument-Metadaten (Titel, Autor), sonst Dateiname und Ordnerpfad |
| Positionsangaben | Zeilen | Zeilen bei Text, Seiten bei PDF, Absätze bei DOCX |
| Chunking | An Überschriften | An Überschriften, wenn erkennbar, sonst an Seiten- oder Absatzgrenzen |
| `verwandt` | Links und Backlinks, dann semantisch | Nur semantisch |
| Git und GitHub | Standard, im Setup eingerichtet | Optional. Ohne Repo rein lokal, ohne Cloud-Sitzungen |
| Speicherort Index | `.vault-index/` im Repo | Im Ordner, wenn Git vorhanden oder zugestimmt; sonst außerhalb im Nutzer-Cache |
| Änderungen am Ordner | Nur Index-Dateien und Konfiguration | Keine, außer dem Index-Ordner mit Zustimmung |

**Regeln für den Sammlungs-Modus**

- **Streng nur lesend:** Das Plugin legt keine Markdown-Fassungen, keine Konfiguration und keine Hilfsdateien in die Sammlung. Extrahierter Text liegt in `.vault-cache/extract/`, adressiert über `file_hash`, und wird bei Bedarf neu erzeugt.
- **Index außerhalb:** Ohne Git und ohne Zustimmung liegen Index, Konfiguration und Cache unter einem Nutzerverzeichnis, z. B. `~/.cache/<plugin>/<pfad-hash>/`. Der Abgleich per Hash funktioniert ohne Git unverändert.
- **Große Dateien:** Bücher erzeugen sehr viele Abschnitte. Der Kostenvoranschlag im Setup ist hier besonders wichtig. Angebot, einzelne Unterordner zuerst oder große Dateien später zu indexieren.
- **GitHub nur mit Bedacht:** Bibliotheken enthalten oft große Binärdateien und urheberrechtlich geschützte Werke. Das Setup empfiehlt hier den rein lokalen Betrieb und bietet ein Repo nur auf Nachfrage an, mit Hinweis auf das 100-MB-Limit und auf ein privates Repo.
- **Mehrere Ordner:** Pro Ordner eine eigene Sammlung mit eigenem Index und eigenem Modell. Eine gemeinsame Suche über mehrere Sammlungen ist nicht Teil von Version 1.
- **Lesen:** `vault lesen` liefert bei PDF und DOCX den extrahierten Text der Seiten oder Absätze, weil das Read-Werkzeug nicht jedes Format zuverlässig liest.

**Auswirkungen auf das Datenmodell**

- Index-Datei: zusätzliches Feld `format` (`markdown`, `text`, `pdf`, `docx` …). Statt `lines` wahlweise `pages` oder `paragraphs`.
- `vault-plugin.yml`: zusätzliche Felder `mode: vault | collection` und `index_location: inside | external`.
- `_meta.json`: zusätzlich die Version der Textextraktion, weil eine verbesserte Extraktion eine Neuindexierung der betroffenen Formate auslöst.

**Offen:** Extraktionsbibliotheken (z. B. PyMuPDF für PDF, python-docx, ebooklib), Umgang mit gescannten PDFs (OCR ja oder nein), Formate für Version 1. Empfehlung: Markdown, Text und PDF mit Textebene in Version 1, alles Weitere später.

**Einordnung in die Umsetzung:** Der Sammlungs-Modus folgt, wenn der Vault-Modus stabil läuft, zwischen Aufnahme und Veröffentlichung. Der Kern muss aber von Anfang an so gebaut sein, dass Dateiformat, Positionsangaben und Speicherort austauschbar sind. Markdown und `.vault-index/` dürfen nicht fest verdrahtet sein.

## Architekturüberblick und Repo-Layout

Das System hat drei Schichten: **Quelle der Wahrheit** (Markdown-Dateien der Vault), **versionierter Index** (eine Index-Datei pro Notiz im Repo) und **flüchtige Suchdatenbank** (SQLite, pro Sitzung gebaut, nie committet).

```
Vault-Dateien (*.md)  ──Abgleich──▶  .vault-index/**/*.json  ──hydrate──▶  .vault-cache/search.db
   Quelle der Wahrheit             versioniert im Repo             lokal, .gitignore
```

**Kernprinzipien**

- Die Vault ist immer die Quelle der Wahrheit. Index und Datenbank sind abgeleitet und jederzeit neu erzeugbar.
- Ein Kern (CLI) macht die Arbeit. Hooks, Skill, Slash-Befehle und ein optionaler MCP-Server rufen nur den Kern auf.
- Abgleich auf dem Arbeitsstand der Dateien per Hash, nicht über den Git-Verlauf. Uncommittete Änderungen werden mit erfasst.

**Plugin-Repo (das, was veröffentlicht wird)**

```
plug-n-rag/
  .claude-plugin/plugin.json
  skills/vault-search/SKILL.md      # wann und wie suchen/lesen
  commands/                         # Slash-Befehle (Markdown-Prompts)
    vault-setup.md
    vault-status.md
    vault-aufnehmen.md
    vault-reindex.md
  hooks/hooks.json                  # SessionStart, Stop
  mcp/server.py                     # dünner MCP-Wrapper um den Kern (optional)
  core/                             # die eigentliche Logik
    cli.py                          # Einstieg: vault <befehl>
    scan.py  chunk.py  hashing.py
    embed/  (local.py, voyage.py)
    index_store.py                  # Index-Dateien lesen/schreiben
    db.py                           # SQLite bauen + abfragen
    search.py  outline.py  related.py  map.py
    tuning.py                       # adaptive Token-Steuerung
    setup/                          # Inventur, Git/GitHub, Obsidian Git
  tests/
```

**Nutzer-Repo (die Vault nach der Einrichtung)**

```
meine-vault/
  .obsidian/                        # Obsidian-Konfiguration
  ...Notizen und Ordner der Nutzer:in...
  .vault-index/                     # committet
    _meta.json                      # Modell, Schema-Version, Chunking-Version
    Themen/Sensorik.md.json         # spiegelt Themen/Sensorik.md
  .vault-cache/                     # .gitignore
    search.db
    log.jsonl                       # Nutzungsprotokoll für die Token-Steuerung
  vault-plugin.yml                  # Konfiguration, committet
  vault-tuning.json                 # Lern-Datei, nur mit Zustimmung committet
  .claude/settings.json             # Plugin-Eintrag für Cloud-Sitzungen (optional)
  CLAUDE.md                         # kurzer Abschnitt mit Hinweis aufs Plugin
```

**Implementierungssprache:** Noch offen. Empfehlung: Python, ausgeführt über `uv`. uv bringt bei Bedarf eine eigene Python-Version mit, Abhängigkeiten werden pro Skript deklariert, Nutzer:innen müssen nichts selbst installieren. Alternative: Node/TypeScript (better-sqlite3, sqlite-vec, transformers.js), wie qmd. Entscheidung vor Beginn der Umsetzung klären.

## Datenmodell

Vier persistente Dateiarten plus eine flüchtige Datenbank. Alle Dateien im Repo sind menschenlesbares JSON oder YAML.

**1. Index-Datei pro Notiz** — `.vault-index/<pfad der notiz>.json`

Der Pfad spiegelt die Vault exakt: `Themen/Sensorik.md` → `.vault-index/Themen/Sensorik.md.json`. Existiert die Notiz nicht mehr, wird die Index-Datei gelöscht. Die Index-Datei enthält **keinen Notiztext**, nur Positionen, Hashes und Vektoren. Der Text wird beim Bauen der Datenbank aus der Notiz selbst gelesen. Das hält das Repo klein und vermeidet doppelte Kopien privater Inhalte.

```json
{
  "schema": 1,
  "source": "wissen/Raumklima.md",
  "file_hash": "sha256:…",
  "model": "local:intfloat/multilingual-e5-small@<revision>",
  "title": "Gesundes Raumklima",
  "tags": ["wohnen", "raumklima"],
  "links": ["Schimmelvermeidung", "Pettenkofer"],
  "private": false,
  "tokens": 2410,
  "outline": [
    {"heading": "Grundlagen", "level": 2, "lines": [5, 44], "tokens": 820}
  ],
  "chunks": [
    {
      "hash": "sha256:…",
      "heading_path": "Grundlagen > Luftfeuchtigkeit",
      "lines": [45, 80],
      "tokens": 512,
      "vec": "<float16, base64>"
    }
  ]
}
```

- `file_hash`: Hash des gesamten Dateiinhalts. Gleich → Datei unverändert, nichts zu tun.
- `chunk.hash`: sha256 über Titel + `heading_path` + Abschnittstext. Gleich → Vektor wiederverwenden, auch nach Umbenennen oder Verschieben.
- `vec`: float16, little-endian, base64. Bei 384 Dimensionen etwa 1 KB pro Abschnitt.
- `model`: Provider, Modellname und Revision. Weicht er von `_meta.json` ab, ist die Datei veraltet.

**2. `.vault-index/_meta.json`**

```json
{"schema": 1, "model": "local:intfloat/multilingual-e5-small@<revision>",
 "dims": 384, "chunking": "v1", "embed_text": "v1", "created": "2026-11-18"}
```

`chunking` und `embed_text` versionieren die Algorithmen. Ändert sich einer, ist eine Neuindexierung nötig. Das Plugin erkennt das und bietet sie an.

**3. `vault-plugin.yml`** — Konfiguration, committet, von Nutzer:innen über den Chat geändert

```yaml
embedding:
  provider: local          # local | voyage
  model: intfloat/multilingual-e5-small
exclude: [".obsidian/**", "Vorlagen/**", "Archiv/**", ".trash/**"]
private_folders: ["Tagebuch/**"]
folders:                   # Beschreibungen für die Karte
  wissen/: "Fachtexte, konvertierte PDFs"
  besprechungen/: "Hausversammlungen, Projekttreffen"
tuning:
  commit_learning: false   # Lern-Datei nur mit Zustimmung committen
```

Kein API-Key in dieser Datei. Der Key kommt aus der Umgebungsvariable `VOYAGE_API_KEY` oder aus der lokalen Nutzerkonfiguration außerhalb des Repos.

**4. `vault-tuning.json`** — gelernte Werte, siehe Abschnitt Token-Steuerung. Liegt im Repo, wenn `commit_learning: true`, sonst in `.vault-cache/`.

**5. `.vault-cache/search.db`** — flüchtig, `.gitignore`

```sql
notes(id, path, title, tags, private, tokens, file_hash)
chunks(id, note_id, heading_path, line_start, line_end, tokens, body)
chunks_fts      USING fts5(body, heading_path, title, tokenize='unicode61 remove_diacritics 2')
chunks_trigram  USING fts5(body, tokenize='trigram')      -- Teilwörter, Komposita
chunks_vec      USING vec0(embedding float[384])          -- sqlite-vec
links(src_note, dst_title)                                -- Wikilinks und Backlinks
```

Gebaut durch `vault hydrate`: Index-Dateien lesen, Text der Abschnitte aus den Notizen schneiden, alles einfügen. Ziel: unter 5 Sekunden für 1.000 Notizen.

## Indexierung und Abgleich

Der Abgleich (`vault sync`) vergleicht den Ist-Zustand der Vault-Dateien mit den Index-Dateien und behebt jede Abweichung. Er ist idempotent: zweimal hintereinander ausgeführt, tut der zweite Lauf nichts.

**Algorithmus**

1. Alle Markdown-Dateien der Vault auflisten, `exclude` und `private_folders` anwenden. Notizen mit `privat: true` im Frontmatter gelten als ausgeschlossen.
2. Pro Datei `file_hash` berechnen. Stimmt er mit der Index-Datei überein und passt das Modell, Datei überspringen.
3. Geänderte oder neue Datei: parsen, in Abschnitte teilen, `chunk.hash` berechnen.
4. Vektoren aus einem Hash-Pool wiederverwenden. Der Pool enthält alle `chunk.hash → vec` aller bestehenden Index-Dateien. Nur unbekannte Hashes werden embeddet.
5. Index-Datei schreiben, atomar: erst temporäre Datei, dann umbenennen.
6. Index-Dateien ohne zugehörige Notiz löschen, ebenso Index-Dateien ausgeschlossener oder privater Notizen.
7. SQLite inkrementell nachführen oder bei Bedarf neu bauen.

Umbenennen und Verschieben brauchen keine Sonderbehandlung. Die alte Index-Datei verschwindet in Schritt 6, die neue entsteht in Schritt 3, und ihre Vektoren kommen in Schritt 4 aus dem Pool. Es wird nichts neu embeddet.

**Chunking**

- Teilung an Markdown-Überschriften, `heading_path` als Pfad wie `Grundlagen > Luftfeuchtigkeit`.
- Zu lange Abschnitte werden an Absätzen geteilt (Richtwert 512 Tokens, etwa 15 % Überlappung).
- Notizen ohne Text erhalten einen Ersatz-Abschnitt aus Titel und Überschriften, damit sie auffindbar bleiben.
- Frontmatter wird nicht embeddet, sondern als Metadaten gespeichert (Tags, `privat`, Typ).
- Eingabe für das Embedding: `Notizname > Titel > heading_path` + Leerzeile + Abschnittstext. So kennt das Modell den Kontext auch bei Abschnitten wie „siehe oben“. Übernommen aus git-rag.

**Auslöser**

| Auslöser | Wann | Was |
| --- | --- | --- |
| SessionStart-Hook | Jede Sitzung | `git pull`, dann `vault sync`, dann `vault hydrate`, dann Kurz-Karte ausgeben |
| Stop-Hook | Ende jeder Claude-Antwort | `vault sync`, schnell, weil meist nichts zu tun ist |
| Git-pre-commit-Hook (optional, im Setup installiert) | Vor jedem Commit | `vault sync` und geänderte Index-Dateien zum Commit hinzufügen |
| `/vault-reindex` | Manuell | Vollständige Neuindexierung, z. B. nach Modellwechsel |

GitHub Actions sind in Version 1 nicht vorgesehen. Später möglich als Sicherheitsnetz für Änderungen, die nur über Obsidian Git oder die GitHub-Weboberfläche kommen.

**Robustheit**

- Sperrdatei verhindert parallele Läufe (Hook und Befehl gleichzeitig).
- Jede Index-Datei ist ein eigener Checkpoint. Ein abgebrochener Lauf setzt beim nächsten Mal einfach fort.
- Merge-Konflikte in Index-Dateien werden nicht aufgelöst. Die betroffene Datei wird verworfen und neu berechnet.
- Fehler bei einer einzelnen Notiz brechen den Lauf nicht ab. Sie werden protokolliert und in `/vault-status` angezeigt.
- Embedding-Provider nicht erreichbar: Index-Dateien für diese Notizen bleiben veraltet, die Stichwortsuche funktioniert weiter, `/vault-status` meldet es.

## Embedding-Provider

Zwei Provider hinter einer gemeinsamen Schnittstelle `embed(texts, kind) -> vectors`, wobei `kind` zwischen `document` und `query` unterscheidet (manche Modelle brauchen unterschiedliche Präfixe).

|  | Lokal (Standard) | Voyage (Option) |
| --- | --- | --- |
| Weiterer Dienst außer Anthropic | Nein | Ja, Voyage AI (gehört zu MongoDB) |
| Kosten | Keine | Pro Token, Preis zur Laufzeit aus der aktuellen Preisliste ermitteln |
| Voraussetzung | Modell-Download (Hugging Face) | API-Key, Netzfreigabe für `api.voyageai.com` |
| Kandidaten | multilingual-e5-small, EmbeddingGemma 300M, Model2Vec-Modelle | Kleines Voyage-Modell, im Setup gewählt |

**Regeln**

- Pro Vault genau ein Modell. Festgelegt beim Setup in `vault-plugin.yml` und `_meta.json`.
- Der Modellbezeichner enthält die Revision (bei Hugging Face der Commit-Hash). Updates der Gewichte dürfen nie unbemerkt passieren.
- Abweichung zwischen konfiguriertem Modell und Index: Suche läuft im Modus „nur Stichwort“ weiter, `/vault-status` und der SessionStart-Hook melden „Index passt nicht zum Modell“ und bieten `/vault-reindex` an.
- Modellwechsel ist ein bewusster Vorgang über den Chat: Kosten und Dauer ansagen, bestätigen lassen, vollständig neu indexieren, in einem Commit ablegen.
- Abfrage-Embeddings werden nicht gespeichert, nur in der Sitzung zwischengespeichert.

**Zur Auswahl des lokalen Standardmodells:** Noch offen. Es muss mehrsprachig sein, insbesondere auf Deutsch, und auf einer CPU in einer Cloud-Sitzung in vertretbarer Zeit laufen. Entscheidung per Vergleichstest an einer echten Vault (siehe Umsetzungsreihenfolge).

**Modell-Download in Cloud-Sitzungen:** Die Cloud-Umgebung muss Hugging Face erreichen dürfen, sonst schlägt der Download fehl. Fallback in dieser Reihenfolge: Modell aus einem Cache-Ordner, dann Hinweis auf die Netzwerkfreigabe, dann Betrieb nur mit Stichwortsuche. Ein kleines Modell (unter 100 MB) im Repo abzulegen ist möglich, aber nicht der Standard.

## Aufnahme und Transkription

PDFs und andere Dateien werden über eine Kaskade in Text umgewandelt, Seite für Seite. Jede Stufe kommt nur zum Zug, wenn die vorige nicht reicht. Auslöser ist `/vault-aufnehmen` oder im Sammlungs-Modus die Indexierung selbst.

**Kaskade pro Seite**

1. **Textebene auslesen** (z. B. PyMuPDF). Kostenlos, exakt. Deckt die meisten PDFs ab.
2. **Lokale Texterkennung** (z. B. Tesseract mit deutschem Sprachpaket, etwa über OCRmyPDF) für Seiten ohne Textebene. Kostenlos, offline.
3. **Qualitätsprüfung:** Erkennungs-Konfidenz und Anteil echter Wörter (Wörterbuchabgleich). Unter der Schwelle gilt die Seite als nicht erkannt.
4. **Subagent `transkription` mit Haiku** für Seiten, die Stufe 3 nicht bestehen, nur mit Zustimmung (siehe unten).
5. **Eskalation auf Sonnet** bei Handschrift, komplexen Tabellen oder wenn Haiku Unsicherheit meldet.

Optional für Layout und Tabellen: Docling als Alternative zu Stufe 2. Marker nur nach Prüfung der Lizenz. Externe Texterkennung (z. B. Mistral, Google, Azure) nur, wenn weitere Dienste erlaubt sind. Nicht Teil von Version 1.

**Subagent `transkription`**

- Liegt als Agent-Definition im Plugin (`agents/transkription.md`), Modell fest auf Haiku, Eskalation auf Sonnet nur durch den Hauptagenten.
- Erhält Seitenbilder in Bündeln von etwa 20 Seiten. Ein Aufruf muss unter 100.000 Tokens bleiben, weil Haiku 5.5 darüber das Fünffache kostet.
- Regeln: wortgetreu transkribieren, nichts korrigieren, nicht zusammenfassen. Seitenmarker `<!-- Seite 12 -->`. Tabellen als Markdown-Tabellen. Unleserliches als `[unleserlich]`, nie raten. Sprache der Vorlage beibehalten.
- Schreibt das Ergebnis selbst in die Zieldatei und meldet dem Hauptagenten nur eine Zusammenfassung (Seiten, unleserliche Stellen, Unsicherheiten). Die Seitenbilder gelangen nie in den Kontext der Hauptsitzung.

**Kosten (grobe Schätzung, Stand November 2026)**

Annahme: etwa 1.700 Input-Tokens pro Seitenbild, etwa 800 Output-Tokens Text. Haiku 5.5 (0,10 $ / 0,50 $ pro Million Tokens bis 100.000 Tokens Prompt): etwa 0,06 Cent pro Seite. Sonnet 5.5 (2 $ / 10 $): etwa 1 Cent pro Seite. Mit Claude-Code-Abo wird das Nutzungskontingent belastet. Das Plugin ermittelt Preise zur Laufzeit und nennt sie im Kostenvoranschlag.

**Zustimmung**

Im normalen Betrieb liest Claude nur gezielt einzelne Abschnitte. Eine Transkription schickt dagegen ganze Dokumente an Anthropic. Deshalb fragt das Plugin vor Stufe 4 ausdrücklich, mit Anzahl der Seiten und Alternative:

> 23 Seiten sind eingescannt. Soll Claude sie vollständig lesen und abschreiben? Alternativ erkenne ich den Text nur lokal, das ist aber ungenauer.

Die Antwort gilt für den aktuellen Auftrag. Eine dauerhafte Einstellung (`transcription: ask | allow | local_only` in `vault-plugin.yml`) setzt das Plugin nur, wenn Nutzer:innen das ausdrücklich wollen.

**Ablage**

- Vault-Modus: Ergebnis als Markdown-Notiz neben oder unter dem Original, mit Frontmatter `quelle:` und `transkription: lokal | haiku | sonnet`. Die Notiz wird normal indexiert.
- Sammlungs-Modus: Ergebnis nur in `.vault-cache/extract/` bzw. im externen Cache, nie im Ordner selbst.

## Suche und Retrieval-Werkzeuge

Claude soll sich stufenweise herantasten: **Karte → Suche → Gliederung → Abschnitt lesen.** Ganze Notizen nur, wenn der Zusammenhang gebraucht wird. Alle Ausgaben sind kompakter Text, kein JSON (außer mit `--json` für den MCP-Wrapper).

**Befehle des Kerns**

| Befehl | Zweck |
| --- | --- |
| `vault karte [--kurz]` | Überblick: Ordner, Anzahl, Beschreibung, Schwerpunkte, häufige Tags |
| `vault suche "<frage>" [--zweck frage\|recherche\|erstellen] [--in <ordner>] [--tag <t>] [--seit <datum>] [--weiter] [--warten [<sek>]] [--chronologisch]` | Relevante Notizen finden; `--chronologisch` listet nach Datum der Notiz statt nach Relevanz |
| `vault gliederung <notiz>` | Überschriften mit Zeilen und Token-Größe |
| `vault lesen <notiz>#<überschrift>` | Einen Abschnitt lesen (alternativ das Read-Werkzeug mit Zeilenangaben) |
| `vault verwandt <notiz>` | Links und Backlinks zuerst, bei datierten Notizen Tag davor/danach und Wochennotiz, dann semantisch ähnliche Notizen |
| `vault status` | Aktualität, Modell, seit wann die semantische Suche vollständig ist, Fehler, gelernte Werte, geschätzte Ersparnis |

**Ranking in `suche`**

1. Drei Kandidatenlisten: FTS5 `unicode61` (ganze Wörter), FTS5 `trigram` (Teilwörter, deutsche Komposita), Vektorsuche (sqlite-vec, Kosinus).
2. Zusammenführen mit Reciprocal Rank Fusion (k = 60).
3. Gruppieren nach Notiz: maximal drei Abschnitte pro Notiz, Notiz-Score = bester Abschnitt plus kleiner Bonus für weitere Treffer.
4. Adaptiver Schnitt statt festem k: an der deutlichsten Score-Stufe (Knick) abschneiden, innerhalb der Grenzen aus `vault-tuning.json`.
5. Liegen alle Treffer unter der Mindestschwelle: „Nichts Passendes gefunden“, keine Liste schwacher Treffer.
6. Ein Filter liefert nichts: automatisch ohne Filter wiederholen und das kennzeichnen („Außerhalb von besprechungen/ gefunden“).
7. `--weiter` liefert die nächste Seite derselben Suche, ohne neu zu rechnen (Sitzungscache).
8. Die Suche lädt nie selbst das Suchmodell. Fehlt es, sucht sie nur mit Stichworten und stößt den
   Download im Hintergrund an. `--warten` blockiert stattdessen, bis Modell und Index bereit sind
   (Standard höchstens 300 s), und bricht früh ab, wenn Warten nicht hilft (Modellkonflikt).

**Ausgabeformat `suche`**

```
Suchmodus: semantisch + Stichwort · Index vollständig (32 Dateien)
3 Notizen zu „Was hilft gegen feuchte Wände?“

1. wissen/Raumklima.md (2.400 Tokens)
   › Luftfeuchtigkeit, Z. 45–80 (sehr passend)
   „…zu feuchte Luft zeigt sich im Alltag oft…“
   › Alltagsstrategien, Z. 112–140 (passend)

2. besprechungen/2026-10-hausversammlung.md (900 Tokens)
   › Dachgeschoss, Z. 12–30 (passend)

[--weiter: 4 weitere Notizen]
```

Die erste Zeile nennt immer den Suchmodus. Ist er unvollständig („nur Stichwort · Suchmodell lädt
(60 %)“, „semantisch + Stichwort, aber erst 20 von 32 Dateien semantisch indexiert“, „Index passt
nicht zum Modell“), folgt direkt unter der Kopfzeile „⚠ Vorläufiges Ergebnis“ mit dem Auftrag an
Claude, die Antwort als vorläufig zu kennzeichnen oder mit `--warten` zu wiederholen. „Nichts
Passendes gefunden“ heißt dann ausdrücklich nicht „steht nicht in den Notizen“.

Pflichtangaben: Suchmodus, Pfad, Token-Größe der Notiz, Überschrift und Zeilen jedes Abschnitts, Relevanz in Worten (nicht als Zahl), kurzer Ausschnitt nur beim besten Abschnitt.

**Karte**

- `--kurz` (SessionStart): zwei bis drei Zeilen, z. B. „Vault: 312 Notizen in 4 Bereichen (wissen, besprechungen, themen, quellen). `vault karte` für Details.“
- Voll: pro Ordner Anzahl, Beschreibung aus `vault-plugin.yml`, Schwerpunkte, Zeitraum; dazu die häufigsten Tags.
- Schwerpunkte werden durch Clustern der Notiz-Vektoren pro Ordner ermittelt und mit häufigen Überschriften- oder Tag-Begriffen benannt. Sie werden beim Abgleich gecacht, nicht bei jedem Aufruf berechnet.

**MCP-Wrapper:** `mcp/server.py` stellt dieselben Befehle als Werkzeuge bereit und ruft intern den Kern auf. Keine eigene Logik im Wrapper. Er ist die Grundlage für den späteren Konnektor in der Claude-App.

## Adaptive Token-Steuerung

Grenzen sind Startwerte, keine Deckel. Das Plugin regelt auf drei Ebenen nach. Die Zahlen in diesem Dokument sind Anfangsannahmen und ausdrücklich zum Überschreiben durch Beobachtung gedacht.

**Ebene 1, pro Anfrage:** Adaptiver Schnitt an der Score-Stufe (siehe Suche), dazu Weiterblättern mit `--weiter` statt hartem Abschneiden. Nichts ist gesperrt, nur gestaffelt.

**Ebene 2, pro Aufgabe:** Claude übergibt `--zweck`.

| Zweck | Startverhalten |
| --- | --- |
| `frage` | Wenige präzise Treffer, Abschnitte statt ganzer Notizen |
| `recherche` | Mehr Notizen, Fokus auf Gliederungen |
| `erstellen` | Weniger Notizen, dafür vollständig lesen, weil Zusammenhang zählt |

**Ebene 3, über die Zeit:** Jeder Werkzeugaufruf schreibt eine Zeile in `.vault-cache/log.jsonl` (Zeit, Zweck, gelieferte Treffer, gelieferte Tokens, danach gelesene Notizen und Ränge, Folgesuchen). `tuning.py` wertet das aus:

| Beobachtung | Anpassung |
| --- | --- |
| Claude liest regelmäßig Treffer jenseits des Schnitts (`--weiter` oder hohe Ränge) | Schnitt großzügiger |
| Claude liest nie über die ersten Treffer hinaus | Schnitt knapper |
| Nach einem Abschnitt folgt fast immer die ganze Notiz | Nachbarabschnitte mitliefern |
| Direkt umformulierte Folgesuche | Mehr Vielfalt (weniger Abschnitte pro Notiz) |

Gelernt wird pro Vault und pro Zweck. Ergebnis in `vault-tuning.json`:

```json
{"schema": 1, "updated": "2026-11-18", "observations": 140,
 "purpose": {"frage": {"max_notes": 3, "neighbors": 0},
             "recherche": {"max_notes": 8, "neighbors": 0},
             "erstellen": {"max_notes": 4, "neighbors": 1}},
 "bounds": {"max_notes": [1, 20], "neighbors": [0, 2]},
 "user_overrides": {}}
```

**Leitplanken**

- Harte Unter- und Obergrenzen (`bounds`), die nur Nutzer:innen ändern können.
- Langsame Anpassung: gleitender Mittelwert, eine Sitzung verschiebt wenig.
- Agenten neigen zu Mehrlesen. Ohne Gegengewicht würden die Werte steigen. Deshalb zählt „weitergelesen“ nur, wenn danach tatsächlich aus der Notiz zitiert oder gelesen wurde.
- Transparent in `/vault-status`, z. B. „Recherche: bis zu 8 Notizen, gelernt aus 140 Suchen“. Zurücksetzen mit einem Befehl.

**Nutzerfeedback:** Äußerungen wie „Das war mir zu oberflächlich“ setzt Claude als `user_overrides` für den betroffenen Zweck. Overrides haben Vorrang vor gelernten Werten.

**Speicherort:** Die Lern-Datei wird nur committet, wenn Nutzer:innen zugestimmt haben (`tuning.commit_learning: true`). Sonst bleibt sie lokal, und Claude bietet von sich aus an nachzujustieren, wenn die Auswertung Verbesserungspotenzial zeigt.

**Ersparnis messen:** Pro Suche wird geschätzt: Tokens, die geliefert wurden, gegenüber Tokens, die das vollständige Lesen aller Trefferdateien gekostet hätte. `/vault-status` weist das als Schätzung aus.

## Plugin-Komponenten

**Skill `vault-search`**

Der Skill legt fest, wann und wie Claude die Vault nutzt. Die SKILL.md bleibt kurz, die Logik steckt im Kern. Inhaltliche Regeln:

1. Bei Fragen zu Inhalten der Vault zuerst `vault suche` verwenden, nicht grep. Grep nur für exakte Zeichenketten (Dateinamen, Datumsangaben, Zitate).
2. Immer `--zweck` angeben.
3. Ablauf: Suche → Gliederung bei Notizen über etwa 1.000 Tokens → passende Abschnitte lesen. Ganze Notizen nur bei `--zweck erstellen` oder wenn der Zusammenhang nötig ist.
4. Filter nur, wenn die Frage einen Bereich nahelegt.
5. Jede Aussage aus der Vault mit Pfad und Zeilen belegen.
6. „Nichts gefunden“ offen sagen und nicht aus Allgemeinwissen antworten, als käme es aus den Notizen.
7. Neue PDFs nicht direkt lesen, sondern `/vault-aufnehmen` anbieten.
8. Nutzerfeedback zur Gründlichkeit als Override speichern.
9. Meldet die Suche einen veralteten Index oder einen Modellkonflikt: Nutzer:innen informieren und `/vault-reindex` anbieten.

**Hooks (`hooks/hooks.json`)**

| Hook | Befehl | Dauer-Ziel |
| --- | --- | --- |
| `SessionStart` | `vault session-start`: Setup-Status prüfen, `git pull --rebase` falls Remote vorhanden, `sync`, `hydrate`, `karte --kurz` ausgeben | Unter 10 s im Normalfall |
| `Stop` | `vault sync --quiet` | Unter 2 s, wenn nichts zu tun ist |

Ist die Vault noch nicht eingerichtet, gibt `session-start` nur einen einzeiligen Hinweis aus („Vault erkannt, noch nicht eingerichtet, `/vault-setup` startet die Einrichtung“) und beendet sich. Kein automatisches Indexieren ohne Setup.

Der Git-pre-commit-Hook gehört nicht zum Plugin-Hook-System. Er wird beim Setup in `.git/hooks/` installiert, verkettet mit bestehenden Hooks (Muster aus git-rag).

**Slash-Befehle (`commands/`)**

| Befehl | Zweck |
| --- | --- |
| `/vault-setup` | Geführte Einrichtung, wiederaufnehmbar, idempotent |
| `/vault-status` | Zustand, Modell, Fehler, gelernte Werte, Ersparnis |
| `/vault-aufnehmen` | PDFs und andere Dateien in Markdown umwandeln und indexieren |
| `/vault-reindex` | Vollständige Neuindexierung, z. B. nach Modellwechsel |
| `/vault-modell-wechseln` | Provider oder Modell ändern, mit Kostenvoranschlag |
| `/vault-lernen-zuruecksetzen` | Lern-Datei auf Startwerte setzen |

**MCP-Server (optional in Version 1)**

Stellt `karte`, `suche`, `gliederung`, `lesen`, `verwandt`, `status` als Werkzeuge bereit. Vorteil gegenüber Bash-Aufrufen: Claude findet die Werkzeuge zuverlässiger und braucht keine Bash-Freigabe. Gleiche Ausgaben wie die CLI.

## Setup und Erstkontakt mit bestehender Vault

`/vault-setup` ist ein geführtes Gespräch. Grundsatz: Claude erledigt alles, was die Umgebung erlaubt. Nutzer:innen entscheiden und melden sich einmal im Browser bei GitHub an. Keine Git-Begriffe, außer auf Nachfrage.

**Drei Stufen für jeden Schritt**

| Stufe | Beispiele |
| --- | --- |
| Selbst erledigen | Dateien anlegen, `git init`, `.gitignore`, Commits, Konfiguration, Indexierung, Obsidian-Git-Dateien ablegen |
| Anbieten, nach Zustimmung erledigen | GitHub-CLI installieren (Homebrew, winget), Vault aus einem Cloud-Sync-Ordner verschieben, PDFs umwandeln |
| Anleiten und danach prüfen | Browser-Anmeldung bei GitHub, Community-Plugins in Obsidian erlauben, Netzfreigabe und Secrets für Cloud-Sitzungen |

**Ablauf**

1. **Bestandsaufnahme (still, ohne KI):** Vault vorhanden? Git? Remote? Remote privat? GitHub-CLI vorhanden und angemeldet? Vault in iCloud, OneDrive oder Dropbox? Dateien über 100 MB?
2. **Weg wählen:** keine Vault → Startstruktur anlegen; Vault ohne Git → Schritte 3 und 4; Vault auf GitHub → direkt zu Schritt 5. Öffentliches Repo → deutliche Warnung, Angebot, es privat zu stellen.
3. **Git lokal:** `git init`, `.gitignore` (u. a. `.obsidian/workspace*.json`, `.trash/`, `.vault-cache/`), erster Commit.
4. **GitHub:** privates Repo per `gh repo create --private` oder Schritt-für-Schritt-Anleitung über die Webseite. Danach Push.
5. **Inventur:** Anzahl und Größe der Notizen, geschätzte Tokens, Ordnerstruktur, Frontmatter-Anteil, Link-Dichte, Nicht-Markdown-Dateien, davon PDFs ohne Textebene (Scans) mit Seitenzahl. Vorlagen-Ordner aus `.obsidian/templates.json` bzw. der Templater-Konfiguration auslesen. Ordner mit Namen wie Tagebuch, Journal, Privat oder Personal gezielt nachfragen.
6. **Datenschutz und Modell:** Zuerst ein kurzer, verständlicher Hinweis, was wohin geht: Was Claude liest, geht wie bei jeder Nutzung von Claude Code an Anthropic. Index und Suche bleiben lokal bzw. im eigenen Repo. Eine vollständige Transkription schickt ganze Dokumente an Anthropic und wird deshalb gesondert erfragt. Danach die Frage: „Dürfen deine Inhalte zusätzlich an einen weiteren Dienst außer Anthropic gehen?“ Nein → lokales Embedding, keine externe Texterkennung. Ja → Voyage und externe Dienste wählbar. Hinweis und Frage gelten im Vault- und im Sammlungs-Modus gleichermaßen. API-Key nur in Umgebungsvariable oder lokale Nutzerkonfiguration lenken, nie ins Repo.
7. **Kostenvoranschlag:** Notizen, Tokens, Dauer lokal und mit Voyage, Kosten mit Voyage (Preis zur Laufzeit ermitteln), vorgeschlagene Ausschlüsse. Gibt es Scans, kommt hier die Transkriptionsfrage mit Seitenzahl und Kosten, oder sie wird auf später verschoben. Erst nach Bestätigung rechnen.
8. **Erste Indexierung:** Neueste Notizen zuerst (nach Änderungsdatum), Fortschrittsanzeige, Suche schon während der Indexierung nutzbar mit Hinweis auf den Fortschritt. Sehr große Vaults (mehrere tausend Notizen): Angebot, ausgewählte Ordner zuerst zu indexieren.
9. **Karte:** Claude liest Stichproben pro Ordner und schlägt Ordnerbeschreibungen vor. Nutzer:innen bestätigen oder korrigieren, Ergebnis in `vault-plugin.yml`.
10. **Testsuche:** Claude wählt ein Thema, das in der Vault vorkommt, sucht und zeigt Treffer mit Quellen.
11. **Optional:** Obsidian Git einrichten (siehe GitHub-Abschnitt), Cloud-Sitzungen freischalten (Plugin in `.claude/settings.json` eintragen, Netzfreigabe und Secret erklären), Lern-Datei committen ja oder nein.
12. **Abschluss:** ein Commit „Vault-Index angelegt (N Notizen)“, Zusammenfassung, was ab jetzt automatisch passiert, die wichtigsten Befehle.

**Invarianten**

- Keine Notiz wird verändert: kein Frontmatter ergänzt, nichts verschoben, außer auf ausdrückliche Zustimmung.
- PDFs werden nur aufgelistet, nicht umgewandelt. Umwandlung später über `/vault-aufnehmen`.
- Jeder Schritt prüft, ob er schon erledigt ist. Ein erneuter Aufruf von `/vault-setup` setzt fort oder bestätigt nur.
- Hooks können beim ersten Ausführen eine Freigabe in Claude Code verlangen. Das Setup kündigt das vorher an.

## Rolle von GitHub und Obsidian Git

GitHub ist Speicher, Synchronisation und Verlauf, aber kein Rechenort. Gerechnet wird immer in der jeweiligen Sitzung.

**Was GitHub leistet**

- **Gemeinsamer Stand:** Notizen und Index-Dateien sind auf allen Geräten und in allen Cloud-Sitzungen identisch. Eine Cloud-Sitzung klont das Repo und hat damit sofort alle Embeddings.
- **Verlauf:** Notiz und zugehörige Index-Datei landen im selben Commit. Ein Revert stellt beide gemeinsam wieder her.
- **Kostenbremse:** Embeddings werden einmal berechnet und dann geteilt, nicht pro Sitzung neu bezahlt oder neu gerechnet.
- **Kein Orphan-Branch:** Alles liegt im Haupt-Branch. Bewusste Entscheidung gegen das eleganter wirkende Muster von git-semantic, weil die Zielgruppe es nicht durchschauen würde.

**Datei-Hygiene**

- Repo ist immer privat. Das Setup prüft das, `/vault-status` ebenfalls.
- `.vault-cache/` steht in `.gitignore`. Die SQLite-Datenbank wird nie committet.
- GitHub lehnt Dateien über 100 MB ab. Das Setup erkennt solche Dateien und schlägt Ausschluss vor.
- Größenrichtwert des Index: etwa 1 KB pro Abschnitt bei 384 Dimensionen in float16. Einige hundert Notizen ergeben wenige Megabyte.

**Reihenfolge bei mehreren Schreibern**

Obsidian und Claude Code können abwechselnd committen. Konflikte werden vermieden, indem jede Seite vor dem Arbeiten den neuesten Stand holt:

- Claude Code: SessionStart-Hook macht `git pull --rebase` vor dem Abgleich.
- Obsidian Git: „Pull on startup“ aktiviert.
- Konflikt in einer Index-Datei: Datei verwerfen und neu berechnen. Konflikt in einer Notiz: Nutzer:innen fragen, nie automatisch auflösen.

**Obsidian Git im Setup**

- Selbst erledigen: aktuelles Release von Obsidian Git von GitHub in `.obsidian/plugins/obsidian-git/` ablegen, in `.obsidian/community-plugins.json` aktivieren, Konfiguration schreiben (Pull beim Start, automatisch sichern und hochladen in festem Intervall, z. B. alle 10 Minuten).
- Anleiten: Nutzer:innen müssen in Obsidian einmal den eingeschränkten Modus ausschalten (Community-Plugins erlauben). Das ist eine Sicherheitsentscheidung und wird nicht umgangen.
- Hinweis für mobile Nutzung: Obsidian Git ist auf dem Handy eingeschränkt und bei großen Vaults unzuverlässig. Empfehlung: Obsidian Sync für die Geräte, Git nur auf dem Rechner.
- Alternative ohne Obsidian Git: Änderungen werden beim nächsten Start von Claude Code erfasst und committet. Das Setup erklärt beide Wege.

**Cloud-Sitzungen**

- Plugin in `.claude/settings.json` des Repos eintragen, damit es in Cloud-Sitzungen geladen wird. Muss in der Umsetzung verifiziert werden.
- Netzfreigaben je nach Provider: Hugging Face (lokales Modell) oder `api.voyageai.com` (Voyage).
- API-Key als Secret der Cloud-Umgebung, nie im Repo.

## Sicherheit und Datenschutz

- **Kein weiterer Dienst als Standard:** Ohne ausdrückliche Zustimmung gehen Inhalte an keinen Dienst außer Anthropic. Was Claude liest, geht wie bei jeder Nutzung von Claude Code an Anthropic. Vollständige Transkriptionen ganzer Dokumente nur nach Rückfrage. Nutzer:innen werden darauf beim Einrichten hingewiesen, in jedem Modus.
- **Private Bereiche:** `private_folders` und `privat: true` im Frontmatter schließen Notizen vollständig aus: kein Embedding, kein Volltextindex, keine Index-Datei. Wird eine Notiz nachträglich privat, löscht der nächste Abgleich ihre Index-Datei.
- **Embeddings sind nicht harmlos:** Sie kodieren Inhalt und können teilweise Rückschlüsse erlauben. Index-Dateien sind deshalb so schützenswert wie die Notizen selbst. Repo immer privat.
- **Kein Notiztext in Index-Dateien:** reduziert Duplikate privater Inhalte im Repo.
- **Geheimnisse:** API-Keys nie in `vault-plugin.yml`, nie im Repo, nie in Logs. Das Setup prüft vor dem ersten Commit, ob ein Key versehentlich in einer Datei steht.
- **Logs:** `log.jsonl` speichert Pfade, Zählwerte und Ränge, aber keine Suchanfragen im Klartext und keine Notizinhalte.
- **Grenzen respektieren:** Sicherheitsentscheidungen von Nutzer:innen (eingeschränkter Modus in Obsidian, Hook-Freigaben in Claude Code, Admin-Passwort bei Installationen) werden erklärt, nie umgangen.
- **Keine destruktiven Git-Operationen:** kein `push --force`, kein `reset --hard`, keine automatische Konfliktlösung in Notizen.

## Referenzen, offene Punkte, Umsetzungsreihenfolge

**Referenzprojekte (vor der Umsetzung ansehen, beide MIT-lizenziert)**

| Projekt | Übernehmen | Nicht übernehmen |
| --- | --- | --- |
| [git-rag](https://github.com/dogfoodlab-io/git-rag) (v0.1.0, Alpha) | Breadcrumb vor dem Embed-Text, Chunk-Hash über Titel + Überschrift + Text, Ersatz-Abschnitt für leere Notizen, Hook-Verkettung, Zitierregeln im Skill | Postgres/Docker, englische FTS-Konfiguration, englisches Standardmodell, Indexierung nur committeter Stände |
| [git-semantic](https://github.com/ccherrad/git-semantic) | Index-Datei pro Quelldatei mit gespiegeltem Pfad, `hydrate` in lokale SQLite, Gliederungs-Modus zum Token-Sparen, Karte | Orphan-Branch, tree-sitter (codespezifisch), Abgleich über Git-Diff |
| [qmd](https://github.com/tobi/qmd) | Kontextbeschreibungen pro Ordner, Hybrid aus BM25 und Vektor mit RRF | Lokale LLM-Modelle von insgesamt etwa 2 GB, globaler Cache außerhalb des Repos |

Beim Übernehmen von Code den MIT-Lizenzhinweis erhalten.

**Offene Punkte**

- [ ] Implementierungssprache: Python über uv oder Node/TypeScript
- [ ] Lokales Standardmodell per Vergleichstest an einer deutschen Vault
- [ ] Bibliotheken für die Transkriptions-Kaskade festlegen, Schwellenwerte der Qualitätsprüfung an echten Scans bestimmen, Lizenz von Marker prüfen
- [ ] Verifizieren: Plugin-Laden in Cloud-Sitzungen über `.claude/settings.json`, Modell-Download hinter der Netzfreigabe
- [ ] Konkrete Schwellenwerte für Knick-Erkennung und Mindest-Relevanz, empirisch bestimmen
- [ ] Lizenz und Pflege festlegen (Name und Repo stehen: plug-n-rag)

**Umsetzungsreihenfolge**

1. **Kern ohne Plugin:** `scan`, `chunk`, Index-Dateien, `sync`, `hydrate`, `suche`, `gliederung`. Getestet an einer Beispiel-Vault mit deutschen Notizen, Komposita und Umbenennungen.
2. **Modellvergleich:** drei lokale Kandidaten und Voyage, zehn typische Fragen, Trefferqualität und Laufzeit auf CPU dokumentieren.
3. **Plugin-Hülle:** Skill, SessionStart- und Stop-Hook, `/vault-status`, `/vault-reindex`. Erster Einsatz in einer echten Vault.
4. **Beobachten:** einige Wochen Alltagsnutzung, `log.jsonl` auswerten, Startwerte anpassen.
5. **Setup-Assistent:** `/vault-setup` mit Inventur, Git/GitHub, Kostenvoranschlag, Karte, Obsidian Git.
6. **Adaptive Steuerung:** `tuning.py`, Overrides, Leitplanken.
7. **Aufnahme:** `/vault-aufnehmen` für PDFs.
8. **Veröffentlichung:** eigenes Plugin-Repo, README auf Deutsch und Englisch, optional MCP-Wrapper.

**Akzeptanzkriterien Version 1**

- Umbenennen einer Notiz löst kein neues Embedding aus.
- Löschen einer Notiz entfernt ihre Index-Datei beim nächsten Abgleich.
- Eine frische Cloud-Sitzung ist nach dem Start ohne erneutes Embedding suchbereit.
- „Dachsanierung“ findet eine Notiz, die nur „Dachsanierungsbedarf“ enthält.
- Bei einer Frage ohne passenden Inhalt meldet die Suche „Nichts Passendes gefunden“.
- Kein Schritt des Setups verändert bestehende Notizen.
