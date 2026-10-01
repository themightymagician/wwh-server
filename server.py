#!/usr/bin/env python3
"""
WWH-Server — Wortgewandter Widerstand im ewiggestrigen Hinterland
==================================================================

Spieleabend-Server nach dem DirectiaNet-Prinzip: ein Python-Prozess (nur
Standardbibliothek) hält den gesamten Spielstand. Drei Oberflächen hängen daran:

  /             Agenten-Gerät   Handy der Mitspielenden: beitreten, antworten,
                                Losungswort sehen, abstimmen, Einsatz setzen
  /leinwand     Leinwand        Beamer oder Bildschirmübertragung (Discord)
  /leitung/     Steuermodul     passwortgeschützt, steuert den ganzen Abend;
                                dort liegen auch Deppardy und Atlas

Antworten, Losungswörter und der Spitzel verlassen den Server erst, wenn sie
aufgedeckt sind. Wer die Leinwand im Browser untersucht, findet dort nichts.

Start:   python3 server.py                (Port 8080)
         python3 server.py --port 9000
Passwort und Beitritts-Adresse stehen in data/config.json (wird beim ersten
Start angelegt, das Passwort erscheint einmal in der Konsole).
"""

import argparse
import base64
import copy
import hmac
import json
import math
import gzip
import mimetypes
import posixpath
import os
import random
import re
import secrets
import socket
import string
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

mimetypes.add_type("font/woff2", ".woff2")      # Flaggen-Schrift; fehlt in manchen Systemtabellen
BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
DATA = os.path.join(BASE, "data")
MEDIA = os.path.join(DATA, "media")
KV = os.path.join(DATA, "kv")
STATE_FILE = os.path.join(DATA, "state.json")
CONFIG_FILE = os.path.join(DATA, "config.json")
VORLAGEN = os.path.join(BASE, "vorlagen")


def vorlage(name, default):
    try:
        with open(os.path.join(VORLAGEN, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# Länder-Tabelle für Atlas: Schwerpunkt, Nachbarn, deutscher Name (vorberechnet aus world-atlas 110m)
with open(os.path.join(WEB, "geo.json"), encoding="utf-8") as _f:
    GEO = json.load(_f)

MAX_BODY = 25 * 1024 * 1024       # Uploads (Bilder, Audio) und Import bis 25 MB
MAX_PUBLIC_BODY = 16 * 1024        # Beitritt und Antworten der Geräte
LONGPOLL_S = 25

# ---------------------------------------------------------------------------
# Spielkatalog
# ---------------------------------------------------------------------------

CODES = ["Konjunktiv", "Semikolon", "Umlaut", "Apostroph", "Genitiv", "Ellipse",
         "Oxymoron", "Alliteration", "Plusquamperfekt", "Diphthong", "Palindrom",
         "Metapher", "Futur II", "Tilde", "Gedankenstrich", "Versalie", "Ligatur",
         "Eszett", "Anakoluth", "Hyperbel", "Imperativ", "Akkusativ"]

GAMES = {
    "schaetzen": {"name": "Schätzfragen", "mode": "solo", "pts": 3, "rounds": 5, "min": 2, "rules": [
        "Die Frage erscheint auf der Leinwand. Alle tippen ihre Schätzung ins Gerät.",
        "Die Moderation schließt die Abgabe und deckt auf.",
        "Wer am nächsten dran ist, birgt die Wörter."]},
    "ranking": {"name": "Rangordnung", "mode": "team", "pts": 3, "rounds": 4, "min": 3, "rules": [
        "Der Karteikasten ist umgekippt – vier bis fünf Karten, wild durcheinander.",
        "Jede Zelle sortiert die Karten im Gerät durch Ziehen und schickt die Reihenfolge ab.",
        "Alles richtig: volle Beute. Die schnellste richtige Zelle birgt ein Wort extra."]},
    "impostor": {"name": "Die Parole", "mode": "solo", "pts": 3, "rounds": 2, "min": 8, "rules": [
        "Eine Übung der Zentrale: Alle sehen im Gerät die Parole – bis auf eine Person, den Eindringling. Er kennt nur die Kategorie.",
        "Reihum nennt jede Person ein einziges Wort dazu. Zwei Umläufe.",
        "Dann Abstimmung im Gerät. Eindringling erkannt: Alle anderen bergen Wörter. Sonst birgt der Eindringling doppelt."]},
    "zoom": {"name": "Vergrößerungsglas", "mode": "solo", "pts": 2, "rounds": 3, "min": 2, "rules": [
        "Ein beschlagnahmtes Bild – extrem vergrößert.",
        "Stufe für Stufe zoomt die Moderation heraus.",
        "Die erste richtige Antwort im Gerät gewinnt. Wer früh richtig liegt, birgt mehr."]},
    "sound": {"name": "Abgehört", "mode": "solo", "pts": 2, "rounds": 5, "min": 2, "rules": [
        "Ein halb zerstörtes Tonband läuft über die Leinwand – dumpf und verrauscht.",
        "Stufe für Stufe dreht die Moderation das Rauschen herunter.",
        "Titel oder Quelle ins Gerät. Wer früh richtig liegt, birgt mehr."]},
    "hoeher": {"name": "Mehr oder weniger", "mode": "team", "pts": 2, "rounds": 5, "min": 1.5, "rules": [
        "Das Amt verkündet, welches von zwei Dingen größer, höher oder schneller ist.",
        "Jede Zelle entscheidet im Gerät: Wahrheit oder Propaganda?",
        "Richtig durchschaut: Wörter für die ganze Zelle."]},
    "emoji": {"name": "Bilderschrift", "mode": "solo", "pts": 2, "rounds": 7, "min": 1.5, "rules": [
        "Eine verschlüsselte Botschaft aus Emojis.",
        "Wer sie zuerst im Gerät knackt, birgt die Wörter."]},
    "wette": {"name": "Einsatz", "mode": "solo", "pts": 0, "rounds": 3, "min": 4, "rules": [
        "Zuerst wird nur die Kategorie verraten.",
        "Jede Person setzt im Gerät einen Teil ihres Rucksacks. Wer nichts hat, darf trotzdem 2 setzen und verliert dabei nichts.",
        "Dann die Frage. Richtig: Einsatz gewonnen. Falsch: Einsatz verloren."]},
    "woerterbuch": {"name": "Das Wörterbuch des Amtes", "mode": "solo", "pts": 2, "rounds": 4, "min": 4, "rules": [
        "Das Amt hat ein altes Wort beschlagnahmt. Alle erfinden im Gerät eine Bedeutung, die echt klingt.",
        "Dann stehen alle Fälschungen und die echte Bedeutung gemischt auf der Leinwand. Abgestimmt wird im Gerät.",
        "Wer die echte findet, birgt Wörter. Wer andere mit seiner Fälschung täuscht, bekommt pro getäuschter Person ein Wort."]},
    "schwaerzung": {"name": "Die Schwärzung", "mode": "solo", "pts": 2, "rounds": 5, "min": 1.5, "rules": [
        "Das Amt hat in Gedichten, Liedern und Gesetzen ein Wort geschwärzt.",
        "Alle tippen gleichzeitig ins Gerät, was unter dem Balken stand.",
        "Jede richtige Antwort birgt Wörter – nicht nur die schnellste."]},
    "deppardy": {"name": "Deppardy", "mode": "solo", "pts": 500, "rounds": 1, "min": 30, "board": True, "kurs": True, "rules": [
        "Das große Fragebrett auf der Leinwand. Die Moderation deckt Feld für Feld auf und liest vor.",
        "Erst wenn die Moderation den Buzzer freigibt, zählt er. Wer zu früh drückt, ist kurz gesperrt.",
        "Richtig bringt die Punkte des Feldes, falsch kostet sie. Risiko-Felder zählen doppelt."]},
    "atlas": {"name": "Atlas", "mode": "team", "pts": 50, "rounds": 8, "min": 1.5, "kurs": True, "rules": [
        "Ein Begriff erscheint – gesucht ist sein Herkunftsland.",
        "Jede Zelle tippt ihr Land auf der Karte im Gerät an. Einzeln geht auch.",
        "Volltreffer 100 Punkte, danach weniger, je weiter weg. Nachbarländer bekommen mindestens 55."]},
}
GAMES.update({
    "maulwurf_los": {"name": "Ein Verdacht", "mode": "solo", "pts": 0, "rounds": 1, "min": 3, "ereignis": True, "rules": [
        "Die Zentrale vermutet einen Maulwurf des Amtes in der Zelle.",
        "Jedes Gerät zeigt jetzt verdeckt eine Rollenkarte – nur für die eigenen Augen.",
        "Wer Maulwurf ist, sammelt ab jetzt für das Amt. Bei der Übergabe wird abgestimmt."]},
    "maulwurf_wahl": {"name": "Wer ist der Maulwurf?", "mode": "solo", "pts": 0, "rounds": 1, "min": 4, "ereignis": True, "rules": [
        "Die Zelle stimmt im Gerät ab: Wer arbeitet für das Amt?",
        "Die letzte Stimme jeder Person zählt, die Stimme des Maulwurfs nicht.",
        "Aufgelöst wird bei der Übergabe."]},
})
EREIGNISSE = ["maulwurf_los", "maulwurf_wahl"]
INTERNAL = ["schaetzen", "ranking", "impostor", "zoom", "sound", "hoeher", "emoji", "wette", "woerterbuch", "schwaerzung"]
SPECIAL = ["deppardy", "atlas"]      # eigene Editoren im Archiv
BUZZ = {"zoom", "sound", "emoji"}

FIELDS = {
    "schaetzen": [["q", "Frage", "wide"], ["a", "Antwort (Zahl)"], ["unit", "Einheit"], ["beute", "Beutewort (optional)"]],
    "ranking": [["q", "Aufgabe", "wide"], ["items", "Richtige Reihenfolge – ein Begriff pro Zeile", "area"], ["beute", "Beutewort (optional)"]],
    "impostor": [["word", "Parole"], ["cat", "Kategorie (bekommt der Eindringling)"], ["beute", "Beutewort (optional)"]],
    "zoom": [["img", "Bild", "img"], ["a", "Lösung"], ["beute", "Beutewort (optional)"]],
    "sound": [["src", "Audio (Datei hochladen, mp3-URL oder YouTube-Link)", "audio"], ["a", "Lösung"], ["beute", "Beutewort (optional)"]],
    "hoeher": [["q", "Frage", "wide"], ["a", "A"], ["av", "Wert A"], ["b", "B"], ["bv", "Wert B"], ["beute", "Beutewort (optional)"]],
    "emoji": [["e", "Emojis"], ["a", "Lösung"], ["cat", "Kategorie"], ["beute", "Beutewort (optional)"]],
    "wette": [["cat", "Kategorie"], ["q", "Frage", "wide"], ["a", "Antwort"], ["beute", "Beutewort (optional)"]],
    "woerterbuch": [["wort", "Beschlagnahmtes Wort"], ["art", "Artikel oder Wortart"], ["def", "Echte Bedeutung", "wide"],
                    ["beute", "Beutewort (leer = das Wort selbst)"]],
    "schwaerzung": [["text", "Text – das geschwärzte Wort in doppelte eckige Klammern: Die Gedanken sind [[frei]]", "area"],
                    ["quelle", "Quelle"], ["beute", "Beutewort (leer = das geschwärzte Wort)"]],
}
HINTS = {
    "schaetzen": "Antwort als reine Zahl eintragen – die Wertung rechnet damit aus, wer am nächsten dran ist.",
    "ranking": "Begriffe in der richtigen Reihenfolge eintragen. Im Spiel liegen sie gemischt als Karteikarten auf dem Handy und werden durch Ziehen sortiert.",
    "impostor": "Pro Runde wird ein Eintrag gezogen und zufällig ein Spitzel bestimmt.",
    "zoom": "Bild hochladen oder URL einfügen. Hochgeladene Bilder liegen auf dem Server und funktionieren auch ohne Internet.",
    "sound": "Hochgeladene Dateien und mp3-URLs spielen auf der Leinwand, gesteuert aus dem Steuermodul. YouTube-Links öffnen sich in einem neuen Tab.",
    "hoeher": "Werte mit Zahl eintragen („161,5 m“). Der größere Wert wird beim Aufdecken markiert, richtige Zellen erkennt das Steuermodul selbst.",
    "emoji": "Emojis direkt einfügen. Kategorie wird als Hinweis gezeigt.",
    "wette": "Die Kategorie ist vor der Frage sichtbar – daran bemessen die Agenten ihren Einsatz.",
    "woerterbuch": "Möglichst unbekannte Wörter wählen – sonst gibt es nichts zu fälschen. Die echte Bedeutung kurz halten, damit sie zwischen den Fälschungen nicht auffällt.",
    "schwaerzung": "Genau ein Wort in [[doppelte eckige Klammern]] setzen. Zeilenumbrüche bleiben erhalten. Nur gemeinfreie Texte, Sprichwörter oder Gesetze verwenden.",
}
WIKI = "https://upload.wikimedia.org/wikipedia/commons/thumb/"
def _wb(wort, art, de):
    return {"wort": wort, "art": art, "def": de, "beute": ""}


SAMPLES = {
    "woerterbuch": [
        _wb("Kaltmamsell", "die", "Angestellte in Hotel- oder Gutsküchen, die kalte Speisen anrichtet"),
        _wb("Hahnrei", "der", "Ein betrogener Ehemann"),
        _wb("Kujon", "der", "Schuft, Schurke"),
        _wb("Blaustrumpf", "der", "Abwertend für eine gelehrte Frau"),
        _wb("Hundsfott", "der", "Derbes Schimpfwort für einen gemeinen, feigen Menschen"),
        _wb("Leumund", "der", "Der Ruf, den jemand bei anderen hat"),
        _wb("Laffe", "der", "Eitler, geckenhafter junger Mann"),
        _wb("Zwickel", "der", "Keilförmiger Stoffeinsatz in Kleidungsstücken"),
        _wb("Gant", "die", "Zwangsversteigerung"),
        _wb("Kiepe", "die", "Korb, der auf dem Rücken getragen wird"),
        _wb("Remise", "die", "Schuppen für Kutschen und Geräte"),
        _wb("Sottise", "die", "Grobheit, freche Bemerkung"),
        _wb("Plünnen", "Pl.", "Alte Kleider, Klamotten"),
        _wb("Plutzer", "der", "Kürbis – oder eine bauchige Tonflasche"),
        _wb("Treidelpfad", "der", "Uferweg, auf dem Pferde Schiffe stromaufwärts zogen"),
        _wb("Scharwache", "die", "Nächtliche Wachmannschaft einer Stadt"),
        _wb("Wehmutter", "die", "Hebamme"),
        _wb("Wiegendruck", "der", "Buch aus der Frühzeit des Buchdrucks, vor 1501"),
        _wb("Mondkalb", "das", "Dummkopf"),
        _wb("Spezerei", "die", "Gewürz"),
    ],
    "schwaerzung": [
        {"text": "Die Gedanken sind [[frei]],\nwer kann sie erraten?", "quelle": "Volkslied, um 1800", "beute": "Gedankenfreiheit"},
        {"text": "Eine [[Zensur]] findet nicht statt.", "quelle": "Grundgesetz, Artikel 5", "beute": "Zensur"},
        {"text": "Denk ich an Deutschland in der Nacht,\nDann bin ich um den [[Schlaf]] gebracht", "quelle": "Heinrich Heine, Nachtgedanken (1844)", "beute": "Nachtgedanken"},
        {"text": "Dort wo man Bücher\nVerbrennt, verbrennt man auch am Ende [[Menschen]].", "quelle": "Heinrich Heine, Almansor (1821)", "beute": "Bücherverbrennung"},
        {"text": "Über allen Gipfeln\nIst [[Ruh]]", "quelle": "Johann Wolfgang von Goethe, Wandrers Nachtlied", "beute": "Ruh"},
        {"text": "Es war, als hätt der Himmel\nDie Erde still [[geküsst]]", "quelle": "Joseph von Eichendorff, Mondnacht (1837)", "beute": "Mondnacht"},
        {"text": "Ein Wiesel\nsaß auf einem [[Kiesel]]\ninmitten Bachgeriesel.", "quelle": "Christian Morgenstern, Das ästhetische Wiesel", "beute": "Bachgeriesel"},
        {"text": "Ich lebe mein Leben in wachsenden [[Ringen]]", "quelle": "Rainer Maria Rilke, Das Stunden-Buch", "beute": "Jahresring"},
        {"text": "Freude, schöner [[Götterfunken]],\nTochter aus Elysium", "quelle": "Friedrich Schiller, An die Freude", "beute": "Götterfunken"},
        {"text": "Der Mensch ist frei geschaffen, ist frei,\nUnd würd er in [[Ketten]] geboren", "quelle": "Friedrich Schiller, Die Worte des Glaubens", "beute": "Fessel"},
        {"text": "Es ist nicht genug, zu wissen, man muss auch [[anwenden]].", "quelle": "Johann Wolfgang von Goethe, Wilhelm Meisters Wanderjahre", "beute": "Tatendrang"},
        {"text": "Reden ist Silber, Schweigen ist [[Gold]].", "quelle": "Sprichwort", "beute": "Schweigegeld"},
        {"text": "Die Würde des Menschen ist [[unantastbar]].", "quelle": "Grundgesetz, Artikel 1", "beute": "Menschenwürde"},
    ],
    "schaetzen": [
        {"q": "Wie viele Stichwörter enthält der Duden in seiner 28. Auflage (2020)?", "a": "148000", "unit": "Stichwörter"},
        {"q": "Wie lang ist die Donau?", "a": "2857", "unit": "Kilometer"},
        {"q": "Wie hoch ist die Zugspitze?", "a": "2962", "unit": "Meter"},
        {"q": "In welchem Jahr erschien Goethes „Die Leiden des jungen Werthers“?", "a": "1774", "unit": ""},
        {"q": "Wie viele Einwohner hat Liechtenstein ungefähr?", "a": "40000", "unit": "Menschen"}],
    "ranking": [
        {"q": "Nach Einwohnern ordnen – die größte Stadt zuerst.", "items": "Berlin\nHamburg\nMünchen\nKöln\nFrankfurt am Main"},
        {"q": "Nach Erscheinungsjahr ordnen – das älteste zuerst.", "items": "Gutenberg-Bibel\nFaust I\nGrimms Kinder- und Hausmärchen\nDer Zauberberg"},
        {"q": "Nach Fläche ordnen – das größte Bundesland zuerst.", "items": "Bayern\nNiedersachsen\nBaden-Württemberg\nNordrhein-Westfalen\nBrandenburg"},
        {"q": "Nach Höhe ordnen – der höchste Gipfel zuerst.", "items": "Zugspitze\nFeldberg (Schwarzwald)\nGroßer Arber\nFichtelberg\nBrocken"}],
    "impostor": [
        {"word": "Gartenzwerg", "cat": "Garten"}, {"word": "Stammtisch", "cat": "Gastwirtschaft"},
        {"word": "Kehrwoche", "cat": "Haushalt"}, {"word": "Schützenfest", "cat": "Dorfleben"},
        {"word": "Faxgerät", "cat": "Büro"}, {"word": "Jägerzaun", "cat": "Garten"}],
    "zoom": [
        {"img": WIKI + "e/ec/Mona_Lisa%2C_by_Leonardo_da_Vinci%2C_from_C2RMF_retouched.jpg/687px-Mona_Lisa%2C_by_Leonardo_da_Vinci%2C_from_C2RMF_retouched.jpg", "a": "Mona Lisa"},
        {"img": WIKI + "a/a5/Tsunami_by_hokusai_19th_century.jpg/1280px-Tsunami_by_hokusai_19th_century.jpg", "a": "Die große Welle vor Kanagawa"},
        {"img": WIKI + "e/ea/Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/1280px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg", "a": "Sternennacht"}],
    "sound": [],
    "hoeher": [
        {"q": "Was ist höher?", "a": "Kölner Dom", "av": "157 m", "b": "Ulmer Münster", "bv": "161,5 m"},
        {"q": "Wer hat mehr Einwohner?", "a": "Leipzig", "av": "≈ 620.000", "b": "Dresden", "bv": "≈ 565.000"},
        {"q": "Was ist größer?", "a": "Saarland", "av": "2.570 km²", "b": "Luxemburg", "bv": "2.586 km²"},
        {"q": "Was ist höher?", "a": "Brocken", "av": "1.141 m", "b": "Fichtelberg", "bv": "1.215 m"},
        {"q": "Welcher Fluss ist länger?", "a": "Rhein", "av": "1.233 km", "b": "Elbe", "bv": "1.094 km"}],
    "emoji": [
        {"e": "🍅👀", "a": "Tomaten auf den Augen haben", "cat": "Redewendung", "beute": "Tomaten auf den Augen"},
        {"e": "🐻🎁", "a": "Jemandem einen Bären aufbinden", "cat": "Redewendung", "beute": "einen Bären aufbinden"},
        {"e": "🐷🍀", "a": "Schwein gehabt", "cat": "Redewendung", "beute": "Schwein gehabt"},
        {"e": "🥒⏰", "a": "Sauregurkenzeit", "cat": "Redewendung", "beute": "Sauregurkenzeit"},
        {"e": "🗣️✂️", "a": "Jemandem das Wort abschneiden", "cat": "Redewendung", "beute": "das Wort abschneiden"},
        {"e": "🌭🤷", "a": "Das ist mir Wurst", "cat": "Redewendung", "beute": "Das ist mir Wurst"},
        {"e": "🐸👄", "a": "Einen Frosch im Hals haben", "cat": "Redewendung", "beute": "Frosch im Hals"}],
    "wette": [
        {"cat": "Sprache", "q": "Aus welcher Sprache stammt das Wort „Tollpatsch“?", "a": "Ungarisch", "beute": "Tollpatsch"},
        {"cat": "Literatur", "q": "Wer schrieb „Die Blechtrommel“?", "a": "Günter Grass"},
        {"cat": "Geografie", "q": "Wie heißt die Hauptstadt Australiens?", "a": "Canberra"}],
}
PLAN0 = [["schaetzen", "solo", 3, 5], ["ranking", "team", 3, 4], ["emoji", "solo", 2, 7],
         ["deppardy", "solo", 500, 1], ["impostor", "solo", 3, 2], ["hoeher", "team", 2, 5],
         ["zoom", "solo", 2, 3], ["atlas", "team", 50, 8], ["sound", "solo", 2, 5], ["wette", "solo", 0, 3]]
ZOOM = [10, 6, 3.5, 2, 1.4, 1]
LETTERS = "ABCDEFGH"
TEAMS = "ABCD"
MAX_BUZZ = 6            # Rateversuche pro Person und Runde
TEAM_SPIELE = ("ranking", "hoeher", "atlas")      # Spiele mit Zellenantwort
ZELLMODI = ("sprecher", "mehrheit", "zuversicht")
TAKT_SPIELE = ("emoji", "schwaerzung")            # Schnell-Antwort-Spiele mit Zeittakt
ATLAS_GEBORGEN = 50     # ab so vielen Atlas-Punkten gilt das Beutewort als geborgen
CUES = [["einsatz", "Einsatzbefehl (Mission startet)"], ["los", "Einsatz beginnt"], ["aufdecken", "Aufdecken"],
        ["treffer", "Treffer / Wörter vergeben"], ["ende", "Mission abgeschlossen"], ["umlagern", "Umlagern"],
        ["verzicht", "Verzicht beim Umlagern"], ["tafel", "Prolog-Tafel"], ["uebergabe", "Übergabe beginnt"],
        ["gerettet", "Ziel erreicht"], ["verloren", "Ziel verfehlt"], ["enttarnt", "Maulwurf enttarnt"],
        ["entkommen", "Maulwurf entkommen"], ["takt", "Zeittakt: Punktestufe fällt"]]
RAUSCH0 = {"tiefpass": 75, "rauschen": 70, "knistern": 40, "brummen": 25, "pfeifen": 15, "verzerrung": 30,
           "aussetzer": 20, "leiern": 25}


def uid():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=7))


