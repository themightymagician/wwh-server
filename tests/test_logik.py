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
