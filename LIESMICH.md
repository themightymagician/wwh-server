# WWH-Server – Wortgewandter Widerstand im ewiggestrigen Hinterland

Spieleabend-Server nach dem DirectiaNet-Prinzip: Ein Python-Prozess hält den ganzen Abend, drei Oberflächen hängen daran. Es wird nur Python 3.8 oder neuer gebraucht, keine weiteren Pakete.

| Adresse | Wer | Wofür |
| --- | --- | --- |
| `/` | Mitspielende am Handy | Beitreten, schätzen, Rangfolge tippen, A/B wählen, Antworten funken, Einsatz setzen, abstimmen, Losungswort sehen |
| `/leinwand` | Beamer oder Discord-Übertragung | Startbild mit QR-Code, Zentrale, Regeln, Spielbühne, Auflösung, Enthüllung |
| `/leitung/` | Moderation (Passwort) | Cockpit mit Lösungen, Wertung, Konfiszierung, Agenten, Einsatzplan, Archiv mit Deppardy-Boards und Atlas-Sets |

## Start

```bash
python3 server.py                    # Port 8080
python3 server.py --port 9000
python3 server.py --passwort geheim  # Passwort setzen (wird gespeichert)
```

Beim ersten Start legt der Server `data/config.json` an und zeigt das Passwort für das Steuermodul einmal in der Konsole. Den Benutzernamen fragt der Browser auch ab, er ist egal.

Die Taste `f` schaltet die Leinwand in den Vollbildmodus.

## Die Geschichte

Die Ordnungsfront hat das Hinterland erobert, ihr Amt für Reinsprache vernichtet alles Fremde, Alte und Doppeldeutige. Die Mitspielenden sind die Zelle Semikolon und bergen Wörter, bevor die Große Säuberung beginnt. Jede Beute landet im eigenen Rucksack.

- **Prolog:** Über „Leinwand → Prolog“ zeigt die Leinwand den Lagebericht Tafel für Tafel, gesteuert in der Zentrale. Die Handys zeigen dazu die Einsatzkarte.
- **Einsatzbefehle:** Jede Mission hat einen Einsatzort und eine Lage, zum Beispiel das Statistische Landesamt für Schätzfragen. Die Leinwand zählt die Tage bis zur Säuberung herunter.
- **Umlagern:** Wer einen Einsatz am besten erledigt, bekommt die Frage direkt aufs Handy: aus welchem fremden Rucksack, und wohin – in den eigenen oder „zur Sicherheit“ in einen anderen fremden. Wer kein Gerät hat, wählt in der Zentrale. Jede Umlagerung und jeder Verzicht wird mitgeschrieben, die Bilanz unterscheidet „für sich selbst“ und „zur Sicherheit“.
- **Übergabe:** Am Ende führst du in der Zentrale Schritt für Schritt durch die Übergabe. Zuerst kommt die Einleitung, dann der Maulwurf (falls eingeschaltet), dann Hüterin oder Hüter des Archivs und zuletzt die Bilanz „Zur Sicherheit – oder für euch selbst?“. Die Bilanz zeigt, wie viel umgelagert wurde, wer die größte Raffhand war, wer am meisten erleichtert wurde und wer verzichtet hat, obwohl er durfte.

Alle Texte stehen im Archiv unter „Drehbuch“ und lassen sich dort umschreiben, auch Zellenname, Tage und die Anzahl der Prolog-Tafeln.

### Regeln der Zelle (Zentrale)

Damit die Schlussfrage „Zur Sicherheit – oder für euch selbst?“ auch spielerisch etwas kostet:

- **Umlagern:** 20 % des fremden Rucksacks, mindestens 3 Wörter. Die Knöpfe zeigen vorher, wie viel genommen wird und wie viel ankommt.
- **Unterwegs beschädigt:** 50 % der umgelagerten Wörter gehen verloren. Umlagern verschiebt also nicht nur, es vernichtet Beute der Zelle.
- **Verzicht:** Wer umlagern dürfte und verzichtet, bekommt 2 Wörter von der Zentrale.
- **Ziel der Zelle:** Bei der Übergabe braucht die Zelle genug Wörter für das Archiv. „Auto“ rechnet aus dem Einsatzplan aus, wie viele Wörter höchstens zu holen sind (alle Runden und Personen, Deppardy-Brett und Atlas über den Kurs, ohne Maulwurf-Anteil), und nimmt davon einen einstellbaren Anteil (Standard 50 %). „Fest“ nimmt eine eigene Zahl, „Aus“ schaltet das Ziel ab. Die Leinwand zeigt den Stand in der Zentrale. Wird das Ziel verfehlt, gibt es keinen Hüter des Archivs. Der Rucksack des Maulwurfs zählt nicht mit, sein Umlagern trifft die Zelle also doppelt.

