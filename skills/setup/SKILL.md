---
name: setup
description: Geführte Einrichtung von plug-n-rag für eine Obsidian-Vault oder auf ausdrücklichen Wunsch für einen anderen Ordner (Dokumentensammlung, Bibliothek), inklusive Datenschutz-Hinweis, Git/GitHub, Kostenvoranschlag, erster Indexierung, Karte und optional Obsidian Git. Verwenden, wenn jemand die Vault oder einen Ordner durchsuchbar machen will oder der Sitzungsstart „noch nicht eingerichtet“ meldet.
argument-hint: "[pfad zum ordner]"
---

# Einrichtung von plug-n-rag (Gesprächsleitfaden)

Du führst ein ruhiges, verständliches Gespräch. Die Nutzer:in hat keinen Entwicklungshintergrund.
Keine Git-, Terminal- oder Datenbankbegriffe, außer auf Nachfrage. Deutsch, gendergerecht mit
Doppelpunkt, kurze Absätze, eine Frage pro Nachricht (höchstens zwei eng verwandte).

Argument (optional): `$ARGUMENTS` – ein Ordner, der eingerichtet werden soll. Ohne Argument gilt
der aktuelle Projektordner.

Der Befehl heißt `plug-n-rag` (Ersatz, falls nicht auf dem PATH:
`"${CLAUDE_PLUGIN_ROOT}/bin/plug-n-rag"`).

## Grundsätze

**Drei Stufen für jeden Schritt**

| Stufe | Beispiele |
| --- | --- |
| Selbst erledigen | Dateien anlegen, `git init`, `.gitignore`, Commits, Konfiguration, Indexierung, Obsidian-Git-Dateien ablegen |
| Anbieten, nach Zustimmung erledigen | GitHub-CLI installieren (Homebrew, winget), Vault aus einem Cloud-Sync-Ordner verschieben, PDFs umwandeln, uv installieren |
| Anleiten und danach prüfen | Browser-Anmeldung bei GitHub, Community-Plugins in Obsidian erlauben, Netzfreigabe und Secrets für Cloud-Sitzungen |

**Invarianten (nie verletzen)**

- Keine bestehende Notiz wird verändert: kein Frontmatter ergänzen, nichts verschieben, nichts
  umbenennen, außer auf ausdrückliche Zustimmung.
- PDFs werden nur aufgelistet, nicht umgewandelt. Umwandlung später über `/plug-n-rag:aufnehmen`.
- Jeder Schritt prüft zuerst, ob er schon erledigt ist. Ein erneuter Aufruf setzt fort oder bestätigt nur.
- Keine destruktiven Git-Operationen: kein `push --force`, kein `reset --hard`, keine automatische
  Konfliktlösung in Notizen.
- API-Keys nie in Dateien, nie ins Repo, nie in den Chat zurückspielen.
- Sicherheitsentscheidungen (eingeschränkter Modus in Obsidian, Freigaben in Claude Code,
  Admin-Passwort) erklären, nie umgehen.
- Hooks von plug-n-rag können beim ersten Ausführen eine Freigabe in Claude Code verlangen.
  Kündige das vorher an.

## Schritt 0: Welcher Modus?

- **Vault-Modus** (Standard): Der Ordner enthält `.obsidian/`. Markdown-Notizen, Index im Repo.
- **Sammlungs-Modus**: nur wenn die Nutzer:in ausdrücklich einen anderen Ordner durchsuchbar
  machen möchte (z. B. „Mach meinen Ordner Fachliteratur durchsuchbar“). Markdown, Text und PDF
  mit Textebene. **Streng nur lesend**: In die Sammlung wird nichts geschrieben. Der Index liegt
  außerhalb im Nutzer-Cache (`--extern`), außer der Ordner ist schon ein Git-Repo oder die
  Nutzer:in stimmt einem Unterordner `.plug-n-rag/` ausdrücklich zu. GitHub nur auf Nachfrage
  (große Binärdateien, urheberrechtlich geschützte Werke, 100-MB-Grenze, nur privates Repo).
  Pro Ordner eine eigene Sammlung. Eine gemeinsame Suche über mehrere Sammlungen gibt es noch nicht.

