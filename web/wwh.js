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
    return `<div class="karteikarte ${opt.klein ? 'kompakt' : ''} ${opt.neu ? 'neu' : ''}">
      <div class="kk-kopf"><div class="kk-wort">${esc(k.wort)}${k.art ? `<small>${esc(k.art)}</small>` : ''}</div>
        <div class="kk-az">${az}${k.tag ? ' · Tag ' + k.tag : ''}</div></div>
      <span class="kk-geborgen">Geborgen</span>
      <dl>${zeile('Bedeutung', k.def || '—')}${zeile('Herkunft', k.herkunft)}${opt.klein ? '' : zeile('Fundort', k.ort)}</dl>
      ${k.vermerk ? `<span class="kk-stempel">${esc(VERMERK[k.vermerk] || k.vermerk)}</span>` : ''}
    </div>`;
  }

  return { esc, pad, sleep, fmtGain, deNum, poll, post, render, actions, qr, karte, VERMERK };
})();