Alle Werte lassen sich während des Abends ändern, falls das Ziel zu leicht oder zu schwer wirkt.

### Weitere Regeln im Spiel

- **Deppardy:** Der Buzzer zählt erst, wenn du ihn freigibst (Taste `B`). Wer zu früh drückt, ist 2 Sekunden gesperrt, und der Timer startet erst mit der Freigabe. Wer das nicht will, stellt im Cockpit auf „sofort scharf“.
- **Vergrößerungsglas:** Ein Treffer auf Stufe 1–2 bringt ein Wort mehr, ab Stufe 5 eins weniger (mindestens 1). Maßgeblich ist die Stufe, auf der der Funkspruch einging.
- **Abgehört – das Rauschen:** Das Band startet dumpf und verrauscht. „Rauschen reduzieren“ macht es über sechs Stufen klarer, gewertet wird wie beim Vergrößerungsglas. Das funktioniert mit Dateien, die über das Archiv hochgeladen wurden. MP3-Adressen von fremden Seiten und YouTube-Links laufen ohne Rauschen, weil der Browser deren Ton nicht bearbeiten darf.
- **Mehr oder weniger – die Propagandaabteilung:** Aus jedem Paar baut der Server eine Behauptung des Amtes, zufällig wahr oder falsch („Das Amt verkündet: Kölner Dom!“). Die Zellen entscheiden: Wahrheit oder Propaganda. Die vorhandenen Inhalte bleiben unverändert nutzbar.
- **Rangordnung – die Registratur:** Die Begriffe liegen als umgekippte Karteikarten auf der Leinwand. Auf dem Handy sortiert die Zelle sie durch Ziehen. Die schnellste richtige Zelle bekommt ein Wort extra.
- **Das Wörterbuch des Amtes:** Ein altes Wort erscheint. Alle erfinden im Handy eine Bedeutung. Trifft jemand die echte, drückst du „Treffer“ – das gibt sofort Wörter, und der Vorschlag kommt nicht in die Abstimmung. Unpassendes lässt sich „streichen“. Danach „Abstimmung starten“: Die Leinwand zeigt alle Fälschungen und die echte Bedeutung gemischt. Wer die echte wählt, bekommt die Wörter der Mission (Standard 2). Wer mit seiner Fälschung andere täuscht, bekommt 1 Wort pro getäuschter Person. Die Wörter pflegst du im Archiv – je unbekannter, desto besser. Mitgeliefert sind 20.
- **Die Schwärzung:** Ein Text erscheint mit schwarzem Balken, alle tippen das fehlende Wort. Jede richtige Antwort zählt. Im Archiv setzt du das geschwärzte Wort in doppelte eckige Klammern: `Die Gedanken sind [[frei]]`. Mitgeliefert sind 13 gemeinfreie Texte, Sprichwörter und Grundgesetz-Artikel. Die Karte zeigt ein thematisches Beutewort, zum Beispiel „Gedankenfreiheit“.

