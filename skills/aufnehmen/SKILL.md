---
name: aufnehmen
description: Wandelt PDFs (auch eingescannte) mit plug-n-rag in durchsuchbaren Text um, Seite für Seite über eine Kaskade aus Textebene, lokaler Texterkennung und – nur mit Zustimmung – Transkription durch den Subagenten transkription. Verwenden, wenn neue PDFs in die Vault oder Sammlung sollen.
argument-hint: "<pdf-datei> [weitere]"
allowed-tools: Bash(plug-n-rag aufnehmen*) Bash(plug-n-rag sync*)
---

# PDFs aufnehmen

Dateien: `$ARGUMENTS` (ohne Angabe: nachfragen, welche PDFs gemeint sind; `plug-n-rag inventur`
listet PDFs und Scans).

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
   Debian/Ubuntu `sudo apt install tesseract-ocr tesseract-ocr-deu`, Windows über den
   UB-Mannheim-Installer anleiten).
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
   - Sammlungs-Modus: Der Text liegt nur im lokalen Cache, die Sammlung bleibt unverändert.
6. `plug-n-rag sync` und kurz berichten: Seiten, Methode, unleserliche Stellen.

Kosten grob (Stand November 2026, vor dem Nennen aktuelle Preise prüfen): Haiku etwa 0,06 Cent
pro Seite, Sonnet etwa 1 Cent pro Seite. Mit Claude-Abo wird das Nutzungskontingent belastet.
