// Reine Logik ohne DOM – im Browser (window.AJ) und in Node (module.exports) nutzbar.
(function (root) {
  const fold = s => String(s).toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/[̀-ͯ]/g, '');

  // Damerau-Levenshtein (Tippfehler: fehlender/doppelter/vertauschter Buchstabe)
  function dl(a, b) {
    const m = a.length, n = b.length;
    if (!m) return n; if (!n) return m;
    const d = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
    for (let j = 0; j <= n; j++) d[0][j] = j;
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
      const c = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
    return d[m][n];
  }

  // Wortschatz-Index: gefaltete Schreibweise -> schöne Schreibweise
  function makeVocab(words) {
    const map = new Map();
    for (const w of words) { const k = fold(w); if (k.length >= 3 && !map.has(k)) map.set(k, w); }
    return map;
  }

  function maxDist(len) { return len <= 3 ? 0 : len <= 6 ? 1 : 2; }

  // Korrigiert ein einzelnes Wort. Gibt {word, changed} zurück.
  function fixWord(word, vocab) {
    if (!/^[A-Za-zÄÖÜäöüß]+$/.test(word) || word.length < 4) return { word, changed: false };
    const k = fold(word);
    if (vocab.has(k)) { const v = vocab.get(k); return { word: v, changed: false }; } // bekannt – Schreibweise (Umlaute) übernehmen
    let best = null, bd = 99, tie = false;
    const lim = maxDist(k.length);
    for (const [vk, v] of vocab) {
      if (Math.abs(vk.length - k.length) > lim) continue;
      const d = dl(k, vk);
      if (d < bd) { bd = d; best = v; tie = false; } else if (d === bd && v !== best) tie = true;
    }
    if (best && bd <= lim && !tie) return { word: keepCase(word, best), changed: true };
    return { word, changed: false };
  }
  function keepCase(orig, fixed) { return orig[0] === orig[0].toLowerCase() ? fixed.charAt(0).toLowerCase() + fixed.slice(1) : fixed.charAt(0).toUpperCase() + fixed.slice(1); }

  // Ganze Eingabe korrigieren (Wort für Wort). Zahlen/Mengen bleiben unberührt.
  function correct(text, vocab) {
    let changed = false;
    const out = text.split(/(\s+)/).map(t => {
      if (/^\s+$/.test(t)) return t;
      const r = fixWord(t, vocab); if (r.changed) changed = true; return r.word;
    }).join('');
    return { text: out, changed };
  }

  // ---- Angebote ----
  const STOP = new Set(['und', 'mit', 'von', 'der', 'die', 'das', 'ohne', 'gram', 'stueck', 'stk', 'pack', 'packung']);
  function tokens(name) {
    return fold(name).split(/[^a-z0-9]+/).filter(t => t.length >= 3 && !/^\d+$/.test(t) && !/^\d+(g|kg|ml|l)$/.test(t) && !STOP.has(t));
  }
  // Treffer nur, wenn das gesuchte Wort am ENDE eines Wortes steht (Hackfleisch, Rinderhackfleisch),
  // nicht am Anfang (Butter ≠ Butterkeks, Eier ≠ Eiernudeln). Plural-Endungen sind erlaubt.
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const stem = t => (t.length >= 6 ? t.replace(/(en|n|e|s)$/, '') : t);
  // Bekannte Verwechslungen: Suchwort -> Wortanfänge, die NICHT gemeint sind
  const FALSE_FRIENDS = { milch: /^(butter|kondens|kokos|sauer|schoko|mandel|hafer|soja|reis|muller|alpen)/, kase: /^(kase)?(kuchen|sahne)/, brot: /^(brot)?(aufstrich)/ };
  function wordMatches(word, t) {
    if (!new RegExp(esc(stem(t)) + '(?:en|n|e|s)?$').test(word)) return false;
    const ff = FALSE_FRIENDS[t];
    return !(ff && ff.test(word));
  }
  // Wenn diese Wörter irgendwo im Produktnamen stehen, ist es nicht das gemeinte Grundprodukt (Milch Reis, Advents-Eier ...)
  const EXCLUDE = { milch: /(reis|schnitte|schoko|choco|brotchen|kakao|drink|pudding|riegel|kondens|shake|kokos|muller|mause|bonbon|freunde|alpen|kaffee|pflanz)/, eier: /(advent|schoko|oster|nougat|marzipan|likor|nudel|kuchen|salat|farbe)/ };
  function matches(itemName, offer) {
    const full = fold((offer.produkt || '') + ' ' + (offer.beschreibung || ''));
    const words = full.split(/[^a-z0-9]+/).filter(Boolean);
    const t = tokens(itemName);
    const need = t.length ? t : [fold(itemName).trim()];
    return need.every(x => x && words.some(w => wordMatches(w, x)) && !(EXCLUDE[x] && EXCLUDE[x].test(full)));
  }
  // marktguru: "grundpreis" = Preis pro kg/l/Stück (steht in "einheit"); "menge" ist nur die Stückzahl.
  function unitPrice(o) {
    const g = Number(o.grundpreis);
    return g > 0 && o.einheit ? { v: g, u: o.einheit } : null;
  }
  function todayISO() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  // Abgelaufene Angebote fliegen raus; schon gültige kommen vor noch nicht gültigen; dann nach Grundpreis (wenn alle gleiche Einheit), sonst Packungspreis.
  function rank(hits, today) {
    today = today || todayISO();
    const live = hits.filter(o => !o.bis || o.bis >= today);
    const us = live.map(unitPrice);
    const useUnit = us.length > 0 && us.every(Boolean) && new Set(us.map(u => u.u)).size === 1;
    return live.map((o, i) => ({ o, u: us[i], later: (o.von || '') > today, key: useUnit ? us[i].v : o.preis }))
      .sort((a, b) => (a.later - b.later) || (a.key - b.key))
      .map(x => ({ ...x.o, _u: x.u, _later: x.later }));
  }
  function offersFor(itemName, offers) { return rank(offers.filter(o => matches(itemName, o))); }

  const api = { fold, dl, makeVocab, fixWord, correct, tokens, matches, unitPrice, todayISO, rank, offersFor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.AJ = api;
})(typeof window !== 'undefined' ? window : globalThis);
