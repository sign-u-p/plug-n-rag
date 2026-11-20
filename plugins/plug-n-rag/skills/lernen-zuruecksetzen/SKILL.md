---
name: lernen-zuruecksetzen
disable-model-invocation: true
description: Setzt die gelernten Werte der Token-Steuerung von plug-n-rag auf die Startwerte zurück oder zeigt sie an. Verwenden, wenn die Suche dauerhaft zu viel oder zu wenig liefert oder die Nutzer:in neu anfangen möchte. English: resets or shows plug-n-rag's learned search depth (/plug-n-rag:reset-learning).
allowed-tools: Bash(plug-n-rag lernen*) Bash(plug-n-rag learn*)
---

> **Sprache / language:** Antworte in der Sprache, in der die Nutzer:in schreibt; auf Deutsch
> gendergerecht mit Doppelpunkt. If the user writes in English, answer in English. Alle Befehle
> gibt es auch englisch (`search`, `read`, `outline`, `--purpose question`, …); die festen Texte
> von plug-n-rag folgen der Sprache der Vault (`language` in der Konfiguration).
>
> **Werkzeug / tool:** `plug-n-rag` immer mit dem **Bash**-Werkzeug ausführen, nie mit PowerShell
> (unter Windows kennt PowerShell den Befehl nicht). Always run `plug-n-rag` with the Bash tool.

1. `plug-n-rag lernen` zeigt die aktuellen Werte je Zweck (frage, recherche, erstellen) und ob sie
   gelernt, Startwert oder eigene Vorgabe sind.
2. Erkläre kurz: plug-n-rag merkt sich, wie tief gelesen wird, und passt an, wie viele Notizen eine
   Suche liefert. Es speichert dafür nur Pfade und Zählwerte, keine Suchanfragen.
3. Frage, ob auch eigene Vorgaben (z. B. „zu oberflächlich“) gelöscht werden sollen.
4. Zurücksetzen: `plug-n-rag lernen --zuruecksetzen` (mit `--vorgaben-behalten`, wenn eigene
   Vorgaben bleiben sollen). Ergebnis in einem Satz bestätigen.