def num(v):
    """Deutsche Zahlschreibweise lesen: '161,5 m' -> 161.5, '≈ 620.000' -> 620000."""
    s = re.sub(r"[^\d,.\-]", "", str(v if v is not None else ""))
    if not s:
        return None
    s = re.sub(r"\.(?=\d{3}(\D|$))", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def make_plan():
    return [{"id": uid(), "type": t, "mode": m, "pts": p, "rounds": r, "opt": "", "zm": "sprecher", "takt": 0}
            for t, m, p, r in PLAN0]


def defaults():
    return {
        "screen": "start", "agents": [], "scores": {}, "plan": make_plan(), "cur": 0,
        "active": False, "phase": "intro", "round": 0, "revealed": False, "gains": {},
        "teams": [], "teamCount": 2, "content": copy.deepcopy(SAMPLES), "cursor": {},
        "stealAmount": 3, "pendingSteal": None, "thief": None, "lastSteal": None,
        "rnd": {}, "zoomStep": 0, "showQ": False, "open": False, "awarded": False,
        "answers": {}, "teamAnswers": {}, "feed": [], "bets": {}, "betDone": {},
        "votes": {}, "judged": {}, "spyResult": None,
        "joinOpen": True, "audio": {"n": 0, "a": ""},
        "boards": vorlage("deppardy-boards.json", []), "atlasSets": vorlage("atlas-sets.json", {}),
        "dep": None, "depDur": 30, "upts": {}, "atlasOrder": [], "atlasRes": None,
        "story": vorlage("drehbuch.json", {}), "prologIdx": 0, "finaleStufe": 0, "stealLog": [],
        "mole": {"on": False, "id": None, "bonus": 5, "voteOpen": False, "result": None}, "moleVotes": {},
        "stealPct": 20, "stealVerlust": 50, "verzichtBonus": 2, "ziel": -1, "beute": [], "funk": None,
        "depArm": True, "judgedPts": {}, "korrekturStand": 4,
        "kartei": vorlage("beutekartei.json", {}),
        "vorschlaege": {}, "zielProzent": 50, "namenZeigen": False, "beispiel": True, "schluesselloch": True,
        "klang": {"an": True, "signale": True, "vol": 80, "cues": {},
                  "musik": {"an": False, "url": "", "spiel": "", "vol": 35}},
        "cues": [], "cueN": 0, "rausch": dict(RAUSCH0),
        "test": None, "tracking": {}, "impressum": "", "beuteImportInfo": "",
    }


# ---------------------------------------------------------------------------
# Zustand, Speichern, Long-Polling
# ---------------------------------------------------------------------------

LOCK = threading.Condition()
STATE = None
VERSION = 0
CONFIG = {}


def deep_merge(base, saved):
    """Gespeicherten Stand über die Standardwerte legen, auch in verschachtelten Einträgen.
    Fehlt in einer alten state.json ein neuer Unterschlüssel, bleibt der Standardwert stehen."""
    if not isinstance(saved, dict):
        return base
    for k, v in saved.items():
        if isinstance(base.get(k), dict) and isinstance(v, dict) and k not in ("content", "atlasSets", "scores", "gains",
                                                                               "upts", "answers", "teamAnswers", "votes",
                                                                               "moleVotes", "bets", "betDone", "judged",
                                                                               "cursor", "rnd", "vorschlaege", "tracking", "test"):
            base[k] = deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def pruefe_state(s):
    """Grobe Typprüfung der Kernfelder – ein falscher Import soll den Abend nicht lahmlegen."""
    typen = {"agents": list, "plan": list, "scores": dict, "boards": list, "atlasSets": dict, "content": dict,
             "mole": dict, "story": dict, "stealLog": list}
    for k, t in typen.items():
        if not isinstance(s.get(k), t):
            raise ValueError(f"Feld „{k}“ fehlt oder hat den falschen Typ")
    for a in s["agents"]:
        if not all(isinstance(a.get(x), str) for x in ("id", "name", "code", "token")):
            raise ValueError("Agentenliste unvollständig")
    for p in s["plan"]:
        if p.get("type") not in GAMES:
            raise ValueError("Unbekannte Mission im Plan: " + str(p.get("type")))
    return s


def korrekturen(s):
    """Einmalige Korrekturen an mitgelieferten Inhalten (Review Okt. 2026) – nur wo der alte Text noch unverändert ist."""
    if s.get("korrekturStand", 0) >= 1:
        return
    ex = (s["atlasSets"].get("exil") or {}).get("eintraege") or []
    for e in ex:
        if e.get("text") == "Mascha Kaléko" and e.get("land") == "616":
            e.update(land="276", auchOk=[], notiz="Geboren in Chrzanów in Galizien, 1938 aus Deutschland nach New York geflohen.")
        if e.get("text") == "Herta Müller" and e.get("auchOk") == ["276"]:
            e["auchOk"] = []
        if e.get("text") == "Isabel Allende" and e.get("auchOk") == ["604"]:
            e["auchOk"] = []
        if e.get("text") == "Salman Rushdie" and e.get("land") == "356":
            e.update(text="Stefan Zweig", land="40", auchOk=[], notiz="Verließ Österreich 1934 Richtung London, später Brasilien.")
    for e in (s["atlasSets"].get("woerter") or {}).get("eintraege") or []:
        if e.get("text") == "Amok" and not e.get("auchOk"):
            e["auchOk"] = ["360"]
        if e.get("text") == "Sarong" and not e.get("auchOk"):
            e["auchOk"] = ["458"]
    for b in s["boards"]:
        for c in b.get("cats", []):
            q = (c.get("qh") or {}).get("400", "")
            if "nach dem Bundeskleingartengesetz" in q:
                c["qh"]["400"] = q.replace("nach dem Bundeskleingartengesetz", "nach der Rechtsprechung zum Bundeskleingartengesetz")
    alt_hoeher = {"Österreich", "Nutella"}
    neu = [x for x in SAMPLES["hoeher"] if x["a"] in ("Brocken", "Rhein")]
    s["content"]["hoeher"] = [neu.pop(0) if x.get("a") in alt_hoeher and neu else x for x in s["content"].get("hoeher", [])]
    if [x.get("cat") for x in s["content"].get("emoji", [])] == ["Film"] * 7:
        s["content"]["emoji"] = copy.deepcopy(SAMPLES["emoji"])
    ms = (s.get("story") or {}).get("missionen") or {}
    vorlage_ms = (vorlage("drehbuch.json", {}).get("missionen") or {})
    if (ms.get("ranking") or {}).get("ort") == "Die Rangliste":
        ms["ranking"].update({k: v for k, v in vorlage_ms.get("ranking", {}).items() if k in ("ort", "lage")})
    if (ms.get("impostor") or {}).get("ort") == "Die Unterwanderung":
        ms["impostor"].update({k: v for k, v in vorlage_ms.get("impostor", {}).items() if k in ("ort", "lage")})
    s["korrekturStand"] = 1


LAGE_ALT = {
    "sound": ["Die Bänder werden heute Nacht gelöscht. Wer erkennt, was darauf ist, rettet die Aufnahme.",
              "Die Tonbänder werden morgen gelöscht. Wer erkennt, was darauf ist, bevor das Band reißt?"],
    "hoeher": ["Propaganda gegen Wirklichkeit. Zwei Behauptungen, nur eine stimmt.",
               "Zwei Behauptungen, nur eine stimmt. Die Front setzt auf die falsche."],
    "ranking": ["Das Amt hat die Kartei neu sortiert – nach Gesinnung statt nach Wahrheit. Stellt die richtige Ordnung wieder her."],
}


def korrekturen2(s):
    """Stand 2: neue Lagetexte für Abgehört, Propaganda und Registratur – nur wo nichts geändert wurde."""
    if s.get("korrekturStand", 0) >= 2:
        return
    ms = (s.get("story") or {}).setdefault("missionen", {})
    neu = vorlage("drehbuch.json", {}).get("missionen") or {}
    for t, alt in LAGE_ALT.items():
        if (ms.get(t) or {}).get("lage") in alt and t in neu:
            ms[t]["lage"] = neu[t]["lage"]
    s["korrekturStand"] = 2


ENTKOMMEN_ALT = "Entkommen. Der Maulwurf verschwindet mit seinem Rucksack über die Grenze. Das Amt zahlt {bonus} Wörter Prämie."


def korrekturen3(s):
    """Stand 3: Die Prämie des entkommenen Maulwurfs zahlt ausdrücklich das Amt."""
    if s.get("korrekturStand", 0) >= 3:
        return
    mw = (s.get("story") or {}).get("maulwurf") or {}
    if mw.get("entkommen") == ENTKOMMEN_ALT:
        mw["entkommen"] = (vorlage("drehbuch.json", {}).get("maulwurf") or {}).get("entkommen", ENTKOMMEN_ALT)
    s["korrekturStand"] = 3


def korrekturen4(s):
    """Stand 4: Epilog, Abspann und die Ereignisse im Einsatzplan bekommen Texte."""
    if s.get("korrekturStand", 0) >= 4:
        return
    st = s.setdefault("story", {})
    neu = vorlage("drehbuch.json", {})
    for k in ("epilog", "abspann"):
        if not st.get(k) and neu.get(k):
            st[k] = copy.deepcopy(neu[k])
    ms = st.setdefault("missionen", {})
    for k in EREIGNISSE:
        if k not in ms and k in (neu.get("missionen") or {}):
            ms[k] = copy.deepcopy(neu["missionen"][k])
    s["korrekturStand"] = 4


def load():
    global STATE, VERSION
    os.makedirs(MEDIA, exist_ok=True)
    os.makedirs(KV, exist_ok=True)
    s = defaults()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            s = deep_merge(s, saved.get("state", {}))
            s["korrekturStand"] = (saved.get("state") or {}).get("korrekturStand", 0)
            for alt in ("extStart", "extResults", "kvImportiert_alt"):   # Reste früherer Versionen
                s.pop(alt, None)
            s["beute"] = [b if isinstance(b, dict) else {"wort": str(b)} for b in s.get("beute") or []]
            for k, v in SAMPLES.items():
                s["content"].setdefault(k, copy.deepcopy(v))
            korrekturen(s)
            korrekturen2(s)
            korrekturen3(s)
            korrekturen4(s)
            for p in s["plan"]:                       # Außeneinsätze sind jetzt eingebaut
                p.setdefault("opt", "")
                p.setdefault("zm", "sprecher")
                p.setdefault("takt", 0)
                if GAMES.get(p["type"], {}).get("kurs") and not p.get("pts"):
                    p["pts"] = GAMES[p["type"]]["pts"]      # früher fest 100 Punkte = 1 Wort
                if p["type"] == "atlas" and p.get("rounds", 1) < 2:
                    p["rounds"] = GAMES["atlas"]["rounds"]
            VERSION = int(saved.get("v", 0))
        except Exception as e:  # beschädigte Datei nicht überschreiben, sondern sichern
            bak = STATE_FILE + ".defekt-" + time.strftime("%Y%m%d-%H%M%S")
            os.replace(STATE_FILE, bak)
            print(f"! state.json unlesbar ({e}), gesichert als {bak}")
    # Boards aus der vorigen Version (Deppardy als eigenes Fenster) einmalig übernehmen
    alt = os.path.join(KV, "deppardy_boards.json")
    if os.path.exists(alt) and not s.get("kvImportiert"):
        try:
            with open(alt, encoding="utf-8") as f:
                for b in json.load(f) or []:
                    nb = board_normal(b)
                    if not any(x["id"] == nb["id"] for x in s["boards"]):
                        s["boards"].append(nb)
        except Exception as e:
            print("! alte Deppardy-Boards nicht lesbar:", e)
        s["kvImportiert"] = True
    STATE = s


def save():
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": VERSION, "state": STATE}, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


SICHT_CACHE = {}
LAN_IP = "127.0.0.1"
SPEICHERN = threading.Event()


def commit(sofort=False):
    """Nach jeder Änderung aufrufen (LOCK muss gehalten werden).
    Gespeichert wird im Hintergrund höchstens alle 0,5 s – bei Buzzer-Salven hält das die Sperre kurz."""
    global VERSION
    VERSION += 1
    SICHT_CACHE.clear()
    if sofort:
        save()
    else:
        SPEICHERN.set()
    LOCK.notify_all()


def speicher_schleife():
    while True:
        SPEICHERN.wait()
        time.sleep(0.5)
        SPEICHERN.clear()
        with LOCK:
            try:
                save()
            except Exception as e:
                print("! Speichern fehlgeschlagen:", e)


def wait_change(since, timeout=LONGPOLL_S):
    end = time.time() + timeout
    with LOCK:
        while VERSION == since:
            rest = end - time.time()
            if rest <= 0:
                break
            LOCK.wait(rest)
        return VERSION


def load_config(args):
    global CONFIG
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    fresh = "password" not in cfg
    cfg.setdefault("password", secrets.token_urlsafe(6))
    cfg.setdefault("joinUrl", "")
    if args.passwort:
        cfg["password"] = args.passwort
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    CONFIG = cfg
    return fresh


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Spiellogik (Portierung aus Widerstand.dc.html, jetzt serverseitig)
# ---------------------------------------------------------------------------

def mission(s):
    return s["plan"][s["cur"]] if s["cur"] < len(s["plan"]) else None


def by_id(s):
    return {a["id"]: a for a in s["agents"]}


def total(s, aid):
    return max(0, s["scores"].get(aid, 0) + s["gains"].get(aid, 0))


def step(m):
    return (m or {}).get("pts") or 1


def item(s):
    return s["rnd"].get("item")


def lines_of(it):
    return [x.strip() for x in (it or {}).get("items", "").split("\n") if x.strip()]


def team_of(s, aid):
    for i, t in enumerate(s["teams"]):
        if aid in t:
            return i
    return None


def roll_teams(s, n):
    ids = [a["id"] for a in s["agents"]]
    random.shuffle(ids)
    t = [[] for _ in range(n)]
    for i, aid in enumerate(ids):
        t[i % n].append(aid)
    return t


def free_code(s, exclude=None):
    used = {a["code"] for a in s["agents"]}
    for zusatz in ("", " II", " III", " IV", " V"):      # ab 23 Personen: „Genitiv II“ usw.
        free = [c + zusatz for c in CODES if c + zusatz not in used and c + zusatz != exclude]
        if free:
            return random.choice(free)
    return "Agent " + str(len(used) + 1)


def round_state(s, r):
    m = mission(s)
    lst = s["content"].get(m["type"]) or []
    it = None
    if m["type"] == "atlas":
        order = s.get("atlasOrder") or []
        if order:
            sid, idx = order[r % len(order)]
            st = s["atlasSets"].get(sid) or {}
            e = (st.get("eintraege") or [])[idx] if idx < len(st.get("eintraege") or []) else None
            if e:
                it = dict(copy.deepcopy(e), marke=st.get("marke", ""), setName=st.get("name", ""))
        lst = []
    test = s.get("test") or {}
    if test.get("i") is not None and m["type"] != "atlas":       # Testlauf: genau dieser Eintrag
        i = int(test["i"])
        it = copy.deepcopy(lst[i]) if 0 <= i < len(lst) else None
        lst = []
    if lst:
        # Nur Einträge in der Rotation; „aus“ markierte werden übersprungen
        c = s["cursor"].get(m["type"], 0)
        for k in range(len(lst)):
            j = (c + k) % len(lst)
            if not lst[j].get("aus"):
                it = copy.deepcopy(lst[j])
                s["cursor"][m["type"]] = c + k + 1
                break
    ln = lines_of(it)
    order = list(range(len(ln)))
    random.shuffle(order)
    ids = [a["id"] for a in s["agents"]]
    extra = {}
    if m["type"] == "hoeher":
        extra["claim"] = random.choice("AB")           # Was das Amt behauptet
    if m["type"] == "woerterbuch":
        extra.update(wbPhase="faelschen", optionen=[], treffer=[], gestrichen=[])
    extra["g0"] = dict(s["gains"])                     # Stand vor der Runde: wurde etwas geborgen?
    extra["t0"] = time.time()                          # Start des Zeittakts
    s.update({
        "round": r, "revealed": False, "zoomStep": 0, "showQ": False, "awarded": False,
        "answers": {}, "teamAnswers": {}, "feed": [], "bets": {}, "betDone": {}, "vorschlaege": {},
        "votes": {}, "judged": {}, "judgedPts": {}, "spyResult": None,
        # Beim Spitzel startet die Abstimmung erst auf Kommando.
        "open": m["type"] != "impostor",
        "rnd": dict({"item": it, "order": order, "spy": random.choice(ids) if ids else None,
                     "ox": 25 + random.random() * 50, "oy": 25 + random.random() * 50}, **extra),
        "atlasRes": None,
    })


def add_gain(s, aid, d):
    s["gains"][aid] = s["gains"].get(aid, 0) + d


def cue(s, art):
    """Klang-Signal für die Leinwand (Musik und Töne spielt nur die Leinwand)."""
    s["cueN"] = s.get("cueN", 0) + 1
    s["cues"] = (s.get("cues") or [])[-11:] + [{"n": s["cueN"], "art": art}]


def track(s, aid, was, n=1):
    """Kleine Strichliste je Person für die Personalakten bei der Übergabe."""
    if not aid:
        return
    t = s.setdefault("tracking", {}).setdefault(aid, {})
    t[was] = t.get(was, 0) + n


def steal_weiter(s, text):
    """Nach einem Umlagern oder Verzicht: Bei „alle dürfen“ ist die nächste Person dran."""
    ps = s["pendingSteal"] or {}
    kette = list(ps.get("kette") or [])
    vorher = ps.get("text") or ""
    gesamt = (vorher + " " + text).strip() if vorher else text
    while kette and kette[0] not in by_id(s):
        kette.pop(0)
    if kette:
        s.update({"thief": kette.pop(0), "lastSteal": gesamt,
                  "pendingSteal": dict(ps, kette=kette, text=gesamt)})
    else:
        s.update({"pendingSteal": None, "thief": None, "lastSteal": gesamt})


TEST_SICHERN = ["plan", "cur", "active", "phase", "screen", "scores", "gains", "beute", "stealLog", "teams", "pendingSteal",
                "thief", "lastSteal", "funk", "upts", "dep", "atlasOrder", "atlasRes", "rnd", "answers", "teamAnswers",
                "feed", "open", "revealed", "round", "vorschlaege", "votes", "judged", "judgedPts", "bets", "betDone",
                "spyResult", "zoomStep", "showQ", "awarded", "mole", "moleVotes", "tracking", "finaleStufe"]


def test_ende(s):
    t = s.get("test") or {}
    for k, v in (t.get("sicher") or {}).items():
        s[k] = v
    s["test"] = None


def zeile_kurz(t, e):
    """Ein Archiv-Eintrag in einer Zeile – für den KI-Auftrag."""
    f = {"schaetzen": lambda: f"Frage: {e.get('q')} (Antwort {e.get('a')} {e.get('unit', '')})",
         "ranking": lambda: f"Aufgabe: {e.get('q')} – " + " / ".join(lines_of(e)),
         "impostor": lambda: f"Parole: {e.get('word')} (Kategorie {e.get('cat')})",
         "zoom": lambda: f"Bild, Lösung: {e.get('a')}", "sound": lambda: f"Tonaufnahme, Lösung: {e.get('a')}",
         "hoeher": lambda: f"{e.get('q')} {e.get('a')} ({e.get('av')}) oder {e.get('b')} ({e.get('bv')})",
         "emoji": lambda: f"Emojis {e.get('e')} = {e.get('a')} ({e.get('cat')})",
         "wette": lambda: f"{e.get('cat')}: {e.get('q')} – {e.get('a')}",
         "woerterbuch": lambda: f"Wort {e.get('wort')}: {e.get('def')}",
         "schwaerzung": lambda: f"Text: {str(e.get('text', '')).replace(chr(10), ' ')} ({e.get('quelle')})"}.get(t)
    return re.sub(r"\s+", " ", f() if f else str(e)).strip()


VERMERKE = ["fremd", "alt", "doppeldeutig", "mundartlich", "derb", "poetisch", "aufrührerisch", "unerwünscht",
            "umgangssprachlich", "unamtlich", "verdächtig", "umstritten"]


def beute_auftrag(s):
    """Text für eine KI: alle Einträge ohne Beutewort und alle Beutewörter ohne Karteikarte – mit Antwortformat."""
    offen, woerter = [], set()
    for t, lst in s["content"].items():
        for i, e in enumerate(lst or []):
            if str(e.get("beute") or "").strip():
                woerter.add(e["beute"].strip())
            elif t not in ("woerterbuch", "schwaerzung"):       # die nehmen notfalls ihr eigenes Wort
                offen.append((f"content:{t}:{i}", GAMES[t]["name"], zeile_kurz(t, e)))
            else:
                woerter.add(beute_von(e, t))
    for b in s["boards"]:
        for ci, c in enumerate(b.get("cats", [])):
            for p in b.get("pts", []):
                q = strip_html((c.get("qh") or {}).get(str(p)))
                if not q:
                    continue
                bw = str((c.get("bw") or {}).get(str(p)) or "").strip()
                if bw:
                    woerter.add(bw)
                else:
                    a = strip_html((c.get("ah") or {}).get(str(p)))
                    offen.append((f"deppardy:{b['id']}:{ci}:{p}", "Deppardy · " + c.get("name", ""), f"{q} – Antwort: {a}"))
    for sid, st in s["atlasSets"].items():
        for i, e in enumerate(st.get("eintraege") or []):
            if str(e.get("beute") or "").strip():
                woerter.add(e["beute"].strip())
            else:
                land = GEO.get(str(e.get("land")), {}).get("name", "")
                offen.append((f"atlas:{sid}:{i}", "Atlas · " + st.get("name", ""), f"{e.get('text')} (Herkunft: {land})"))
    ohne_karte = sorted(w for w in woerter if w and w not in s["kartei"])
    zeilen = [
        "Du hilfst bei einem Quiz-Abend. Die Geschichte: Ein „Amt für Reinsprache“ verbietet alles Fremde, Alte und "
        "Doppeldeutige. Die Mitspielenden bergen verbotene deutsche Wörter. Jede Quizfrage bringt ein „Beutewort“: "
        "ein schönes, seltenes, altes, fremdstämmiges oder doppeldeutiges deutsches Wort, das thematisch zur Frage passt.",
        "",
        "AUFGABE 1 – Für jeden Eintrag unten genau ein passendes Beutewort finden (ein Wort oder eine kurze Wendung, "
        "höchstens 40 Zeichen, nicht die Lösung der Frage selbst, möglichst kein Wort doppelt).",
        "AUFGABE 2 – Für jedes Beutewort (deine neuen und die Liste „Ohne Karteikarte“) eine Karteikarte schreiben: "
        "art (der/die/das, Pl., Adj., Verb …), def (Bedeutung, ein Satz, höchstens 160 Zeichen), herkunft (kurz, darf leer sein), "
        "vermerk (genau einer von: " + ", ".join(VERMERKE) + ").",
        "",
        "Antworte NUR mit gültigem JSON in genau diesem Format, ohne Erklärung davor oder danach:",
        '{"beute": [{"ref": "<ref aus der Liste>", "wort": "<Beutewort>"}],',
        ' "kartei": {"<Beutewort>": {"art": "", "def": "", "herkunft": "", "vermerk": ""}}}',
        "",
        f"EINTRÄGE OHNE BEUTEWORT ({len(offen)}):",
    ]
    zeilen += [f"- ref={r} | {wo} | {txt}" for r, wo, txt in offen] or ["(keine)"]
    zeilen += ["", f"OHNE KARTEIKARTE ({len(ohne_karte)}):"] + ([f"- {w}" for w in ohne_karte] or ["(keine)"])
    return "\n".join(zeilen), len(offen), len(ohne_karte)


def beute_import(s, daten):
    """Antwort der KI übernehmen: Beutewörter an die Einträge, Karten in die Beutekartei."""
    if not isinstance(daten, dict):
        raise CmdError("Erwartet wird ein JSON-Objekt mit „beute“ und „kartei“")
    n_b = n_k = 0
    for x in daten.get("beute") or []:
        if not isinstance(x, dict):
            continue
        ref, wort = str(x.get("ref") or ""), str(x.get("wort") or "").strip()[:60]
        teile = ref.split(":")
        if not wort:
            continue
        try:
            if teile[0] == "content" and teile[1] in s["content"]:
                e = s["content"][teile[1]][int(teile[2])]
                if not str(e.get("beute") or "").strip():
                    e["beute"] = wort
                    n_b += 1
            elif teile[0] == "deppardy":
                b = next(bb for bb in s["boards"] if bb["id"] == teile[1])
                c = b["cats"][int(teile[2])]
                if not (c.get("bw") or {}).get(teile[3]):
                    c.setdefault("bw", {})[teile[3]] = wort
                    n_b += 1
            elif teile[0] == "atlas":
                e = s["atlasSets"][teile[1]]["eintraege"][int(teile[2])]
                if not str(e.get("beute") or "").strip():
                    e["beute"] = wort
                    n_b += 1
        except (IndexError, KeyError, ValueError, StopIteration):
            continue
    for wort, k in (daten.get("kartei") or {}).items():
        wort = str(wort).strip()[:60]
        if not wort or not isinstance(k, dict):
            continue
        verm = str(k.get("vermerk") or "").strip().lower()
        s["kartei"][wort] = {"art": str(k.get("art") or "")[:30], "def": str(k.get("def") or "")[:300],
                             "herkunft": str(k.get("herkunft") or "")[:200], "vermerk": verm if verm in VERMERKE else ""}
        n_k += 1
    s["beuteImportInfo"] = f"{n_b} Beutewörter und {n_k} Karteikarten übernommen."


def personalakten(s):
    """Wer hat sich am häufigsten umentschieden, wer am meisten gefunkt … – für die Übergabe."""
    ids = by_id(s)
    tr = s.get("tracking") or {}
    verd = {}
    mo = s.get("mole") or {}
    for voter, ziel in (s.get("moleVotes") or {}).items():
        verd[ziel] = verd.get(ziel, 0) + 1
    def spitze(werte):
        werte = {k: v for k, v in werte.items() if k in ids and v > 0}
        if not werte:
            return None
        mx = max(werte.values())
        return {"codes": [ids[k]["code"] for k, v in werte.items() if v == mx], "namen": [ids[k]["name"] for k, v in werte.items() if v == mx], "wert": mx}
    feld = lambda k: {a: t.get(k, 0) for a, t in tr.items()}
    akten = [
        ("wankelmut", "Der Wankelmut", "× umentschieden", spitze(feld("wechsel"))),
        ("treffsicher", "Treffsicher", "× getroffen", spitze(feld("treffer"))),
        ("dauerfunker", "Dauerfunker", "× gefunkt", spitze(feld("funk"))),
        ("buzzer", "Schnellster Finger", "× gebuzzert", spitze(feld("buzz"))),
        ("fleiss", "Aktenfleiß", "Abgaben insgesamt", spitze(feld("abgaben"))),
        ("verdacht", "Unter Verdacht", "× als Maulwurf verdächtigt", spitze(verd) if mo.get("on") else None),
    ]
    return [{"key": k, "titel": t, "was": w, **x} for k, t, w, x in akten if x]


def zell_modus(m):
    return (m or {}).get("zm") if (m or {}).get("zm") in ZELLMODI else "sprecher"


def zell_wertung(s, idx, now):
    """Zellenantwort aus den Vorschlägen der Mitglieder: Mehrheit (eine Stimme pro Person)
    oder Zuversicht (Stimmen nach Schieberegler gewichtet). Rangordnung zählt nach Plätzen (Borda)."""
    m = mission(s)
    team = s["teams"][idx] if idx < len(s["teams"]) else []
    vs = [(aid, s["vorschlaege"][aid]) for aid in team if aid in s["vorschlaege"]]
    if not vs:
        s["teamAnswers"].pop(str(idx), None)
        return
    gew = (lambda x: 1.0) if zell_modus(m) == "mehrheit" else (lambda x: max(0.05, x.get("c", 50) / 100))
    if m["type"] == "ranking":
        n = len(vs[0][1]["v"])
        punkte = {}
        for _, x in vs:
            for pos, l in enumerate(x["v"]):
                punkte[l] = punkte.get(l, 0) + gew(x) * (n - pos)
        # Gleichstand: Reihenfolge des sichersten bzw. frühesten Vorschlags entscheidet
        best = sorted(vs, key=lambda z: (-gew(z[1]), z[1]["t"]))[0][1]["v"]
        v = "".join(sorted(punkte, key=lambda l: (-punkte[l], best.index(l) if l in best else 99)))
    else:
        summe, frueh = {}, {}
        for _, x in vs:
            summe[x["v"]] = summe.get(x["v"], 0) + gew(x)
            frueh[x["v"]] = min(frueh.get(x["v"], x["t"]), x["t"])
        v = sorted(summe, key=lambda k: (-summe[k], frueh[k]))[0]
    alt = s["teamAnswers"].get(str(idx)) or {}
    s["teamAnswers"][str(idx)] = {"v": v, "t": alt["t"] if alt.get("v") == v and alt.get("by") == "zelle" else now,
                                  "by": "zelle", "n": len(vs)}


def zellen_vorschlag(s, m, aid, v, a, now):
    """Eingabe eines Zellenmitglieds: immer als Vorschlag sichtbar für die eigene Zelle (Live-Ansicht)."""
    idx = team_of(s, aid)
    if idx is None:
        raise CmdError("Du bist in keiner Zelle")
    try:
        c = max(0, min(100, int(a.get("c", 50))))
    except (TypeError, ValueError):
        c = 50
    s["vorschlaege"][aid] = {"v": v, "c": c, "t": now}
    if zell_modus(m) == "sprecher":
        if a.get("kind") != "vorschlag":
            s["teamAnswers"][str(idx)] = {"v": v, "t": now, "by": aid}
    else:
        zell_wertung(s, idx, now)


def takt_wert(s, m, t):
    """Zeittakt: im ersten Takt volle Wörter, danach je Takt die Hälfte (mindestens 1)."""
    takt = int((m or {}).get("takt") or 0)
    if takt <= 0 or m["type"] not in TAKT_SPIELE:
        return step(m)
    stufe = max(0, int((t - s["rnd"].get("t0", t)) // takt))
    return max(1, jround(step(m) * 0.5 ** stufe))


def umlagern(s, thief, vic, ziel=None):
    """Wörter aus einem fremden Rucksack nehmen – in den eigenen oder in einen anderen fremden."""
    ids = by_id(s)
    ziel = ziel or thief
    if not (thief and vic in ids and thief in ids and ziel in ids):
        raise CmdError("Ungültig")
    if vic == thief:
        raise CmdError("Nicht aus dem eigenen Rucksack")
    if vic == ziel:
        raise CmdError("Quelle und Ziel sind derselbe Rucksack")
    amt, an = umlager_menge(s, vic)
    s["scores"][vic] = s["scores"].get(vic, 0) - amt
    s["scores"][ziel] = s["scores"].get(ziel, 0) + an
    s["stealLog"].append({"thief": thief, "victim": vic, "ziel": ziel, "amt": amt, "an": an, "cur": s["cur"]})
    rest = f" – angekommen sind {an}" if an != amt else ""
    wohin = "" if ziel == thief else f" in den Rucksack von {ids[ziel]['code']}"
    steal_weiter(s, f"{ids[thief]['code']} hat {amt} Wörter aus dem Rucksack von {ids[vic]['code']}{wohin} umgelagert{rest}.")
    cue(s, "umlagern")


def verzichten(s):
    ids = by_id(s)
    text = ""
    if s["thief"]:
        bonus = s.get("verzichtBonus", 0)
        s["stealLog"].append({"thief": s["thief"], "victim": None, "amt": 0, "cur": s["cur"], "verzicht": True, "bonus": bonus})
        if s["thief"] in ids:
            s["scores"][s["thief"]] = s["scores"].get(s["thief"], 0) + bonus
            text = f"{ids[s['thief']]['code']} hätte umlagern dürfen – und hat verzichtet." + (
                f" Die Zentrale dankt mit {bonus} Wörtern." if bonus else "")
        cue(s, "verzicht")
        steal_weiter(s, text)
    else:
        s.update({"pendingSteal": None, "thief": None})


def beute_pruefen(s):
    """Ist das Beutewort der laufenden Runde wirklich geborgen? Nur wenn jemand in dieser Runde
    Wörter bekommen hat – sonst erscheint die Karte ausgegraut und zählt nicht als gerettet."""
    m = mission(s)
    if not m or not s.get("active") or s.get("phase") != "play":
        return
    if m["type"] == "deppardy":
        d = s.get("dep")
        if not d or not d.get("cell") or d["stage"] < 2:
            return
        c = d["cell"]
        wort = str((d["board"]["cats"][c["c"]].get("bw") or {}).get(str(c["p"])) or "").strip()
        rk = f"{s['cur']}:d{c['c']}|{c['p']}"
        u0 = d.get("u0") or {}
        ok = any(v > u0.get(k, 0) for k, v in s["upts"].items())
    else:
        if not s["revealed"] or not item(s):
            return
        wort = beute_von(item(s), m["type"])
        rk = f"{s['cur']}:{s['round']}"
        if m["type"] == "atlas":
            ok = any(r.get("pts", 0) >= ATLAS_GEBORGEN for r in (s.get("atlasRes") or {}).values())
        else:
            g0 = s["rnd"].get("g0") or {}
            ok = any(v > g0.get(k, 0) for k, v in s["gains"].items())
    for b in s["beute"]:
        if b.get("wort") == wort and b.get("rk") == rk:
            b["verloren"] = not ok


def board_wert(b):
    return sum(p * (2 if (c.get("rk") or {}).get(str(p)) else 1)
               for c in b.get("cats", []) for p in b.get("pts", []) if (c.get("qh") or {}).get(str(p)))


def max_woerter(s):
    """Wie viele Wörter könnte die Zelle laut Einsatzplan höchstens bergen? Grundlage für das Auto-Ziel."""
    n = len(s["agents"])
    if n == 0:
        return 0
    t = max(1, min(s.get("teamCount", 2), n))
    summe = 0.0
    for m in s["plan"]:
        r, p, typ = m.get("rounds", 1), m.get("pts", 0), m["type"]
        if typ == "schaetzen" or typ == "emoji":
            summe += r * p
        elif typ in ("zoom", "sound"):
            summe += r * (p + 1)
        elif typ == "ranking":
            summe += r * (p * n + math.ceil(n / t))
        elif typ in ("hoeher", "woerterbuch", "schwaerzung"):
            summe += r * p * n
        elif typ == "impostor":
            summe += r * p * max(0, n - 1)
        elif typ == "deppardy":
            b = next((x for x in s["boards"] if x["id"] == m.get("opt")), None) or (s["boards"] or [None])[0]
            if b:
                summe += board_wert(b) / kurs(m) * (n / t if m["mode"] == "team" else 1)
        elif typ == "atlas":
            summe += r * 100 / kurs(m) * n
    mo = s.get("mole") or {}
    if mo.get("on") and n > 1:                      # der Rucksack des Maulwurfs zählt nicht
        summe *= (n - 1) / n
    return jround(summe)


def closest_ids(s):
    it = item(s)
    target = num((it or {}).get("a"))
    if target is None:
        return []
    diffs = []
    for aid, ans in s["answers"].items():
        g = num(ans.get("v"))
        if g is not None:
            diffs.append((aid, abs(g - target)))
    if not diffs:
        return []
    md = min(d for _, d in diffs)
    return [aid for aid, d in diffs if d == md]


def rank_code(s):
    ln = lines_of(item(s))
    order = s["rnd"].get("order") or []
    if len(order) != len(ln):
        order = list(range(len(ln)))
    return "".join(LETTERS[order.index(i)] for i in range(len(ln)))


def hoeher_correct(s):
    it = item(s) or {}
    a, b = num(it.get("av")), num(it.get("bv"))
    if a is None or b is None or a == b:
        return None
    return "A" if a > b else "B"


def team_correct(s, idx):
    m = mission(s)
    ans = (s["teamAnswers"].get(str(idx)) or {}).get("v")
    if not ans:
        return False
    if m["type"] == "ranking":
        return ans == rank_code(s)
    if m["type"] == "hoeher":
        return ans == propaganda_wahr(s)
    return False


def propaganda_wahr(s):
    """„W“, wenn die Behauptung des Amtes stimmt, sonst „P“ (Propaganda)."""
    richtig = hoeher_correct(s)
    if not richtig:
        return None
    return "W" if s["rnd"].get("claim") == richtig else "P"


def schwarz_wort(it):
    mt = re.search(r"\[\[(.+?)\]\]", (it or {}).get("text", ""))
    return mt.group(1).strip() if mt else ""


def beute_von(it, typ):
    """Beutewort einer Runde – bei Wörterbuch und Schwärzung notfalls das Wort selbst."""
    b = str((it or {}).get("beute") or "").strip()
    if b:
        return b
    if typ == "woerterbuch":
        return str((it or {}).get("wort") or "").strip()
    if typ == "schwaerzung":
        return schwarz_wort(it)
    return ""


def zoom_wert(m, z):
    """Stufe 1–2: ein Wort extra, Stufe 5–6: eins weniger (mindestens 1)."""
    return max(1, step(m) + (1 if z <= 1 else 0) - (1 if z >= 4 else 0))


def normtext(t):
    t = str(t or "").lower().replace("ß", "ss")
    for x, y in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        t = t.replace(x, y)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\b(der|die|das|den|dem|des|ein|eine|einen|the|a|an|le|la)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    vor = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        jetzt = [i]
        for j, cb in enumerate(b, 1):
            jetzt.append(min(vor[j] + 1, jetzt[j - 1] + 1, vor[j - 1] + (ca != cb)))
        vor = jetzt
    return vor[-1]


def wohl_richtig(antwort, loesung):
    """Nur ein Hinweis für die Moderation – entschieden wird von Hand."""
    a, b = normtext(antwort), normtext(loesung)
    if not a or not b:
        return False
    if a == b or (len(a) >= 4 and (a in b or b in a)):
        return True
    return levenshtein(a, b) <= max(1, min(3, len(b) // 5))


def wb_werten(s, m):
    """Echte Bedeutung gefunden: +pts. Fälschung gewählt: der Fälscher bekommt 1 Wort pro getäuschter Person."""
    r = s["rnd"]
    opt = r.get("optionen") or []
    erg = {"echt": [], "getaeuscht": {}}
    for voter, nr in s["votes"].items():
        if not isinstance(nr, int) or nr >= len(opt):
            continue
        ziel = opt[nr]["id"]
        if ziel == "echt":
            add_gain(s, voter, step(m))
            track(s, voter, "treffer")
            erg["echt"].append(voter)
        elif ziel != voter:
            add_gain(s, ziel, 1)
            erg["getaeuscht"].setdefault(ziel, []).append(voter)
    r["ergebnis"] = erg
    r["wbPhase"] = "aufgedeckt"


def bet_cap(s, aid):
    """Höchsteinsatz: der aktuelle Rucksack – inklusive der in dieser Mission gewonnenen und verlorenen Wörter."""
    return max(total(s, aid), 2)


def vote_tally(s):
    t = {}
    for target in s["votes"].values():
        t[target] = t.get(target, 0) + 1
    return t


def finish(s):
    m = mission(s)
    nach = (((s.get("story") or {}).get("missionen") or {}).get(m["type"], {}) if m else {}).get("nach", "")
    s["funk"] = {"ort": ((s.get("story") or {}).get("missionen") or {}).get(m["type"], {}).get("ort", ""), "text": nach} if nach else None
    for aid, g in s["gains"].items():
        s["scores"][aid] = max(0, s["scores"].get(aid, 0) + g)
    vals = [s["gains"].get(a["id"], 0) for a in s["agents"]]
    mx = max([0] + vals)
    winners = [a["id"] for a in s["agents"] if mx > 0 and s["gains"].get(a["id"], 0) == mx]
    steal = bool(winners) and s["stealAmount"] > 0 and m
    s.update({"gains": {}, "cur": s["cur"] + 1, "active": False, "screen": "hq", "phase": "intro",
              "lastSteal": None, "pendingSteal": {"winners": winners} if steal else None,
              "thief": winners[0] if steal and len(winners) == 1 else None,
              "rnd": {}, "answers": {}, "teamAnswers": {}, "feed": [], "open": False})


def umlager_menge(s, vic):
    """Wie viel wird genommen, wie viel kommt an? Prozent vom fremden Rucksack, mindestens stealAmount;
    ein Teil nimmt beim Umlagern Schaden (stealVerlust %)."""
    hat = s["scores"].get(vic, 0)
    amt = min(hat, max(s["stealAmount"], jround(hat * s.get("stealPct", 0) / 100)))
    an = amt - (amt * s.get("stealVerlust", 0)) // 100
    return amt, an


def ziel_wert(s):
    z = s.get("ziel", -1)
    if z < 0:
        mx = max_woerter(s)
        return max(1, jround(mx * s.get("zielProzent", 50) / 100)) if mx else 8 * len(s["agents"])
    return z


def ziel_stand(s, ohne_maulwurf=True):
    mo = s.get("mole") or {}
    raus = mo.get("id") if ohne_maulwurf and mo.get("on") else None
    return sum(total(s, a["id"]) for a in s["agents"] if a["id"] != raus)


def birg(s, wort, spiel=None):
    """Ein Beutewort in die Liste des Abends aufnehmen (jedes Wort nur einmal)."""
    wort = str(wort or "").strip()
    if not wort:
        return
    m = mission(s)
    d = s.get("dep") if m and m["type"] == "deppardy" else None
    rk = f"{s['cur']}:d{d['cell']['c']}|{d['cell']['p']}" if d and d.get("cell") else f"{s['cur']}:{s['round']}"
    alt = next((b for b in s["beute"] if b.get("wort") == wort), None)
    if alt:
        if alt.get("verloren") and alt.get("rk") != rk:     # zweite Chance für ein verlorenes Wort
            alt["rk"] = rk
        return
    ms = ((s.get("story") or {}).get("missionen") or {}).get(m["type"], {}) if m else {}
    tage = (s.get("story") or {}).get("tage", 7)
    tag = max(1, tage - math.ceil(stunden_uebrig(s) / 24) + 1)
    s["beute"].append({"wort": wort, "ort": ms.get("ort", ""), "spiel": GAMES[m["type"]]["name"] if m else (spiel or ""),
                       "tag": tag, "rk": rk, "verloren": True})


def karte(s, wort, info=None):
    """Karteikarte zu einem Beutewort – Einträge aus der Beutekartei, Fundort aus der Beuteliste."""
    wort = str(wort or "").strip()
    if not wort:
        return None
    k = dict((s.get("kartei") or {}).get(wort) or {})
    b = info or next((x for x in s["beute"] if x.get("wort") == wort), {})
    nr = next((i + 1 for i, x in enumerate(s["beute"]) if x.get("wort") == wort), None)
    return {"wort": wort, "art": k.get("art", ""), "def": k.get("def", ""), "herkunft": k.get("herkunft", ""),
            "vermerk": k.get("vermerk", ""), "ort": b.get("ort", ""), "spiel": b.get("spiel", ""),
            "tag": b.get("tag"), "nr": nr, "verloren": bool(b.get("verloren"))}


def prolog_tafeln(s):
    """Tafeln mit „maulwurf“: nur zeigen, wenn der Maulwurf eingeschaltet ist."""
    on = bool((s.get("mole") or {}).get("on"))
    return [t for t in ((s.get("story") or {}).get("prolog") or []) if on or not t.get("maulwurf")]


def jround(x):
    return int(math.floor(x + 0.5))


def units(s, m=None):
    """Wertungseinheiten: einzelne Agenten oder Zellen."""
    m = m or mission(s)
    ids = by_id(s)
    if m and m["mode"] == "team" and s["teams"]:
        return [{"key": f"t{i}", "label": "Zelle " + TEAMS[i], "members": [x for x in t if x in ids]}
                for i, t in enumerate(s["teams"])]
    return [{"key": a["id"], "label": a["code"], "members": [a["id"]]} for a in s["agents"]]


def unit_of(s, aid):
    for u in units(s):
        if aid in u["members"]:
            return u
    return None


def kurs(m):
    """Punkte pro Wort für Deppardy und Atlas – steht im Einsatzplan im Feld „pts“."""
    if m and GAMES[m["type"]].get("kurs") and m.get("pts", 0) > 0:
        return m["pts"]
    return 100


def sync_gains(s):
    """Deppardy und Atlas zählen Punkte je Einheit; umgerechnet wird mit dem Kurs der Mission."""
    g, k = {}, kurs(mission(s))
    for u in units(s):
        w = jround(s["upts"].get(u["key"], 0) / k)
        for aid in u["members"]:
            g[aid] = w
    s["gains"] = g


def km_zwischen(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(min(1, math.sqrt(h)))


def atlas_wertung(tip, it):
    """Wie im ursprünglichen Atlas: Volltreffer 100, sonst exp. Abfall (1200 km), Nachbarn mind. 55."""
    ziele = [str(it.get("land"))] + [str(x) for x in it.get("auchOk", [])]
    ziele = [z for z in ziele if z in GEO]
    if not ziele or tip not in GEO:
        return None
    if tip in ziele:
        return {"tip": tip, "ziel": tip, "pts": 100, "km": 0, "hit": True, "nb": False}
    km, z = min((km_zwischen(GEO[tip]["c"], GEO[k]["c"]), k) for k in ziele)
    nb = z in GEO[tip]["n"]
    p = jround(100 * math.exp(-km / 1200))
    if nb:
        p = max(p, 55)
    return {"tip": tip, "ziel": z, "pts": p, "km": round(km), "hit": False, "nb": nb}


def atlas_tips(s):
    """Tipp je Einheit (Zelle: Zellenantwort, einzeln: eigene Antwort)."""
    out = {}
    for u in units(s):
        if u["key"].startswith("t"):
            a = s["teamAnswers"].get(u["key"][1:])
        else:
            a = s["answers"].get(u["key"])
        if a:
            out[u["key"]] = a["v"]
    return out


def dep_value(d):
    c = d.get("cell")
    if not c:
        return 0
    cat = d["board"]["cats"][c["c"]]
    return c["p"] * (2 if (cat.get("rk") or {}).get(str(c["p"])) else 1)


def strip_html(h):
    t = re.sub(r"<(br|/p|/div|/li)[^>]*>", " ", h or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")).strip()


DATA_URI = re.compile(r"data:(image|audio)/([a-z0-9.+-]+);base64,([A-Za-z0-9+/=]+)", re.I)


def media_aus_datauri(html):
    """Eingebettete Bilder/Töne aus alten Deppardy-Boards als Dateien ablegen – die Seiten bleiben leicht."""
    def ersetze(mt):
        ext = {"jpeg": ".jpg", "svg+xml": ".svg", "mpeg": ".mp3", "x-m4a": ".m4a", "mp4": ".m4a"}.get(mt.group(2).lower(), "." + mt.group(2).lower())
        name = "dep-" + secrets.token_hex(5) + ext
        try:
            with open(os.path.join(MEDIA, name), "wb") as f:
                f.write(base64.b64decode(mt.group(3)))
        except Exception:
            return mt.group(0)
        return "/media/" + name
    return DATA_URI.sub(ersetze, html or "")


def board_normal(b):
    pts = sorted({int(p) for p in b.get("pts", []) if str(p).strip().lstrip("-").isdigit() and int(p) > 0})
    cats = []
    for c in b.get("cats", []):
        cat = {"name": str(c.get("name", "Kategorie"))[:60], "qh": {}, "hh": {}, "ah": {}, "rk": {}, "bw": {}}
        alt = {"qh": "qs", "ah": "ans"}             # Deppardy v4: Klartext-Felder als Rückfall
        for key in ("qh", "hh", "ah"):
            src = c.get(key) if isinstance(c.get(key), dict) else {}
            fb = c.get(alt.get(key, ""), {}) if isinstance(c.get(alt.get(key, "")), dict) else {}
            for p in pts:
                v = src.get(str(p)) or fb.get(str(p))
                if v:
                    cat[key][str(p)] = media_aus_datauri(str(v))
        for p in pts:
            if (c.get("rk") or {}).get(str(p)):
                cat["rk"][str(p)] = True
            bw = str((c.get("bw") or {}).get(str(p)) or "").strip()
            if bw:
                cat["bw"][str(p)] = bw[:60]
        cats.append(cat)
    return {"id": str(b.get("id") or uid()), "name": str(b.get("name") or "Board")[:80], "pts": pts, "cats": cats}


class CmdError(Exception):
    pass


BRAUCHT_MISSION = {"mission_begin", "round_next", "round_skip", "reveal", "zoom_out", "show_q", "gain", "gain_team",
                   "set_answer", "set_bet", "set_team_answer", "award_closest", "award_teams", "judge", "spy_award",
                   "upts_adj", "teams_count", "teams_reroll"}


def host_cmd(s, c, a):
    """Alle Befehle des Steuermoduls. a = Argumente als dict."""
    _host_cmd(s, c, a)
    beute_pruefen(s)


def _host_cmd(s, c, a):
    m = mission(s)
    ids = by_id(s)
    if c in BRAUCHT_MISSION and (not m or not s["active"]):
        raise CmdError("Gerade läuft keine Mission")

    if c == "agent_add":
        name = str(a.get("name", "")).strip()[:40]
        if not name:
            raise CmdError("Name fehlt")
        s["agents"].append({"id": uid(), "name": name, "code": free_code(s), "token": secrets.token_urlsafe(12)})
    elif c == "agent_del":
        s["agents"] = [x for x in s["agents"] if x["id"] != a.get("id")]
        if s["mole"]["id"] == a.get("id"):
            s["mole"]["id"] = None
        s["teams"] = [[i for i in t if i != a.get("id")] for t in s["teams"]]
    elif c == "agent_rename":
        for x in s["agents"]:
            if x["id"] == a.get("id"):
                x["name"] = str(a.get("name", "")).strip()[:40] or x["name"]
    elif c == "agent_reroll":
        for x in s["agents"]:
            if x["id"] == a.get("id"):
                x["code"] = free_code(s, x["code"])
    elif c == "agents_clear":
        s["agents"], s["scores"], s["gains"], s["teams"] = [], {}, {}, []
        s["mole"]["id"], s["moleVotes"] = None, {}
    elif c == "score_adj":
        aid = a.get("id")
        s["scores"][aid] = max(0, s["scores"].get(aid, 0) + int(a.get("d", 0)))
    elif c == "join_toggle":
        s["joinOpen"] = not s["joinOpen"]
    elif c == "settings":
        grenzen = {"stealAmount": (0, 99), "stealPct": (0, 100), "stealVerlust": (0, 100),
                   "verzichtBonus": (0, 20), "ziel": (-1, 9999)}
        for k, (lo, hi) in grenzen.items():
            if k in a:
                s[k] = max(lo, min(hi, int(a[k] if a[k] not in ("", None) else lo)))
        if "zielProzent" in a:
            s["zielProzent"] = max(1, min(100, int(a["zielProzent"] or 50)))
        for k in ("depArm", "namenZeigen", "beispiel", "schluesselloch"):
            if k in a:
                s[k] = bool(a[k])
    elif c == "plan_set":
        plan = []
        for p in a.get("plan", []):
            if p.get("type") in GAMES:
                plan.append({"id": p.get("id") or uid(), "type": p["type"],
                             "mode": "team" if p.get("mode") == "team" else "solo",
                             "pts": max(0, int(p.get("pts", 0))), "rounds": max(1, int(p.get("rounds", 1))),
                             "opt": str(p.get("opt") or ""),
                             "zm": p.get("zm") if p.get("zm") in ZELLMODI else "sprecher",
                             "takt": max(0, min(300, int(p.get("takt") or 0)))})
        s["plan"] = plan
        s["cur"] = max(0, min(int(a.get("cur", s["cur"])), len(plan)))
    elif c == "plan_reset":
        s.update({"plan": make_plan(), "cur": 0, "active": False})
    elif c == "content_set":
        t = a.get("type")
        if t not in FIELDS:
            raise CmdError("Unbekannter Typ")
        keys = [f[0] for f in FIELDS[t]]
        s["content"][t] = [dict({k: str(e.get(k, "")) for k in keys}, **({"aus": True} if e.get("aus") else {}))
                           for e in a.get("list", [])]
    elif c == "content_restore":
        t = a.get("type")
        s["content"][t] = copy.deepcopy(SAMPLES.get(t, []))
    elif c == "screen":
        if a.get("name") in ("start", "prolog", "hq", "finale"):
            if a["name"] == "finale" and s["screen"] != "finale":
                s["finaleStufe"] = 0
            if a["name"] == "prolog" and s["screen"] != "prolog":
                s["prologIdx"] = 0
                cue(s, "tafel")
            if a["name"] == "finale" and s["screen"] != "finale":
                cue(s, "uebergabe")
            s["screen"] = a["name"]
    elif c == "prolog_step":
        n = len(prolog_tafeln(s))
        alt = s["prologIdx"]
        s["prologIdx"] = max(0, min(n - 1, s["prologIdx"] + int(a.get("d", 1))))
        if s["prologIdx"] > alt:
            cue(s, "tafel")
    elif c == "finale_step":
        stufen = finale_stufen(s)
        alt = s["finaleStufe"]
        s["finaleStufe"] = max(0, min(len(stufen) - 1, s["finaleStufe"] + int(a.get("d", 1))))
        if s["finaleStufe"] > alt and stufen[s["finaleStufe"]] == "ziel":
            cue(s, "gerettet" if ziel_stand(s) >= ziel_wert(s) else "verloren")
    # ---- Maulwurf ---------------------------------------------------------
    elif c == "mole_toggle":
        s["mole"]["on"] = bool(a.get("on"))
        if s["mole"]["on"] and not s["mole"]["id"] and s["agents"]:
            s["mole"]["id"] = random.choice(s["agents"])["id"]
    elif c == "mole_pick":
        if s["mole"]["result"]:
            raise CmdError("Der Maulwurf ist schon aufgeflogen")
        others = [x["id"] for x in s["agents"] if x["id"] != s["mole"]["id"]] or [x["id"] for x in s["agents"]]
        s["mole"]["id"] = random.choice(others) if others else None
        s["moleVotes"] = {}
    elif c == "mole_bonus":
        s["mole"]["bonus"] = max(0, min(50, int(a.get("n", 5))))
    elif c == "mole_vote":
        s["mole"]["voteOpen"] = bool(a.get("on"))
    elif c == "mole_resolve":
        mo = s["mole"]
        if mo["result"]:
            raise CmdError("Schon aufgelöst")
        if mo["id"] not in ids:
            raise CmdError("Kein Maulwurf bestimmt")
        tally = {}
        for voter, target in s["moleVotes"].items():
            if voter != mo["id"] and voter in ids and target in ids:
                tally[target] = tally.get(target, 0) + 1
        top = tally.get(mo["id"], 0)
        caught = top > 0 and all(n < top for k, n in tally.items() if k != mo["id"])
        others = [x["id"] for x in s["agents"] if x["id"] != mo["id"]]
        res = {"caught": caught, "tally": tally, "anteil": 0, "bonus": mo["bonus"]}
        if caught and others:
            beute = s["scores"].get(mo["id"], 0)
            res["anteil"] = beute // len(others)
            for o in others:
                s["scores"][o] = s["scores"].get(o, 0) + res["anteil"]
            s["scores"][mo["id"]] = beute - res["anteil"] * len(others)
        elif not caught:
            # Die Prämie zahlt das Amt für Reinsprache aus eigener Kasse – kein Rucksack der Zelle wird angetastet
            s["scores"][mo["id"]] = s["scores"].get(mo["id"], 0) + mo["bonus"]
            res["praemie"] = mo["bonus"]
        mo["result"], mo["voteOpen"] = res, False
        cue(s, "enttarnt" if caught else "entkommen")
    elif c == "story_set":
        st = a.get("story") or {}
        s["story"] = {
            "zelle": str(st.get("zelle", ""))[:40], "tage": max(1, min(30, int(st.get("tage") or 7))),
            "auftrag": str(st.get("auftrag", ""))[:200],
            "prolog": [{"titel": str(t.get("titel", ""))[:60], "text": str(t.get("text", ""))[:600],
                        **({"maulwurf": True} if t.get("maulwurf") else {}),
                        **({"motiv": str(t["motiv"])[:20]} if t.get("motiv") else {})} for t in st.get("prolog", [])][:12],
            "missionen": {k: {"ort": str(v.get("ort", ""))[:60], "lage": str(v.get("lage", ""))[:400],
                              "nach": str(v.get("nach", ""))[:400]}
                          for k, v in (st.get("missionen") or {}).items() if k in GAMES},
            "finale": {k: str(v)[:400] for k, v in (st.get("finale") or {}).items()},
            "maulwurf": {k: str(v)[:500] for k, v in (st.get("maulwurf") or {}).items()},
            "epilog": [{"titel": str(t.get("titel", ""))[:60], "text": str(t.get("text", ""))[:600]}
                       for t in st.get("epilog", []) if isinstance(t, dict)][:8],
            "abspann": str(st.get("abspann", ""))[:3000],
        }
    elif c == "impressum_set":
        s["impressum"] = str(a.get("text") or "")[:5000]
    elif c == "beute_import":
        beute_import(s, a.get("daten"))
    elif c == "story_restore":
        s["story"] = vorlage("drehbuch.json", {})
    elif c == "test_start":
        if s.get("test"):
            test_ende(s)
        t = a.get("type")
        if t not in GAMES or GAMES[t].get("ereignis"):
            raise CmdError("Unbekanntes Spiel")
        if s["active"] and not a.get("trotzdem"):
            raise CmdError("Es läuft gerade eine Mission – erst abschließen oder abbrechen")
        g = GAMES[t]
        sicher = {k: copy.deepcopy(s.get(k)) for k in TEST_SICHERN}
        test = {"sicher": sicher, "type": t, "i": a.get("i"), "atlas": a.get("atlas")}
        mode = "team" if a.get("mode") == "team" else (g["mode"] if a.get("mode") is None else "solo")
        s["test"] = test
        s.update({"plan": [{"id": "test", "type": t, "mode": mode, "pts": int(a.get("pts") or g["pts"]), "rounds": 1 if t != "deppardy" else 1,
                            "opt": str(a.get("board") or ""), "zm": a.get("zm") if a.get("zm") in ZELLMODI else "sprecher",
                            "takt": int(a.get("takt") or 0)}], "cur": 0, "active": False})
        if t == "atlas" and a.get("atlas"):
            s["plan"][0]["rounds"] = 1
        _host_cmd(s, "mission_start", {})
    elif c == "test_ende":
        if s.get("test"):
            test_ende(s)
    elif c == "mission_start":
        if not m:
            raise CmdError("Keine Mission mehr offen")
        if not s["agents"] and not s.get("test"):
            raise CmdError("Noch keine Agenten")
        if s["mole"]["on"] and s["mole"]["id"] not in ids:
            s["mole"]["id"] = random.choice(s["agents"])["id"]
        if s["active"]:
            s["screen"] = "mission"
        else:
            s.update({"screen": "mission", "active": True, "phase": "intro", "round": 0, "gains": {},
                      "revealed": False, "lastSteal": None, "pendingSteal": None, "thief": None,
                      "teams": roll_teams(s, s["teamCount"]) if m["mode"] == "team" else [],
                      "rnd": {}, "answers": {}, "teamAnswers": {}, "feed": [], "open": False,
                      "upts": {}, "dep": None, "atlasRes": None, "atlasOrder": [], "funk": None, "vorschlaege": {}})
            cue(s, "einsatz")
    elif c == "mission_abort" and s.get("test"):
        test_ende(s)
    elif c == "mission_abort":
        s.update({"screen": "hq", "active": False, "phase": "intro", "gains": {}, "rnd": {},
                  "answers": {}, "teamAnswers": {}, "feed": [], "open": False})
    elif c == "teams_count":
        n = max(2, min(4, int(a.get("n", 2))))
        s["teamCount"] = n
        s["teams"] = roll_teams(s, n)
    elif c == "teams_reroll":
        s["teams"] = roll_teams(s, s["teamCount"])
    elif c == "mission_begin":
        if not m:
            raise CmdError("Keine Mission")
        if m["type"] == "maulwurf_los":              # Rollen verteilen, verdeckt auf jedem Gerät
            s["mole"]["on"] = True
            if s["mole"]["id"] not in ids and s["agents"]:
                s["mole"]["id"] = random.choice(s["agents"])["id"]
            s.update({"phase": "play", "rnd": {"ereignis": True}, "revealed": False, "open": False})
        elif m["type"] == "maulwurf_wahl":
            s["mole"]["on"] = True
            if s["mole"]["id"] not in ids and s["agents"]:
                s["mole"]["id"] = random.choice(s["agents"])["id"]
            if not s["mole"]["result"]:
                s["mole"]["voteOpen"] = True
            s.update({"phase": "play", "rnd": {"ereignis": True}, "revealed": False, "open": False})
        elif m["type"] == "deppardy":
            b = next((x for x in s["boards"] if x["id"] == m.get("opt")), None) or (s["boards"] or [None])[0]
            if not b:
                raise CmdError("Im Archiv gibt es noch kein Deppardy-Board")
            s["dep"] = {"board": copy.deepcopy(b), "revealed": {}, "cell": None, "stage": 0,
                        "dur": s.get("depDur", 30), "tRun": False, "tEnd": 0, "tLeft": 0, "buzz": [], "wrong": []}
            s.update({"phase": "play", "rnd": {}, "revealed": False, "open": False})
        elif m["type"] == "atlas":
            sets = [m["opt"]] if m.get("opt") in s["atlasSets"] else list(s["atlasSets"].keys())
            pool = [(k, i) for k in sets for i, e in enumerate(s["atlasSets"][k].get("eintraege") or []) if not e.get("aus")]
            if (s.get("test") or {}).get("atlas"):
                pool = [tuple(s["test"]["atlas"])]
            if not pool:
                raise CmdError("Im Archiv gibt es keine Atlas-Begriffe")
            random.shuffle(pool)
            s["atlasOrder"] = pool
            s["phase"] = "play"
            round_state(s, 0)
        else:
            s["phase"] = "play"
            round_state(s, 0)
        cue(s, "los")
    elif c == "round_next":
        if m and s["round"] < m["rounds"] - 1:
            round_state(s, s["round"] + 1)
    elif c == "round_skip":            # anderes Item ziehen, gleiche Runde
        if m and s["phase"] == "play" and m["type"] != "deppardy":
            if m["type"] == "atlas" and s["atlasOrder"]:
                i = s["round"] % len(s["atlasOrder"])
                s["atlasOrder"].append(s["atlasOrder"].pop(i))
            round_state(s, s["round"])
    elif c == "open":
        s["open"] = bool(a.get("on"))
    elif c == "reveal":
        if m and m["type"] == "atlas" and not s["revealed"] and item(s):
            res = {}
            for key, tip in atlas_tips(s).items():
                r = atlas_wertung(tip, item(s))
                if r:
                    res[key] = r
                    s["upts"][key] = s["upts"].get(key, 0) + r["pts"]
            s["atlasRes"] = res
            sync_gains(s)
        if not s["revealed"]:
            cue(s, "aufdecken")
        s["revealed"], s["open"] = True, False
        if m and m["type"] == "woerterbuch" and s["rnd"].get("wbPhase") == "abstimmen":
            wb_werten(s, m)
        bw = beute_von(item(s), m["type"] if m else "")
        if bw and m and m["type"] == "woerterbuch" and bw not in s["kartei"]:
            it = item(s)                           # Karte aus dem Wörterbuch-Eintrag anlegen
            s["kartei"][bw] = {"art": it.get("art", ""), "def": it.get("def", ""), "herkunft": "", "vermerk": "alt"}
        birg(s, bw)
        if m and m["type"] == "sound":
            s["zoomStep"] = len(ZOOM) - 1
        if m and m["type"] == "zoom":
            s["zoomStep"] = len(ZOOM) - 1
    elif c == "zoom_out":
        s["zoomStep"] = min(len(ZOOM) - 1, s["zoomStep"] + 1)
    elif c == "show_q":
        s["showQ"], s["open"] = True, True
    elif c == "gain":
        add_gain(s, a.get("id"), int(a.get("d", 0)))
        if int(a.get("d", 0)) > 0:
            cue(s, "treffer")
    elif c == "gain_team":
        for aid in s["teams"][int(a.get("idx"))]:
            add_gain(s, aid, int(a.get("d", 0)))
        if int(a.get("d", 0)) > 0:
            cue(s, "treffer")
    elif c == "set_answer":               # Moderation trägt für Agenten ohne Gerät ein
        aid, v = a.get("id"), str(a.get("v", "")).strip()[:80]
        if v:
            s["answers"][aid] = {"v": v, "t": time.time(), "by": "leitung"}
        else:
            s["answers"].pop(aid, None)
    elif c == "set_bet":
        aid = a.get("id")
        s["bets"][aid] = max(0, min(int(a.get("v") or 0), bet_cap(s, aid)))
    elif c == "set_team_answer":
        v = str(a.get("v", "")).upper().strip()[:8]
        if m["type"] == "ranking" and v:
            n = len(lines_of(item(s)))
            if len(v) != n or sorted(v) != list(LETTERS[:n]):
                raise CmdError("Jeder Begriff genau einmal")
        if v:
            s["teamAnswers"][str(int(a["idx"]))] = {"v": v, "t": time.time(), "by": "leitung"}
    elif c == "award_closest":
        if not s["awarded"]:
            for aid in closest_ids(s):
                add_gain(s, aid, step(m))
                track(s, aid, "treffer")
            if closest_ids(s):
                cue(s, "treffer")
            s["awarded"] = True
    elif c == "award_teams":
        if not s["awarded"]:
            richtig = [i for i in range(len(s["teams"])) if team_correct(s, i)]
            for i in richtig:
                for aid in s["teams"][i]:
                    add_gain(s, aid, step(m))
                    track(s, aid, "treffer")
            if m["type"] == "ranking" and richtig:           # schnellste richtige Zelle: ein Wort extra
                schnell = min(richtig, key=lambda i: s["teamAnswers"][str(i)]["t"])
                for aid in s["teams"][schnell]:
                    add_gain(s, aid, 1)
                s["rnd"]["schnellste"] = schnell
            if richtig:
                cue(s, "treffer")
            s["awarded"] = True
    elif c == "judge":
        aid, ok = a.get("id"), bool(a.get("ok"))
        if m["type"] == "wette":
            if aid in s["betDone"]:
                raise CmdError("Schon gewertet")
            b = max(0, min(int(s["bets"].get(aid, 0)), bet_cap(s, aid)))
            # Wer nichts im Rucksack hat, setzt trotzdem 2 – verliert aber nur, was wirklich da ist
            add_gain(s, aid, b if ok else -min(b, total(s, aid)))
            s["betDone"][aid] = "r" if ok else "w"
            if ok and b:
                track(s, aid, "treffer")
                cue(s, "treffer")
        else:
            prev = s["judged"].get(aid)
            wert = step(m)
            i = a.get("i")
            f = s["feed"][int(i)] if i is not None and 0 <= int(i) < len(s["feed"]) else None
            if m["type"] in ("zoom", "sound"):        # Stufe zum Zeitpunkt des Funkspruchs
                wert = zoom_wert(m, f.get("z", 0) if f else s["zoomStep"])
            elif m["type"] in TAKT_SPIELE:            # Zeittakt: wann kam die Antwort?
                t = f["t"] if f else (s["answers"].get(aid) or {}).get("t", time.time())
                wert = takt_wert(s, m, t)
            if ok and prev != "r":
                add_gain(s, aid, wert)
                s["judgedPts"][aid] = wert
                track(s, aid, "treffer")
                cue(s, "treffer")
            if not ok and prev == "r":
                add_gain(s, aid, -s["judgedPts"].pop(aid, step(m)))
            s["judged"][aid] = "r" if ok else "w"
    elif c == "wb_treffer":                    # Fälschung trifft die echte Bedeutung
        r, aid = s["rnd"], a.get("id")
        if r.get("wbPhase") != "faelschen" or aid not in s["answers"]:
            raise CmdError("Nur während des Fälschens")
        if aid in r["treffer"]:
            r["treffer"].remove(aid)
            add_gain(s, aid, -step(m))
        else:
            r["treffer"].append(aid)
            add_gain(s, aid, step(m))
            cue(s, "treffer")
    elif c == "wb_streichen":
        r, aid = s["rnd"], a.get("id")
        if aid in r["gestrichen"]:
            r["gestrichen"].remove(aid)
        else:
            r["gestrichen"].append(aid)
    elif c == "wb_abstimmen":
        r, it = s["rnd"], item(s)
        if r.get("wbPhase") != "faelschen":
            raise CmdError("Abstimmung läuft schon")
        opt = [{"id": "echt", "text": it.get("def", "")}] + [
            {"id": aid, "text": x["v"]} for aid, x in s["answers"].items()
            if aid not in r["treffer"] and aid not in r["gestrichen"] and x["v"].strip()]
        random.shuffle(opt)
        r.update(wbPhase="abstimmen", optionen=opt)
        s.update({"votes": {}, "open": True})
    elif c == "award_schwarz":                 # alle wahrscheinlichen Treffer auf einmal
        neu = 0
        for aid, x in s["answers"].items():
            if aid not in s["judged"] and wohl_richtig(x["v"], schwarz_wort(item(s))):
                wert = takt_wert(s, m, x["t"])
                add_gain(s, aid, wert)
                s["judged"][aid] = "r"
                s["judgedPts"][aid] = wert
                track(s, aid, "treffer")
                neu += 1
        if neu:
            cue(s, "treffer")
    elif c == "spy_award":
        spy = s["rnd"].get("spy")
        if s["spyResult"] or not spy:
            raise CmdError("Schon gewertet")
        if a.get("caught"):
            for x in s["agents"]:
                if x["id"] != spy:
                    add_gain(s, x["id"], step(m))
            s["spyResult"] = "caught"
            cue(s, "treffer")
        else:
            add_gain(s, spy, 2 * step(m))
            s["spyResult"] = "escaped"
    elif c == "audio":
        s["audio"] = {"n": s["audio"].get("n", 0) + 1, "a": a.get("a", "play")}
    elif c == "mission_finish" and s.get("test"):
        test_ende(s)
    elif c == "mission_finish":
        if m:
            beute_pruefen(s)
            cue(s, "ende")
            if m["type"] == "maulwurf_wahl":
                s["mole"]["voteOpen"] = False
        finish(s)
    elif c == "steal_thief":
        if a.get("id") not in ((s["pendingSteal"] or {}).get("winners") or []):
            raise CmdError("Nur wer den Einsatz gewonnen hat, darf umlagern")
        s["thief"] = a.get("id")
    elif c in ("steal_zufall", "steal_alle"):
        w = [x for x in ((s["pendingSteal"] or {}).get("winners") or []) if x in ids]
        if not w:
            raise CmdError("Niemand darf gerade umlagern")
        if c == "steal_zufall":
            s["thief"] = random.choice(w)
        else:                                   # alle Sieger nacheinander, in zufälliger Reihenfolge
            random.shuffle(w)
            s["thief"] = w[0]
            s["pendingSteal"] = dict(s["pendingSteal"], kette=w[1:])
    elif c == "steal_victim":
        umlagern(s, s["thief"], a.get("id"), a.get("ziel"))
    elif c == "steal_skip":
        verzichten(s)
    elif c == "klang_set":
        k, neu = s["klang"], a.get("klang") or {}
        for f in ("an", "signale"):
            if f in neu:
                k[f] = bool(neu[f])
        if "vol" in neu:
            k["vol"] = max(0, min(100, int(neu["vol"] or 0)))
        mu = neu.get("musik") or {}
        for f in ("an",):
            if f in mu:
                k["musik"][f] = bool(mu[f])
        for f in ("url", "spiel"):
            if f in mu:
                k["musik"][f] = str(mu[f] or "")[:300]
        if "vol" in mu:
            k["musik"]["vol"] = max(0, min(100, int(mu["vol"] or 0)))
        gueltig = {x for x, _ in CUES}
        for art, url in (neu.get("cues") or {}).items():
            if art in gueltig:
                if url:
                    k["cues"][art] = str(url)[:300]
                else:
                    k["cues"].pop(art, None)
    elif c == "klang_test":
        cue(s, a.get("art") if a.get("art") in {x for x, _ in CUES} else "treffer")
    elif c == "rausch_set":
        for k, v in (a.get("rausch") or {}).items():
            if k in RAUSCH0:
                s["rausch"][k] = max(0, min(100, int(v or 0)))
    elif c == "rausch_reset":
        s["rausch"] = dict(RAUSCH0)
    elif c == "evening_reset":
        s.update({"stealLog": [], "prologIdx": 0, "finaleStufe": 0, "moleVotes": {}, "beute": [], "funk": None})
        s["mole"].update({"id": None, "voteOpen": False, "result": None})
        s.update({"scores": {}, "gains": {}, "cur": 0, "active": False, "phase": "intro",
                  "pendingSteal": None, "thief": None, "lastSteal": None, "screen": "hq",
                  "rnd": {}, "answers": {}, "teamAnswers": {}, "feed": [], "open": False})
    # ---- Deppardy -------------------------------------------------------
    elif c.startswith("dep_") and c not in ("dep_dur",):
        d = s.get("dep")
        if not d or s["phase"] != "play":
            raise CmdError("Deppardy läuft nicht")
        now = time.time()
        if c == "dep_open":
            ci, p = int(a["c"]), int(a["p"])
            if f"{ci}|{p}" in d["revealed"]:
                raise CmdError("Feld ist schon gespielt")
            if not (d["board"]["cats"][ci].get("qh") or {}).get(str(p)):
                raise CmdError("Feld ist leer")
            frei = not s.get("depArm", True)
            d.update({"cell": {"c": ci, "p": p}, "stage": 0, "u0": dict(s["upts"]), "buzz": [], "wrong": [], "armed": frei, "sperre": {},
                      "tLeft": d["dur"], "tRun": frei and d["dur"] > 0, "tEnd": now + d["dur"]})
        elif c == "dep_arm":
            if d["cell"] and not d.get("armed"):
                d["armed"] = True
                if d["dur"] > 0 and d["stage"] < 2:
                    d.update({"tRun": True, "tEnd": now + (d["tLeft"] or d["dur"])})
        elif c == "dep_stage":
            if d["cell"]:
                cat = d["board"]["cats"][d["cell"]["c"]]
                has_hint = bool(strip_html((cat.get("hh") or {}).get(str(d["cell"]["p"]))))
                d["stage"] = 2 if d["stage"] >= 1 or not has_hint else 1
                if d["stage"] == 2:
                    birg(s, (cat.get("bw") or {}).get(str(d["cell"]["p"])))       # Antwort gezeigt: geborgen
                    d["tLeft"], d["tRun"] = max(0, d["tEnd"] - now) if d["tRun"] else d["tLeft"], False
        elif c == "dep_timer":
            if d["tRun"]:
                d["tLeft"], d["tRun"] = max(0, d["tEnd"] - now), False
            else:
                left = d["tLeft"] if d["tLeft"] > 0 else d["dur"]
                if left > 0:
                    d.update({"tLeft": left, "tEnd": now + left, "tRun": True})
        elif c == "dep_award":
            key, sign = a.get("key"), (1 if int(a.get("sign", 1)) > 0 else -1)
            if key not in {u["key"] for u in units(s)}:
                raise CmdError("Unbekannt")
            s["upts"][key] = s["upts"].get(key, 0) + sign * dep_value(d)
            if sign < 0 and key not in d["wrong"]:
                d["wrong"].append(key)
            sync_gains(s)
        elif c == "dep_buzz_reset":
            d["buzz"], d["wrong"] = [], []
        elif c == "dep_close":
            if d["cell"]:
                d["revealed"][f"{d['cell']['c']}|{d['cell']['p']}"] = True
                if d["stage"] >= 2:          # nur wenn die Antwort gezeigt wurde
                    cat = d["board"]["cats"][d["cell"]["c"]]
                    birg(s, (cat.get("bw") or {}).get(str(d["cell"]["p"])))
            d.update({"cell": None, "stage": 0, "tRun": False, "buzz": [], "wrong": []})
        elif c == "dep_reopen":
            d["revealed"].pop(f"{int(a['c'])}|{int(a['p'])}", None)
        else:
            raise CmdError("Unbekannter Befehl: " + c)
    elif c == "dep_dur":
        v = max(0, min(600, int(a.get("s", 30))))
        s["depDur"] = v
        if s.get("dep"):
            s["dep"]["dur"] = v
    elif c == "upts_adj":
        s["upts"][a.get("key")] = s["upts"].get(a.get("key"), 0) + int(a.get("d", 0))
        sync_gains(s)
    # ---- Archiv: Boards und Atlas-Sets ------------------------------------
    elif c == "board_save":
        b = board_normal(a.get("board") or {})
        if a.get("neu"):
            b["id"] = uid()
        alt = next((x for x in s["boards"] if x["id"] == b["id"]), None)
        b["autor"] = (alt or {}).get("autor") or str(a.get("_host") or "")
        for i, x in enumerate(s["boards"]):
            if x["id"] == b["id"]:
                s["boards"][i] = b
                break
        else:
            s["boards"].append(b)
    elif c == "board_del":
        s["boards"] = [x for x in s["boards"] if x["id"] != a.get("id")]
    elif c == "board_restore":
        for b in vorlage("deppardy-boards.json", []):
            s["boards"] = [x for x in s["boards"] if x["id"] != b["id"]] + [b]
    elif c == "atlas_set_save":
        sid = re.sub(r"[^a-z0-9_-]", "", str(a.get("id") or "").lower()) or uid()
        st = a.get("set") or {}
        eintraege = []
        for e in st.get("eintraege", []):
            land = str(e.get("land") or "")
            eintraege.append(dict({"text": str(e.get("text", ""))[:80], "land": land if land in GEO else "",
                                   "auchOk": [str(x) for x in e.get("auchOk", []) if str(x) in GEO],
                                   "notiz": str(e.get("notiz", ""))[:300], "beute": str(e.get("beute", ""))[:60]},
                                  **({"aus": True} if e.get("aus") else {})))
        alt = s["atlasSets"].get(sid) or {}
        s["atlasSets"][sid] = {"name": str(st.get("name") or "Neues Set")[:60], "marke": str(st.get("marke") or "")[:120],
                               "eintraege": eintraege, "autor": alt.get("autor") or str(a.get("_host") or "")}
    elif c == "kartei_set":
        wort = str(a.get("wort") or "").strip()[:60]
        if not wort:
            raise CmdError("Wort fehlt")
        s["kartei"][wort] = {k: str(a.get(k) or "")[:300] for k in ("art", "def", "herkunft", "vermerk")}
    elif c == "kartei_del":
        s["kartei"].pop(str(a.get("wort") or ""), None)
    elif c == "kartei_restore":
        s["kartei"].update(vorlage("beutekartei.json", {}))
    elif c == "cursor_reset":
        t = a.get("type")
        if t:
            s["cursor"].pop(t, None)
        else:
            s["cursor"] = {}
    elif c == "atlas_set_del":
        s["atlasSets"].pop(a.get("id"), None)
    elif c == "atlas_restore":
        s["atlasSets"].update(vorlage("atlas-sets.json", {}))
    else:
        raise CmdError("Unbekannter Befehl: " + str(c))


def _eingaben(s, aid):
    d = s.get("dep") or {}
    return {"antwort": (s["answers"].get(aid) or {}).get("v"), "stimme": s["votes"].get(aid), "einsatz": s["bets"].get(aid),
            "vorschlag": (s["vorschlaege"].get(aid) or {}).get("v"), "mole": s["moleVotes"].get(aid),
            "funk": sum(1 for f in s["feed"] if f["id"] == aid), "buzz": sum(1 for b in d.get("buzz") or [] if b.get("id") == aid)}


def player_act(s, agent, a):
    """Eingaben von den Agenten-Geräten – mit Strichliste für die Personalakten."""
    aid = agent["id"]
    vor = _eingaben(s, aid)
    _player_act(s, agent, a)
    nach = _eingaben(s, aid)
    for k in ("antwort", "stimme", "einsatz", "vorschlag", "mole"):
        if k == "vorschlag" and a.get("kind") == "vorschlag":
            continue                             # Live-Vorschläge beim Ziehen zählen nicht
        if nach[k] != vor[k]:
            track(s, aid, "abgaben")
            if vor[k] is not None:
                track(s, aid, "wechsel")
    if nach["funk"] > vor["funk"]:
        track(s, aid, "funk")
        track(s, aid, "abgaben")
    if nach["buzz"] > vor["buzz"]:
        track(s, aid, "buzz")


def _player_act(s, agent, a):
    """Eingaben von den Agenten-Geräten."""
    m = mission(s)
    aid = agent["id"]
    if a.get("kind") == "mole_vote":
        if not (s["mole"]["on"] and s["mole"]["voteOpen"]):
            raise CmdError("Die Abstimmung ist geschlossen")
        v = a.get("v")
        if v not in by_id(s) or v == aid:
            raise CmdError("Ungültige Stimme")
        s["moleVotes"][aid] = v
        return
    if a.get("kind") in ("steal", "steal_skip"):          # Umlagern direkt am Gerät
        if not s["pendingSteal"] or s["thief"] != aid:
            raise CmdError("Du darfst gerade nicht umlagern")
        if a["kind"] == "steal_skip":
            verzichten(s)
        else:
            umlagern(s, aid, a.get("v"), a.get("ziel") or aid)
        return
    if m and m["type"] == "deppardy" and s["screen"] == "mission" and s["phase"] == "play" and s.get("dep"):
        d = s["dep"]
        if not d["cell"] or d["stage"] >= 2:
            raise CmdError("Gerade ist keine Frage offen")
        u = unit_of(s, aid)
        if not u:
            raise CmdError("Du bist in keiner Zelle")
        if u["key"] in d["wrong"]:
            raise CmdError("Für diese Frage gesperrt")
        sperre = d.setdefault("sperre", {})
        if sperre.get(u["key"], 0) > time.time():
            raise CmdError("Noch gesperrt")
        if not d.get("armed", True):
            sperre[u["key"]] = time.time() + 2
            raise CmdError("Zu früh! 2 Sekunden gesperrt")
        if not any(b["key"] == u["key"] for b in d["buzz"]):
            d["buzz"].append({"key": u["key"], "id": aid, "t": time.time()})
        return
    if not m or s["screen"] != "mission" or s["phase"] != "play" or not item(s):
        raise CmdError("Gerade keine Eingabe möglich")
    t, v = m["type"], a.get("v")
    now = time.time()
    if t == "wette" and a.get("kind") == "bet":
        if s["showQ"]:
            raise CmdError("Einsätze sind geschlossen")
        s["bets"][aid] = max(0, min(int(v or 0), bet_cap(s, aid)))
        return
    if s["revealed"] or not s["open"]:
        raise CmdError("Abgabe ist geschlossen")
    if t == "atlas":
        v = str(v or "")
        if v not in GEO:
            raise CmdError("Unbekanntes Land")
        if m["mode"] == "team" and s["teams"]:
            zellen_vorschlag(s, m, aid, v, a, now)
        else:
            s["answers"][aid] = {"v": v, "t": now}
        return
    if t == "impostor":
        if v not in by_id(s) or v == aid:
            raise CmdError("Ungültige Stimme")
        s["votes"][aid] = v
    elif t in ("ranking", "hoeher"):
        v = str(v or "").upper().strip()
        if t == "hoeher" and v not in ("W", "P"):
            raise CmdError("Wahrheit oder Propaganda")
        if t == "ranking":
            n = len(lines_of(item(s)))
            if len(v) != n or sorted(v) != list(LETTERS[:n]):
                raise CmdError("Jeder Begriff genau einmal")
        zellen_vorschlag(s, m, aid, v, a, now)
    elif t in BUZZ:
        v = str(v or "").strip()[:80]
        if not v:
            raise CmdError("Leer")
        if sum(1 for f in s["feed"] if f["id"] == aid) >= MAX_BUZZ:
            raise CmdError("Keine Versuche mehr in dieser Runde")
        s["feed"].append({"id": aid, "v": v, "t": now, "z": s["zoomStep"]})
    elif t == "woerterbuch":
        r = s["rnd"]
        if r.get("wbPhase") == "faelschen":
            v = str(v or "").strip()[:160]
            if not v:
                raise CmdError("Leer")
            s["answers"][aid] = {"v": v, "t": now}
        elif r.get("wbPhase") == "abstimmen":
            nr = int(v)
            if not 0 <= nr < len(r["optionen"]):
                raise CmdError("Ungültig")
            if r["optionen"][nr]["id"] == aid:
                raise CmdError("Nicht für die eigene Fälschung")
            s["votes"][aid] = nr
        else:
            raise CmdError("Gerade keine Eingabe möglich")
    elif t == "schwaerzung":
        v = str(v or "").strip()[:60]
        if not v:
            raise CmdError("Leer")
        s["answers"][aid] = {"v": v, "t": now}
    elif t == "schaetzen":
        v = str(v or "").strip()[:30]
        if num(v) is None:
            raise CmdError("Bitte eine Zahl")
        s["answers"][aid] = {"v": v, "t": now}
    elif t == "wette":
        if not s["showQ"]:
            raise CmdError("Frage noch nicht offen")
        s["answers"][aid] = {"v": str(v or "").strip()[:80], "t": now}


# ---------------------------------------------------------------------------
# Sichten: öffentlich (Leinwand + Geräte), privat (ein Gerät), Leitung (alles)
# ---------------------------------------------------------------------------

def finale_stufen(s):
    mo = s.get("mole") or {}
    st = s.get("story") or {}
    return (["uebergabe"] + (["maulwurf"] if mo.get("on") and mo.get("id") else [])
            + (["ziel"] if ziel_wert(s) > 0 else []) + ["hueter", "bilanz"] + (["akten"] if personalakten(s) else [])
            + (["kartei"] if s.get("beute") else []) + ["epilog"] * len(st.get("epilog") or []) + ["abspann"])


def fuell(text, **kw):
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def stunden_uebrig(s):
    """Countdown in Stunden: fällt mit jedem Einsatz, ohne dass derselbe Tag zweimal erscheint."""
    st = s.get("story") or {}
    n, tage = max(1, len(s["plan"])), st.get("tage", 7)
    return jround(tage * 24 * (n - s["cur"]) / n) if s["cur"] < len(s["plan"]) else 0


def tage_uebrig(s):
    st = s.get("story") or {}
    n, tage = max(1, len(s["plan"])), st.get("tage", 7)
    return max(0, math.ceil(tage * (n - s["cur"]) / n)) if s["cur"] < len(s["plan"]) else 0


def abend_statistik(s):
    """Für die Übergabe: wer hat wie viel umgelagert, wer wurde erleichtert, wer hat verzichtet."""
    ids = by_id(s)
    genommen, verloren, verzicht, zuege, verteilt = {}, {}, {}, {}, {}
    for e in s.get("stealLog", []):
        if e.get("verzicht"):
            verzicht[e["thief"]] = verzicht.get(e["thief"], 0) + 1
            continue
        if e.get("ziel") and e["ziel"] != e["thief"]:            # in einen fremden Rucksack umgelagert
            verteilt[e["thief"]] = verteilt.get(e["thief"], 0) + e["amt"]
        else:
            genommen[e["thief"]] = genommen.get(e["thief"], 0) + e["amt"]
        zuege[e["thief"]] = zuege.get(e["thief"], 0) + 1
        if e["victim"]:
            verloren[e["victim"]] = verloren.get(e["victim"], 0) + e["amt"]
    unterwegs = sum(e.get("amt", 0) - e.get("an", e.get("amt", 0)) for e in s.get("stealLog", []) if not e.get("verzicht"))
    bonus = sum(e.get("bonus", 0) for e in s.get("stealLog", []) if e.get("verzicht"))
    praemie = ((s.get("mole") or {}).get("result") or {}).get("praemie", 0)
    gesamt = max(0, sum(total(s, a["id"]) for a in s["agents"]) - praemie)     # die Prämie des Amtes ist keine Beute
    umgelagert = sum(genommen.values()) + sum(verteilt.values())
    code = lambda i: ids[i]["code"] if i in ids else "?"
    def spitze(d):
        if not d or max(d.values()) <= 0:
            return None
        mx = max(d.values())
        return {"codes": [code(k) for k, v in d.items() if v == mx and k in ids], "wert": mx}
    return {"gesamt": gesamt, "umgelagert": umgelagert,
            "anteil": round(100 * umgelagert / gesamt) if gesamt else 0,
            "zuege": sum(zuege.values()), "unterwegs": unterwegs, "verzichtBonus": bonus,
            "meist": spitze(genommen), "erleichtert": spitze(verloren), "verteiler": spitze(verteilt),
            "fuerSich": sum(genommen.values()), "fuerAndere": sum(verteilt.values()),
            "unbestechlich": [code(k) for k in verzicht if k in ids and k not in genommen and k not in verteilt],
            "pro": {a["id"]: {"genommen": genommen.get(a["id"], 0) + verteilt.get(a["id"], 0),
                               "fuerSich": genommen.get(a["id"], 0), "fuerAndere": verteilt.get(a["id"], 0),
                               "verloren": verloren.get(a["id"], 0),
                               "verzicht": verzicht.get(a["id"], 0)} for a in s["agents"]}}


def public_view(s, full=False):
    ids = by_id(s)
    m = mission(s)
    g = GAMES[m["type"]] if m else None
    ranking = sorted(({"id": a["id"], "code": a["code"], "name": a["name"], "total": total(s, a["id"]),
                       "gain": s["gains"].get(a["id"], 0)} for a in s["agents"]),
                     key=lambda x: -x["total"])
    v = {
        "screen": s["screen"], "joinOpen": s["joinOpen"], "joinUrl": CONFIG.get("joinUrl") or "",
        "agents": [{"id": a["id"], "code": a["code"], "name": a["name"]} for a in s["agents"]],
        "ranking": ranking, "cur": s["cur"], "planLen": len(s["plan"]),
        "plan": [{"type": p["type"], "name": GAMES[p["type"]]["name"], "mode": p["mode"]} for p in s["plan"]],
        "lastSteal": s["lastSteal"], "stealAmount": s["stealAmount"],
        "pendingSteal": bool(s["pendingSteal"]),
        "thief": ids[s["thief"]]["code"] if s["thief"] in ids else None,
        "audio": s["audio"], "now": time.time(),
        "namenZeigen": bool(s.get("namenZeigen")), "beispiel": bool(s.get("beispiel", True)),
        "test": bool(s.get("test")), "impressum": bool(str(s.get("impressum") or "").strip()),
        "klang": s.get("klang"), "cues": s.get("cues") or [],
    }
    st = s.get("story") or {}
    v["story"] = {"zelle": st.get("zelle", ""), "tage": tage_uebrig(s), "stunden": stunden_uebrig(s), "auftrag": st.get("auftrag", ""),
                  "finale": st.get("finale", {}), "prologLen": len(prolog_tafeln(s))}
    if m:
        v["story"]["mission"] = (st.get("missionen") or {}).get(m["type"], {})
    tafeln = prolog_tafeln(s)
    if s["screen"] == "prolog" and tafeln:
        i = min(s["prologIdx"], len(tafeln) - 1)
        v["story"]["tafel"] = dict(tafeln[i], nr=i + 1)
    v["umlagern"] = {"min": s["stealAmount"], "pct": s.get("stealPct", 0), "verlust": s.get("stealVerlust", 0),
                     "bonus": s.get("verzichtBonus", 0)}
    v["zielLive"] = {"ziel": ziel_wert(s), "stand": ziel_stand(s, ohne_maulwurf=False)}
    v["funk"] = s.get("funk") if s["screen"] in ("hq", "start") else None
    mo = s["mole"]
    v["mole"] = {"on": mo["on"] and bool(mo["id"]), "voteOpen": mo["voteOpen"], "voted": list(s["moleVotes"].keys()),
                 "frage": (st.get("maulwurf") or {}).get("frage", "Wer ist der Maulwurf?")}
    if s["screen"] == "finale":
        stufen = finale_stufen(s)
        i = min(s["finaleStufe"], len(stufen) - 1)
        v["finaleStufe"], v["finaleArt"], v["finaleStufen"] = i, stufen[i], len(stufen)
        gerettet = sum(1 for b in s.get("beute") or [] if not b.get("verloren"))
        if stufen[i] == "epilog":
            nr = stufen[:i].count("epilog")
            t = (st.get("epilog") or [])[nr]
            v["epilog"] = {"titel": t.get("titel", ""), "nr": nr + 1, "von": stufen.count("epilog"),
                           "text": fuell(t.get("text", ""), zelle=st.get("zelle", ""), gerettet=gerettet)}
        if stufen[i] == "akten":
            v["akten"] = personalakten(s)
        if stufen[i] == "abspann":
            v["abspann"] = {"text": fuell(st.get("abspann", ""), zelle=st.get("zelle", ""), gerettet=gerettet),
                            "agenten": [{"code": a["code"], "name": a["name"], "total": total(s, a["id"])} for a in s["agents"]],
                            "missionen": [((st.get("missionen") or {}).get(p["type"]) or {}).get("ort") or GAMES[p["type"]]["name"]
                                          for p in s["plan"]], "gerettet": gerettet}
        stat = abend_statistik(s)
        pro = stat.pop("pro")
        if mo["result"] and mo["id"] in ids:
            mt = st.get("maulwurf") or {}
            r = mo["result"]
            v["maulwurf"] = {"code": ids[mo["id"]]["code"], "name": ids[mo["id"]]["name"], "caught": r["caught"],
                             "tally": {ids[k]["code"]: n for k, n in r["tally"].items() if k in ids},
                             "text": fuell(mt.get("enttarnt" if r["caught"] else "entkommen", ""), anteil=r["anteil"], bonus=r["bonus"])}
            stat["maulwurf"] = {"code": ids[mo["id"]]["code"], "genommen": pro.get(mo["id"], {}).get("genommen", 0)}
            v["maulwurf"]["praemie"] = r.get("praemie", 0)
            # Hüter des Archivs kann nur werden, wer zur Zelle gehört
            v["hueterRanking"] = [x for x in ranking if x["id"] != mo["id"]]
        v["statistik"] = stat
        v["beute"] = [karte(s, b["wort"], b) for b in s.get("beute") or []]
        v["beuteGerettet"] = sum(1 for k in v["beute"] if not k["verloren"])
        if ziel_wert(s) > 0:
            raus = bool(mo["on"] and mo["id"] in ids)
            stand = ziel_stand(s)
            v["zielErgebnis"] = {"ziel": ziel_wert(s), "stand": stand, "erreicht": stand >= ziel_wert(s),
                                 "maulwurfRaus": raus and not (mo.get("result") or {}).get("caught"),
                                 "maulwurfBekannt": bool(mo.get("result"))}
    if m:
        v["mission"] = {"type": m["type"], "name": g["name"], "mode": m["mode"], "pts": m["pts"],
                        "rounds": m["rounds"], "zm": zell_modus(m) if m["mode"] == "team" else None,
                        "takt": int(m.get("takt") or 0) if m["type"] in TAKT_SPIELE else 0,
                        "rules": g["rules"] + ([f"Kurs: {kurs(m)} Punkte = 1 Wort."] if g.get("kurs") else [])
                        + (zell_regel(m) if m["mode"] == "team" and m["type"] in TEAM_SPIELE else [])
                        + (takt_regel(m) if m["type"] in TAKT_SPIELE and m.get("takt") else [])}
    if s["screen"] != "mission" or not m:
        return v
    v.update({"phase": s["phase"], "round": s["round"], "revealed": s["revealed"], "open": s["open"],
              "teams": [[{"id": i, "code": ids[i]["code"], "name": ids[i]["name"]} for i in t if i in ids]
                        for t in s["teams"]]})
    if m["type"] == "deppardy" and s["phase"] == "play" and s.get("dep"):
        v["stage"] = dep_view(s, full)
        return v
    if GAMES[m["type"]].get("ereignis") and s["phase"] == "play":
        v["stage"] = {"type": m["type"], "voted": list(s["moleVotes"].keys())}
        return v
    it = item(s)
    if s["phase"] != "play" or not it:
        v["noItem"] = s["phase"] == "play" and not it
        return v
    if m["type"] == "atlas":
        v["stage"] = atlas_view(s)
        return v
    t, rev = m["type"], s["revealed"]
    st = {"type": t}
    # Wer hat schon abgegeben (ohne Inhalt)
    if t in ("schaetzen", "wette"):
        st["answered"] = list(s["answers"].keys())
    if t == "wette":
        st["betPlaced"] = list(s["bets"].keys())
    if t == "impostor":
        st["voted"] = list(s["votes"].keys())
    if t in ("ranking", "hoeher"):
        st["teamAnswered"] = list(s["teamAnswers"].keys())
        st["teamVotes"] = {str(i): sum(1 for x in tm if x in s["vorschlaege"]) for i, tm in enumerate(s["teams"])}
    if t in TAKT_SPIELE and m.get("takt") and not rev:
        st["takt"] = {"s": int(m["takt"]), "t0": s["rnd"].get("t0", 0), "voll": step(m)}
    if t in BUZZ:
        st["attempts"] = len(s["feed"])

    if t == "schaetzen":
        st.update({"q": it.get("q"), "unit": it.get("unit")})
        if rev:
            cl = closest_ids(s)
            tgt = num(it.get("a"))
            st.update({"a": it.get("a"), "closest": cl,
                       "guesses": sorted(({"id": k, "v": x["v"],
                                           "diff": (abs(num(x["v"]) - tgt) if tgt is not None and num(x["v"]) is not None else None)}
                                          for k, x in s["answers"].items()),
                                         key=lambda z: z["diff"] if z["diff"] is not None else 1e18)})
    elif t == "ranking":
        ln = lines_of(it)
        order = s["rnd"].get("order") or list(range(len(ln)))
        st.update({"q": it.get("q"), "items": [{"letter": LETTERS[i], "text": ln[idx]} for i, idx in enumerate(order)]})
        if rev:
            st.update({"solution": ln, "code": rank_code(s),
                       "teamAnswers": {k: x["v"] for k, x in s["teamAnswers"].items()}})
    elif t == "impostor":
        if rev:
            spy = ids.get(s["rnd"].get("spy"))
            st.update({"word": it.get("word"), "cat": it.get("cat"),
                       "spy": spy["code"] if spy else None, "tally": vote_tally(s), "spyResult": s["spyResult"]})
    elif t == "zoom":
        st.update({"img": it.get("img"), "scale": ZOOM[s["zoomStep"]], "step": s["zoomStep"] + 1, "steps": len(ZOOM),
                   "loch": bool(s.get("schluesselloch", True)),
                   "origin": f"{s['rnd'].get('ox', 50):.1f}% {s['rnd'].get('oy', 50):.1f}%"})
    elif t == "sound":
        st.update({"src": it.get("src"), "stufe": s["zoomStep"] + 1, "stufen": len(ZOOM), "rausch": s.get("rausch") or RAUSCH0})
    elif t == "hoeher":
        claim = s["rnd"].get("claim", "A")
        st.update({"q": it.get("q"), "a": it.get("a"), "b": it.get("b"), "claim": claim,
                   "claimName": it.get("a") if claim == "A" else it.get("b")})
        if rev:
            st.update({"av": it.get("av"), "bv": it.get("bv"), "correct": hoeher_correct(s), "wahr": propaganda_wahr(s),
                       "teamAnswers": {k: x["v"] for k, x in s["teamAnswers"].items()}})
    elif t == "woerterbuch":
        r = s["rnd"]
        st.update({"wort": it.get("wort"), "art": it.get("art"), "phase": r.get("wbPhase")})
        if r.get("wbPhase") == "faelschen":
            st["answered"] = list(s["answers"].keys())
            st["treffer"] = list(r.get("treffer") or [])
        else:
            st["optionen"] = [{"nr": i, "text": o["text"]} for i, o in enumerate(r.get("optionen") or [])]
            st["voted"] = list(s["votes"].keys())
        if rev:
            erg = r.get("ergebnis") or {}
            stimmen = {}
            for voter, nr in s["votes"].items():
                stimmen.setdefault(nr, []).append(voter)
            st["optionen"] = [{"nr": i, "text": o["text"], "echt": o["id"] == "echt",
                               "von": None if o["id"] == "echt" else o["id"], "stimmen": stimmen.get(i, [])}
                              for i, o in enumerate(r.get("optionen") or [])]
            st["treffer"] = list(r.get("treffer") or [])
            st["def"] = it.get("def")
    elif t == "schwaerzung":
        txt = it.get("text", "")
        mt = re.search(r"\[\[(.+?)\]\]", txt)
        vor, nach = (txt[:mt.start()], txt[mt.end():]) if mt else (txt, "")
        st.update({"vor": vor, "nach": nach, "laenge": len(schwarz_wort(it)), "quelle": it.get("quelle"),
                   "answered": list(s["answers"].keys())})
        if rev:
            st.update({"wort": schwarz_wort(it),
                       "antworten": [{"id": k, "v": x["v"], "ok": s["judged"].get(k) == "r"} for k, x in s["answers"].items()]})
    elif t == "emoji":
        st.update({"e": it.get("e"), "cat": it.get("cat")})
    elif t == "wette":
        st["cat"] = it.get("cat")
        if s["showQ"]:
            st["q"] = it.get("q")
        if rev:
            st["bets"] = s["bets"]
            st["betDone"] = s["betDone"]
    if rev and t in ("zoom", "sound", "emoji", "wette"):
        st["a"] = it.get("a")
    if t in BUZZ and rev:
        st["winners"] = [k for k, x in s["judged"].items() if x == "r"]
    bw = beute_von(it, t)
    if rev and bw:
        st["beute"] = bw
        st["karte"] = karte(s, bw)
    v["stage"] = st
    return v


def zell_regel(m):
    zm = zell_modus(m)
    if zm == "mehrheit":
        return ["Zellenmodus Abstimmung: Jede Person stimmt im Gerät ab, die Mehrheit gilt für die Zelle. Was die anderen wählen, seht ihr live."]
    if zm == "zuversicht":
        return ["Zellenmodus Zuversicht: Jede Person gibt eine Antwort und stellt ein, wie sicher sie ist. Sichere Stimmen wiegen mehr."]
    return ["Zellenmodus Sprecher: Alle sehen die Vorschläge der Zelle live, eine Person schickt für alle ab."]


def takt_regel(m):
    t = int(m.get("takt") or 0)
    return [f"Zeittakt: Wer in den ersten {t} Sekunden richtig liegt, birgt alles – danach jede {t} Sekunden nur noch die Hälfte."]


def unit_scores(s):
    k = kurs(mission(s))
    return [{"key": u["key"], "label": u["label"], "pts": s["upts"].get(u["key"], 0),
             "words": jround(s["upts"].get(u["key"], 0) / k)} for u in units(s)]


def dep_view(s, full):
    d = s["dep"]
    b = d["board"]
    lbl = {u["key"]: u["label"] for u in units(s)}
    st = {"type": "deppardy", "name": b["name"], "pts": b["pts"], "cats": [c["name"] for c in b["cats"]],
          "revealed": list(d["revealed"].keys()),
          "leer": [f"{i}|{p}" for i, c in enumerate(b["cats"]) for p in b["pts"] if not (c.get("qh") or {}).get(str(p))],
          "stage": d["stage"], "scores": unit_scores(s), "armed": d.get("armed", True),
          "timer": {"run": d["tRun"], "end": d["tEnd"], "left": d["tLeft"], "dur": d["dur"]},
          "buzz": [{"key": x["key"], "label": lbl.get(x["key"], "?"), "t": x["t"]} for x in d["buzz"]],
          "wrong": [lbl.get(k, "?") for k in d["wrong"]], "cell": None}
    if d["cell"]:
        c, p = d["cell"]["c"], d["cell"]["p"]
        cat = b["cats"][c]
        g = lambda k: (cat.get(k) or {}).get(str(p), "")
        cell = {"c": c, "p": p, "cat": cat["name"], "value": dep_value(d), "risk": bool((cat.get("rk") or {}).get(str(p)))}
        cell["q"] = g("qh") if full else strip_html(g("qh"))
        if d["stage"] >= 1:
            cell["hint"] = g("hh") if full else strip_html(g("hh"))
        if d["stage"] >= 2:
            cell["a"] = g("ah") if full else strip_html(g("ah"))
            if g("bw"):
                cell["karte"] = karte(s, g("bw"))
        st["cell"] = cell
    return st


def atlas_view(s):
    it = item(s)
    st = {"type": "atlas", "text": it.get("text"), "marke": it.get("marke"), "set": it.get("setName"),
          "scores": unit_scores(s), "units": [{"key": u["key"], "label": u["label"]} for u in units(s)]}
    st["answered"] = list(atlas_tips(s).keys())
    if s["revealed"]:
        if (it.get("beute") or "").strip():
            st["karte"] = karte(s, it["beute"])
        ziele = [str(it.get("land"))] + [str(x) for x in it.get("auchOk", [])]
        st.update({"ziele": ziele, "zielName": GEO.get(str(it.get("land")), {}).get("name", ""),
                   "notiz": it.get("notiz", ""), "res": s.get("atlasRes") or {}})
    return st


def me_view(s, agent):
    aid = agent["id"]
    me = {"id": aid, "code": agent["code"], "name": agent["name"], "total": total(s, aid),
          "gain": s["gains"].get(aid, 0), "team": team_of(s, aid)}
    mo = s["mole"]
    if mo["on"] and mo["id"]:
        mt = (s.get("story") or {}).get("maulwurf") or {}
        ist = mo["id"] == aid
        # Gleiches Format für alle, damit niemand am Bildschirm des Nachbarn etwas erkennt
        me["rolle"] = {"maulwurf": ist, "text": fuell(mt.get("rolle" if ist else "zelle", ""), bonus=mo["bonus"])}
        me["moleVote"] = s["moleVotes"].get(aid)
    if s["screen"] == "finale":
        me["bilanz"] = abend_statistik(s)["pro"].get(aid)
    if s["pendingSteal"] and s["thief"] == aid:
        me["umlagern"] = {"bonus": s.get("verzichtBonus", 0),
                          "rucksaecke": [{"id": a["id"], "code": a["code"], "name": a["name"], "total": total(s, a["id"]),
                                          "menge": umlager_menge(s, a["id"])} for a in s["agents"] if a["id"] != aid]}
    m = mission(s)
    it = item(s)
    if m and m["type"] in ("deppardy", "atlas") and s["screen"] == "mission":
        u = unit_of(s, aid)
        me["unitPts"] = s["upts"].get(u["key"], 0) if u else 0
    if m and m["type"] == "deppardy" and s["screen"] == "mission" and s["phase"] == "play" and s.get("dep"):
        d = s["dep"]
        u = unit_of(s, aid)
        k = u["key"] if u else None
        me["buzzPos"] = next((i + 1 for i, b in enumerate(d["buzz"]) if b["key"] == k), None)
        me["wrong"] = k in d["wrong"]
        me["sperre"] = (d.get("sperre") or {}).get(k, 0)
    if m and s["screen"] == "mission" and s["phase"] == "play" and it:
        t = m["type"]
        if t == "impostor":
            if s["rnd"].get("spy") == aid:
                me["secret"] = {"spy": True, "cat": it.get("cat")}
            else:
                me["secret"] = {"spy": False, "word": it.get("word")}
            me["vote"] = s["votes"].get(aid)
        if t in ("schaetzen", "wette", "schwaerzung", "woerterbuch") and aid in s["answers"]:
            me["answer"] = s["answers"][aid]["v"]
        if t == "schwaerzung":
            me["judged"] = s["judged"].get(aid)
        if t == "woerterbuch":
            r = s["rnd"]
            me["vote"] = s["votes"].get(aid)
            me["eigeneNr"] = next((i for i, o in enumerate(r.get("optionen") or []) if o["id"] == aid), None)
            me["treffer"] = aid in (r.get("treffer") or [])
            me["gestrichen"] = aid in (r.get("gestrichen") or [])
        if t == "wette":
            me["bet"] = s["bets"].get(aid)
            me["betCap"] = bet_cap(s, aid)
            me["betDone"] = s["betDone"].get(aid)
        if t in ("ranking", "hoeher") and me["team"] is not None:
            ta = s["teamAnswers"].get(str(me["team"]))
            if ta:
                by = by_id(s).get(ta.get("by"))
                me["teamAnswer"] = {"v": ta["v"], "by": by["code"] if by else ("Abstimmung der Zelle" if ta.get("by") == "zelle" else "Moderation")}
        if t in TEAM_SPIELE and m["mode"] == "team" and me["team"] is not None and me["team"] < len(s["teams"]):
            ids = by_id(s)
            me["zelle"] = {"modus": zell_modus(m), "mein": s["vorschlaege"].get(aid),
                           "vorschlaege": [dict(s["vorschlaege"][x], id=x, code=ids[x]["code"], name=ids[x]["name"])
                                           for x in s["teams"][me["team"]] if x in s["vorschlaege"] and x in ids],
                           "groesse": len(s["teams"][me["team"]])}
        if t == "atlas":
            u = unit_of(s, aid)
            tip = atlas_tips(s).get(u["key"]) if u else None
            me["unit"] = u["key"] if u else None
            me["tip"] = tip
            if s["revealed"] and u:
                me["res"] = (s.get("atlasRes") or {}).get(u["key"])
        if t in TAKT_SPIELE and aid in s["judgedPts"]:
            me["wert"] = s["judgedPts"][aid]
        if t in BUZZ:
            me["tries"] = [f["v"] for f in s["feed"] if f["id"] == aid]
            me["triesLeft"] = MAX_BUZZ - len(me["tries"])
            me["judged"] = s["judged"].get(aid)
    return me


def host_view(s):
    """Für das Steuermodul: alles, inklusive Lösungen und Auswertungshilfen."""
    v = copy.deepcopy(s)
    m = mission(s)
    extra = {"finaleStufen": finale_stufen(s), "statistik": abend_statistik(s)}
    tally = {}
    for voter, target in s["moleVotes"].items():
        if voter != s["mole"]["id"]:
            tally[target] = tally.get(target, 0) + 1
    extra["moleTally"] = tally
    extra["prolog"] = prolog_tafeln(s)
    extra["reihenfolge"] = {t: {"naechster": (s["cursor"].get(t, 0) % len(l)) + 1 if l else 0, "von": len(l),
                                "gespielt": s["cursor"].get(t, 0)} for t, l in s["content"].items()}
    extra["ziel"] = {"wert": ziel_wert(s), "stand": ziel_stand(s, ohne_maulwurf=False), "ohneMaulwurf": ziel_stand(s),
                     "max": max_woerter(s)}
    if s["pendingSteal"]:
        extra["umlagerVorschau"] = {x["id"]: umlager_menge(s, x["id"]) for x in s["agents"]}
    if m and s["phase"] == "play" and item(s):
        t = m["type"]
        if t == "schaetzen":
            extra["closest"] = closest_ids(s)
        if t == "ranking":
            extra["rankCode"] = rank_code(s)
            code_ok = rank_code(s)
            extra["teamPlaces"] = [sum(1 for x, y in zip((s["teamAnswers"].get(str(i)) or {}).get("v", ""), code_ok) if x == y)
                                   for i in range(len(s["teams"]))]
        if t == "hoeher":
            extra["hoeherCorrect"] = hoeher_correct(s)
            extra["propaganda"] = propaganda_wahr(s)
        if t == "woerterbuch":
            extra["wbMatch"] = {k: wohl_richtig(x["v"], item(s).get("def")) for k, x in s["answers"].items()}
        if t == "schwaerzung":
            extra["schwarzWort"] = schwarz_wort(item(s))
            extra["schwarzMatch"] = {k: wohl_richtig(x["v"], schwarz_wort(item(s))) for k, x in s["answers"].items()}
        if t in ("ranking", "hoeher"):
            extra["teamCorrect"] = [team_correct(s, i) for i in range(len(s["teams"]))]
        if t == "impostor":
            extra["tally"] = vote_tally(s)
        if t == "wette":
            extra["betCaps"] = {a["id"]: bet_cap(s, a["id"]) for a in s["agents"]}
        if t in BUZZ:
            extra["feedMatch"] = [wohl_richtig(f["v"], item(s).get("a")) for f in s["feed"]]
            if t in ("zoom", "sound"):
                extra["feedWert"] = [zoom_wert(m, f.get("z", 0)) for f in s["feed"]]
        if t in TAKT_SPIELE and m.get("takt"):
            if t == "emoji":
                extra["feedWert"] = [takt_wert(s, m, f["t"]) for f in s["feed"]]
            else:
                extra["antwortWert"] = {k: takt_wert(s, m, x["t"]) for k, x in s["answers"].items()}
    if m and s["phase"] == "play" and m["type"] in ("deppardy", "atlas"):
        extra["units"] = units(s)
        if m["type"] == "deppardy" and s.get("dep"):
            extra["depValue"] = dep_value(s["dep"])
        if m["type"] == "atlas" and item(s):
            extra["atlasPreview"] = {k: atlas_wertung(t, item(s)) for k, t in atlas_tips(s).items()}
    v["extra"] = extra
    v["totals"] = {a["id"]: total(s, a["id"]) for a in s["agents"]}
    v["statistik"] = abend_statistik(s)
    v["tage"] = tage_uebrig(s)
    v["joinUrl"] = CONFIG.get("joinUrl") or ""
    return v


META = {"ereignisse": EREIGNISSE, "vermerke": VERMERKE, "games": GAMES, "internal": INTERNAL, "special": SPECIAL, "fields": FIELDS, "hints": HINTS, "zoom": ZOOM,
        "cues": CUES, "rausch": RAUSCH0, "teamSpiele": TEAM_SPIELE, "taktSpiele": TAKT_SPIELE, "zellmodi": ZELLMODI}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def normpfad(roh):
    """/./leitung, //leitung, /x/../leitung usw. auf eine Form bringen, bevor der Passwortschutz prüft."""
    p = posixpath.normpath("/" + urllib.parse.unquote(roh or "/"))
    p = "/" + p.lstrip("/")
    if roh.endswith("/") and not p.endswith("/"):
        p += "/"
    return p


class Handler(BaseHTTPRequestHandler):
    server_version = "WWH/1.0"
    timeout = 60   # hängende Verbindungen nicht ewig offen halten

    def log_message(self, fmt, *args):
        if "--laut" in sys.argv:
            super().log_message(fmt, *args)

    # -- Antworten ---------------------------------------------------------
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_err(self, msg, code=400):
        self.send_json({"ok": False, "error": msg}, code)

    GZIP_CACHE = {}
    GZIP_TYPEN = ("text/", "application/javascript", "application/json", "image/svg+xml")

    def send_file(self, path, cache=False):
        if not path or not os.path.isfile(path):
            return self.send_error(404, "Nicht gefunden")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        packbar = ctype.startswith(self.GZIP_TYPEN)
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        cc = "public, max-age=86400" if cache else "no-cache"

        # Texte (d3, Weltkarte, Seiten) gepackt ausliefern – wichtig für Handys über den Tunnel
        if packbar and not rng and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            key = (path, os.path.getmtime(path))
            body = self.GZIP_CACHE.get(key)
            if body is None:
                with open(path, "rb") as f:
                    body = gzip.compress(f.read(), 6)
                self.GZIP_CACHE[key] = body
            self.send_response(200)
            for h, v in (("Content-Type", ctype), ("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding"),
                         ("Content-Length", str(len(body))), ("Cache-Control", cc)):
                self.send_header(h, v)
            self.end_headers()
            self.wfile.write(body)
            return

        start, end = 0, size - 1
        if rng and rng.startswith("bytes=") and "," not in rng:     # Audio-Scrubbing im Browser
            a, _, b = rng[6:].strip().partition("-")
            try:
                if a == "":                                  # Suffix: die letzten b Bytes
                    start, end = max(0, size - int(b)), size - 1
                else:
                    start, end = int(a), min(int(b) if b else size - 1, size - 1)
            except ValueError:
                start, end = 1, 0
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", cc)
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            rest = end - start + 1
            while rest > 0:                                  # in Blöcken statt alles in den Speicher
                block = f.read(min(65536, rest))
                if not block:
                    break
                self.wfile.write(block)
                rest -= len(block)

    def body_json(self, limit=MAX_PUBLIC_BODY):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise CmdError("Anfrage zu groß")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def authed(self):
        """Hauptpasswort (beliebiger Name) = Leitung mit allen Rechten. Zusätzliche Zugänge stehen in config.json
        unter „hosts“: Name und eigenes Passwort, z. B. für Leute, die Boards vorbereiten."""
        h = self.headers.get("Authorization", "")
        self.host, self.admin = None, False
        if h.startswith("Basic "):
            try:
                name, _, pw = base64.b64decode(h[6:]).decode("utf-8").partition(":")
                if hmac.compare_digest(pw.encode(), CONFIG["password"].encode()):
                    self.host, self.admin = (name.strip() or "Leitung"), True
                    return True
                for hn, hpw in (CONFIG.get("hosts") or {}).items():
                    if hn.lower() == name.strip().lower() and hmac.compare_digest(pw.encode(), str(hpw).encode()):
                        self.host = hn
                        return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="WWH Steuermodul", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    @staticmethod
    def safe_join(root, rel):
        wurzel = os.path.realpath(root)
        p = os.path.realpath(os.path.join(wurzel, rel.lstrip("/")))
        return p if os.path.commonpath([p, wurzel]) == wurzel else None

    def agent_by_token(self, token):
        for a in STATE["agents"]:
            if token and hmac.compare_digest(a["token"], token):
                return a
        return None

    # -- GET ---------------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path, q = normpfad(u.path), urllib.parse.parse_qs(u.query)
        qv = lambda k, d=None: q.get(k, [d])[0]

        if path == "/api/view":
            since = int(qv("v", -1) or -1)
            wait_change(since)
            with LOCK:
                agent = self.agent_by_token(qv("t"))
                full = qv("full") == "1"
                ck = (VERSION, full)
                if ck not in SICHT_CACHE:
                    SICHT_CACHE[ck] = public_view(STATE, full=full)
                # Serverzeit frisch mitgeben, sonst läuft der Deppardy-Timer bei spät abholenden Geräten falsch
                out = {"v": VERSION, "view": dict(SICHT_CACHE[ck], now=time.time())}
                if qv("t") is not None:
                    out["me"] = me_view(STATE, agent) if agent else None
            return self.send_json(out)

        if path.startswith("/media/"):
            p = self.safe_join(MEDIA, path[len("/media/"):])
            return self.send_file(p, cache=True) if p else self.send_error(404)

        if path.startswith("/leitung"):
            if not self.authed():
                return
            if path == "/leitung":
                self.send_response(301)
                self.send_header("Location", "/leitung/")
                self.end_headers()
                return
            if path == "/leitung/api/state":
                since = int(qv("v", -1) or -1)
                wait_change(since)
                with LOCK:
                    out = {"v": VERSION, "state": host_view(STATE), "meta": META}
                out["ich"] = {"name": self.host, "admin": self.admin}
                if self.admin:
                    out["hosts"] = sorted((CONFIG.get("hosts") or {}).keys(), key=str.lower)
                out["lan"] = f"http://{LAN_IP}:{self.server.server_port}/"
                out["now"] = time.time()
                return self.send_json(out)
            if path == "/leitung/api/beute-auftrag":
                with LOCK:
                    text, n_offen, n_karten = beute_auftrag(STATE)
                return self.send_json({"ok": True, "text": text, "offen": n_offen, "ohneKarte": n_karten})
            if path == "/leitung/api/export":
                with LOCK:
                    body = json.dumps({"v": VERSION, "state": STATE}, ensure_ascii=False, indent=1).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition", 'attachment; filename="wwh-spielstand-%s.json"' % time.strftime("%Y%m%d-%H%M"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            rel = path[len("/leitung/"):] or "index.html"
            if rel.endswith("/"):
                rel += "index.html"
            p = self.safe_join(os.path.join(WEB, "leitung"), rel)
            return self.send_file(p, cache="vendor/" in rel or "data/" in rel) if p else self.send_error(404)

        if path == "/impressum":
            with LOCK:
                txt = str(STATE.get("impressum") or "").strip() or "Noch kein Impressum hinterlegt."
            esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            body = ('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                    '<title>Impressum</title><link rel="stylesheet" href="/wwh.css"><style>main{max-width:720px;margin:0 auto;padding:32px 20px 60px;}'
                    'h1{font-family:var(--display);font-weight:400;text-transform:uppercase;font-size:44px;margin:0 0 20px;}'
                    '.text{font-family:var(--serif);font-size:18px;line-height:1.55;white-space:pre-line;}</style></head><body><main>'
                    '<h1>Impressum</h1><div class="text">' + esc(txt) + '</div><p><a href="/">Zurück</a></p></main></body></html>').encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        routes = {"/": "index.html", "/leinwand": "leinwand.html"}
        rel = routes.get(path, path)
        if rel.startswith("/leitung"):
            return self.send_error(404)
        p = self.safe_join(WEB, rel)
        return self.send_file(p, cache="vendor/" in rel) if p else self.send_error(404)

    # -- POST --------------------------------------------------------------
    def do_POST(self):
        global STATE
        path = normpfad(urllib.parse.urlsplit(self.path).path)
        try:
            if path == "/api/join":
                a = self.body_json()
                name = str(a.get("name", "")).strip()[:40]
                if not name:
                    return self.send_err("Bitte einen Namen eingeben")
                with LOCK:
                    if not STATE["joinOpen"]:
                        return self.send_err("Der Beitritt ist gerade geschlossen", 403)
                    if any(x["name"].lower() == name.lower() for x in STATE["agents"]):
                        return self.send_err("Diesen Namen gibt es schon. Falls das du bist: "
                                             "die Moderation kann dir deinen Geräte-Link schicken.", 409)
                    ag = {"id": uid(), "name": name, "code": free_code(STATE), "token": secrets.token_urlsafe(12)}
                    STATE["agents"].append(ag)
                    m = mission(STATE)
                    if STATE["active"] and m and m["mode"] == "team" and STATE["teams"]:
                        min(STATE["teams"], key=len).append(ag["id"])   # Nachzügler
                    commit()
                return self.send_json({"ok": True, "token": ag["token"]})

            if path == "/api/act":
                a = self.body_json()
                with LOCK:
                    agent = self.agent_by_token(a.get("t"))
                    if not agent:
                        return self.send_err("Unbekanntes Gerät", 403)
                    player_act(STATE, agent, a)
                    commit()
                return self.send_json({"ok": True})

            if path.startswith("/leitung/"):
                if not self.authed():
                    return
                if path == "/leitung/api/cmd":
                    a = self.body_json(MAX_BODY)
                    a["_host"] = self.host
                    with LOCK:
                        host_cmd(STATE, a.get("cmd"), a)
                        commit(sofort=a.get("cmd") in ("mission_finish", "steal_victim", "steal_skip", "mole_resolve",
                                                       "evening_reset", "agents_clear"))
                        v = VERSION
                    return self.send_json({"ok": True, "v": v})
                if path == "/leitung/api/hosts":
                    if not self.admin:
                        return self.send_err("Nur die Leitung mit dem Hauptpasswort darf Zugänge verwalten", 403)
                    a = self.body_json()
                    name = str(a.get("name") or "").strip()[:30]
                    if not name:
                        return self.send_err("Name fehlt")
                    with LOCK:
                        hosts = CONFIG.setdefault("hosts", {})
                        if a.get("aktion") == "del":
                            hosts.pop(name, None)
                        else:
                            pw = str(a.get("pw") or "").strip()
                            if len(pw) < 4:
                                return self.send_err("Passwort bitte mit mindestens 4 Zeichen")
                            hosts[name] = pw
                        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
                        commit()
                    return self.send_json({"ok": True})
                if path == "/leitung/api/config":
                    if not self.admin:
                        return self.send_err("Nur mit dem Hauptpasswort", 403)
                    a = self.body_json(MAX_BODY)
                    with LOCK:
                        if "joinUrl" in a:
                            CONFIG["joinUrl"] = str(a["joinUrl"]).strip()
                        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
                        commit()
                    return self.send_json({"ok": True})
                if path == "/leitung/api/upload":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n <= 0 or n > MAX_BODY:
                        return self.send_err("Datei leer oder größer als 25 MB")
                    orig = urllib.parse.unquote(self.headers.get("X-Filename", "datei"))
                    ext = os.path.splitext(orig)[1].lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp3", ".ogg", ".m4a", ".wav", ".opus"):
                        return self.send_err("Nur Bilder oder Audio")
                    name = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3) + ext
                    with open(os.path.join(MEDIA, name), "wb") as f:
                        f.write(self.rfile.read(n))
                    return self.send_json({"ok": True, "url": "/media/" + name})
                if path == "/leitung/api/import":
                    if not self.admin:
                        return self.send_err("Nur mit dem Hauptpasswort", 403)
                    a = self.body_json(MAX_BODY)
                    try:
                        roh = a.get("state", a)
                        neu = pruefe_state(deep_merge(defaults(), roh))
                        neu["korrekturStand"] = (roh or {}).get("korrekturStand", 0)
                        for alt in ("extStart", "extResults"):
                            neu.pop(alt, None)
                        neu["beute"] = [b if isinstance(b, dict) else {"wort": str(b)} for b in neu.get("beute") or []]
                        for k, v in SAMPLES.items():        # neue Spiele bekommen ihre Beispielinhalte
                            neu["content"].setdefault(k, copy.deepcopy(v))
                        korrekturen(neu)
                        korrekturen2(neu)
                        korrekturen3(neu)
                        korrekturen4(neu)
                    except ValueError as e:
                        return self.send_err("Import abgelehnt: " + str(e))
                    with LOCK:
                        bak = STATE_FILE + ".vor-import-" + time.strftime("%Y%m%d-%H%M%S")
                        with open(bak, "w", encoding="utf-8") as f:
                            json.dump({"v": VERSION, "state": STATE}, f, ensure_ascii=False)
                        STATE = neu
                        commit(sofort=True)
                    return self.send_json({"ok": True, "backup": os.path.basename(bak)})
            return self.send_error(404)
        except CmdError as e:
            return self.send_err(str(e))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            return self.send_err("Ungültige Eingabe: " + str(e))


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Geschlossene Browser-Tabs brechen Long-Polls ab – das ist kein Fehler.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def main():
    ap = argparse.ArgumentParser(description="WWH-Spieleabend-Server")
    ap.add_argument("--port", type=int, default=int(os.environ.get("WWH_PORT", 8080)))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--passwort", help="Passwort für das Steuermodul setzen (wird gespeichert)")
    ap.add_argument("--laut", action="store_true", help="Jede Anfrage protokollieren")
    args = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    global LAN_IP
    fresh = load_config(args)
    load()
    LAN_IP = lan_ip()
    threading.Thread(target=speicher_schleife, daemon=True).start()

    def beenden(*_):                     # systemctl stop: Stand noch sichern
        with LOCK:
            save()
        sys.exit(0)
    import signal
    signal.signal(signal.SIGTERM, beenden)
    srv = Server((args.host, args.port), Handler)
    ip = lan_ip()
    print(f"WWH-Server läuft.\n"
          f"  Agenten-Geräte : http://{ip}:{args.port}/\n"
          f"  Leinwand       : http://{ip}:{args.port}/leinwand\n"
          f"  Steuermodul    : http://{ip}:{args.port}/leitung/   (Passwort in data/config.json)")
    if fresh or args.passwort:
        print(f"  Passwort       : {CONFIG['password']}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        with LOCK:
            save()
        print("\nBeendet.")


if __name__ == "__main__":
    main()
