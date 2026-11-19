# plug-n-rag

**Deine Obsidian-Vault für Claude Code durchsuchbar machen – gezielt statt alles zu lesen.**

plug-n-rag ist ein Plugin für [Claude Code](https://code.claude.com). Es macht deine Notizen
semantisch durchsuchbar: Claude findet passende Stellen auch dann, wenn du andere Worte benutzt
als in der Notiz stehen, und liest dann nur die Abschnitte, die wirklich gebraucht werden. Das
spart Tokens (also Nutzungskontingent oder Geld) und liefert Antworten mit genauen Quellen.

> Beispiel: Du fragst „Wie helfe ich einem Kind, das morgens beim Anziehen eskaliert?“.
> Claude sucht in deiner Vault, findet die Supervisionsnotiz und den Abschnitt „Intervention“
> in deiner Notiz zur Handlungsplanung, liest nur diese Abschnitte und antwortet mit
> Quellenangaben wie „(themen/Handlungsplanung.md, Z. 24–38)“.

## Was plug-n-rag kann

- **Suchen nach Bedeutung und nach Stichwort**, auch in deutschen Wortzusammensetzungen:
  „Reizverarbeitung“ findet „Reizverarbeitungsstörung“.
- **Stufenweise lesen**: erst Überblick, dann Treffer, dann Gliederung, dann nur der passende
  Abschnitt. Ganze Notizen nur, wenn der Zusammenhang gebraucht wird.
- **Ehrlich bleiben**: Findet sich nichts Passendes, sagt die Suche das, statt schwache Treffer
  aufzulisten.
- **Automatisch aktuell**: Beim Start jeder Sitzung und nach jeder Antwort gleicht plug-n-rag
  Notizen und Suchindex ab. Umbenennen oder Verschieben kostet nichts, weil bekannte Abschnitte
  wiedererkannt werden.
- **Lernt mit**: Merkt sich, wie tief Claude üblicherweise liest, und passt an, wie viel eine Suche
  liefert. Rückmeldungen wie „das war mir zu oberflächlich“ werden gespeichert.
- **Private Bereiche** bleiben vollständig außen vor: Ordner wie `Tagebuch/` oder Notizen mit
  `privat: true` im Frontmatter werden nie indexiert.
- **Geführte Einrichtung**, auch ohne Git-Kenntnisse: Claude erledigt alles, was möglich ist, und
  erklärt den Rest Schritt für Schritt.
- **PDFs aufnehmen**: Text aus PDFs übernehmen; eingescannte Seiten auf Wunsch von Claude
  abschreiben lassen (nur nach Rückfrage).
- **Auch für andere Ordner**: Auf ausdrücklichen Wunsch auch für Dokumentensammlungen oder
  Bibliotheken (Markdown, Text, PDF), streng nur lesend.

## So funktioniert es (kurz)

```
Deine Notizen (*.md)  ──Abgleich──▶  .plug-n-rag/index/  ──beim Start──▶  lokale Suchdatenbank
   bleiben unverändert               im eigenen Repo                    nur auf deinem Gerät
```

Für jede Notiz entsteht eine kleine Index-Datei mit „Fingerabdrücken“ der Abschnitte (ohne
Notiztext). Sie liegt in deinem eigenen, privaten Repo. Dadurch ist jede neue Sitzung, auch in
der Cloud, sofort suchbereit, ohne alles neu zu berechnen. Die eigentliche Suchdatenbank wird bei
jedem Start lokal gebaut und nie hochgeladen. Es gibt keinen Server und kein Datenbank-Hosting.

## Installation Schritt für Schritt

### 1. Voraussetzungen

- **Claude Code** ist installiert und du bist angemeldet.
  ([Anleitung](https://code.claude.com/docs/de/quickstart))
- **uv** ist installiert. uv ist ein kleines Hilfsprogramm, das plug-n-rag ausführt und alles
  Nötige selbst mitbringt. Du musst Python nicht selbst installieren.
  - macOS oder Linux: Terminal öffnen und eingeben

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

  - Windows: PowerShell öffnen und eingeben

    ```bash
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

  Du kannst diesen Schritt auch überspringen: Fehlt uv, bietet Claude an, es zu installieren.

### 2. Plugin installieren

Öffne Claude Code (im Terminal `claude`, oder die Desktop-App) und gib nacheinander ein:

```
/plugin marketplace add sign-u-p/plug-n-rag
```

```
/plugin install plug-n-rag@plug-n-rag
```

Ab Claude Code 2.1.275 geht es auch in einem Schritt:

```
/plugin install plug-n-rag --marketplace sign-u-p/plug-n-rag
```

Alternativ im Terminal, außerhalb von Claude Code:

```bash
claude plugin marketplace add sign-u-p/plug-n-rag
```

```bash
claude plugin install plug-n-rag@plug-n-rag
```

### 3. Vault einrichten

1. Starte Claude Code **im Ordner deiner Vault** (dem Ordner, in dem auch `.obsidian/` liegt).
   In der Desktop-App: Ordner der Vault als Projekt wählen. Im Terminal: `cd` in den Ordner,
   dann `claude`.
2. Claude meldet beim Start: „Obsidian-Vault erkannt, aber noch nicht eingerichtet.“
3. Gib ein:

   ```
   /plug-n-rag:setup
   ```

4. Claude führt dich durch die Einrichtung: Bestandsaufnahme, Hinweis zum Datenschutz, Frage nach
   privaten Ordnern, auf Wunsch ein privates GitHub-Repo, Kostenvoranschlag, erste Indexierung,
   eine Karte deiner Vault und eine Testsuche. Du entscheidest, Claude erledigt.
5. Beim ersten Mal fragt Claude Code eventuell, ob plug-n-rag seine automatischen Abläufe
   (Hooks) ausführen darf. Bitte erlauben, sonst bleibt der Index nicht aktuell.

Die erste Indexierung lädt einmalig ein Sprachmodell (etwa 470 MB) herunter. Das dauert je nach
Verbindung ein paar Minuten. Die Stichwortsuche funktioniert schon vorher.

## Erste Schritte

Frag einfach in normaler Sprache, zum Beispiel:

- „Was habe ich zu sensorischer Integration notiert?“
- „Fass meine Supervisionsnotizen vom Oktober zusammen.“
- „Recherchiere in meiner Vault alles zu betätigungsorientierter Befunderhebung.“
- „Schreib mir aus meinen Notizen einen Elternbrief zum Thema Morgenroutine.“

Claude nutzt dafür automatisch die Suche von plug-n-rag und nennt die Quellen mit Zeilen.

### Befehle

| Befehl | Wofür |
| --- | --- |
| `/plug-n-rag:setup` | Geführte Einrichtung (auch zum Fortsetzen oder Prüfen) |
| `/plug-n-rag:status` | Ist alles aktuell? Fehler? Wie viel wurde gespart? |
| `/plug-n-rag:cloud` | Vault in Cloud-Sitzungen nutzen: Einrichtung und Prüfung |
| `/plug-n-rag:nach-main` | Änderungen aus dem Chat in den Hauptstand übernehmen |
| `/plug-n-rag:aufnehmen` | PDFs in durchsuchbaren Text umwandeln |
| `/plug-n-rag:reindex` | Alles neu aufbauen, z. B. nach einem Modellwechsel |
| `/plug-n-rag:modell-wechseln` | Lokales Modell oder Voyage AI wählen |
| `/plug-n-rag:lernen-zuruecksetzen` | Gelernte Suchgewohnheiten zurücksetzen |

Claude selbst verwendet im Hintergrund `plug-n-rag suche`, `gliederung`, `lesen`, `verwandt` und
`karte`. Du kannst sie auch selbst im Terminal aufrufen (`plug-n-rag --help`).

### Rückmeldung geben

- „Das war mir zu oberflächlich.“ → Claude liefert künftig für diese Art Aufgabe mehr.
- „Das war zu ausführlich.“ → künftig knapper.

## Datenschutz

- **Ohne deine Zustimmung geht nichts an einen weiteren Dienst außer Anthropic.** Was Claude beim
  Arbeiten liest, geht wie bei jeder Nutzung von Claude Code an Anthropic. Der Suchindex wird
  lokal auf deinem Gerät berechnet.
- **Index-Dateien enthalten keinen Notiztext**, bilden aber Inhalte ab. Sie sind deshalb so
  schützenswert wie deine Notizen. Das Repo muss **privat** sein; Setup und Status prüfen das.
- **Private Ordner und Notizen** (`private_folders` in `plug-n-rag.yml` oder `privat: true` im
  Frontmatter) werden vollständig ausgeschlossen. Wird eine Notiz nachträglich privat, löscht der
  nächste Abgleich ihren Index.
- **Eingescannte Dokumente** werden nur nach ausdrücklicher Rückfrage von Claude abgeschrieben,
  weil dabei ganze Dokumente an Anthropic gehen.
- **Das Nutzungsprotokoll** (`.plug-n-rag/cache/log.jsonl`, nie im Repo) speichert Pfade und
  Zählwerte, aber keine Suchanfragen und keine Notizinhalte.
- **API-Keys** (nur für Voyage AI) gehören in die Umgebungsvariable `VOYAGE_API_KEY`, nie in eine
  Datei im Repo.
- plug-n-rag verändert **keine bestehenden Notizen**. Es legt nur `plug-n-rag.yml` und den Ordner
  `.plug-n-rag/` an und ergänzt `.gitignore`.

## Cloud-Sitzungen

Liegt deine Vault in einem privaten GitHub-Repo, kannst du plug-n-rag auch in Cloud-Sitzungen
nutzen: Claude Code im Browser unter claude.ai/code oder in der Desktop- oder Handy-App. Du
kannst sogar **alles direkt in der Cloud einrichten**, ohne vorher etwas auf deinem Rechner zu
installieren.

### Einrichtung direkt in der Cloud

1. Starte unter claude.ai/code (oder in der App) eine Sitzung mit deinem **Vault-Repo**.
2. Schreib als erste Nachricht:

   ```text
   Bitte installiere das Plugin plug-n-rag mit
   claude plugin marketplace add sign-u-p/plug-n-rag
   und claude plugin install plug-n-rag@plug-n-rag
   und richte danach meine Vault mit /plug-n-rag:setup ein.
   ```

   Falls Claude den Setup-Befehl nicht sofort findet, schreib einfach „weiter“.
3. Claude führt dich durch die Einrichtung (Datenschutz, private Ordner, Indexierung, Karte,
   Testsuche). Für das Suchmodell braucht die Cloud-Umgebung eine Netzwerkfreigabe für Hugging Face.
   Claude schlägt sie vor oder erklärt, wo du sie einträgst.
4. Zum Schluss sorgt Claude mit einem **Setup-Skript** in der Cloud-Umgebung dafür, dass künftige
   Sitzungen plug-n-rag automatisch haben, und legt auf Wunsch alles nach `main` (siehe unten).

**Warum nicht über das Repo?** Cloud-Sitzungen installieren keine Plugins, die ein Repo in
`.claude/settings.json` einträgt. Deshalb bekommt die **Cloud-Umgebung** ein Setup-Skript.
In einer Sitzung mit plug-n-rag erzeugt `/plug-n-rag:cloud` Netzwerkfreigabe und Setup-Skript passend
zu deiner Vault.

### Cloud-Umgebung von Hand einrichten

1. In der Sitzungsleiste auf den Namen der Cloud-Umgebung tippen, dann „Bearbeiten“ (oder eine
   eigene Umgebung „Hinzufügen“, z. B. „Vault“).
2. **Network access**: „Limited“, „Allow package managers“ angehakt lassen. Unter
   **Allowed domains** eintragen (für das Suchmodell von Hugging Face):

   ```text
   huggingface.co
   *.hf.co
   ```

3. **Setup script** einfügen:

   ```bash
   #!/bin/bash
   command -v claude >/dev/null 2>&1 || exit 0
   claude plugin marketplace add sign-u-p/plug-n-rag >/dev/null 2>&1 \
     || claude plugin marketplace update plug-n-rag >/dev/null 2>&1 || true
   claude plugin install plug-n-rag@plug-n-rag >/dev/null 2>&1 || true
   P=$(ls -d "$HOME"/.claude/plugins/cache/plug-n-rag/plug-n-rag/*/ 2>/dev/null | sort -V | tail -1)
   if [ -n "$P" ]; then "${P}bin/plug-n-rag" modell-laden --modell intfloat/multilingual-e5-small || true; fi
   exit 0
   ```

4. Speichern und eine neue Sitzung mit dem Vault-Repo in dieser Umgebung starten. Der erste Start
   dauert einige Minuten, weil das Modell (etwa 470 MB) geladen wird. Danach wird die Umgebung als
   Abbild gespeichert, und neue Sitzungen sind sofort suchbereit.
5. In der Cloud-Sitzung prüfen: Claude bitten, `plug-n-rag cloud --pruefen` auszuführen.

Gut zu wissen:

- Die Index-Dateien (`.plug-n-rag/index/`) müssen committet und gepusht sein. Dann berechnet die
  Cloud-Sitzung nichts neu.
- Cloud-Sitzungen arbeiten auf einem eigenen Branch (`claude/…`). Sag Claude einfach
  „leg das nach main“, dann übernimmt plug-n-rag Notizen und Index in den Hauptstand (siehe unten).
- **Voyage AI** statt lokalem Modell: keine Hugging-Face-Freigabe nötig. Den Voyage-Key trägst du als
  **Netzwerk-Secret** der Umgebung für den Host `api.voyageai.com` ein, nie als Umgebungsvariable
  und nie ins Repo. plug-n-rag lässt den Key dann vom Netzwerk-Proxy einsetzen.
- Updates von plug-n-rag kommen in die Cloud-Umgebung, wenn sie neu gebaut wird (spätestens nach
  etwa sieben Tagen oder nach einer Änderung am Setup-Skript).

## Aus dem Chat nach main

Ob lokal oder in der Cloud: Sag Claude „leg das nach main“ (oder `/plug-n-rag:nach-main`).
plug-n-rag übernimmt dann neue und geänderte Notizen zusammen mit dem Suchindex in den Hauptstand
deines Repos. Danach siehst du die Änderungen auch in Obsidian.

Dabei gilt:

- Es wird nichts überschrieben. Hat sich `main` inzwischen geändert (z. B. durch Obsidian Git),
  wird der neueste Stand zuerst zusammengeführt.
- Haben Claude und du **dieselbe Notiz** unterschiedlich geändert, bricht plug-n-rag ab und Claude
  fragt dich, welche Fassung gelten soll.
- Sieht etwas wie ein API-Key aus, wird nichts übernommen.
- Ist `main` auf GitHub geschützt, bietet Claude stattdessen einen Pull Request an.

## Andere Ordner (Sammlungs-Modus)

Sag zum Beispiel: „Mach meinen Ordner Fachliteratur durchsuchbar“ oder
`/plug-n-rag:setup ~/Dokumente/Fachliteratur`. In diesem Modus schreibt plug-n-rag **nichts** in
den Ordner. Der Index liegt in deinem Benutzer-Cache. Unterstützt werden Markdown, Text und PDF
mit Textebene. Eingescannte PDFs lassen sich mit `/plug-n-rag:aufnehmen` erschließen.

## Optional: MCP-Server

plug-n-rag bringt einen MCP-Server mit denselben Werkzeugen (`karte`, `suche`, `gliederung`,
`lesen`, `verwandt`, `status`) mit. Er ist nicht automatisch aktiv. Nach der ersten Sitzung mit
plug-n-rag kannst du ihn so registrieren (der Pfad zeigt auf einen Starter, den plug-n-rag beim
Sitzungsstart anlegt):

```bash
claude mcp add plug-n-rag -- ~/.cache/plug-n-rag/plug-n-rag mcp
```

## Bekannte Grenzen

- Version 1 versteht Markdown, Text und PDF mit Textebene. Word, HTML und E-Books folgen später.
- Die lokale Texterkennung für Scans braucht das Programm Tesseract (Claude bietet die Installation
  an). Ohne Tesseract bleibt nur das Abschreiben durch Claude, nach Rückfrage.
- Der einmalige Modell-Download ist mit etwa 470 MB groß. In Cloud-Sitzungen lädt ihn das
  Setup-Skript einmal pro Umgebungsabbild.
- Die Relevanzschwellen sind an einer kleinen Test-Vault kalibriert und werden mit echten Vaults
  nachjustiert.
- Unter Windows wird Git Bash benötigt (bringt Git für Windows mit).
- Mehrere Sammlungen lassen sich noch nicht gemeinsam durchsuchen.
- Obsidian Git ist auf dem Handy eingeschränkt. Empfehlung: Obsidian Sync für Geräte, Git nur auf
  dem Rechner.

Details: [DECISIONS.md](DECISIONS.md) (Entscheidungen), [OPEN.md](OPEN.md) (offene Punkte),
[SPEC.md](SPEC.md) (Spezifikation).

## Für Entwickler:innen

```bash
uv sync --all-extras
```

```bash
uv run pytest
```

Die Tests nutzen eine Beispiel-Vault unter `tests/fixtures/vault/`. Tests mit dem echten lokalen
Modell sind mit `model` markiert (`uv run pytest -m "not model"` überspringt sie), Tests gegen die
echte Voyage-API mit `voyage` (laufen nur mit gesetztem `VOYAGE_API_KEY`).

Aufbau:

```
.claude-plugin/       plugin.json, marketplace.json
bin/plug-n-rag        Starter (uv, Umgebung im Nutzer-Cache)
hooks/hooks.json      SessionStart, Stop
skills/               suche, setup, cloud, nach-main, status, reindex, aufnehmen, modell-wechseln, lernen-zuruecksetzen
agents/               transkription (Haiku)
src/plug_n_rag/       Kern: formats, chunk, index_store, sync, db, search, navigate, mapview,
                      status, tuning, ingest, inventory, gitops, cloud, embed/, mcp_server, cli
tests/                pytest, Fixture-Vault, PDF-Generator
```

Lizenz: MIT. Hinweise zu übernommenen Ideen: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
