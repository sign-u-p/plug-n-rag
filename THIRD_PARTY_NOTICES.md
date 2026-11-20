# Hinweise zu Drittprojekten

plug-n-rag übernimmt Ideen und Muster aus den folgenden Projekten. Code wurde nicht wörtlich
kopiert, sondern in Python neu geschrieben; die Lizenzhinweise bleiben trotzdem erhalten.

## git-rag

https://github.com/dogfoodlab-io/git-rag (v0.1.0)

Übernommen: Breadcrumb vor dem Embedding-Text, Chunk-Hash über Titel + Überschrift + Text,
Ersatz-Abschnitt für leere Notizen, Parsing von Frontmatter/Tags/Wikilinks, Verkettung
bestehender Git-Hooks, Zitierregeln im Skill. Betroffene Dateien: `plugins/plug-n-rag/src/plug_n_rag/chunk.py`,
`plugins/plug-n-rag/src/plug_n_rag/formats/markdown.py`, `plugins/plug-n-rag/src/plug_n_rag/gitops.py`, `plugins/plug-n-rag/skills/suche/SKILL.md`.

```
MIT License

Copyright (c) 2026 Dogfood Lab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## git-semantic

https://github.com/ccherrad/git-semantic (Lizenz laut Cargo.toml: MIT OR Apache-2.0)

Übernommen: Index-Datei pro Quelldatei mit gespiegeltem Pfad, `hydrate` in eine lokale
SQLite-Datenbank, Gliederungs-Modus zum Token-Sparen, Karte vor der Suche. Betroffene Dateien:
`plugins/plug-n-rag/src/plug_n_rag/index_store.py`, `plugins/plug-n-rag/src/plug_n_rag/db.py`, `plugins/plug-n-rag/src/plug_n_rag/navigate.py`,
`plugins/plug-n-rag/src/plug_n_rag/mapview.py`. Genutzt unter der MIT-Lizenz.

## qmd

https://github.com/tobi/qmd (MIT)

Übernommen (nur als Idee): Kontextbeschreibungen pro Ordner, Hybrid aus BM25 und Vektorsuche
mit Reciprocal Rank Fusion.

## Laufzeit-Abhängigkeiten

numpy (BSD), PyYAML (MIT), sqlite-vec (MIT/Apache-2.0), onnxruntime (MIT), tokenizers
(Apache-2.0), pypdf (BSD), optional pypdfium2 (Apache-2.0/BSD), optional mcp (MIT).
Modell: intfloat/multilingual-e5-small (MIT), wird zur Laufzeit von Hugging Face geladen.
