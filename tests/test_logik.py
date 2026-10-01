"""Tests für die Spiellogik – nur Standardbibliothek.  Aufruf:  python3 -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as W  # noqa: E402


def abend(n=4):
    s = W.defaults()
    for name in ["Anna", "Ben", "Cleo", "Dora", "Emil", "Fritz"][:n]:
        W.host_cmd(s, "agent_add", {"name": name})
    return s, [a["id"] for a in s["agents"]]


class Umlagern(unittest.TestCase):
    def setUp(self):
        self.s, self.ids = abend()
        for i, a in enumerate(self.ids):
            self.s["scores"][a] = 10 * (i + 1)
        self.s["pendingSteal"] = {"winners": [self.ids[0]]}
        self.s["thief"] = self.ids[0]

    def test_nicht_aus_eigenem_rucksack(self):
        with self.assertRaises(W.CmdError):
            W.host_cmd(self.s, "steal_victim", {"id": self.ids[0]})

    def test_nur_sieger_duerfen(self):
        with self.assertRaises(W.CmdError):
            W.host_cmd(self.s, "steal_thief", {"id": self.ids[2]})

    def test_prozent_und_verlust(self):
        # Opfer hat 40: 20 % = 8 genommen, 50 % Verlust → 4 kommen an
        W.host_cmd(self.s, "steal_victim", {"id": self.ids[3]})
        self.assertEqual(self.s["scores"][self.ids[3]], 32)
        self.assertEqual(self.s["scores"][self.ids[0]], 14)
        self.assertEqual(self.s["stealLog"][-1]["amt"], 8)
        self.assertEqual(self.s["stealLog"][-1]["an"], 4)

    def test_verzicht_wird_belohnt(self):
        W.host_cmd(self.s, "steal_skip", {})
        self.assertEqual(self.s["scores"][self.ids[0]], 12)


class Deppardy(unittest.TestCase):
    def test_kurs_und_buzzer_freigabe(self):
        s, ids = abend()
        s["plan"] = [p for p in s["plan"] if p["type"] == "deppardy"]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        W.host_cmd(s, "dep_open", {"c": 0, "p": 500})
        ag = s["agents"][0]
        with self.assertRaises(W.CmdError):          # zu früh
            W.player_act(s, ag, {"kind": "buzz"})
        W.host_cmd(s, "dep_arm", {})
        with self.assertRaises(W.CmdError):          # noch 2 s gesperrt
            W.player_act(s, ag, {"kind": "buzz"})
        s["dep"]["sperre"] = {}
        W.player_act(s, ag, {"kind": "buzz"})
        W.host_cmd(s, "dep_award", {"key": ag["id"], "sign": 1})
        # Risiko-500er = 1000 Punkte, Kurs 500 → 2 Wörter
        self.assertEqual(s["gains"][ag["id"]], 2)


class Uebergabe(unittest.TestCase):
    def test_ziel_ohne_maulwurf_rucksack(self):
        s, ids = abend()
        W.host_cmd(s, "mole_toggle", {"on": True})
        mole = s["mole"]["id"]
        for a in ids:
            s["scores"][a] = 10
        s["ziel"] = 35
        self.assertEqual(W.ziel_stand(s), 30)       # Maulwurf zählt nicht
        self.assertIn("ziel", W.finale_stufen(s))
        self.assertIn(mole, ids)


class Hilfen(unittest.TestCase):
    def test_wohl_richtig(self):
        self.assertTrue(W.wohl_richtig("herr der ringe", "Der Herr der Ringe"))
        self.assertTrue(W.wohl_richtig("Sauregurkenzeit", "Saure-Gurken-Zeit"))
        self.assertFalse(W.wohl_richtig("Hobbit", "Der Herr der Ringe"))

    def test_normpfad(self):
        self.assertEqual(W.normpfad("/./leitung/index.html"), "/leitung/index.html")
        self.assertEqual(W.normpfad("//leitung/"), "/leitung/")
        self.assertEqual(W.normpfad("/a/../leitung"), "/leitung")

    def test_decknamen_nie_doppelt(self):
        s, _ = abend(0)
        for i in range(30):
            W.host_cmd(s, "agent_add", {"name": f"P{i}"})
        codes = [a["code"] for a in s["agents"]]
        self.assertEqual(len(codes), len(set(codes)))

    def test_alter_spielstand_ohne_neue_schluessel(self):
        alt = {"mole": {"on": True}, "agents": []}
        s = W.deep_merge(W.defaults(), alt)
        self.assertEqual(s["mole"]["bonus"], 5)


if __name__ == "__main__":
    unittest.main()


class Beute(unittest.TestCase):
    def test_atlas_und_deppardy_behalten_beutewoerter(self):
        s, _ = abend()
        W.host_cmd(s, "atlas_set_save", {"id": "t", "set": {"name": "T", "eintraege": [
            {"text": "Sauna", "land": "246", "beute": "Sauna"}]}})
        self.assertEqual(s["atlasSets"]["t"]["eintraege"][0]["beute"], "Sauna")
        b = W.board_normal({"name": "B", "pts": [100], "cats": [{"name": "K", "qh": {"100": "F"}, "bw": {"100": "Kaff"}}]})
        self.assertEqual(b["cats"][0]["bw"]["100"], "Kaff")

    def test_deppardy_birgt_beim_aufloesen(self):
        s, ids = abend()
        s["plan"] = [p for p in s["plan"] if p["type"] == "deppardy"]
        s["boards"][0]["cats"][0]["bw"] = {"100": "Briefmarke"}
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        W.host_cmd(s, "dep_open", {"c": 0, "p": 100})
        W.host_cmd(s, "dep_stage", {})            # Tipp
        W.host_cmd(s, "dep_stage", {})            # Antwort
        self.assertEqual([b["wort"] for b in s["beute"]], ["Briefmarke"])
        k = W.karte(s, "Briefmarke")
        self.assertEqual(k["nr"], 1)
        self.assertTrue(k["def"])

    def test_prolog_tafel_nur_mit_maulwurf(self):
        s, _ = abend()
        n = len(W.prolog_tafeln(s))
        W.host_cmd(s, "mole_toggle", {"on": True})
        self.assertEqual(len(W.prolog_tafeln(s)), n + 1)


class NeueSpiele(unittest.TestCase):
    def _start(self, typ, mode="solo"):
        s, ids = abend()
        s["plan"] = [{"id": "x", "type": typ, "mode": mode, "pts": 2, "rounds": 3, "opt": ""}]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        return s, ids

    def test_woerterbuch_ablauf(self):
        s, ids = self._start("woerterbuch")
        ag = s["agents"]
        W.player_act(s, ag[0], {"v": "Ein kleiner Hund"})
        W.player_act(s, ag[1], {"v": "Eine Suppe"})
        W.host_cmd(s, "wb_abstimmen", {})
        opt = s["rnd"]["optionen"]
        echt = next(i for i, o in enumerate(opt) if o["id"] == "echt")
        von0 = next(i for i, o in enumerate(opt) if o["id"] == ag[0]["id"])
        with self.assertRaises(W.CmdError):                  # nicht für sich selbst
            W.player_act(s, ag[0], {"v": von0})
        W.player_act(s, ag[1], {"v": von0})                  # 1 getäuscht von Anna
        W.player_act(s, ag[2], {"v": echt})                  # 2 findet die echte
        W.host_cmd(s, "reveal", {})
        self.assertEqual(s["gains"].get(ag[0]["id"]), 1)
        self.assertEqual(s["gains"].get(ag[2]["id"]), 2)
        self.assertTrue(s["beute"])

    def test_schwaerzung_und_propaganda(self):
        s, ids = self._start("schwaerzung")
        W.player_act(s, s["agents"][0], {"v": "frei"})
        W.host_cmd(s, "award_schwarz", {})
        self.assertEqual(s["gains"].get(ids[0]), 2)
        s, ids = self._start("hoeher", "team")
        wahr = W.propaganda_wahr(s)
        self.assertIn(wahr, ("W", "P"))
        W.player_act(s, s["agents"][0], {"v": wahr})
        self.assertTrue(W.team_correct(s, W.team_of(s, ids[0])))


class Runde2026(unittest.TestCase):
    """Änderungen Okt. 2026: Einsatz-Limit, Umlagern am Gerät, Beutestatus, Zellenmodi, Zeittakt, Ziel."""

    def _start(self, typ, mode="solo", **extra):
        s, ids = abend()
        s["plan"] = [dict({"id": "x", "type": typ, "mode": mode, "pts": 2, "rounds": 3, "opt": ""}, **extra)]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        return s, ids

    def test_einsatz_limit_folgt_dem_rucksack(self):
        s, ids = self._start("wette")
        ag = s["agents"][0]
        s["scores"][ag["id"]] = 39
        W.player_act(s, ag, {"kind": "bet", "v": 10})
        W.host_cmd(s, "show_q", {})
        W.host_cmd(s, "reveal", {})
        W.host_cmd(s, "judge", {"id": ag["id"], "ok": False})
        self.assertEqual(W.total(s, ag["id"]), 29)
        W.host_cmd(s, "round_next", {})
        W.player_act(s, ag, {"kind": "bet", "v": 39})
        self.assertEqual(s["bets"][ag["id"]], 29)           # nicht mehr 39
        # Leerer Rucksack: darf 2 setzen, verliert aber nichts
        leer = s["agents"][1]
        W.player_act(s, leer, {"kind": "bet", "v": 5})
        self.assertEqual(s["bets"][leer["id"]], 2)
        W.host_cmd(s, "show_q", {})
        W.host_cmd(s, "judge", {"id": leer["id"], "ok": False})
        self.assertEqual(s["gains"].get(leer["id"]), 0)

    def test_umlagern_am_geraet_auch_in_fremde_rucksaecke(self):
        s, ids = abend()
        for i, a in enumerate(ids):
            s["scores"][a] = 10 * (i + 1)
        s["pendingSteal"], s["thief"] = {"winners": [ids[0]]}, ids[0]
        dieb = s["agents"][0]
        me = W.me_view(s, dieb)
        self.assertEqual(len(me["umlagern"]["rucksaecke"]), 3)
        with self.assertRaises(W.CmdError):                    # nur der Dieb darf
            W.player_act(s, s["agents"][1], {"kind": "steal", "v": ids[3]})
        W.player_act(s, dieb, {"kind": "steal", "v": ids[3], "ziel": ids[1]})
        self.assertEqual(s["scores"][ids[3]], 32)
        self.assertEqual(s["scores"][ids[1]], 24)              # 20 + 4
        self.assertEqual(s["scores"][ids[0]], 10)
        self.assertIsNone(s["pendingSteal"])
        self.assertEqual(W.abend_statistik(s)["fuerAndere"], 8)

    def test_beutekarte_ohne_treffer_bleibt_grau(self):
        s, ids = self._start("emoji")
        W.host_cmd(s, "reveal", {})
        self.assertTrue(s["beute"][0]["verloren"])
        self.assertTrue(W.public_view(s)["stage"]["karte"]["verloren"])
        W.host_cmd(s, "gain", {"id": ids[0], "d": 2})
        self.assertFalse(s["beute"][0]["verloren"])

    def test_zellen_abstimmung_und_zuversicht(self):
        s, ids = abend(5)
        s["plan"] = [{"id": "x", "type": "hoeher", "mode": "team", "pts": 2, "rounds": 2, "opt": "", "zm": "mehrheit"}]
        s["teamCount"] = 2
        W.host_cmd(s, "mission_start", {})
        s["teams"] = [ids[:3], ids[3:]]
        W.host_cmd(s, "mission_begin", {})
        ag = W.by_id(s)
        W.player_act(s, ag[ids[0]], {"v": "W"})
        W.player_act(s, ag[ids[1]], {"v": "P"})
        W.player_act(s, ag[ids[2]], {"v": "P"})
        self.assertEqual(s["teamAnswers"]["0"]["v"], "P")
        me = W.me_view(s, ag[ids[0]])
        self.assertEqual(len(me["zelle"]["vorschlaege"]), 3)   # live sichtbar für die eigene Zelle
        self.assertEqual(W.me_view(s, ag[ids[3]])["zelle"]["vorschlaege"], [])   # andere Zelle sieht nichts
        # Zuversicht: eine sehr sichere Stimme schlägt zwei unsichere
        s["plan"][0]["zm"] = "zuversicht"
        W.host_cmd(s, "round_next", {})
        W.player_act(s, ag[ids[0]], {"v": "W", "c": 100})
        W.player_act(s, ag[ids[1]], {"v": "P", "c": 20})
        W.player_act(s, ag[ids[2]], {"v": "P", "c": 20})
        self.assertEqual(s["teamAnswers"]["0"]["v"], "W")

    def test_rangordnung_borda(self):
        s, ids = abend(3)
        s["plan"] = [{"id": "x", "type": "ranking", "mode": "team", "pts": 2, "rounds": 1, "opt": "", "zm": "mehrheit"}]
        W.host_cmd(s, "mission_start", {})
        s["teams"] = [ids, []]
        W.host_cmd(s, "mission_begin", {})
        n = len(W.lines_of(W.item(s)))
        a = W.LETTERS[:n]
        ag = W.by_id(s)
        W.player_act(s, ag[ids[0]], {"v": a})
        W.player_act(s, ag[ids[1]], {"v": a})
        W.player_act(s, ag[ids[2]], {"v": a[::-1]})
        self.assertEqual(s["teamAnswers"]["0"]["v"], a)
        with self.assertRaises(W.CmdError):
            W.player_act(s, ag[ids[0]], {"v": "A"})

    def test_zeittakt(self):
        s, ids = self._start("emoji", takt=10)
        s["plan"][0]["pts"] = 4
        t0 = s["rnd"]["t0"]
        m = W.mission(s)
        self.assertEqual(W.takt_wert(s, m, t0 + 5), 4)
        self.assertEqual(W.takt_wert(s, m, t0 + 15), 2)
        self.assertEqual(W.takt_wert(s, m, t0 + 25), 1)
        self.assertEqual(W.takt_wert(s, m, t0 + 95), 1)
        s["feed"].append({"id": ids[0], "v": "x", "t": t0 + 12, "z": 0})
        W.host_cmd(s, "judge", {"id": ids[0], "ok": True, "i": 0})
        self.assertEqual(s["gains"][ids[0]], 2)

    def test_auto_ziel_aus_dem_plan(self):
        s, ids = abend()
        s["plan"] = [{"id": "x", "type": "schaetzen", "mode": "solo", "pts": 3, "rounds": 5, "opt": ""},
                     {"id": "y", "type": "hoeher", "mode": "team", "pts": 2, "rounds": 5, "opt": ""}]
        self.assertEqual(W.max_woerter(s), 15 + 40)
        s["zielProzent"] = 50
        self.assertEqual(W.ziel_wert(s), 28)

    def test_maulwurf_praemie_zahlt_das_amt(self):
        s, ids = abend()
        W.host_cmd(s, "mole_toggle", {"on": True})
        mole = s["mole"]["id"]
        for a in ids:
            s["scores"][a] = 10
        W.host_cmd(s, "mole_resolve", {})                     # keine Stimmen → entkommen
        self.assertEqual(s["scores"][mole], 15)
        self.assertTrue(all(s["scores"][a] == 10 for a in ids if a != mole))
        s["screen"] = "finale"
        v = W.public_view(s)
        self.assertNotIn(mole, [x["id"] for x in v["hueterRanking"]])
        self.assertEqual(v["statistik"]["gesamt"], 40)

    def test_klang_signale(self):
        s, ids = self._start("emoji")
        arten = [c["art"] for c in s["cues"]]
        self.assertEqual(arten[-2:], ["einsatz", "los"])
        W.host_cmd(s, "klang_set", {"klang": {"musik": {"an": True, "url": "/media/x.mp3"}, "cues": {"ende": "/media/e.mp3", "quatsch": "y"}}})
        self.assertEqual(s["klang"]["cues"], {"ende": "/media/e.mp3"})
        self.assertTrue(s["klang"]["musik"]["an"])


class Runde2026b(unittest.TestCase):
    """Zweite Runde Okt. 2026: Rotation, Testlauf, Ereignisse, Gleichstand, Personalakten, KI-Import, Epilog."""

    def test_rotation_ueberspringt_ausgeschaltete(self):
        s, ids = abend()
        liste = [{"e": "1", "a": "a"}, {"e": "2", "a": "b", "aus": True}, {"e": "3", "a": "c"}]
        W.host_cmd(s, "content_set", {"type": "emoji", "list": liste})
        self.assertTrue(s["content"]["emoji"][1]["aus"])
        s["plan"] = [{"id": "x", "type": "emoji", "mode": "solo", "pts": 2, "rounds": 3, "opt": ""}]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        gesehen = [W.item(s)["e"]]
        for _ in range(2):
            W.host_cmd(s, "round_next", {})
            gesehen.append(W.item(s)["e"])
        self.assertEqual(gesehen, ["1", "3", "1"])

    def test_testlauf_laesst_den_abend_unberuehrt(self):
        s, ids = abend()
        s["scores"][ids[0]] = 7
        cur = s["cursor"].get("emoji", 0)
        W.host_cmd(s, "test_start", {"type": "emoji", "i": 2})
        self.assertEqual(W.item(s) if s["phase"] == "play" else None, None)
        W.host_cmd(s, "mission_begin", {})
        self.assertEqual(W.item(s)["e"], s["content"]["emoji"][2]["e"])
        W.host_cmd(s, "gain", {"id": ids[0], "d": 5})
        W.host_cmd(s, "reveal", {})
        W.host_cmd(s, "mission_finish", {})
        self.assertIsNone(s["test"])
        self.assertEqual(s["scores"][ids[0]], 7)
        self.assertEqual(s["beute"], [])
        self.assertEqual(s["cursor"].get("emoji", 0), cur)
        self.assertEqual(len(s["plan"]), len(W.make_plan()))

    def test_maulwurf_im_einsatzplan(self):
        s, ids = abend()
        s["plan"] = [{"id": "a", "type": "maulwurf_los", "mode": "solo", "pts": 0, "rounds": 1, "opt": ""},
                     {"id": "b", "type": "maulwurf_wahl", "mode": "solo", "pts": 0, "rounds": 1, "opt": ""}]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        self.assertTrue(s["mole"]["on"] and s["mole"]["id"] in ids)
        self.assertIn("rolle", W.me_view(s, s["agents"][0]))
        W.host_cmd(s, "mission_finish", {})
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        self.assertTrue(s["mole"]["voteOpen"])
        self.assertEqual(W.public_view(s)["stage"]["type"], "maulwurf_wahl")
        W.host_cmd(s, "mission_finish", {})
        self.assertFalse(s["mole"]["voteOpen"])

    def test_gleichstand_alle_duerfen_nacheinander(self):
        s, ids = abend()
        for a in ids:
            s["scores"][a] = 20
        s["pendingSteal"] = {"winners": [ids[0], ids[1]]}
        W.host_cmd(s, "steal_alle", {})
        erster = s["thief"]
        W.host_cmd(s, "steal_skip", {})
        self.assertIsNotNone(s["pendingSteal"])
        self.assertNotEqual(s["thief"], erster)
        W.host_cmd(s, "steal_victim", {"id": ids[3]})
        self.assertIsNone(s["pendingSteal"])
        self.assertIn("verzichtet", s["lastSteal"])
        self.assertIn("umgelagert", s["lastSteal"])

    def test_wankelmut_wird_gezaehlt(self):
        s, ids = abend()
        s["plan"] = [{"id": "x", "type": "schaetzen", "mode": "solo", "pts": 2, "rounds": 1, "opt": ""}]
        W.host_cmd(s, "mission_start", {})
        W.host_cmd(s, "mission_begin", {})
        ag = s["agents"][0]
        for v in ("10", "12", "15"):
            W.player_act(s, ag, {"v": v})
        self.assertEqual(s["tracking"][ag["id"]]["wechsel"], 2)
        akten = W.personalakten(s)
        self.assertEqual(akten[0]["key"], "wankelmut")

    def test_ki_auftrag_und_import(self):
        s, ids = abend()
        text, offen, _ = W.beute_auftrag(s)
        self.assertIn("ref=content:schaetzen:0", text)
        W.host_cmd(s, "beute_import", {"daten": {"beute": [{"ref": "content:schaetzen:0", "wort": "Wörterflut"},
                                                           {"ref": "unsinn:1", "wort": "x"}],
                                                 "kartei": {"Wörterflut": {"art": "die", "def": "Sehr viele Wörter.", "vermerk": "poetisch"}}}})
        self.assertEqual(s["content"]["schaetzen"][0]["beute"], "Wörterflut")
        self.assertEqual(s["kartei"]["Wörterflut"]["vermerk"], "poetisch")
        self.assertLess(W.beute_auftrag(s)[1], offen)

    def test_epilog_und_abspann(self):
        s, ids = abend()
        stufen = W.finale_stufen(s)
        self.assertEqual(stufen[-1], "abspann")
        self.assertEqual(stufen.count("epilog"), len(s["story"]["epilog"]))
        s["screen"] = "finale"
        s["finaleStufe"] = stufen.index("epilog")
        v = W.public_view(s)
        self.assertEqual(v["epilog"]["nr"], 1)
