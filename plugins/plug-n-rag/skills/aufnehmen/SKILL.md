---
name: aufnehmen
description: Wandelt PDFs (auch eingescannte) mit plug-n-rag in durchsuchbaren Text um, Seite für Seite über eine Kaskade aus Textebene, lokaler Texterkennung und – nur mit Zustimmung – Transkription durch den Subagenten transkription. Verwenden, wenn neue PDFs in die Vault oder Sammlung sollen. English: turns PDFs, including scans, into searchable text (/plug-n-rag:ingest).
argument-hint: "<pdf-datei> [weitere]"
allowed-tools: Bash(plug-n-rag aufnehmen*) Bash(plug-n-rag sync*) Bash(plug-n-rag ingest*)
---

> **Sprache / language:** Antworte in der Sprache, in der die Nutzer:in schreibt; auf Deutsch
> gendergerecht mit Doppelpunkt. If the user writes in English, answer in English. Alle Befehle
> gibt es auch englisch (`search`, `read`, `outline`, `--purpose question`, …); die festen Texte
> von plug-n-rag folgen der Sprache der Vault (`language` in der Konfiguration).
>
> **Werkzeug / tool:** `plug-n-rag` immer mit dem **Bash**-Werkzeug ausführen, nie mit PowerShell
> (unter Windows kennt PowerShell den Befehl nicht). Always run `plug-n-rag` with the Bash tool.

# PDFs aufnehmen

Dateien: `$ARGUMENTS` (ohne Angabe: nachfragen, welche PDFs gemeint sind; `plug-n-rag inventur`
listet PDFs und Scans).

0. **Ablage (einmalig):** Meldet der Befehl „Wohin sollen Abschriften von PDFs?“, diese Frage mit
   den angezeigten Möglichkeiten stellen und dann mit `--ablage <wahl>` erneut ausführen; die Wahl
   wird gemerkt. Möglichkeiten:
   - Vault: `neben_original` (neue Notiz neben dem PDF) oder `ordner` (eigener Ordner „Abschriften/“,
     gleiche Unterordner wie die PDFs).
   - Sammlung: `ordner` (lesbare Dateien in `.plug-n-rag/abschriften/`; wandern mit dem Index, eine
     Kopie des Ordners braucht kein erneutes Abschreiben) oder `intern` (nur für die Suche).
   Gibt es gleichzeitig Scans, beide Fragen (Ablage und Abschreiben) in einer Nachricht stellen.
1. `plug-n-rag aufnehmen "<datei>"` ausführen. Der Befehl liest die Textebene, nutzt lokale
   Texterkennung (falls Tesseract installiert ist) und prüft die Qualität. Seiten mit Textebene
   werden sofort übernommen.
2. Meldet er `FRAGE AN NUTZER:IN`: diese Frage sinngemäß stellen, mit Seitenzahl und Alternative:

   > 23 Seiten sind eingescannt. Soll Claude sie vollständig lesen und abschreiben? Alternativ
   > erkenne ich den Text nur lokal, das ist aber ungenauer.

   Erkläre in einem Satz: Beim Abschreiben gehen diese Seiten vollständig an Anthropic. Die
   Antwort gilt nur für diesen Auftrag. Eine dauerhafte Einstellung
   (`plug-n-rag konfig --setzen transcription=allow|local_only`) nur, wenn die Nutzer:in das
   ausdrücklich will. Steht `transcription: allow` oder `local_only` schon in der Konfiguration,
   nicht erneut fragen.
3. **Lokal**: `plug-n-rag aufnehmen "<datei>" --transkription lokal`. Fehlt Tesseract, anbieten,
   es nach Zustimmung zu installieren (macOS `brew install tesseract tesseract-lang`,
   Debian/Ubuntu `sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng`, Windows über
   den UB-Mannheim-Installer anleiten, dort „German“ und „English“ anhaken). plug-n-rag nutzt die
   installierten Sprachpakete Deutsch und Englisch; meldet die Ausgabe ein fehlendes Paket, anbieten,
   es nachzuinstallieren.
4. **Abschreiben erlaubt**: `plug-n-rag aufnehmen "<datei>" --transkription erlaubt`. Die Ausgabe
   enthält einen JSON-Plan mit `batches` (Listen von Seitenbildern, je höchstens 20) und
   `pages_dir`. Rufe für **jedes Bündel** den Subagenten `transkription` auf (Agent-Werkzeug,
   `subagent_type: "plug-n-rag:transkription"`) mit der Bildliste und `pages_dir`. Die Seitenbilder
   gelangen so nie in diesen Kontext. Ein Aufruf bleibt unter 100.000 Tokens.
   - Meldet der Subagent Handschrift, komplexe Tabellen oder Unsicherheiten, frage, ob diese
     Seiten mit Sonnet nachgearbeitet werden sollen (etwa 1 Cent pro Seite statt 0,06 Cent).
     Wenn ja, rufe denselben Subagenten mit `model: "sonnet"` nur für diese Seiten auf.
5. Abschließen: `plug-n-rag aufnehmen "<datei>" --abschliessen haiku` (bzw. `sonnet`).
   - Vault-Modus: Es entsteht eine **neue** Notiz neben dem PDF mit Frontmatter `quelle:` und
     `transkription:`. Bestehende Notizen werden nie verändert.
   - Sammlungs-Modus: Die Sammlung bleibt unverändert. Der Text liegt je nach Wahl als lesbare
     Abschrift in `.plug-n-rag/abschriften/` oder nur intern für die Suche.
6. `plug-n-rag sync` und kurz berichten: Seiten, Methode, unleserliche Stellen.

Kosten grob (Stand November 2026, vor dem Nennen aktuelle Preise prüfen): Haiku etwa 0,06 Cent
pro Seite, Sonnet etwa 1 Cent pro Seite. Mit Claude-Abo wird das Nutzungskontingent belastet.
