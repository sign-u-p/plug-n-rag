---
name: modell-wechseln
disable-model-invocation: true
description: Wechselt bei plug-n-rag den Embedding-Provider oder das Modell (lokal oder Voyage AI) mit Kostenvoranschlag und anschließender vollständiger Neuindexierung. Nur auf ausdrücklichen Wunsch der Nutzer:in.
allowed-tools: Bash(plug-n-rag konfig*) Bash(plug-n-rag inventur*) Bash(plug-n-rag status*)
---

Ein Modellwechsel ist ein bewusster Vorgang. Schritte:

1. `plug-n-rag status --schnell` und `plug-n-rag konfig` zeigen das aktuelle Modell.
2. Optionen erklären, ohne Fachjargon:
   - **lokal** `intfloat/multilingual-e5-small`: kostenlos, nichts verlässt den Rechner außer dem
     einmaligen Download (etwa 470 MB von Hugging Face).
   - **Voyage AI** `voyage-3.5-lite`: weiterer Dienst außer Anthropic (gehört zu MongoDB), kostet pro
     Token, braucht einen API-Key in `VOYAGE_API_KEY` (nie in eine Datei im Repo).
   Wechsel zu Voyage nur, wenn die Nutzer:in zustimmt, dass Inhalte an diesen Dienst gehen.
3. Kostenvoranschlag: `plug-n-rag inventur --json` → `estimate`. Dauer lokal nennen, bei Voyage
   Tokens nennen und den aktuellen Preis auf voyageai.com/pricing nachsehen.
4. Nach Bestätigung umstellen, z. B.
   `plug-n-rag konfig --setzen embedding.provider=voyage embedding.model=voyage-3.5-lite`.
   Ab jetzt meldet die Suche „nur Stichwortsuche“, bis neu indexiert ist.
5. `/plug-n-rag:reindex` ausführen (fragt erneut nach Zustimmung) und das Ergebnis in **einem**
   Commit ablegen.
