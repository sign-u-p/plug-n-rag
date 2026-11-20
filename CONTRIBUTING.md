# Mitarbeiten

## Aufbau des Repos

Das Repo ist ein **Marketplace** für Claude Code. Jedes Plugin liegt in einem eigenen Ordner unter
`plugins/` und wird über `.claude-plugin/marketplace.json` angeboten:

```
plug-n-rag/                         Repo sign-u-p/plug-n-rag
├── .claude-plugin/marketplace.json  Katalog: ein Eintrag pro Plugin
├── plugins/
│   ├── plug-n-rag/                  das Hauptplugin (Python über uv)
│   └── plug-n-rag-anzeige/          optionale Anzeige im Chat (Mod, TypeScript)
├── tools/check.sh                   prüft Katalog und alle Plugins
├── README.md, README.de.md         Anleitung für Nutzer:innen (Englisch, Deutsch)
├── SPEC.md, DECISIONS.md, OPEN.md   Spezifikation, Entscheidungen, offene Punkte
└── LICENSE, THIRD_PARTY_NOTICES.md
```

Installiert wird immer über den Marketplace:
`/plugin marketplace add sign-u-p/plug-n-rag`, dann `/plugin install <plugin>@plug-n-rag`.

## Ein neues Plugin hinzufügen

1. Ordner `plugins/<name>/` mit mindestens `.claude-plugin/plugin.json` (`name` = Ordnername,
   `version`, `description`, `author`, `license`), `README.md` und `LICENSE` anlegen.
2. Braucht es plug-n-rag, in `plugin.json` `"dependencies": ["plug-n-rag"]` eintragen.
3. Eintrag in `.claude-plugin/marketplace.json` ergänzen:
   `{ "name": "<name>", "source": "./plugins/<name>", "description": "…" }`.
   Der Name im Eintrag muss dem Namen in `plugin.json` entsprechen.
4. Tests in den Plugin-Ordner legen: Python unter `tests/` (pytest), Mods als `*.test.tsx`.
5. `tools/check.sh` ausführen. Es findet neue Plugins von selbst.

Regeln, die für alle Plugins gelten:
- Kein Ordner `bin/` auf oberster Ebene eines Plugins (claude.ai lehnt solche Plugins ab).
- Texte für Nutzer:innen zweisprachig, Englisch und Deutsch (Deutsch gendergerecht mit Doppelpunkt).
  Im Python-Kern mit `tr("Deutsch", "English")` aus `i18n.py`, im Mod mit `T(…)` aus `parse.ts`.
  Code und Kommentare englisch.
- Keine API-Keys in Dateien; Notizen der Nutzer:innen nie ohne Zustimmung verändern.

## Versionen

Jedes Plugin hat seine eigene Version in `plugin.json` (bei plug-n-rag zusätzlich in
`pyproject.toml` und `src/plug_n_rag/__init__.py`). Installierte Plugins bekommen Änderungen nur
mit einer neuen Versionsnummer. Also bei jeder Änderung, die ankommen soll, die Version erhöhen.

## Entwickeln

```bash
tools/check.sh --schnell
```

plug-n-rag einzeln:

```bash
cd plugins/plug-n-rag && uv sync --all-extras && uv run pytest
```

Die Anzeige einzeln:

```bash
claude plugin test plugins/plug-n-rag-anzeige
```

Zum Ausprobieren in einer Sitzung den Repo-Ordner als Marketplace hinzufügen
(`claude plugin marketplace add .`); Änderungen gelten dann nach `/reload-plugins`.
