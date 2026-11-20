---
name: status
disable-model-invocation: true
description: Zeigt den Zustand von plug-n-rag für die aktuelle Vault oder Sammlung (Aktualität, Modell, Fehler, gelernte Werte, geschätzte Token-Ersparnis) und erklärt ihn verständlich. English: shows and explains plug-n-rag's state for the current vault or collection.
allowed-tools: Bash(plug-n-rag status*)
---

> **Sprache / language:** Antworte in der Sprache, in der die Nutzer:in schreibt; auf Deutsch
> gendergerecht mit Doppelpunkt. If the user writes in English, answer in English. Alle Befehle
> gibt es auch englisch (`search`, `read`, `outline`, `--purpose question`, …); die festen Texte
> von plug-n-rag folgen der Sprache der Vault (`language` in der Konfiguration).
>
> **Werkzeug / tool:** `plug-n-rag` immer mit dem **Bash**-Werkzeug ausführen, nie mit PowerShell
> (unter Windows kennt PowerShell den Befehl nicht). Always run `plug-n-rag` with the Bash tool.

Führe `plug-n-rag status` aus (bei langsamer Verbindung `plug-n-rag status --schnell`).

Fasse das Ergebnis für die Nutzer:in in wenigen Sätzen in ihrer Sprache zusammen, ohne Fachbegriffe
wie Embedding oder Hash, außer sie fragt danach:

- Ist alles aktuell? Wie viele Dateien sind durchsuchbar, wie viele warten noch?
- Gibt es Fehler bei einzelnen Dateien? Nenne sie und schlage einen Weg vor
  (eingescannte PDFs: `/plug-n-rag:aufnehmen`).
- ⚠-Zeilen immer ansprechen: öffentliches Repo (dringend privat stellen, Hilfe anbieten),
  Modellkonflikt (`/plug-n-rag:reindex` anbieten), Provider nicht erreichbar
  (Netzwerkfreigabe für huggingface.co bzw. api.voyageai.com erklären).
- Gelernte Werte und Ersparnis kurz erwähnen. Die Ersparnis ist eine Schätzung.

Ist noch nichts eingerichtet, `/plug-n-rag:setup` anbieten.
