# plug-n-rag Anzeige

Ein optionaler Zusatz zu [plug-n-rag](../../README.md). Er zeigt dir im Chat, **was plug-n-rag
gerade tut**: welche Notizen eine Suche gefunden hat, welche Abschnitte Claude gelesen hat, ob
die Vault aktuell ist und wie viele Tokens das gezielte Lesen ungefähr gespart hat.

Die Anzeige ist bewusst unaufdringlich. Claude sieht nichts davon, sie kostet also keine Tokens.

## Was du siehst

- **Eine ruhige Zeile pro Schritt** anstelle des technischen Befehls, zum Beispiel
  „🔍 plug-n-rag · Gesucht: 3 Notizen · beste sehr passend“. Mit **Details** klappst du sie auf:
  Trefferliste mit Abschnitten, Zeilen und Relevanz (als Wort und als ●●○), Hinweise und die
  geschätzte Ersparnis. Mit Strg+O siehst du wie gewohnt den Original-Befehl.
- **Ein kurzes Wort am Arbeits-Hinweis**, solange plug-n-rag läuft („Durchsucht deine Vault“).
- **Ein schmales Band über dem Eingabefeld**, aber nur, wenn im Hintergrund indexiert wird
  (mit Fortschritt) oder etwas auf dich wartet (z. B. eingescannte PDFs). Es lässt sich
  ausblenden. Der Button „Vorschlag ins Eingabefeld“ schreibt nur einen Vorschlag hinein:
  Abschicken entscheidest du.
- **Eine Seitenleiste** mit den Reitern **Verlauf**, **Vault** und **Ersparnis**. Sie öffnet sich nur,
  wenn du sie willst: über „Seitenleiste öffnen“, „Details“ im Band oder den Befehl `/pnr`.
  Tasten: 1, 2, 3 für die Reiter, R zum Aktualisieren.

## Installation

plug-n-rag muss installiert sein (der Zusatz bringt es als Abhängigkeit mit). Dann in Claude Code:

```
/plugin install plug-n-rag-anzeige@plug-n-rag
```

oder im Terminal:

```bash
claude plugin install plug-n-rag-anzeige@plug-n-rag
```

Danach eine neue Sitzung starten oder `/reload-plugins` eingeben.

## Wo es funktioniert

| Wo | Anzeige |
| --- | --- |
| Desktop-App, Code-Tab (lokale Sitzung) | vollständig |
| Terminal, VS Code | vollständig (VS Code ohne Band) |
| Handy-App | eine ruhige Zeile unter dem jeweiligen Schritt |
| Cloud-Sitzungen (claude.ai/code) | nichts, dort schreibt plug-n-rag stattdessen eine Quellenzeile unter Antworten |

Voraussetzung: Claude Code ab Version 2.1.287 (Desktop-App ab 2.1.286). Organisationen können
solche Zusätze („Mods“) zentral sperren; plug-n-rag funktioniert dann trotzdem, nur ohne Anzeige.

## Was der Zusatz darf und tut

Er **liest und zeichnet nur**. Er verändert keine Befehle, schickt nichts ab und hat keinen
Netzzugriff. Für die Seitenleiste ruft er lokal `plug-n-rag anzeige-daten` auf (Anzahl Dateien,
wartende Scans, Ersparnis; keine Notizinhalte, keine Suchanfragen). Prüfen kannst du das selbst:
`claude plugin validate` listet alles auf, was ein Zusatz aufruft.

Abschalten: in `/plugin` deaktivieren oder deinstallieren.