Die beiden neuen Spiele stehen im Einsatzplan unter „Mission anhängen“. Sie haben eigene Einsatzorte im Drehbuch: die Wörterbuchredaktion und die Zensurbehörde.
- **Einsatz:** Höchsteinsatz ist immer der aktuelle Rucksack – Gewinne und Verluste aus früheren Runden derselben Mission zählen mit. Wer leer ist, darf 2 setzen und verliert dabei nichts.
- **Zellenmodus** (Einsatzplan, bei Rangordnung, Mehr oder weniger und Atlas): *Sprecher* – alle sehen die Vorschläge der eigenen Zelle live, eine Person schickt ab. *Abstimmung* – jede Stimme zählt gleich, die Mehrheit gilt (bei der Rangordnung nach Plätzen verrechnet). *Zuversicht* – jede Person stellt per Schieberegler ein, wie sicher sie ist; sichere Stimmen wiegen mehr. Andere Zellen sehen nichts davon.
- **Zeittakt** (Einsatzplan, bei Bilderschrift und Schwärzung): Wer im ersten Takt (z. B. 10 s) richtig liegt, birgt alle Wörter, danach je Takt die Hälfte, mindestens 1. Leinwand und Handys zeigen den laufenden Wert.
- **Bildarchiv:** Das Bild liegt hinter einem Schlüsselloch und öffnet sich beim Aufdecken (abschaltbar in der Zentrale).
- **Abgehört – Störgeräusche:** Im Cockpit gibt es Regler für Dumpf, Rauschen, Knistern, Brummen, Pfeifen, Verzerrung, Aussetzer und Leiern. Sie gelten für Stufe 1 und nehmen mit jeder Stufe ab. Rauschen, Knistern, Brummen, Pfeifen und Leiern liegen auch über fremden mp3-Adressen.
- **Beispiel vor jedem Einsatz:** Bei der Einweisung zeigen Leinwand und Handys ein animiertes Handy, das den Spielablauf vorführt (abschaltbar).
- **Echte Namen:** In der Zentrale lässt sich einschalten, dass die Leinwand neben jedem Decknamen den echten Namen zeigt.
- **Klang:** Unter „Archiv → Klang“ lassen sich Hintergrundmusik (Dauerschleife, optional eigene Spielmusik) und Signaltöne für Einsatzbefehl, Aufdecken, Treffer, Missionsende, Umlagern, Übergabe, Ziel erreicht/verfehlt, Maulwurf u. a. hochladen. Ohne eigene Datei erklingt ein eingebauter Ton. Beim Abhören schweigt die Musik.
- **Leinwand ohne Scrollen:** Emojis, Titel und Karten werden einzeilig eingepasst, und der ganze Inhalt verkleinert sich, statt zu scrollen. Die Beutekarte bekommt eine eigene Spalte und verdeckt keine Antworten oder Punkte mehr. Hat in einer Runde niemand Wörter bekommen, erscheint sie ausgegraut als „Nicht geborgen“ und zählt bei der Übergabe nicht als gerettet.
- **Flaggen:** Eine mitgelieferte Flaggen-Schrift (Twemoji, CC BY 4.0) sorgt dafür, dass Flaggen-Emojis auch unter Windows als Flagge statt als „FR“ erscheinen.
- **Funksprüche:** Das Cockpit markiert Antworten mit einem roten Punkt, die nach der Lösung aussehen. Groß- und Kleinschreibung, Umlaute, Artikel und kleine Tippfehler werden dabei ignoriert. Entscheiden musst du trotzdem selbst.
- **Rangordnung:** Die Begriffe sind auf dem Handy echte Karteikarten zum Ziehen, Buchstabencodes gibt es nicht mehr. Das Cockpit zeigt bei falschen Antworten, wie viele Begriffe am richtigen Platz stehen, und kann die Reihenfolge einer Zelle mit ↑/↓ setzen.
- **Beutewörter und Karteikarten:** Jeder Inhalt kann ein Beutewort haben – in allen Minispielen, bei jedem Atlas-Begriff und bei jedem Deppardy-Feld. Beim Aufdecken schiebt sich auf der Leinwand eine Karteikarte ins Bild: Stichwort mit Artikel, Bedeutung, Herkunft, Fundort, Aktenzeichen und ein Stempel des Amtes, warum das Wort verboten ist („Fremd“, „Veraltet“, „Doppeldeutig“ …). Die Handys zeigen dieselbe Karte. Bei Deppardy gilt ein Wort als geborgen, sobald die Antwort gezeigt wird. Am Ende der Übergabe liegen alle Karten des Abends als „Das habt ihr gerettet“ auf dem Tisch.
- **Beutekartei im Archiv:** Unter „Archiv → Beutekartei“ stehen alle Beutewörter mit ihrer Karte. Wörter ohne Karte sind rot markiert. Mitgeliefert sind Karten für 281 Wörter.
- **Funksprüche nach dem Einsatz:** Nach jeder Mission meldet sich die Zentrale mit einem Satz aus dem Drehbuch („Das Statistische Landesamt brennt …“).
- **Countdown:** Er läuft in Tagen und Stunden, damit er mit jedem Einsatz sichtbar sinkt.
- **Reihenfolge der Inhalte:** Jedes Spiel merkt sich, welcher Eintrag als Nächstes kommt – auch über einen Abend hinaus, damit beim zweiten Abend neue Fragen kommen. Das Archiv zeigt pro Spiel „Als Nächstes kommt Eintrag … von …“ und hat einen Knopf „Wieder von vorn“. Unter „System“ gibt es denselben Knopf für alle Spiele zusammen. Wer vorher mit Testrunden probiert hat, sollte vor dem echten Abend zurücksetzen.
- **Schattenmotive der Prolog-Tafeln:** Jede Tafel bekommt ein Schattenmotiv: Licht durch eine Jalousie, Aktenstapel mit Verbotsstempel, Uhr vor zwölf über Feuerschein, ein riesiges Semikolon, ein Rucksack oder eine Gestalt im Türlicht. Das Motiv wird über den Titel erkannt („Lagebericht“, „Amt“, „Frist“ …) oder im Drehbuch pro Tafel ausgewählt.
- **Einsatzbefehl als Akte:** In der Zentrale und bei der Einweisung liegt der Einsatzbefehl als Akte in der Mitte. Funksprüche, Vermerke und das Umlagern hängen als Zettel links daneben, der Stand fürs Archiv steht als Säule rechts. Die Rucksäcke laufen als Leiste unten durch, bei Zelleneinsätzen stattdessen die Zellen.
- **Prolog-Tafel zum Maulwurf:** Im Drehbuch lässt sich jede Tafel auf „nur mit Maulwurf“ stellen. Mitgeliefert ist „Ein Verdacht“, die nur erscheint, wenn der Maulwurf eingeschaltet ist.