Prüfe außerdem, ob `uv` vorhanden ist (`command -v uv`). Fehlt es, anbieten, es zu installieren
(macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows:
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`), erst nach Zustimmung.

## Schritt 1: Bestandsaufnahme (still, ohne KI)

`plug-n-rag inventur <pfad>` (bei Bedarf `--json`). Sie liefert: Vault ja/nein, schon eingerichtet,
Git, Remote, Sichtbarkeit, GitHub-CLI und Anmeldung, Cloud-Sync-Ordner, Dateien über 100 MB,
Anzahl/Größe/Tokens der Notizen, Ordner, Frontmatter-Anteil, Link-Dichte, andere Dateien, PDFs
ohne Textebene mit Seitenzahl, Vorlagen-Ordner, möglicherweise private Ordner, Schätzung.

Fasse das in drei bis fünf Sätzen zusammen. Ist alles schon eingerichtet: nur bestätigen,
`plug-n-rag status --schnell` zeigen und fragen, ob etwas fehlt (weiter bei Schritt 11).

Liegt die Vault in iCloud, OneDrive, Dropbox oder Google Drive: erklären, dass Git und
Cloud-Sync gemeinsam oft Konflikte erzeugen. Anbieten, die Vault nach Zustimmung an einen
normalen Ort zu verschieben (Obsidian muss die Vault danach neu öffnen; Schritt für Schritt
anleiten). Nicht ohne Zustimmung verschieben.

## Schritt 2: Weg wählen

- Keine Vault, leerer Ordner → Startstruktur anlegen (z. B. `wissen/`, `themen/`, `notizen/`,
  `Vorlagen/`) und dann wie „Vault ohne Git“.
- Vault ohne Git → Schritte 3 und 4.
- Vault mit Git, aber ohne GitHub → Schritt 4.
- Vault schon auf GitHub → direkt zu Schritt 5.
- **Öffentliches Repo** → deutliche Warnung: Notizen und Index sind für alle sichtbar.
  Anbieten, es auf privat zu stellen (`gh repo edit <owner/repo> --visibility private
  --accept-visibility-change-consequences` nach Zustimmung, sonst über die GitHub-Webseite
  anleiten: Settings → General → Danger Zone → Change visibility).

## Schritt 3: Git lokal

Nur wenn noch kein Repo: `git init`, dann `.gitignore` ergänzen (nur anhängen, nie überschreiben)
mit `.plug-n-rag/cache/`, `.obsidian/workspace*.json`, `.trash/`. `plug-n-rag init` ergänzt diese
Zeilen ebenfalls. Erster Commit: „Vault in Git aufgenommen“. Ist kein Git-Name gesetzt, nach Name
und E-Mail fragen und nur lokal für dieses Repo setzen (`git config user.name ...`).

## Schritt 4: GitHub

- GitHub-CLI vorhanden und angemeldet → `gh repo create <name> --private --source . --push`.
- CLI fehlt → Installation anbieten (macOS: `brew install gh`, Windows: `winget install GitHub.cli`),
  danach `gh auth login --web` anleiten: Die Nutzer:in meldet sich einmal im Browser an.
  Danach mit `gh auth status` prüfen.
- Lieber ohne CLI → Schritt für Schritt über github.com anleiten (neues Repo, **Private** wählen,
  keine README anlegen), dann `git remote add origin <url>` und `git push -u origin HEAD`.
- Immer privat. Danach Sichtbarkeit mit `plug-n-rag inventur --json` (git.visibility) prüfen.

## Schritt 5: Inventur besprechen

Aus der Bestandsaufnahme vorschlagen:
- Vorlagen-Ordner ausschließen (werden von `plug-n-rag init` automatisch erkannt).
- Ordner mit Namen wie Tagebuch, Journal, Privat, Personal **gezielt nachfragen**: Sollen sie privat
  bleiben? Private Ordner und Notizen mit `privat: true` im Frontmatter werden vollständig
  ausgeschlossen: kein Index, keine Suche, nichts geht an einen Dienst.
- Weitere Ausschlüsse (z. B. `Archiv/**`) nur auf Wunsch.
- Dateien über 100 MB ausschließen, sonst lehnt GitHub den Push ab.
- Gescannte PDFs nur nennen, nicht umwandeln.

## Schritt 6: Datenschutz und Modell

Zuerst dieser Hinweis, sinngemäß und kurz:

> Was ich (Claude) beim Arbeiten lese, geht wie bei jeder Nutzung von Claude Code an Anthropic.
> Der Suchindex wird bei dir auf dem Rechner berechnet und liegt in deinem eigenen, privaten
> Repo. Er enthält keinen Notiztext, aber er bildet Inhalte ab und ist deshalb so schützenswert
> wie die Notizen selbst. Wenn eingescannte Dokumente vollständig abgeschrieben werden sollen,
> frage ich vorher gesondert, weil dann ganze Dokumente an Anthropic gehen.

Dann die Frage: **„Dürfen deine Inhalte zusätzlich an einen weiteren Dienst außer Anthropic gehen?“**

- **Nein** (Standard) → lokales Modell (`--provider local`, intfloat/multilingual-e5-small, gut für
  Deutsch). Einmaliger Download von etwa 470 MB von Hugging Face. Keine externe Texterkennung.
- **Ja** → Voyage AI möglich (`--provider voyage`, Modell `voyage-3.5-lite`): schneller auf schwachen
  Rechnern, kostet pro Token. Der API-Key gehört **nur** in die Umgebungsvariable `VOYAGE_API_KEY`
  oder in die Datei `~/.config/plug-n-rag/voyage_api_key` außerhalb des Repos. Erkläre, wie die
  Nutzer:in die Variable selbst setzt; lass dir den Key nicht in den Chat schreiben.

Hinweis und Frage gelten im Vault- und im Sammlungs-Modus gleichermaßen.

## Schritt 7: Kostenvoranschlag und Konfiguration

Nenne aus der Inventur: Anzahl Dateien, Tokens, geschätzte Dauer lokal (plus Download), bei
Voyage die Tokens und die Kosten. Den Voyage-Preis zur Laufzeit auf voyageai.com/pricing
nachsehen (WebFetch), nicht aus dem Gedächtnis. Vorgeschlagene Ausschlüsse nennen. Bei Scans
die Transkriptionsfrage stellen oder ausdrücklich auf später verschieben.

**Erst nach Bestätigung** konfigurieren:

```
plug-n-rag init <pfad> --modus vault|sammlung [--extern] --provider local|voyage \
  --privat "Tagebuch/**" --ausschliessen "Archiv/**"
```

`init` überschreibt nie eine bestehende Konfiguration. Anpassungen später mit
`plug-n-rag konfig --setzen schluessel=wert` (z. B. `private_folders=["Tagebuch/**"]`).

## Schritt 8: Erste Indexierung

`plug-n-rag sync --fortschritt` (bei großen Vaults im Hintergrund starten). Neueste Dateien kommen
zuerst. Die Stichwortsuche funktioniert sofort, die semantische Suche wächst mit. Bei mehreren
tausend Notizen anbieten, zuerst ausgewählte Ordner zu indexieren (übrige vorübergehend
ausschließen, danach wieder aufnehmen). Den Fortschritt in einfachen Worten melden.

## Schritt 9: Karte

`plug-n-rag karte`. Lies pro Ordner zwei bis drei Stichproben (Gliederung oder Abschnitt, nicht
ganze Notizen) und schlage je Ordner eine Beschreibung in einem Satz vor. Nach Bestätigung oder
Korrektur speichern: `plug-n-rag konfig --setzen 'folders={"wissen/": "Fachtexte", ...}'`.

## Schritt 10: Testsuche

Wähle ein Thema, das in der Vault vorkommt, suche mit `plug-n-rag suche "…" --zweck frage`,
lies den besten Abschnitt und zeige das Ergebnis mit Quelle (Pfad und Zeilen). Erkläre in einem
Satz, warum das Tokens spart.

## Schritt 11: Optionales

Jeweils einzeln anbieten:

**a) Obsidian Git** (automatisches Sichern aus Obsidian):
- Selbst erledigen: aktuelles Release von https://github.com/Vinzent03/obsidian-git/releases/latest
  herunterladen (`main.js`, `manifest.json`, `styles.css`) nach `.obsidian/plugins/obsidian-git/`.
  `"obsidian-git"` in `.obsidian/community-plugins.json` ergänzen (Liste erhalten). Eine
  `data.json` nur anlegen, wenn keine existiert: Pull beim Start an, automatisch sichern und
  hochladen alle 10 Minuten. Schlüsselnamen vorher in `main.js` unter `DEFAULT_SETTINGS` prüfen
  (z. B. `autoPullOnBoot`, `autoSaveInterval`, `autoPullInterval`), nicht raten.
- Anleiten: In Obsidian einmal den eingeschränkten Modus ausschalten (Einstellungen →
  Community-Plugins → „Eingeschränkten Modus deaktivieren“). Das ist eine Sicherheitsentscheidung
  der Nutzer:in, nicht umgehen.
- Hinweis mobil: Obsidian Git ist auf dem Handy eingeschränkt. Empfehlung: Obsidian Sync für die
  Geräte, Git nur auf dem Rechner.
- Alternative ohne Obsidian Git: `plug-n-rag konfig --setzen git.auto_commit=all` – dann werden
  Änderungen beim nächsten Start von Claude Code übernommen und committet
  (`git.auto_push=true` lädt sie zusätzlich hoch). Beide Wege erklären, die Nutzer:in wählt.
- Git-pre-commit-Hook anbieten: `plug-n-rag git-hook` (hält den Index im selben Commit wie die
  Notizen, verkettet bestehende Hooks).

**b) Cloud-Sitzungen** (Claude Code im Browser/App mit dieser Vault):
- In `.claude/settings.json` des Vault-Repos eintragen (bestehende Einträge erhalten):
  ```json
  {
    "extraKnownMarketplaces": {
      "plug-n-rag": {"source": {"source": "github", "repo": "sign-u-p/plug-n-rag"}}
    },
    "enabledPlugins": {"plug-n-rag@plug-n-rag": true}
  }
  ```
- Netzfreigabe der Cloud-Umgebung erklären: lokales Modell braucht `huggingface.co` und die
  Download-Server von Hugging Face (z. B. `us.aws.cdn.hf.co`, `cas-bridge.xethub.hf.co`);
  Voyage braucht `api.voyageai.com`. Der Voyage-Key kommt als Secret der Cloud-Umgebung hinein,
  nie ins Repo.
- Die Index-Dateien liegen im Repo, deshalb ist eine frische Cloud-Sitzung ohne neues Embedding
  sofort suchbereit. Nur Suchanfragen selbst brauchen das Modell.

**c) Lern-Datei** committen ja/nein: `plug-n-rag konfig --setzen tuning.commit_learning=true`
(Standard: nur lokal).

**d) CLAUDE.md**: kurzen Abschnitt anbieten (nur nach Zustimmung, nur anhängen):
„Diese Vault ist mit plug-n-rag durchsuchbar. Für Inhalte zuerst `plug-n-rag suche` nutzen.“

## Schritt 12: Abschluss

- Prüfen, dass kein API-Key in einer Datei steht (`git grep -n -I -E "pa-[A-Za-z0-9_-]{20,}|VOYAGE_API_KEY="`).
- Ein Commit: `git add .plug-n-rag plug-n-rag.yml .gitignore` (plus ggf. `.claude/settings.json`,
  `.obsidian/plugins/obsidian-git`, `.obsidian/community-plugins.json`) und
  `git commit -m "Vault-Index angelegt (N Notizen)"`. Push nur, wenn ein Remote eingerichtet ist.
- Zusammenfassung in einfachen Worten: was ab jetzt automatisch passiert (beim Start: neuester
  Stand, Abgleich, Kurz-Karte; nach jeder Antwort: kurzer Abgleich im Hintergrund) und die
  wichtigsten Befehle: `/plug-n-rag:status`, `/plug-n-rag:reindex`, `/plug-n-rag:aufnehmen`.
