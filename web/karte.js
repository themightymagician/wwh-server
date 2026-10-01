/* WWH — Weltkarte für Atlas. Braucht d3 und topojson (liegen unter /vendor).
   Karte.erstellen(element, { onPick(key) }) → { klassen(map), notizen({pins, linien}), name(key) } */
const Karte = (() => {
  let laden = null;
  const daten = () => laden || (laden = Promise.all([
    fetch('/vendor/countries-110m.json').then(r => r.json()),
    fetch('/geo.json').then(r => r.json()),
  ]).then(([topo, geo]) => ({ topo, geo, feats: topojson.feature(topo, topo.objects.countries).features })));
  const schluessel = f => f.id != null ? String(+f.id) : 'x:' + f.properties.name;

  async function erstellen(el, opt = {}) {
    const { geo, feats } = await daten();
    el.innerHTML = '';
    const svg = d3.select(el).append('svg').attr('class', 'karte-svg').attr('role', 'img').attr('aria-label', 'Weltkarte');
    const gGitter = svg.append('g'), gLand = svg.append('g'), gNotiz = svg.append('g');
    let weg = null, zoomlage = d3.zoomIdentity, gedrueckt = null, notizen = { pins: [], linien: [] };

    gGitter.append('path').datum(d3.geoGraticule10()).attr('class', 'k-gitter');
    gLand.selectAll('path').data(feats).join('path')
      .attr('class', 'k-land').attr('data-k', schluessel)
      .on('click', (ev, f) => {
        if (gedrueckt && Math.hypot(ev.clientX - gedrueckt[0], ev.clientY - gedrueckt[1]) > 6) return;
        if (opt.onPick) opt.onPick(schluessel(f));
      });
    svg.on('pointerdown', ev => { gedrueckt = [ev.clientX, ev.clientY]; });

    function zeichnen() {
      const b = el.clientWidth, h = el.clientHeight;
      if (!b || !h) return;
      weg = d3.geoPath(d3.geoEqualEarth().fitSize([b, h * 0.96], { type: 'Sphere' }).translate([b / 2, h / 2]));
      svg.attr('width', b).attr('height', h).attr('viewBox', `0 0 ${b} ${h}`);
      gLand.selectAll('path').attr('d', weg);
      gGitter.selectAll('path').attr('d', weg);
      notizZeichnen();
    }
    function notizZeichnen() {
      if (!weg) return;
      gNotiz.selectAll('*').remove();
      const p = k => geo[k] ? weg.projection()(geo[k].c) : null;
      (notizen.linien || []).forEach(l => {
        if (!geo[l.von] || !geo[l.nach]) return;
        gNotiz.append('path').datum({ type: 'LineString', coordinates: [geo[l.von].c, geo[l.nach].c] })
          .attr('class', 'k-peilung').attr('d', weg);
      });
      (notizen.pins || []).forEach((pin, i) => {
        const xy = p(pin.key); if (!xy) return;
        const g = gNotiz.append('g').attr('class', 'k-pin ' + (pin.cls || '')).attr('transform', `translate(${xy[0]},${xy[1]})`);
        g.append('circle').attr('r', 5);
        if (pin.label) g.append('text').attr('y', -9 - (pin.stapel || 0) * 14).attr('text-anchor', 'middle').text(pin.label);
      });
      zoomen();
    }
    function zoomen() {
      const k = zoomlage.k;
      [gGitter, gLand, gNotiz].forEach(g => g.attr('transform', zoomlage));
      gLand.selectAll('path').style('stroke-width', (0.4 / k) + 'px');
      gGitter.selectAll('path').style('stroke-width', (0.5 / k) + 'px');
      gNotiz.selectAll('.k-peilung').style('stroke-width', (1.8 / k) + 'px').style('stroke-dasharray', `${5 / k}px ${4 / k}px`);
      gNotiz.selectAll('.k-pin').each(function () {
        const t = d3.select(this).attr('transform').replace(/ scale\(.*\)/, '');
        d3.select(this).attr('transform', t + ` scale(${1 / k})`);
      });
    }
    const zoom = d3.zoom().scaleExtent([1, 14]).on('zoom', ev => { zoomlage = ev.transform; zoomen(); });
    svg.call(zoom);
    new ResizeObserver(zeichnen).observe(el);
    zeichnen();
    // Hochkant (Handy): gleich etwas hineinzoomen, damit die Länder groß genug zum Antippen sind
    const b0 = el.clientWidth, h0 = el.clientHeight;
    if (weg && h0 > b0 * 0.6) {
      const k = Math.min(3, (h0 / b0) / 0.5), pt = weg.projection()(opt.mitte || [15, 38]);
      svg.call(zoom.transform, d3.zoomIdentity.translate(b0 / 2 - k * pt[0], h0 / 2 - k * pt[1]).scale(k));
    }

    return {
      klassen(map) { gLand.selectAll('path').attr('class', f => 'k-land ' + (map[schluessel(f)] || '')); },
      notizen(n) { notizen = n || { pins: [], linien: [] }; notizZeichnen(); },
      name: k => geo[k] ? geo[k].name : k,
      geo,
    };
  }
  return { erstellen, daten };
})();
