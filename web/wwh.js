/* WWH — gemeinsame Helfer. */
const WWH = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pad = n => String(n).padStart(2, '0');
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const fmtGain = n => !n ? '' : (n > 0 ? '+' + n : String(n));
  const deNum = v => { const s = String(v ?? '').replace(/[^\d,.-]/g, ''); if (!s) return NaN; return parseFloat(s.replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.')); };

  // Long-Polling: der Server antwortet sofort bei neuer Version, sonst nach ~25 s.
  function poll(url, onData) {
    let v = -1, down = false, sofort = false;
    const banner = document.createElement('div');
    banner.className = 'verbindung'; banner.hidden = true; banner.textContent = 'Verbindung zum Server unterbrochen …';
    document.addEventListener('DOMContentLoaded', () => document.body.appendChild(banner));
    if (document.body) document.body.appendChild(banner);
    (async () => {
      for (;;) {
        try {
          // Nach einer Störung sofort antworten lassen (v=-1), statt bis zu 25 s auf eine Änderung zu warten
          const r = await fetch(url() + (url().includes('?') ? '&' : '?') + 'v=' + (sofort ? -1 : v), { cache: 'no-store' });
          if (r.status === 401) { location.reload(); return; }
          if (!r.ok) throw new Error(r.status);
          const d = await r.json();
          if (down) { down = false; banner.hidden = true; }
          if (d.v !== v || sofort) { v = d.v; onData(d); }
          sofort = false;
        } catch (e) {
          // Ein abgebrochener Abruf (Download, Tab im Hintergrund) ist meist harmlos: erst kurz still neu versuchen
          sofort = true;
          await sleep(down ? 2000 : 300);
          if (!down) { down = true; setTimeout(() => { if (down) banner.hidden = false; }, 1500); }
        }
      }
    })();
    return { force: () => { v = -1; } };
  }

  async function post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    let d = {}; try { d = await r.json(); } catch (e) {}
    if (!r.ok || d.ok === false) throw new Error(d.error || ('HTTP ' + r.status));
    return d;
  }

  // Neu zeichnen, ohne dem Nutzer den Fokus oder halb getippten Text zu klauen.
  // Eingabefelder brauchen dafür ein data-k-Attribut.
  function render(el, html) {
    const a = document.activeElement;
    const k = a && el.contains(a) && a.dataset ? a.dataset.k : null;
    const val = k && 'value' in a ? a.value : null;
    let ss = null, se = null; try { ss = a.selectionStart; se = a.selectionEnd; } catch (e) {}
    el.innerHTML = html;
    if (k) {
      const n = el.querySelector('[data-k="' + CSS.escape(k) + '"]');
      if (n) { if (val !== null && n.type !== 'file') n.value = val; n.focus(); try { if (ss != null) n.setSelectionRange(ss, se); } catch (e) {} }
    }
  }

  // Klick-Delegation: <button data-do="name" data-x="…">
  function actions(root, map) {
    root.addEventListener('click', e => {
      const b = e.target.closest('[data-do]');
      if (!b || !root.contains(b) || b.disabled) return;
      const fn = map[b.dataset.do];
      if (fn) { e.preventDefault(); fn(b.dataset, b, e); }
    });
  }

  function qr(text, cell) {
    if (typeof qrcode !== 'function') return '';
    const q = qrcode(0, 'M'); q.addData(text); q.make();
    return q.createSvgTag({ cellSize: cell || 6, margin: 2, scalable: true });
  }

  // Karteikarte eines Beuteworts. k = {wort, art, def, herkunft, vermerk, ort, tag, nr}
  const VERMERK = { fremd: 'Fremd', alt: 'Veraltet', doppeldeutig: 'Doppeldeutig', mundartlich: 'Mundart', derb: 'Unanständig',
    poetisch: 'Gefühlsduselig', 'aufrührerisch': 'Aufrührerisch', 'unerwünscht': 'Unerwünscht', umgangssprachlich: 'Umgangssprache',
    unamtlich: 'Unamtlich', 'verdächtig': 'Verdächtig', umstritten: 'Umstritten' };
  function karte(k, opt) {
    if (!k) return '';
    opt = opt || {};
    const zeile = (dt, dd) => dd ? `<dt>${dt}</dt><dd>${esc(dd)}</dd>` : '';
    const az = k.nr ? `Az. WWH-${pad(k.nr)}` : 'Az. WWH-··';
    return `<div class="karteikarte ${opt.klein ? 'kompakt' : ''} ${opt.neu ? 'neu' : ''} ${k.verloren ? 'verloren' : ''}">
      <div class="kk-kopf"><div class="kk-wort" data-fit="0.45">${esc(k.wort)}${k.art ? `<small>${esc(k.art)}</small>` : ''}</div>
        <div class="kk-az">${az}${k.tag ? ' · Tag ' + k.tag : ''}</div></div>
      <span class="kk-geborgen">${k.verloren ? 'Nicht geborgen' : 'Geborgen'}</span>
      <dl>${zeile('Bedeutung', k.def || '—')}${zeile('Herkunft', k.herkunft)}${opt.klein ? '' : zeile('Fundort', k.ort)}</dl>
      ${k.vermerk ? `<span class="kk-stempel">${esc(VERMERK[k.vermerk] || k.vermerk)}</span>` : ''}
    </div>`;
  }

  // ---- Einpassen: nichts bricht um, nichts scrollt
  // [data-fit] = eine Zeile; die Schrift schrumpft bis höchstens auf data-fit × Ausgangsgröße (Standard 0,3).
  function passeText(root) {
    (root || document).querySelectorAll('[data-fit]').forEach(el => {
      el.style.fontSize = '';
      if (el.scrollWidth <= el.clientWidth + 1) return;
      const max = parseFloat(getComputedStyle(el).fontSize), min = max * (parseFloat(el.dataset.fit) || 0.3);
      let lo = min, hi = max;
      for (let i = 0; i < 9; i++) { const mid = (lo + hi) / 2; el.style.fontSize = mid + 'px'; if (el.scrollWidth <= el.clientWidth + 1) lo = mid; else hi = mid; }
      el.style.fontSize = lo + 'px';
    });
  }
  // Ganzen Inhalt so weit verkleinern (CSS zoom), dass er ohne Scrollen in seine Fläche passt.
  // Gemessen wird nur der Inhalt selbst – was daneben liegt (z. B. die Karteikarte), zählt nicht.
  function passeBox(box, inhalt, min) {
    if (!box || !inhalt) return 1;
    inhalt.style.zoom = '';
    const passt = () => inhalt.scrollHeight <= inhalt.clientHeight + 1 && inhalt.scrollWidth <= inhalt.clientWidth + 1;
    if (passt()) return 1;
    let lo = min || 0.3, hi = 1;
    for (let i = 0; i < 8; i++) { const mid = (lo + hi) / 2; inhalt.style.zoom = mid; if (passt()) lo = mid; else hi = mid; }
    inhalt.style.zoom = lo;
    return lo;
  }

  // ---- Karten ziehen: Liste mit <li data-l="…">; fertig(reihenfolge) nach dem Loslassen
  const ziehen = { aktiv: false };
  function sortierbar(root, listSel, fertig) {
    root.addEventListener('pointerdown', e => {
      const li = e.target.closest(listSel + ' > li[data-l]');
      if (!li || e.target.closest('button') || e.button > 0) return;
      e.preventDefault();
      const liste = li.parentElement, greif = e.clientY - li.getBoundingClientRect().top;
      ziehen.aktiv = true; li.classList.add('zieht'); try { li.setPointerCapture(e.pointerId); } catch (x) {}
      if (navigator.vibrate) navigator.vibrate(15);
      const bewegen = ev => {
        const y = ev.clientY, andere = [...liste.children].filter(x => x !== li);
        const vorher = new Map(andere.map(k => [k, k.getBoundingClientRect().top]));
        const ziel = andere.find(k => { const r = k.getBoundingClientRect(); return y < r.top + r.height / 2; });
        if ((ziel || null) !== li.nextElementSibling) {
          if (ziel) liste.insertBefore(li, ziel); else liste.appendChild(li);
          andere.forEach(k => { const d = vorher.get(k) - k.getBoundingClientRect().top; if (d) { k.style.transition = 'none'; k.style.transform = `translateY(${d}px)`;
            requestAnimationFrame(() => { k.style.transition = ''; k.style.transform = ''; }); } });
        }
        li.style.transform = '';
        li.style.transform = `translateY(${y - greif - li.getBoundingClientRect().top}px)`;
      };
      const los = () => {
        li.removeEventListener('pointermove', bewegen); li.removeEventListener('pointerup', los); li.removeEventListener('pointercancel', los);
        li.classList.remove('zieht'); li.style.transform = '';
        ziehen.aktiv = false;
        fertig([...liste.children].map(x => x.dataset.l), liste);
      };
      li.addEventListener('pointermove', bewegen); li.addEventListener('pointerup', los); li.addEventListener('pointercancel', los);
    });
  }

  // ---- Beispiel-Vorführung: ein Handy zeigt den Spielablauf in Dauerschleife
  const VF = {
    schaetzen: [
      ['<div class="vk">Schätzfrage</div><div class="vt">Wie lang ist die Donau?</div><div class="vfeld"><span class="tippen">2850</span></div><div class="vknopf vf-tipp">Schätzung abschicken</div>', 'Alle tippen ihre Schätzung ins Handy.'],
      ['<div class="vt">Wie lang ist die Donau?</div><div class="vok">✓ Abgegeben: 2850 Kilometer</div>', 'Die Moderation schließt die Abgabe und deckt auf.'],
      ['<div class="vkarte"><div class="vk">Lösung</div><div class="vh">2.857 km</div><b style="color:#c23522">Du warst am nächsten dran.</b></div><div class="vplus">+3</div>', 'Wer am nächsten dran ist, birgt die Wörter.']],
    ranking: [
      ['<div class="vk">Registratur</div><div class="vt">Nach Höhe ordnen</div><div class="vkk">Brocken</div><div class="vkk">Zugspitze</div><div class="vkk">Feldberg</div>', 'Die Karten liegen durcheinander.'],
      ['<div class="vk">Registratur</div><div class="vt">Nach Höhe ordnen</div><div class="vkk runter">Brocken</div><div class="vkk hoch">Zugspitze</div><div class="vkk">Feldberg</div>', 'Karte festhalten und an die richtige Stelle ziehen.'],
      ['<div class="vkk">Zugspitze</div><div class="vkk">Brocken</div><div class="vkk">Feldberg</div><div class="vzelle">Genitiv schlägt dieselbe Reihenfolge vor</div><div class="vknopf vf-tipp">Für die Zelle abschicken</div>', 'Die Zelle sieht live, was die anderen vorschlagen.'],
      ['<div class="vkarte"><div class="vk">Richtig sortiert</div><div class="vh">Zelle A</div></div><div class="vplus">+3</div>', 'Die schnellste richtige Zelle birgt ein Wort extra.']],
    impostor: [
      ['<div class="vk">Geheimsache</div><div class="vkarte vf-tipp" style="min-height:90px;background:repeating-linear-gradient(-45deg,#26221b 0 10px,#1d1a15 10px 20px);color:var(--papier)"><div class="vh">Antippen</div></div>', 'Jedes Handy zeigt verdeckt die Parole.'],
      ['<div class="vkarte" style="min-height:90px"><div class="vk">Die Parole</div><div class="vh">Gartenzwerg</div></div>', 'Nur der Eindringling kennt bloß die Kategorie.'],
      ['<div class="vk">Wer ist der Eindringling?</div><div class="vzwei"><div>Tilde</div><div class="an vf-tipp">Umlaut</div><div>Genitiv</div><div>Ellipse</div></div>', 'Reihum ein Wort sagen, dann abstimmen.'],
      ['<div class="vkarte"><div class="vk">Erkannt</div><div class="vh">Umlaut</div></div><div class="vplus">+3</div>', 'Erkannt: Alle anderen bergen Wörter.']],
    zoom: [
      ['<div class="vk">Bildarchiv</div><div class="vschloss" style="background-size:600%"></div><div class="vfeld"><span class="tippen">Sternennacht</span></div>', 'Ein Foto, sichtbar nur durchs Schlüsselloch.'],
      ['<div class="vschloss" style="background-size:200%"></div><div class="vknopf vf-tipp">Antwort funken</div>', 'Stufe für Stufe wird mehr sichtbar.'],
      ['<div class="vkarte"><div class="vh">Treffer!</div><div class="vt">auf Stufe 1</div></div><div class="vplus">+3</div>', 'Wer früh richtig liegt, birgt mehr.']],
    sound: [
      ['<div class="vk">Rundfunkarchiv</div><div class="vwelle">' + '<i style="animation-delay:-.1s"></i><i style="animation-delay:-.5s"></i><i style="animation-delay:-.3s"></i><i style="animation-delay:-.7s"></i><i style="animation-delay:-.2s"></i><i style="animation-delay:-.6s"></i>' + '</div><div class="vt" style="text-align:center">Rauschen Stufe 1 von 6</div>', 'Das Band läuft verrauscht über die Leinwand.'],
      ['<div class="vfeld"><span class="tippen">Lili Marleen</span></div><div class="vknopf vf-tipp">Antwort funken</div>', 'Titel oder Quelle ins Handy funken.'],
      ['<div class="vkarte"><div class="vh">Treffer!</div></div><div class="vplus">+3</div>', 'Früh erkannt bringt mehr.']],
    hoeher: [
      ['<div class="vkarte" style="background:#c23522;color:#f4ecda"><div class="vk" style="color:#f4ecda">Das Amt verkündet</div><div class="vh">Kölner Dom!</div><div class="vt">Höher als das Ulmer Münster.</div></div>', 'Das Amt behauptet etwas.'],
      ['<div class="vzwei"><div>Wahrheit</div><div class="an vf-tipp">Propaganda</div></div><div class="vzelle">Tilde: Propaganda · Genitiv: Propaganda</div>', 'Die Zelle entscheidet: Wahrheit oder Propaganda?'],
      ['<div class="vkarte"><div class="vk">Propaganda</div><div class="vt">Ulmer Münster 161,5 m</div><b style="color:#c23522">Durchschaut.</b></div><div class="vplus">+2</div>', 'Richtig durchschaut: Wörter für die ganze Zelle.']],
    emoji: [
      ['<div class="vk">Verschlüsselter Funk</div><div class="vemoji">🐷🍀</div><div class="vfeld"><span class="tippen">Schwein gehabt</span></div>', 'Eine Botschaft aus Zeichen.'],
      ['<div class="vemoji">🐷🍀</div><div class="vknopf vf-tipp">Antwort funken</div>', 'Wer sie zuerst knackt, funkt die Lösung.'],
      ['<div class="vkarte"><div class="vh">Treffer!</div></div><div class="vplus">+2</div>', 'Richtig geknackt birgt die Wörter.']],
    wette: [
      ['<div class="vk">Kategorie</div><div class="vh">Geografie</div><div class="vt">Dein Einsatz – höchstens 12</div><div class="vfeld"><span class="tippen">5</span></div><div class="vknopf vf-tipp">Einsatz setzen</div>', 'Erst die Kategorie, dann der Einsatz.'],
      ['<div class="vt">Wie heißt die Hauptstadt Australiens?</div><div class="vfeld"><span class="tippen">Canberra</span></div>', 'Dann kommt die Frage.'],
      ['<div class="vkarte"><div class="vh">Einsatz gewonnen</div></div><div class="vplus">+5</div>', 'Richtig: gewonnen. Falsch: verloren.']],
    woerterbuch: [
      ['<div class="vk">Beschlagnahmt</div><div class="vh">Kujon</div><div class="vfeld"><span class="tippen">Ein Butterfass</span></div>', 'Alle erfinden eine Bedeutung.'],
      ['<div class="vzwei" style="grid-template-columns:1fr"><div>A · Schuft, Schurke</div><div class="an vf-tipp">B · Ein Butterfass</div><div>C · Ein Kutscher</div></div>', 'Dann wird abgestimmt: Welche ist echt?'],
      ['<div class="vkarte"><div class="vt">Zwei sind auf deine Fälschung reingefallen.</div></div><div class="vplus">+2</div>', 'Echte finden oder andere täuschen.']],
    schwaerzung: [
      ['<div class="vtext">Die Gedanken sind <span class="vschwarz">████</span>, wer kann sie erraten?</div><div class="vfeld"><span class="tippen">frei</span></div><div class="vknopf vf-tipp">Antwort abgeben</div>', 'Was stand unter dem Balken?'],
      ['<div class="vtext">Die Gedanken sind <b style="color:#c23522">frei</b>, wer kann sie erraten?</div><div class="vkarte"><div class="vh">Richtig!</div></div><div class="vplus">+2</div>', 'Jede richtige Antwort birgt Wörter.']],
    deppardy: [
      ['<div class="vk">Deppardy</div><div class="vbrett">' + [100, 100, 100, 100, 200, 200, 200, 200, 300, 300, 300, 300].map(p => `<span>${p}</span>`).join('') + '</div>', 'Die Moderation wählt ein Feld.'],
      ['<div class="vt">Was ist ein „Plutzer“?</div><div class="vbuzzer vf-tipp">Buzzer</div>', 'Nach der Freigabe buzzern.'],
      ['<div class="vkarte"><div class="vh">Du bist dran!</div></div><div class="vplus">+200</div>', 'Richtig bringt Punkte, falsch kostet sie.']],
    atlas: [
      ['<div class="vk">Grenzkarte</div><div class="vh">Thuja</div><div class="vt">Woher stammt es wirklich?</div>', 'Ein Begriff erscheint.'],
      ['<div class="vwelt"><i style="left:8%;top:20%;width:30%;height:35%"></i><i style="left:44%;top:14%;width:22%;height:30%"></i><i class="vf-tipp" style="left:12%;top:30%;width:22%;height:24%;background:var(--signal)"></i><i style="left:60%;top:50%;width:30%;height:30%"></i></div><div class="vknopf">Tipp abschicken</div>', 'Land auf der Karte antippen.'],
      ['<div class="vkarte"><div class="vk">Richtig</div><div class="vh">Kanada</div><div class="vt">Nachbarland · 72 Punkte</div></div>', 'Je näher dran, desto mehr Punkte.']],
  };
  const ZELLE = { mehrheit: ['<div class="vzelle">Tilde: A · Genitiv: A · Umlaut: B</div><div class="vkarte"><div class="vk">Mehrheit der Zelle</div><div class="vh">A</div></div>', 'Abstimmung: Jede Person stimmt ab, die Mehrheit gilt.'],
    zuversicht: ['<div class="vt">Wie sicher bist du?</div><div style="height:6px;background:var(--nacht-3);position:relative"><i style="position:absolute;left:0;top:0;bottom:0;width:80%;background:var(--signal)"></i></div><div class="vzelle">Tilde 80 % · Genitiv 30 %</div>', 'Zuversicht: Sichere Stimmen wiegen mehr.'] };
  const vfStand = {};
  function vorfuehrung(typ, opt) {
    opt = opt || {};
    let bilder = (VF[typ] || []).slice();
    if (!bilder.length) return '';
    if (opt.zm && ZELLE[opt.zm]) bilder.splice(Math.max(1, bilder.length - 1), 0, ZELLE[opt.zm]);
    const key = typ + (opt.zm || '');
    const i = (vfStand[key] || 0) % bilder.length;
    return `<div class="vf" data-vf="${key}" data-n="${bilder.length}"${opt.breite ? ` style="--vfb:${opt.breite}"` : ''}><div class="vf-marke">So geht's</div>
      <div class="vf-handy">${bilder.map(([h], j) => `<div class="vf-bild ${j === i ? 'aktiv' : ''}">${h}</div>`).join('')}</div>
      <div class="vf-text">${bilder.map(([, t], j) => `<span class="${j === i ? 'aktiv' : ''}">${esc(t)}</span>`).join('')}</div></div>`;
  }
  setInterval(() => {
    const weiter = new Set();
    document.querySelectorAll('.vf[data-vf]').forEach(el => {
      const key = el.dataset.vf, n = +el.dataset.n;
      if (!weiter.has(key)) { vfStand[key] = ((vfStand[key] || 0) + 1) % n; weiter.add(key); }
      const i = vfStand[key] % n;
      el.querySelectorAll('.vf-bild').forEach((b, j) => b.classList.toggle('aktiv', j === i));
      el.querySelectorAll('.vf-text>span').forEach((b, j) => b.classList.toggle('aktiv', j === i));
    });
  }, 3200);

  return { esc, pad, sleep, fmtGain, deNum, poll, post, render, actions, qr, karte, VERMERK,
    passeText, passeBox, sortierbar, ziehen, vorfuehrung };
})();
