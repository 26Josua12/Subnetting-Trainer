# subnet-trainer

Subnetting-Trainer fürs Terminal – zur Vorbereitung auf die **CCNA-Prüfung**.

Der Trainer stellt dir zufällige, realistische Subnetting-Aufgaben. Antwortest du falsch,
erklärt er dir die Lösung Schritt für Schritt mit der Magic-Number-/Blockgrößen-Methode.
Deine Ergebnisse werden gespeichert, damit du siehst, wo du noch hakst – und gezielt genau
das üben kannst.

**Inhalt**

1. [Installation](#1-installation)
2. [Schnellstart](#2-schnellstart)
3. [Die Modi](#3-die-modi)
4. [Schwierigkeit einstellen](#4-schwierigkeit-einstellen)
5. [Aufgabentypen auswählen](#5-aufgabentypen-auswählen)
6. [Antworten eingeben](#6-antworten-eingeben)
7. [Statistik und Wertung](#7-statistik-und-wertung)
8. [Alle Optionen auf einen Blick](#8-alle-optionen-auf-einen-blick)
9. [Übungsplan für die CCNA](#9-übungsplan-für-die-ccna)
10. [Problemlösung](#10-problemlösung)
11. [Für Entwickler](#11-für-entwickler)

---

## 1. Installation

Voraussetzungen: Linux oder Windows, Python 3.11 oder neuer und
[uv](https://docs.astral.sh/uv/) (alternativ pipx). Fehlt Python, lädt uv automatisch eine
passende Version herunter.

Die Anleitung für Windows steht [weiter unten](#windows).

### Linux

Wechsle in den Projektordner und installiere den Trainer als Programm:

```bash
cd ~/subnetting-trainer
uv tool install .
```

> **Wichtig:** Der Punkt am Ende gehört dazu – er steht für „das Projekt in diesem Ordner“.
> Ohne ihn meldet uv `the following required arguments were not provided: <PACKAGE>`.

Danach gibt es den Befehl `subnet-trainer` in jedem Terminal. Prüfen:

```bash
subnet-trainer --version
```

Mit pipx geht es genauso: `pipx install .`

**Aktualisieren** (nachdem sich der Code geändert hat):

```bash
cd ~/subnetting-trainer
uv tool install --reinstall .
```

Wer am Code arbeitet, installiert besser einmal mit `uv tool install --editable .` –
dann wirkt jede Änderung sofort, ohne neu zu installieren.

**Deinstallieren:**

```bash
uv tool uninstall subnet-trainer
```

Deine Statistik bleibt dabei erhalten (siehe [Abschnitt 7](#7-statistik-und-wertung)).

### Windows

Unter Windows funktionieren alle Modi genauso wie unter Linux – auch `exam` und `speed`
mit ihrem Zeitlimit.

**1. uv installieren.** In der PowerShell einen der beiden Befehle ausführen:

```powershell
winget install --id=astral-sh.uv -e
```

oder

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Danach die PowerShell schließen und neu öffnen.

**2. Projektordner auf den Rechner bringen**, z. B. mit `git clone` oder indem du den
Ordner `subnetting-trainer` kopierst.

**3. Installieren** – auch hier mit dem Punkt am Ende:

```powershell
cd C:\Users\DeinName\subnetting-trainer
uv tool install .
```

**4. Terminal neu öffnen und testen:**

```powershell
subnet-trainer --version
```

Wird der Befehl nicht gefunden: `uv tool update-shell` ausführen und das Terminal erneut
öffnen.

Aktualisieren und deinstallieren funktionieren wie unter Linux
(`uv tool install --reinstall .` bzw. `uv tool uninstall subnet-trainer`).
Alle Befehle und Optionen sind identisch, z. B. `subnet-trainer drill -l schwer`.

**Tipp:** Nimm das **Windows Terminal** (bei Windows 11 Standard, sonst kostenlos im
Microsoft Store). Dort werden Farben, Rahmen und Symbole wie ✔ ✘ ⏱ richtig dargestellt.
In der klassischen Konsole (`cmd.exe` bzw. PowerShell im alten Konsolenfenster) fehlen
diese Symbole in der Schrift – dort zeigt der Trainer automatisch einfache Ersatzzeichen
(`OK`, `X`, `Zeit` …). Siehe auch [Problemlösung](#10-problemlösung).

**Eingabe mit Zeitlimit** (`exam`, `speed`): Hier liest der Trainer die Tastatur direkt.
Backspace löscht das letzte Zeichen, Esc leert die ganze Zeile. Pfeiltasten werden
ignoriert.

---

## 2. Schnellstart

```bash
subnet-trainer
```

Das startet den Standardmodus **drill** auf Level **mittel**. Du siehst eine Aufgabe, tippst
deine Antwort ein und drückst Enter:

```text
╭─ Aufgabe 1 · Netzadresse ────────────────────────────────────────────────────╮
│ Wie lautet die Netzadresse von 172.18.24.207/21?                             │
╰───────────────────────────────────────────────────────────────────── Mittel ─╯
Netzadresse (z. B. 192.168.1.0) › 172.18.16.0
✘ Leider falsch. (9,3 s)
              Deine Antwort   Richtig
─────────────────────────────────────────
Netzadresse   172.18.16.0     172.18.24.0
╭─ So rechnest du es ──────────────────────────────────────────────────────────╮
│ 1. /21 = 8 + 8 + 5 Bits → Maske 255.255.248.0. Das interessante Oktett ist   │
│    das 3. – dort steht 248 (5 Netzbits: 128 + 64 + 32 + 16 + 8).             │
│ 2. Blockgröße (Magic Number) im 3. Oktett = 256 − 248 = 8.                   │
│ 3. Vielfache von 8 im 3. Oktett: … 8, 16, 24, 32, 40 … → 24 liegt im Block   │
│    24–31.                                                                    │
│ 4. Netzadresse: Oktette davor übernehmen (172.18), das 3. Oktett wird 24,    │
│    alle Oktette danach werden 0 → 172.18.24.0.                               │
│                                                                              │
│ Adresse  172.18.24.207  10101100.00010010.00011|000.11001111                 │
│   Maske  255.255.248.0  11111111.11111111.11111|000.00000000                 │
│    Netz    172.18.24.0  10101100.00010010.00011|000.00000000                 │
│                         Netzteil | Hostteil                                  │
╰──────────────────────────────────────────────────────────────────────────────╯

╭─ Aufgabe 2 · Gleiches Netz? ─────────────────────────────────────────────────╮
│ Liegen 192.168.240.198 und 192.168.241.102 bei der Maske 255.255.255.0 im    │
│ selben Subnetz?                                                              │
╰───────────────────────────────────────────────────────────────────── Mittel ─╯
Gleiches Subnetz? (ja oder nein) › nein
✔ Richtig! (3,1 s)
```

Im Terminal ist das farbig: Netz- und Hostteil der Binärdarstellung sind unterschiedlich
eingefärbt, Adressen und Präfixe in den Erklärungen hervorgehoben.

Während einer Aufgabe gibt es diese Sonderbefehle:

| Eingabe  | Wirkung                                                              |
|----------|----------------------------------------------------------------------|
| `?`      | Hinweis anzeigen – zählt als halber Fehler                           |
| `s`      | Aufgabe überspringen – zählt als nicht gelöst, die Lösung wird gezeigt |
| `q`      | Beenden – du bekommst eine Zusammenfassung der Session               |
| `Strg+C` | Beendet ebenfalls sauber, alles bisher Beantwortete ist gespeichert  |

---

## 3. Die Modi

Den Modus wählst du über den **Befehl** direkt hinter `subnet-trainer`.

### `drill` – üben mit Erklärungen

```bash
subnet-trainer drill
```

Der Standardmodus. Zufällige Aufgaben, nach jeder Antwort sofort richtig/falsch und bei
Fehlern die ausführliche Erklärung. Hinweise (`?`) sind erlaubt. Es geht so lange weiter,
bis du `q` eingibst – oder genau so viele Aufgaben, wie du mit `-n` angibst:

```bash
subnet-trainer drill -n 15
```

**Gut für:** Neues lernen, Methode verinnerlichen.

### `exam` – Prüfungssimulation

```bash
subnet-trainer exam
```

So läuft es ab:

1. Du bekommst **20 Fragen** mit je **60 Sekunden** Zeit. Die verbleibende Zeit steht vor
   dem Eingabefeld (`⏱ 42 s`).
2. Es gibt **keine Hinweise** und **kein Feedback** zwischendurch – wie in der echten Prüfung.
3. Ist die Zeit abgelaufen, zählt die Frage als falsch und es geht mit der nächsten weiter.
4. Am Ende siehst du eine Tabelle mit allen Fragen, deinen Antworten, den Lösungen und
   deiner Quote.
5. Danach fragt der Trainer, ob er dir die Erklärungen zu den falschen Antworten zeigen soll.

Anzahl und Zeit lassen sich anpassen:

```bash
subnet-trainer exam -n 30 --time 45 -l schwer
```

**Gut für:** realistisch testen, ob du prüfungsreif bist. Richtwert: ab 85 % sitzt es.

### `speed` – 2-Minuten-Sprint

```bash
subnet-trainer speed
```

1. Drücke Enter, um zu starten.
2. Beantworte in **2 Minuten** so viele Aufgaben richtig wie möglich. Es kommen nur die
   schnellen Typen (Netzadresse, Broadcast, Host-Bereich, Hostanzahl, Maske, Wildcard,
   Gleiches Netz).
3. Bei Fehlern wird nur kurz die richtige Lösung gezeigt, keine lange Erklärung. Hinweise
   gibt es nicht, überspringen mit `s` geht.
4. Am Ende siehst du deine Punktzahl. Pro Level wird ein **Highscore** gespeichert – aber nur
   für vollständig gespielte Runden, nicht wenn du mit `q` abbrichst.

**Gut für:** Tempo. In der Prüfung zählt jede Minute.

### `weak` – an den Schwächen arbeiten

```bash
subnet-trainer weak
```

Der Trainer schaut in deine Statistik und stellt bevorzugt Aufgaben aus den Bereichen, in
denen du am schlechtesten bist – aufgeschlüsselt nach Aufgabentyp **und** Präfixbereich
(z. B. „Netzadresse bei /19–/21“). Zu Beginn zeigt er dir, worauf er sich konzentriert:

```text
Fokus: Wildcard-Maske, Präfixe /19–/21 (21 %); Host-Bereich, Präfixe /19–/21 (32 %); …
```

- Neuere Antworten zählen mehr als alte. Wer sich verbessert, bekommt das Thema also
  seltener.
- Die Auswahl passt sich schon **während** der Session an.
- Auch Bereiche, die du noch nie geübt hast, kommen dran – sie gelten als „50 %“.

Ohne bisherige Statistik funktioniert `weak` auch, wird aber erst mit der Zeit gezielt.

**Gut für:** regelmäßiges Training, nachdem du ein paar Sessions `drill` gemacht hast.

### `ipv6` – IPv6-Grundlagen

```bash
subnet-trainer ipv6
```

Eigener Modus mit vier Aufgabenarten:

- Adresse **kürzen** (`2001:0db8:0000:0000:…` → `2001:db8::…`, nach RFC 5952)
- Adresse **ausschreiben** (alle 8 Blöcke mit je 4 Ziffern)
- **Präfix bestimmen** (`2001:db8:acad:1234::1/48` → `2001:db8:acad::/48`)
- **Subnetze zählen** („Wie viele /64 passen in ein /48?“)

Funktioniert wie `drill`, also mit Hinweisen und Erklärungen.

### `stats` – Statistik ansehen

```bash
subnet-trainer stats
```

Zeigt:

- **Überblick:** Anzahl Antworten, Gesamtquote, Ø-Antwortzeit, Sessions, Trainingstage
- **Nach Aufgabentyp:** Quote, Trend der letzten 10 Antworten (↑ ↓ →), Ø-Zeit, Hinweise
- **Nach Präfixbereich:** z. B. wie gut du bei /19–/21 bist
- **Schwachstellen:** die Bereiche mit der schlechtesten Quote
- **Letzte Sessions** und **Highscores**

```text
Nach Präfixbereich (IPv4)

  Präfixe   Antworten   Quote                  Ø Zeit
 ─────────────────────────────────────────────────────
  /16–/18          50    91 %   ███████████░   14,9 s
  /19–/21          50    44 %   █████░░░░░░░   14,0 s
  /22–/24          91    85 %   ██████████░░   14,2 s

╭────────────────────────── Schwachstellen ───────────────────────────╮
│ • Präfixe /19–/21: 44 % (50 Antworten)                              │
│ • Wildcard-Maske, Präfixe /19–/21: 21 % gewichtet (8 Antworten)     │
│ • Host-Bereich, Präfixe /19–/21: 32 % gewichtet (8 Antworten)       │
│ Tipp: 'subnet-trainer weak' übt genau diese Bereiche.               │
╰─────────────────────────────────────────────────────────────────────╯
```

### `reset` – Statistik löschen

```bash
subnet-trainer reset        # fragt vorher nach
subnet-trainer reset --yes  # ohne Rückfrage
```

Löscht alle Antworten, Sessions und Highscores. Das lässt sich nicht rückgängig machen.

---

## 4. Schwierigkeit einstellen

Die Schwierigkeit stellst du mit **`-l`** (lang: `--level`) ein. Das geht bei `drill`,
`exam`, `speed`, `weak` und `ipv6`.

```bash
subnet-trainer drill -l leicht
subnet-trainer exam  -l schwer
subnet-trainer speed -l mittel
```

| Level      | Adressen                                        | Präfixe             | Extras                          |
|------------|-------------------------------------------------|---------------------|---------------------------------|
| `leicht`   | Klasse-C-Bereich, meist 192.168.x.x             | /24 bis /30         | –                               |
| `mittel`   | alle privaten Netze (10/8, 172.16/12, 192.168/16) | /16 bis /30       | Fragen teils mit Maske statt Präfix |
| `schwer`   | privat und öffentlich                           | /8 bis /32          | /31 und /32, VLSM, Summarization |

- Standard ist `mittel`.
- Kurzformen gehen auch: `-l l`, `-l m`, `-l s`.
- Auf „schwer“ kommen auch die Sonderfälle **/31** (Punkt-zu-Punkt-Links nach RFC 3021) und
  **/32** (Host-Route) dran – jeweils mit eigener Erklärung.
- Adressen sind überwiegend private (RFC 1918), gelegentlich öffentliche – so wie in echten
  Netzen.

Bei `ipv6` bestimmt das Level, welche Präfixlängen vorkommen: „leicht“ nur /48 und /64,
„schwer“ auch krumme Präfixe wie /37, die mitten durch einen Block schneiden.

---

## 5. Aufgabentypen auswählen

Ohne weitere Angabe bekommst du einen Mix. Mit **`-t`** (lang: `--type`) übst du gezielt
einzelne Typen – bei `drill` und `exam`:

```bash
subnet-trainer drill -t wildcard                     # nur Wildcard-Masken
subnet-trainer drill -t netzadresse -t broadcast     # zwei Typen
subnet-trainer drill -t vlsm,summarization -l schwer # kommagetrennt geht auch
```

| Typ             | Worum es geht                                                           |
|-----------------|-------------------------------------------------------------------------|
| `netzadresse`   | IP + Präfix (oder Maske) → Netzadresse                                  |
| `broadcast`     | IP + Präfix → Broadcast-Adresse                                         |
| `hostbereich`   | erste und letzte nutzbare Host-Adresse                                  |
| `hostanzahl`    | Präfix → nutzbare Hosts, und umgekehrt „500 Hosts nötig“ → Präfix       |
| `maske`         | CIDR ↔ Subnetzmaske, in beide Richtungen                                |
| `wildcard`      | Wildcard-Masken, auch in ACL- und OSPF-Befehlen, und umgekehrt          |
| `gleiches-netz` | Liegen zwei IPs im selben Subnetz? (ja/nein)                            |
| `aufteilen`     | „Teile 192.168.10.0/24 in 6 gleich große Subnetze“ → Präfix + Netze     |
| `vlsm`          | mehrere LANs/WAN-Links planen, größte zuerst                            |
| `summarization` | mehrere Netze → kleinste Sammelroute                                    |

VLSM und Summarization kommen im Mix nur auf „schwer“ vor. Wählst du sie mit `-t` aus,
gibt es sie auf jedem Level – auf „leicht“ dann in einfacherer Form.

---

## 6. Antworten eingeben

Der Trainer ist bei der Eingabe tolerant. In jeder Eingabezeile steht in Klammern ein
Beispiel für das erwartete Format.

| Antwort          | So eingeben                                               |
|------------------|-----------------------------------------------------------|
| Adresse          | `192.168.1.0`                                             |
| Präfix           | `/27` oder `27` – meist geht auch die Maske `255.255.255.224` |
| Maske / Wildcard | `255.255.255.0` bzw. `0.0.0.255`                          |
| Host-Bereich     | `10.0.0.1 - 10.0.0.14` (auch `bis` oder Komma als Trenner) |
| Anzahl           | `510` (auch `16.777.214` mit Tausenderpunkten)            |
| Ja/Nein          | `ja` / `nein` oder `j` / `n`                              |
| Netz             | `192.168.1.64/26` oder `192.168.1.64 255.255.255.192`     |
| Liste            | `10.0.0.0, 10.0.0.32, 10.0.0.64` – Reihenfolge egal       |

- Leerzeichen am Anfang und Ende sind egal.
- Eine Eingabe, die sich gar nicht lesen lässt (z. B. `foo` statt einer Adresse), zählt
  **nicht** als Fehler. Du bekommst einen Hinweis und wirst nochmal gefragt.

**Mehrteilige Aufgaben** fragen die Teile nacheinander ab:

- **Aufteilen:** erst das neue Präfix, dann die Netzadressen (bei vielen Subnetzen nur die
  ersten sechs).
- **VLSM:** pro LAN/WAN ein Feld, jeweils als `Netz/Präfix`. Vergib die Subnetze lückenlos
  ab der ersten Adresse, das größte zuerst. Gleich große Subnetze dürfen vertauscht sein.

---

## 7. Statistik und Wertung

**Wertung pro Aufgabe**

| Ergebnis                              | Punkte |
|---------------------------------------|--------|
| richtig                               | 1      |
| richtig, aber mit Hinweis             | ½      |
| falsch, übersprungen, Zeit abgelaufen | 0      |

**Was gespeichert wird:** zu jeder Antwort Zeitpunkt, Aufgabentyp, Level, Präfix, Ergebnis,
ob ein Hinweis genutzt wurde, und die Antwortzeit. Dazu jede Session und die
Speed-Highscores.

**Wo:**

- Linux: `~/.local/share/subnet-trainer/stats.json`
  (bzw. `$XDG_DATA_HOME/subnet-trainer/stats.json`, falls gesetzt)
- Windows: `%APPDATA%\subnet-trainer\stats.json`, also meist
  `C:\Users\DeinName\AppData\Roaming\subnet-trainer\stats.json`

Der genaue Pfad steht auch unten in `subnet-trainer stats`.

- Gespeichert wird **nach jeder Antwort**. Auch bei Strg+C oder einem Absturz geht nichts
  verloren.
- Ist die Datei einmal beschädigt, legt der Trainer sie als `stats.json.defekt-…` beiseite
  und fängt neu an, statt sie zu überschreiben.
- Zum Sichern einfach die Datei kopieren.

---

## 8. Alle Optionen auf einen Blick

| Option                    | drill | exam | speed | weak | ipv6 | Bedeutung                                      |
|---------------------------|:-----:|:----:|:-----:|:----:|:----:|------------------------------------------------|
| `-l`, `--level`           | ✓     | ✓    | ✓     | ✓    | ✓    | `leicht`, `mittel` (Standard), `schwer`        |
| `-t`, `--type`            | ✓     | ✓    |       |      |      | nur bestimmte Aufgabentypen                    |
| `-n`, `--count`           | ✓     | ✓    |       | ✓    | ✓    | Anzahl Aufgaben (exam: Standard 20, sonst endlos) |
| `--time`                  |       | ✓    |       |      |      | Sekunden pro Frage (Standard 60)               |
| `--seed`                  | ✓     | ✓    | ✓     | ✓    | ✓    | dieselben Aufgaben wiederholen (siehe unten)   |
| `--ohne-binaer`           | ✓     | ✓    |       | ✓    |      | Erklärungen ohne Binärdarstellung              |
| `-h`, `--help`            | ✓     | ✓    | ✓     | ✓    | ✓    | Hilfe zum Befehl                               |

Zu `reset` gibt es noch `-y`/`--yes` (ohne Rückfrage), zu `subnet-trainer` selbst `--version`.

**Seed – Aufgaben wiederholen:** Oben im Kasten jeder Session steht ein Seed, z. B.
`Seed 48213`. Mit dem gleichen Seed (und den gleichen Optionen) bekommst du exakt dieselben
Aufgaben noch einmal – praktisch, um eine verpatzte Runde zu wiederholen:

```bash
subnet-trainer drill --seed 48213
```

Die Hilfe zu jedem Befehl im Terminal:

```bash
subnet-trainer -h
subnet-trainer exam -h
```

---

## 9. Übungsplan für die CCNA

Ein Vorschlag, wie du den Trainer einsetzen kannst:

1. **Grundlagen** – ein paar Tage `subnet-trainer drill -l leicht`, bis Netzadresse,
   Broadcast und Host-Bereich zuverlässig sitzen. Lies die Erklärungen aufmerksam und nutze
   ruhig `?`.
2. **Ausbauen** – `subnet-trainer drill` (mittel), dann einzelne Themen gezielt, z. B.
   `-t wildcard` oder `-t aufteilen`.
3. **Täglich 10 Minuten** – `subnet-trainer weak`, gefolgt von einer Runde
   `subnet-trainer speed`. Schau ab und zu in `subnet-trainer stats`, ob die Schwachstellen
   kleiner werden.
4. **Fortgeschritten** – `subnet-trainer drill -l schwer -t vlsm,summarization`.
5. **Prüfungsreife testen** – `subnet-trainer exam -l schwer`. Liegst du mehrmals bei
   85 % oder mehr, bist du gut vorbereitet.
6. **IPv6 nicht vergessen** – zwischendurch `subnet-trainer ipv6`.

---

## 10. Problemlösung

**`uv tool install` meldet `required arguments were not provided: <PACKAGE>`**
Der Punkt fehlt: `uv tool install .` (im Projektordner) oder den Pfad angeben:
`uv tool install ~/subnetting-trainer`.

**`subnet-trainer: command not found`**
Das Installationsverzeichnis `~/.local/bin` fehlt im `PATH`. Einmal ausführen und das
Terminal neu öffnen:

```bash
uv tool update-shell
```

**Ich habe den Code geändert, aber der Befehl verhält sich wie vorher.**
Neu installieren: `uv tool install --reinstall .` – oder einmalig mit `--editable`
installieren (siehe [Installation](#1-installation)).

**Die Ausgabe hat keine Farben / soll keine Farben haben.**
Farben gibt es nur in einem echten Terminal. Um sie abzuschalten:
`NO_COLOR=1 subnet-trainer` (Linux) bzw. in der PowerShell erst `$env:NO_COLOR=1`, dann
`subnet-trainer`.

**Die Tabellen sehen zerschossen aus.**
Das Terminal ist zu schmal – mindestens 80 Zeichen Breite sind ideal. Unter Windows
außerdem das Windows Terminal statt `cmd.exe` verwenden.

**Windows: Statt Symbolen erscheinen Kästchen oder Fragezeichen.**
Die Schrift des Konsolenfensters kennt die Zeichen nicht. Am besten das Windows Terminal
nutzen. Oder die einfachen Ersatzzeichen erzwingen – in der PowerShell:

```powershell
$env:SUBNET_TRAINER_EINFACH=1
subnet-trainer
```

Umgekehrt erzwingt `$env:SUBNET_TRAINER_EINFACH=0` die normalen Symbole.

**Warnung „Die Statistikdatei war beschädigt …“**
Die alte Datei liegt als `stats.json.defekt-<Datum>` im selben Ordner. Der Trainer arbeitet
mit einer leeren Statistik weiter.

**Ich will von vorne anfangen.**
`subnet-trainer reset`

---

## 11. Für Entwickler

```bash
uv sync                  # .venv mit allen Abhängigkeiten inkl. pytest und ruff
uv run subnet-trainer    # aus dem Quellcode starten
uv run pytest            # Tests
uv run ruff check .      # Linter
uv run ruff format .     # Formatierung
```

Der GitHub-Actions-Workflow in `.github/workflows/tests.yml` führt Linter und Tests bei
jedem Push auf Linux, Windows und macOS mit Python 3.11 und 3.14 aus. Die Windows-Eingabe
mit Zeitlimit wird zusätzlich auf jedem System mit einer simulierten Tastatur getestet
(`tests/test_windows.py`).

**Aufbau**

```
src/subnet_trainer/
├── core/            # reine Logik: Generierung, Prüfung, Erklärungen (keine UI, keine I/O)
│   ├── addressing.py    # Oktett-Arithmetik, realistische Zufallsadressen
│   ├── explain.py       # Magic-Number-Methode als Erklärungsbausteine
│   ├── parsing.py       # tolerante Eingabe-Parser mit deutschen Fehlermeldungen
│   └── tasks/           # ein Modul pro Aufgabentyp, gemeinsames Interface in base.py
├── stats/           # Datensätze, JSON-Speicher, Auswertung
├── session.py       # Sitzungsablauf ohne UI
├── ui/              # rich-Ausgabe, Eingabe mit Zeitlimit, die Modi
└── cli.py           # typer-Befehle
```

**Warum die Erklärungen stimmen:** Jede Aufgabe berechnet ihre Lösung mit Pythons
`ipaddress`-Modul. Unabhängig davon rechnet die Erklärung die Lösung mit der
Blockgrößen-Methode nach. Die Tests erzeugen pro Aufgabentyp und Level 1000 Zufallsaufgaben
und prüfen, dass beide Wege zum selben Ergebnis kommen.