### Maulwurf (Schalter in der Zentrale)

Eingeschaltet bekommt eine zufällige Person heimlich die Rolle Maulwurf. Jedes Handy zeigt eine verdeckte Rollenkarte im gleichen Format, damit niemand am Bildschirm des Nachbarn etwas erkennt. Die Moderation sieht den Namen nur nach Klick auf „Anzeigen“.

Die Abstimmung „Wer ist der Maulwurf?“ lässt sich jederzeit öffnen, in der Mission „Die Parole“ gibt es dafür einen eigenen Knopf. Es zählt die letzte Stimme jeder Person, die Stimme des Maulwurfs selbst zählt nicht. Aufgelöst wird bei der Übergabe:

- **Enttarnt** (der Maulwurf hat allein die meisten Stimmen): Sein Rucksack wird gleichmäßig auf alle anderen verteilt.
- **Entkommen:** Das Amt für Reinsprache zahlt ihm eine Prämie aus eigener Kasse, einstellbar in der Zentrale (Standard 5 Wörter). Kein Rucksack der Zelle wird dafür angerührt. Ein enttarnter oder entkommener Maulwurf kann nicht Hüter des Archivs werden.

„Abend neu starten“ setzt auch den Maulwurf zurück, beim ersten Einsatz wird dann neu gelost.

## Ablauf eines Abends

1. Steuermodul öffnen, oben rechts „Leinwand öffnen“ und dieses Fenster auf den Beamer ziehen oder in Discord teilen.
2. Die Leinwand zeigt den QR-Code. Alle scannen ihn und tragen ihren Namen ein, der Deckname kommt von der Zentrale.
3. Wer kein Handy hat, wird unter „Agenten“ angelegt. Für diese Person trägt die Moderation im Cockpit ein.
4. Optional „Leinwand → Prolog“ und den Lagebericht durchklicken, bei Bedarf den Maulwurf einschalten. Dann „Zentrale“ → „Einsatz starten“. Leinwand und Geräte zeigen die Regeln, bei Zellen-Missionen auch die Zelle.
5. „Einsatz beginnen“. Im Cockpit steht links die Lösung mit den Steuertasten, rechts die Wertung.
6. „Aufdecken“, Punkte vergeben, „Nächste Runde“. Nach der letzten Runde „Mission abschließen“.
7. Nach jeder Mission darf der Sieger Wörter umlagern. Die Auswahl erfolgt in der Zentrale.
8. Am Ende „Übergabe auf der Leinwand beginnen“ und die Stufen durchklicken.

Nachzügler können jederzeit beitreten. Läuft gerade eine Zellen-Mission, kommen sie in die kleinste Zelle. Der Beitritt lässt sich unter „Agenten“ sperren. Wer das Gerät wechselt oder den Browser leert, bekommt dort per „Geräte-Link kopieren“ seinen persönlichen Link.

