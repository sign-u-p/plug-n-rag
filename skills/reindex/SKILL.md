---
name: reindex
disable-model-invocation: true
description: Vollständige Neuindexierung der Vault oder Sammlung mit plug-n-rag, etwa nach einem Modellwechsel oder wenn der Index nicht zum Modell passt. Fragt vorher nach Zustimmung.
allowed-tools: Bash(plug-n-rag reindex*) Bash(plug-n-rag status*)
---

1. `plug-n-rag reindex` (ohne `--ja`) zeigt, was neu berechnet würde. Dazu `plug-n-rag status --schnell`.
2. Erkläre der Nutzer:in kurz und ohne Fachjargon: Alle Dateien werden neu für die Suche
   aufbereitet. Lokal kostet das nichts, dauert aber je nach Größe einige Minuten. Mit Voyage
   entstehen Kosten (Tokens aus `plug-n-rag inventur` nennen, aktuellen Preis auf
   voyageai.com/pricing nachsehen, nicht raten).
3. Erst nach ausdrücklicher Zustimmung: `plug-n-rag reindex --ja --fortschritt`.
4. Danach, wenn die Vault ein Git-Repo ist, die geänderten Index-Dateien in einem eigenen Commit
   ablegen: `git add .plug-n-rag/index plug-n-rag.yml` und
   `git commit -m "plug-n-rag: Index neu aufgebaut (<Modell>)"`. Kein Push ohne Rückfrage, nie `--force`.
5. Zum Schluss `plug-n-rag status --schnell` und das Ergebnis in einem Satz zusammenfassen.
