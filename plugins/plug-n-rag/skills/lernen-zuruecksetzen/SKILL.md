---
name: lernen-zuruecksetzen
disable-model-invocation: true
description: Setzt die gelernten Werte der Token-Steuerung von plug-n-rag auf die Startwerte zurück oder zeigt sie an. Verwenden, wenn die Suche dauerhaft zu viel oder zu wenig liefert oder die Nutzer:in neu anfangen möchte.
allowed-tools: Bash(plug-n-rag lernen*)
---

1. `plug-n-rag lernen` zeigt die aktuellen Werte je Zweck (frage, recherche, erstellen) und ob sie
   gelernt, Startwert oder eigene Vorgabe sind.
2. Erkläre kurz: plug-n-rag merkt sich, wie tief gelesen wird, und passt an, wie viele Notizen eine
   Suche liefert. Es speichert dafür nur Pfade und Zählwerte, keine Suchanfragen.
3. Frage, ob auch eigene Vorgaben (z. B. „zu oberflächlich“) gelöscht werden sollen.
4. Zurücksetzen: `plug-n-rag lernen --zuruecksetzen` (mit `--vorgaben-behalten`, wenn eigene
   Vorgaben bleiben sollen). Ergebnis in einem Satz bestätigen.