## Was auf welchem Gerät passiert

| Spiel | Gerät | Cockpit |
| --- | --- | --- |
| Schätzfragen | Zahl eintippen | Nächste Schätzung wird markiert, ein Klick vergibt die Wörter |
| Rangordnung | Karteikarten ziehen oder mit Pfeilen sortieren, für die Zelle abschicken | Erkennt richtige Zellen selbst, Tempo-Bonus für die schnellste |
| Die Parole | Parole verdeckt (antippen zum Aufdecken), später Abstimmung | Zeigt den Eindringling und die Stimmen, „erkannt“ oder „nicht erkannt“ |
| Vergrößerungsglas, Abgehört, Bilderschrift | Antworten funken, höchstens 6 pro Runde | Funksprüche nach Zeit sortiert, ✓ vergibt die Wörter |
| Mehr oder weniger | „Wahrheit“ oder „Propaganda“ für die Zelle | Zeigt, was das Amt behauptet und ob es stimmt |
| Einsatz | Erst Einsatz setzen, dann antworten | Pro Person „Richtig“ oder „Falsch“, der Einsatz wird verrechnet |
| Das Wörterbuch des Amtes | Bedeutung erfinden, dann für die echte abstimmen | Fälschungen mit ● für „trifft die echte“, Knöpfe „Treffer“ und „streichen“, dann „Abstimmung starten“ |
| Die Schwärzung | Das geschwärzte Wort tippen | Antworten mit ●, „Alle ● als richtig werten“ oder einzeln ✓/✗ |
| Deppardy | Buzzer, danach Platz in der Reihe oder „gesperrt“ | Brett zum Anklicken, Frage → Tipp → Antwort, Timer, Buzzer-Reihe mit ✓/✗, Risiko-Felder ×2 |
| Atlas | Land auf der Weltkarte antippen (Zelle oder einzeln) | Tipps mit Punkte-Vorschau, beim Aufdecken wird automatisch gewertet |

Lösungen, Parolen und der Eindringling verlassen den Server erst beim Aufdecken. Auf der Leinwand und den Geräten ist vorher auch mit Entwicklertools nichts zu finden.

### Deppardy

Die Leinwand zeigt das Brett, im Cockpit klickst du ein Feld an. Die Frage erscheint auf der Leinwand und kurz gefasst auf den Handys, dazu läuft der Timer. Wer buzzert, landet in der Reihe; der Erste ist grün markiert. ✓ gibt die Punkte des Feldes, ✗ zieht sie ab und sperrt diese Person oder Zelle für die Frage, dann ist der Nächste dran.

Tastatur im Cockpit, sobald ein Feld offen ist: `Leertaste` weiter (Tipp, Antwort, Feld schließen), `T` Timer, `R` richtig und `F` falsch für den Ersten in der Reihe, `Esc` schließen.

Die Leinwand spielt die Töne aus dem Deppardy-Original. Dafür einmal unten rechts auf „Ton freigeben“ klicken.

Boards pflegst du unter „Archiv → Deppardy“. Exportierte Boards aus dem eigenständigen Deppardy (.json, alte und neue Version) lassen sich dort importieren. Eingebettete Bilder und Töne legt der Server dabei als Dateien in `data/media/` ab. Welches Board eine Mission spielt, steht im Einsatzplan.

### Atlas

Jede Runde zeigt einen Begriff. Die Handys zeigen eine Weltkarte zum Antippen und Zoomen; bei Zellen gilt der letzte Tipp aus der Zelle. Beim Aufdecken rechnet der Server die Punkte wie das ursprüngliche Atlas: 100 für einen Volltreffer, danach weniger mit der Entfernung, mindestens 55 für ein Nachbarland. Die Leinwand zeigt alle Tipps auf der Karte.

Sets pflegst du unter „Archiv → Atlas“, das Set einer Mission wählst du im Einsatzplan, sonst werden alle gemischt. Die Rundenzahl steht ebenfalls im Einsatzplan.

Bei beiden Spielen steht der Umrechnungskurs im Einsatzplan (Feld „Punkte / Wort“). Standard: Deppardy 500 Punkte = 1 Wort, Atlas 50 Punkte = 1 Wort. So bringt Deppardy höchstens rund 24 Wörter und entscheidet den Abend nicht allein.

## Inhalte für den Hinterland-Abend

