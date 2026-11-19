---
name: status
description: Zeigt den Zustand von plug-n-rag für die aktuelle Vault oder Sammlung (Aktualität, Modell, Fehler, gelernte Werte, geschätzte Token-Ersparnis) und erklärt ihn verständlich.
allowed-tools: Bash(plug-n-rag status*)
---

Führe `plug-n-rag status` aus (bei langsamer Verbindung `plug-n-rag status --schnell`).

Fasse das Ergebnis für die Nutzer:in in wenigen Sätzen auf Deutsch zusammen, ohne Fachbegriffe
wie Embedding oder Hash, außer sie fragt danach:

- Ist alles aktuell? Wie viele Dateien sind durchsuchbar, wie viele warten noch?
- Gibt es Fehler bei einzelnen Dateien? Nenne sie und schlage einen Weg vor
  (eingescannte PDFs: `/plug-n-rag:aufnehmen`).
- ⚠-Zeilen immer ansprechen: öffentliches Repo (dringend privat stellen, Hilfe anbieten),
  Modellkonflikt (`/plug-n-rag:reindex` anbieten), Provider nicht erreichbar
  (Netzwerkfreigabe für huggingface.co bzw. api.voyageai.com erklären).
- Gelernte Werte und Ersparnis kurz erwähnen. Die Ersparnis ist eine Schätzung.

Ist noch nichts eingerichtet, `/plug-n-rag:setup` anbieten.