Mitgeliefert und jederzeit über das Archiv wiederherstellbar:

- **Deppardy im Hinterland** mit sechs Kategorien zu je fünf Feldern: Amtsdeutsch, Omas Wortschatz, Spießerkunde, Scheinanglizismen, Schmuggelware (Lehnwörter) und Stilmittel des Widerstands. Die 500er-Felder sind Risiko-Felder.
- **Atlas „Hinterland-Inventar“** (26 Begriffe): Was im deutschen Vorgarten steht und doch von weit her kommt – Geranie, Thuja, Kartoffel, Wellensittich, dazu ein paar tatsächlich urdeutsche Fallen wie Gartenzwerg und Schrebergarten.
- **Atlas „Im Exil“** (22 Stimmen): Aus welchem Land mussten diese Dichterinnen und Dichter fort – von Ovid bis Herta Müller.
- Die drei ursprünglichen Atlas-Sets (Nationalgerichte, Wanderwörter, Dichtung).

## Ohne Internet

D3, TopoJSON, die Weltkarte für Atlas und der QR-Code-Generator liegen im Paket. Offen bleiben nur zwei Dinge:

- **Schriften.** Anton und IBM Plex kommen von Google Fonts. Ohne Internet zeigen die Seiten Ersatzschriften, die breiter laufen.
- **Beispielbilder.** Die Bilder für das Vergrößerungsglas liegen auf Wikimedia. Für den Offline-Betrieb im Archiv per Datei hochladen, dann liegen sie in `data/media/`.

Audio für „Abgehört“ ebenfalls hochladen. Die Leinwand spielt es ab, gesteuert über „Abspielen / Pause / Von vorn“ im Cockpit. Beim ersten Ton fragt die Leinwand einmal nach Freigabe, das ist eine Browser-Regel.

## Online spielen (Discord)

Spielen alle am selben Ort, reicht das WLAN: Der Server ermittelt seine Adresse selbst und zeigt sie als QR-Code. Sitzen die Mitspielenden zu Hause, muss der Server von außen erreichbar sein, etwa so:

```bash
cloudflared tunnel --url http://localhost:8080
```

Die ausgegebene `https://…trycloudflare.com`-Adresse unter „System → Beitritts-Adresse“ eintragen, dann zeigt die Leinwand den richtigen QR-Code. Das Steuermodul ist auch über den Tunnel nur mit Passwort erreichbar.

## Dauerbetrieb auf dem Futro

```bash
sudo mkdir -p /opt/wwh && sudo cp -r server.py web vorlagen LIESMICH.md /opt/wwh/
sudo useradd --system --home /opt/wwh wwh && sudo chown -R wwh: /opt/wwh
sudo cp wwh-quiz.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now wwh-quiz
journalctl -u wwh-quiz -n 20      # Passwort beim ersten Start
```

Soll parallel eine Test-Instanz laufen, die Service-Datei kopieren, Port und `WorkingDirectory` ändern.

## Daten

| Datei | Inhalt |
| --- | --- |
| `data/state.json` | Kompletter Spielstand inkl. Archiv, Deppardy-Boards, Atlas-Sets und Plan, nach jeder Aktion gespeichert |
| `vorlagen/` | Mitgelieferte Inhalte (Drehbuch, Hinterland-Board, Atlas-Sets, Beutekartei), Grundlage für „wiederherstellen“ |
| `data/config.json` | Passwort und Beitritts-Adresse |
| `data/media/` | Hochgeladene Bilder und Audio |

„System → Exportieren“ lädt den Spielstand als JSON herunter, „Importieren“ spielt ihn wieder ein. Vor jedem Import legt der Server eine Sicherung `data/state.json.vor-import-…` an, und Dateien mit fehlenden oder falschen Kernfeldern werden abgelehnt. Ein Neustart des Servers mitten im Abend verliert nichts, die Geräte verbinden sich selbst neu.

## Tests

```bash
python3 -m unittest discover tests
```

Die Tests brauchen nur die Standardbibliothek und prüfen die Spiellogik ohne laufenden Server: Umlagern (auch in fremde Rucksäcke, am Gerät), Einsatz-Limit, Beutestatus, Zellenmodi, Zeittakt, Auto-Ziel, Maulwurf-Prämie, Deppardy-Freigabe und -Kurs, Pfadnormalisierung, Decknamen und das Laden alter Spielstände.
