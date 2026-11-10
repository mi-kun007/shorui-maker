/* 導入の道順パネル。配布版だけの機能。
   達成は自前で持たず、サーバー（/api/quest）が設定と出力の実物を見て返した物をそのまま出す。
   ここで「済み」を書き換えられると、入れたつもりで先に進んでしまうため。 */
(function () {
  if (!/^https?:/.test(location.protocol)) return;   // file:// では出さない（APIが無い）

  var CSS = [
    '#qz{position:fixed;right:14px;bottom:14px;width:360px;max-width:calc(100vw - 28px);z-index:9999;',
    'font:13px/1.7 "Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,sans-serif;color:#111}',
    '#qz .card{background:#fff;border:1px solid #c9ced6;border-radius:8px;box-shadow:0 6px 22px rgba(0,0,0,.13);overflow:hidden}',
    '#qz .hd{display:flex;align-items:center;gap:8px;padding:9px 12px;background:#f6f7f9;border-bottom:1px solid #e3e6ea;cursor:pointer}',
    '#qz .hd b{font-size:13px;font-weight:600}',
    '#qz .cnt{margin-left:auto;font-size:12px;color:#555;font-variant-numeric:tabular-nums}',
    '#qz .bar{height:3px;background:#e3e6ea}',
    '#qz .bar i{display:block;height:3px;background:#2d6cdf;transition:width .35s}',
    '#qz .bd{padding:11px 12px 12px;max-height:66vh;overflow:auto}',
    '#qz .upd{background:#0b5cff;color:#fff;padding:8px 12px;font-size:12px;display:flex;',
    'align-items:center;gap:8px;justify-content:space-between}',
    '#qz .upd button{background:#fff;color:#0b5cff;border:0;border-radius:5px;padding:4px 10px;',
    'font-size:12px;cursor:pointer}',
    '#qz .ol{display:block;font-size:11px;color:#555;margin:6px 0}',
    '#qz .rrow{display:grid;grid-template-columns:1fr 72px 72px 22px;gap:4px;margin:3px 0}',
    '#qz .rrow input{padding:4px 6px;border:1px solid #d5d5d8;border-radius:5px;font-size:12px;width:100%;box-sizing:border-box}',
    '#qz .rrow.rhd{font-size:10px;color:#888}',
    '#qz .rrow .rx{border:0;background:none;color:#c33;cursor:pointer;font-size:13px}',
    '#qz .brow{border:1px solid #e3e3e6;border-radius:6px;padding:6px 8px;margin:4px 0;font-size:12px}',
    '#qz .brow.cur{border-color:#0b5cff;background:#f2f6ff}',
    '#qz .brow em{float:right;font-style:normal;color:#0b5cff;font-size:11px}',
    '#qz .brow button{float:right;font-size:11px;padding:2px 8px;border:1px solid #c9c9cf;',
    'background:#fff;border-radius:4px;cursor:pointer}',
    '#qz .ol input{display:block;width:100%;box-sizing:border-box;margin-top:2px;padding:5px 7px;',
    'border:1px solid #d5d5d8;border-radius:5px;font-size:12px}',
    '#qz .now{font-size:11px;color:#666;letter-spacing:.08em}',
    '#qz .now a{color:#2d6cdf;margin-left:8px;letter-spacing:0}',
    '#qz h4{margin:2px 0 5px;font-size:15px;font-weight:600}',
    '#qz p{margin:0 0 6px}',
    '#qz .why{color:#444}',
    '#qz .todo{background:#f4f7fd;border-left:3px solid #2d6cdf;padding:6px 9px;margin:6px 0}',
    '#qz .rw{color:#1c6b3c;font-size:12px}',
    '#qz .how{color:#555;font-size:12px;word-break:break-word;white-space:pre-wrap;line-height:1.75}',
    '#qz code{background:#f2f3f5;padding:1px 4px;border-radius:3px;font-size:12px}',
    '#qz .note{font-size:12px;color:#8a4b00;margin-top:5px}',
    '#qz .btns{display:flex;gap:6px;margin-top:9px;flex-wrap:wrap}',
    '#qz button{font:inherit;padding:4px 11px;border:1px solid #c2c7cf;background:#fff;border-radius:5px;cursor:pointer}',
    '#qz button:disabled{opacity:.4;cursor:default}',
    '#qz .nav{margin-top:9px;margin-bottom:-3px}',
    '#qz .nav button{padding:3px 10px;font-size:12px;color:#42618f}',
    '#qz button.pri{background:#2d6cdf;border-color:#2d6cdf;color:#fff}',
    '#qz ol{list-style:none;margin:9px 0 0;padding:9px 0 0;border-top:1px solid #eceef1}',
    '#qz li{display:flex;gap:7px;align-items:baseline;color:#777;font-size:12px;padding:1.5px 0;cursor:pointer}',
    '#qz li .mk{width:13px;flex:none;text-align:center}',
    '#qz li.ok{color:#1c6b3c}', '#qz li.cur{color:#111;font-weight:600}',
    '#qz li.sk{color:#aaa;text-decoration:line-through}',
    '#qz.min .bd{display:none}',
    '#qz .done{padding:12px;text-align:center}',
    '#qz .drop{border:2px dashed #9fb3d4;border-radius:7px;background:#f7faff;padding:14px 10px;text-align:center;',
    'color:#42618f;margin:8px 0 4px;cursor:pointer;transition:background .15s,border-color .15s}',
    '#qz .drop:hover,#qz .drop.on{background:#e9f1ff;border-color:#2d6cdf}',
    '#qz .drop b{display:block;font-size:13px;margin-bottom:2px}',
    '#qz .drop small{color:#6b7f9e;font-size:11px}',
    '#qz .files{margin:5px 0 0;font-size:11px;color:#555;max-height:76px;overflow:auto;text-align:left}',
    '#qz .files li{display:block;padding:1px 0;color:#555;cursor:default}',
    '#qz .rows{margin-top:7px;font-size:11.5px;max-height:150px;overflow:auto}',
    '#qz .rows h5{margin:6px 0 2px;font-size:11.5px;font-weight:600}',
    '#qz .rows .sure{color:#1c6b3c}#qz .rows .wait{color:#8a4b00}#qz .rows .clash{color:#a40000}',
    '#qz .busy{color:#42618f;font-size:12px;margin-top:6px}',
    '#qz .aibox{border:1px solid #c9ced6;border-radius:6px;padding:9px;margin:8px 0 2px;background:#fbfcfd}',
    '#qz .aibox label{display:block;font-size:11px;color:#5a6675;margin:5px 0 2px}',
    '#qz .aibox select,#qz .aibox input{width:100%;box-sizing:border-box;font:inherit;font-size:12px;',
    'padding:4px 6px;border:1px solid #c2c7cf;border-radius:4px;background:#fff}',
    '#qz .aibox .where{font-size:11px;color:#6b7f9e;margin-top:4px;word-break:break-all}',
    '#qz .aires{margin-top:7px;font-size:12px}',
    '#qz .aires.ok{color:#1c6b3c}#qz .aires.ng{color:#a40000}',
    '#qz .shot{margin:7px 0 2px;border:1px solid #dde1e6;border-radius:5px;overflow:hidden;background:#fff}',
    '#qz .shot img{display:block;width:100%;height:auto}',
    '#qz .shotcap{font-size:10.5px;color:#7a8493;padding:3px 6px;background:#f6f7f9;border-top:1px solid #eceef1}',
    '#qz .gain{background:#f2f8f4;border-left:3px solid #1c6b3c;padding:6px 9px;margin:7px 0 2px;color:#1c4a2c}',
    '#qz .shot{cursor:zoom-in}',
    '#qzbig{position:fixed;inset:0;background:rgba(20,24,30,.82);z-index:10000;display:flex;',
    'align-items:center;justify-content:center;padding:24px;cursor:zoom-out}',
    '#qzbig img{max-width:min(1100px,94vw);max-height:88vh;border-radius:6px;box-shadow:0 10px 40px rgba(0,0,0,.5);background:#fff}'
  ].join('');

  var st = { data: null, min: localStorage.getItem('pm_quest_min') === '1', view: null };

  function el(id) { return document.getElementById(id); }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }

  function mount() {
    var s = document.createElement('style'); s.textContent = CSS; document.head.appendChild(s);
    var w = document.createElement('div'); w.id = 'qz';
    w.innerHTML = '<div class="card"><div class="hd"><b>はじめの道順</b><span class="cnt"></span></div>' +
      '<div class="bar"><i style="width:0"></i></div><div class="bd"></div></div>';
    document.body.appendChild(w);
    w.querySelector('.hd').addEventListener('click', function () {
      st.min = !st.min; localStorage.setItem('pm_quest_min', st.min ? '1' : '0'); render();
    });
    if (st.min) w.classList.add('min');
  }

  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); });
  }

  function render() {
    var w = el('qz'); if (!w || !st.data) return;
    var d = st.data;
    w.classList.toggle('min', st.min);
    w.querySelector('.cnt').textContent = d.done + ' / ' + d.total;
    w.querySelector('.bar i').style.width = Math.round(d.done / d.total * 100) + '%';
    var bd = w.querySelector('.bd');

    if (d.finished) {
      bd.innerHTML = '<div class="done">ここまでで一通り動きます。<br>あとは毎朝、前日分が置いてあります。' +
        '<div class="btns" style="justify-content:center"><button id="qz-hide">閉じる</button></div></div>';
      el('qz-hide').onclick = function () { w.remove(); localStorage.setItem('pm_quest_done', '1'); };
      return;
    }

    var cur = st.view || d.current;
    var q = null, i;
    for (i = 0; i < d.quests.length; i++) if (d.quests[i].id === cur) q = d.quests[i];
    if (!q) q = d.quests[0];

    var h = '<div class="now">' + q.id + ' / ' + d.total +
            (d.current && q.id !== d.current ? ' <a href="#" id="qz-back">いまの続きへ戻る</a>' : '') +
            '</div><h4>' + esc(q.title) + '</h4>';
    if (q.gain) h += '<div class="gain">' + esc(q.gain) + '</div>';
    if (q.id === 11) h += outZoneHtml();
    if (q.id === 3) h += baseZoneHtml();
    if (q.id === 9) h += rateZoneHtml();
    if (q.id === 1 && d.done < 5) h += autoZoneHtml();
    if (q.shot) {
      h += '<div class="shot"><img src="tutorial/' + esc(q.shot) + '" alt="">' +
           '<div class="shotcap">' + (q.done ? 'いま出せる形' : 'こうなります') + '（見本の会社での例）</div></div>';
    }
    h += '<div class="todo">' + esc(q.todo) + '</div>';
    h += '<div class="how">' + esc(q.how) + '</div>';
    if (q.note) h += '<div class="note">' + esc(q.note) + '</div>';
    if (q.id === 5) h += '<div class="aibox" id="qz-ai">読み込み中…</div>';
    if (q.id === 6) h += routeZoneHtml();
    if (q.id === 6 && !q.done) h += dropZoneHtml();
    if (q.id === 8) h += knowZoneHtml();
    h += '<div class="btns nav">';
    h += '<button id="qz-prev"' + (q.id <= 1 ? ' disabled' : '') + '>← 前</button>';
    h += '<button id="qz-next"' + (q.id >= d.total ? ' disabled' : '') + '>次 →</button>';
    h += '</div>';
    h += '<div class="btns">';
    if (q.id === 9 && !q.done) h += '<button class="pri" id="qz-run">旅費規程を出す</button>';
    h += '<button id="qz-re">確かめる</button>';
    if (!q.done) h += '<button id="qz-skip">あとで</button>';
    h += '</div>';

    h += '<ol>';
    for (i = 0; i < d.quests.length; i++) {
      var x = d.quests[i];
      var cls = x.done ? 'ok' : (x.skipped ? 'sk' : (x.id === cur ? 'cur' : ''));
      h += '<li data-id="' + x.id + '" class="' + cls + '"><span class="mk">' +
        (x.done ? '✓' : (x.skipped ? '–' : '□')) + '</span>' + esc(x.title) + '</li>';
    }
    h += '</ol>';
    bd.innerHTML = h;

    wireAutoZone();
    wireOutZone();
    wireBaseZone();
    wireRouteZone();
    wireRateZone();
    var bk = el('qz-back'); if (bk) bk.onclick = function (e) { e.preventDefault(); st.view = null; render(); };
    var pv = el('qz-prev'); if (pv) pv.onclick = function () { st.view = Math.max(1, q.id - 1); render(); };
    var nx = el('qz-next'); if (nx) nx.onclick = function () { st.view = Math.min(d.total, q.id + 1); render(); };
    var re = el('qz-re'); if (re) re.onclick = function () { re.textContent = '見ています'; st.view = null; load(); };
    var sk = el('qz-skip'); if (sk) sk.onclick = function () {
      post('/api/quest/skip', { id: q.id }).then(function (r) { st.data = r; st.view = null; render(); });
    };
    if (q.id === 5) loadAiBox();
    if (q.id === 6 && !q.done) wireDropZone();
    if (q.id === 8) wireKnowZone();
    var run = el('qz-run'); if (run) run.onclick = function () {
      run.disabled = true; run.textContent = '出しています';
      post('/api/quest/run', { what: 'rules' }).then(function (r) {
        if (r.error) { run.disabled = false; run.textContent = '旅費規程を出す'; alert('出せませんでした: ' + r.error); return; }
        alert('出しました\n' + r.path);
        load();
      });
    };
    var shot = bd.querySelector('.shot');
    if (shot) shot.onclick = function () {
      var src = shot.querySelector('img').getAttribute('src');
      var big = document.createElement('div');
      big.id = 'qzbig';
      big.innerHTML = '<img src="' + src + '">';
      big.onclick = function () { big.remove(); };
      document.body.appendChild(big);
    };
    bd.querySelectorAll('li').forEach(function (li) {
      li.onclick = function () { st.view = +li.dataset.id; render(); };
    });
  }

  var picked = [];

  // ---- 日当と規程の金額 ----
  function rateZoneHtml() {
    return '<div class="know" id="qz-rate">' +
      '<div class="knowhd">日当と規程の金額</div>' +
      '<div class="knownote">ここで決めた額が、旅費規程と出張精算の両方に出ます。' +
      '相場はありますが、決めるのは会社です。税理士に見せてから施行してください。</div>' +
      '<div id="qz-rlist"></div>' +
      '<div class="btns" style="margin-top:2px"><button id="qz-radd">役職を足す</button></div>' +
      '<label class="ol">自分の役職<input id="qz-rrole" placeholder="代表取締役"></label>' +
      '<label class="ol">宿泊費の上限（1泊）<input id="qz-rlodge" placeholder="12000"></label>' +
      '<label class="ol">精算の期限（日）<input id="qz-rday" placeholder="7"></label>' +
      '<label class="ol">領収書が要らない額（未満）<input id="qz-rfree" placeholder="30000"></label>' +
      '<label class="ol">施行日<input id="qz-reff" placeholder="2026-09-01"></label>' +
      '<div class="btns"><button class="pri" id="qz-rsave">保存する</button>' +
      '<button id="qz-rmake">規程を出す</button></div>' +
      '<div id="qz-rres"></div></div>';
  }

  function rateRow(name, day, night) {
    return '<div class="rrow">' +
      '<input class="rn" value="' + esc(name) + '" placeholder="役職">' +
      '<input class="rd" value="' + esc(String(day)) + '" placeholder="日帰り">' +
      '<input class="rg" value="' + esc(String(night)) + '" placeholder="宿泊">' +
      '<button class="rx">×</button></div>';
  }

  function wireRateZone() {
    var z = el('qz-rate'); if (!z) return;
    fetch('/api/travel').then(function (r) { return r.json(); }).then(function (t) {
      var h = '<div class="rrow rhd"><span>役職</span><span>日帰り</span><span>宿泊</span><span></span></div>';
      var rates = t.rates || {};
      Object.keys(rates).forEach(function (k) {
        h += rateRow(k, rates[k].day || 0, rates[k].night || 0);
      });
      if (!Object.keys(rates).length) h += rateRow('代表取締役', 5000, 10000);
      el('qz-rlist').innerHTML = h;
      wireRateRows();
      el('qz-rrole').value = t.role || '';
      el('qz-rlodge').value = (t.lodging && t.lodging.cap) || '';
      el('qz-rday').value = t.settleWithinDays || '';
      el('qz-rfree').value = t.receiptFreeUnder || '';
      el('qz-reff').value = t.effectiveDate || '';
    });
    el('qz-radd').onclick = function () {
      el('qz-rlist').insertAdjacentHTML('beforeend', rateRow('', '', ''));
      wireRateRows();
    };
    el('qz-rsave').onclick = function () { saveRates(false); };
    el('qz-rmake').onclick = function () { saveRates(true); };
  }

  function wireRateRows() {
    el('qz-rlist').querySelectorAll('.rx').forEach(function (b) {
      b.onclick = function () { b.parentNode.remove(); };
    });
  }

  function saveRates(alsoMake) {
    var rates = {};
    el('qz-rlist').querySelectorAll('.rrow').forEach(function (row) {
      if (row.classList.contains('rhd')) return;
      var n = row.querySelector('.rn').value.trim();
      if (!n) return;
      rates[n] = { day: +row.querySelector('.rd').value || 0,
                   night: +row.querySelector('.rg').value || 0 };
    });
    var body = { rates: rates, role: el('qz-rrole').value.trim(),
                 lodgingCap: +el('qz-rlodge').value || 0,
                 settleWithinDays: +el('qz-rday').value || 7,
                 receiptFreeUnder: +el('qz-rfree').value || 0,
                 effectiveDate: el('qz-reff').value.trim() };
    el('qz-rres').innerHTML = '<div class="busy">入れています…</div>';
    post('/api/travel', body).then(function (r) {
      if (r.error) { el('qz-rres').innerHTML = '<div class="err">' + esc(r.error) + '</div>'; return; }
      if (!alsoMake) {
        el('qz-rres').innerHTML = '<div class="knownote">入れました。次に出す書類からこの額です。</div>';
        setTimeout(function () { st.view = null; load(); }, 700);
        return;
      }
      post('/api/quest/run', { what: 'rules' }).then(function (x) {
        el('qz-rres').innerHTML = x.error
          ? '<div class="err">' + esc(x.error) + '</div>'
          : '<div class="knownote">' + esc(x.message || '出しました') + '</div>';
        setTimeout(function () { st.view = null; load(); }, 900);
      });
    });
  }

  // ---- 経路と運賃を調べる（どこからどこへでも） ----
  var routeGot = null;

  function routeZoneHtml() {
    return '<div class="know" id="qz-route">' +
      '<div class="knowhd">区間の運賃を調べる</div>' +
      '<div class="knownote">出発と到着を入れて「乗換案内を開く」。' +
      'いつも使っている乗換案内が別にあるなら、そちらで構いません。<br>' +
      '出てきた画面をそのまま撮って、下の枠に落としてください。読んで候補を並べます。' +
      'どれで行ったかを押すと、その額が入ります。<br>' +
      '選んだ乗り物は覚えるので、同じ区間は次から手が要りません。</div>' +
      '<label class="ol">出発<input id="qz-r1" placeholder="東京"></label>' +
      '<label class="ol">到着<input id="qz-r2" placeholder="横浜"></label>' +
      '<div class="btns"><button class="pri" id="qz-ropen">乗換案内を開く</button>' +
      '<button id="qz-rlist2">要る区間を出す</button></div>' +
      '<div class="drop" id="qz-rdrop" style="display:none"></div>' +
      '<div id="qz-rres"></div></div>';
  }

  function wireRouteZone() {
    var b = el('qz-ropen'); if (!b) return;
    b.onclick = function () {
      var f = el('qz-r1').value, t = el('qz-r2').value;
      if (!f || !t) { el('qz-rres').innerHTML = '<div class="err">出発と到着を入れてください</div>'; return; }
      post('/api/route', { from: f, to: t, open: true }).then(function (r) {
        if (r.url) window.open(r.url, '_blank');
        el('qz-rres').innerHTML = '<div class="knownote">別の窓で開きました。' +
          '出てきた画面を撮って、上の枠に落としてください。</div>';
      });
    };
    var lb = el('qz-rlist2');
    if (lb) lb.onclick = function () {
      el('qz-rres').innerHTML = '<div class="busy">予定を見ています…</div>';
      fetch('/api/fare/pending').then(function (r) { return r.json(); }).then(function (g) {
        if (g.error) { el('qz-rres').innerHTML = '<div class="err">' + esc(g.error) + '</div>'; return; }
        if (!g.pairs || !g.pairs.length) {
          el('qz-rres').innerHTML = '<div class="knownote">' +
            esc(g.note || (g.base + ' から行く先は、もう額が入っています')) + '</div>';
          return;
        }
        var h = '<div class="knowhd">' + esc(g.base) + ' から、まだ額の無い区間</div>' +
          '<div class="knownote">押すと乗換案内が開きます。出てきた画面を上の枠に落としてください。</div>';
        g.pairs.forEach(function (p) {
          h += '<div class="brow"><b>' + esc(p.from) + ' → ' + esc(p.to) + '</b>' +
            '<button data-f="' + esc(p.from) + '" data-t="' + esc(p.to) + '">開く</button></div>';
        });
        el('qz-rres').innerHTML = h;
        el('qz-rres').querySelectorAll('button').forEach(function (b) {
          b.onclick = function () {
            el('qz-r1').value = b.dataset.f; el('qz-r2').value = b.dataset.t;
            post('/api/route', { from: b.dataset.f, to: b.dataset.t, open: true })
              .then(function (r) { if (r.url) window.open(r.url, '_blank'); });
          };
        });
      });
    };
    var z = el('qz-rdrop');
    var inp = document.createElement('input');
    inp.type = 'file'; inp.accept = 'image/*'; inp.style.display = 'none';
    inp.setAttribute('data-fd-small', '');
    inp.setAttribute('data-fd-title', '検索結果の画面を放り込む');
    z.parentNode.insertBefore(inp, z);
    z.onclick = function () { inp.click(); };
    inp.onchange = function () { readShot(inp.files[0]); };
    z.ondragover = function (e) { e.preventDefault(); z.classList.add('over'); };
    z.ondragleave = function () { z.classList.remove('over'); };
    z.ondrop = function (e) {
      e.preventDefault(); z.classList.remove('over');
      readShot(e.dataTransfer.files[0]);
    };
  }

  function readShot(file) {
    if (!file) return;
    var r = new FileReader();
    r.onload = function () {
      el('qz-rres').innerHTML = '<div class="busy">画面を読んでいます… 10秒ほど</div>';
      post('/api/route', { from: el('qz-r1').value, to: el('qz-r2').value, shot: r.result })
        .then(function (res) {
          renderRoutes(res.from || el('qz-r1').value, res.to || el('qz-r2').value, res);
        }).catch(function () {
          el('qz-rres').innerHTML = '<div class="err">読めませんでした</div>';
        });
    };
    r.readAsDataURL(file);
  }

  function renderRoutes(f, t, r) {
    var box = el('qz-rres'); if (!box) return;
    if (r.error) { box.innerHTML = '<div class="err">' + esc(r.error) + '</div>'; return; }
    routeGot = r;
    var rows = r.routes || [];
    if (!rows.length) {
      box.innerHTML = '<div class="knownote">' + esc(r.note || '画面から金額を読み取れませんでした。もう少し大きく撮ってみてください') + '</div>';
      return;
    }
    var h = '';
    if (r.note) h += '<div class="knownote">' + esc(r.note) + '</div>';
    rows.forEach(function (x, i) {
      h += '<div class="brow' + (i === r.picked ? ' cur' : '') + '">' +
        '<b>' + fmtYen(x.amount) + '</b> ' + esc(String(x.minutes)) + '分' +
        '<span class="src">' + esc((x.lines || []).join('／') || x.note || '') + '</span>' +
        '<button data-i="' + i + '">これで行った</button></div>';
    });
    box.innerHTML = h;
    box.querySelectorAll('button').forEach(function (btn) {
      btn.onclick = function () {
        btn.disabled = true; btn.textContent = '入れています';
        post('/api/route', { from: f, to: t, pick: +btn.dataset.i, routes: rows })
          .then(function (res) {
            box.innerHTML = res.error
              ? '<div class="err">' + esc(res.error) + '</div>'
              : '<div class="knownote">' + fmtYen(res.amount) + ' で入れました' +
                (res.prefer && res.prefer.length ? '。次からは ' + esc(res.prefer.join('・')) + ' を優先します' : '') +
                '</div>';
            setTimeout(function () { st.view = null; load(); }, 900);
          });
      };
    });
  }

  // ---- 拠点（今いる場所） ----
  function baseZoneHtml() {
    return '<div class="know" id="qz-base">' +
      '<div class="knowhd">拠点</div>' +
      '<div class="knownote">住所を入れれば、出発に使う駅はこちらで調べます。' +
      'バス停でも構いません（高速バスで出るなら乗り場を入れる）。<br>' +
      '出張先へ移ったら、下の一覧から今いる所を選び直してください。</div>' +
      '<div id="qz-blist" class="bl">読み込み中…</div>' +
      '<label class="ol">呼び名<input id="qz-b1" placeholder="呼び名（土地の名前でいい）"></label>' +
      '<label class="ol">住所<input id="qz-b2" placeholder="例: 東京都新宿区…"></label>' +
      '<label class="ol">出発に使う駅・バス停（空でよい）<input id="qz-b3" placeholder="調べます"></label>' +
      '<div class="btns"><button class="pri" id="qz-badd">足す</button></div>' +
      '<div id="qz-bres"></div></div>';
  }

  function wireBaseZone() {
    var z = el('qz-base'); if (!z) return;
    loadBases();
    el('qz-badd').onclick = function () {
      var b = el('qz-badd'); b.disabled = true; b.textContent = '調べています';
      post('/api/bases', { action: 'add', label: el('qz-b1').value,
                           address: el('qz-b2').value, station: el('qz-b3').value })
        .then(function (r) {
          b.disabled = false; b.textContent = '足す';
          if (r.error) { el('qz-bres').innerHTML = '<div class="err">' + esc(r.error) + '</div>'; return; }
          el('qz-b1').value = el('qz-b2').value = el('qz-b3').value = '';
          el('qz-bres').innerHTML = r.note ? '<div class="knownote">' + esc(r.note) + '</div>' : '';
          renderBases(r.bases);
          setTimeout(function () { st.view = null; load(); }, 700);
        });
    };
  }

  function loadBases() {
    fetch('/api/bases').then(function (r) { return r.json(); })
      .then(function (r) { renderBases(r.bases || []); }).catch(function () {});
  }

  function renderBases(rows) {
    var box = el('qz-blist'); if (!box) return;
    if (!rows.length) { box.innerHTML = '<div class="knownote">まだ1つもありません。</div>'; return; }
    var h = '';
    rows.forEach(function (b) {
      h += '<div class="brow' + (b.current ? ' cur' : '') + '" data-k="' + esc(b.key) + '">' +
        '<b>' + esc(b.label) + '</b> ' + esc(b.station || '（駅なし）') +
        '<span class="src">' + esc(b.address) + '</span>' +
        (b.current ? '<em>いまここ</em>' : '<button data-k="' + esc(b.key) + '">ここにいる</button>') +
        '</div>';
    });
    box.innerHTML = h;
    box.querySelectorAll('button').forEach(function (btn) {
      btn.onclick = function () {
        post('/api/bases', { action: 'use', key: btn.dataset.k }).then(function (r) {
          if (r.bases) renderBases(r.bases);
          setTimeout(function () { st.view = null; load(); }, 500);
        });
      };
    });
  }

  // ---- 控えの置き場 ----
  function outZoneHtml() {
    return '<div class="know" id="qz-out">' +
      '<div class="knowhd">置き場</div>' +
      '<div class="knownote">要るものだけ入れてください。空の欄は使いません。</div>' +
      '<label class="ol">書類（PDF・HTML）<input id="qz-o1" placeholder="~/Documents/書類メーカー"></label>' +
      '<label class="ol">Obsidian の保管庫<input id="qz-o2" placeholder="空でよい"></label>' +
      '<label class="ol">台帳の CSV<input id="qz-o3" placeholder="~/Documents/書類メーカー/台帳.csv"></label>' +
      '<div class="btns"><button class="pri" id="qz-osave">保存する</button></div>' +
      '<div id="qz-ores"></div></div>';
  }

  function wireOutZone() {
    var b = el('qz-osave'); if (!b) return;
    fetch('/api/output').then(function (r) { return r.json(); }).then(function (o) {
      if (el('qz-o1')) el('qz-o1').value = o.dir || '';
      if (el('qz-o2')) el('qz-o2').value = o.obsidianDir || '';
      if (el('qz-o3')) el('qz-o3').value = o.sheetCsv || '';
    });
    b.onclick = function () {
      b.disabled = true; b.textContent = '保存しています';
      post('/api/output', { dir: el('qz-o1').value, obsidianDir: el('qz-o2').value,
                            sheetCsv: el('qz-o3').value }).then(function (r) {
        b.disabled = false; b.textContent = '保存する';
        el('qz-ores').innerHTML = r.error
          ? '<div class="err">' + esc(r.error) + '</div>'
          : '<div class="knownote">入れました。次に出す書類からここに置きます。</div>';
        if (!r.error) setTimeout(function () { st.view = null; load(); }, 700);
      });
    };
  }

  // ---- 新しい版が出ていたら知らせる（iPhone の更新と同じ形） ----
  function checkUpdate() {
    fetch('/api/update').then(function (r) { return r.json(); }).then(function (u) {
      if (!u.newer) return;
      var w = el('qz'); if (!w) return;
      var bar = document.createElement('div');
      bar.className = 'upd';
      bar.innerHTML = '新しい版があります（' + esc(u.current) + ' → ' + esc(u.version) + '）' +
        '<button id="qz-upd">入れる</button>';
      w.querySelector('.card').insertBefore(bar, w.querySelector('.bd'));
      el('qz-upd').onclick = function () {
        var b = el('qz-upd'); b.disabled = true; b.textContent = '入れています…';
        post('/api/update', {}).then(function (r) {
          bar.innerHTML = r.error
            ? esc(r.error.split('\n')[0]) + '<br><small>くわしくは paper-maker update</small>'
            : esc(r.message) + '<br><small>画面を開き直してください</small>';
        });
      };
    }).catch(function () {});
  }

  // ---- まとめて埋める（過去の請求書1枚から名乗り・振込先・拠点まで） ----
  var autoPicked = [];

  function autoZoneHtml() {
    return '<div class="know" id="qz-auto">' +
      '<div class="knowhd">ひとつずつ埋めるのが面倒なら</div>' +
      '<div class="knownote">去年の請求書を1枚渡してください。名乗り・振込先・住所・登録番号を、そこから写します。' +
      'カレンダーと AI は、このパソコンを見て勝手に決めます。<br>' +
      '書く前に一覧で見せます。押すまでは何も保存しません。</div>' +
      '<div class="drop" id="qz-adrop" style="display:none"></div>' +
      '<div class="btns"><button id="qz-ago">渡さずに見てみる</button></div>' +
      '<div id="qz-ares"></div></div>';
  }

  function wireAutoZone() {
    var z = el('qz-adrop'); if (!z) return;
    var inp = document.createElement('input');
    inp.type = 'file'; inp.multiple = true; inp.style.display = 'none';
    inp.setAttribute('data-fd-title', '請求書か見積を放り込む');
    z.parentNode.insertBefore(inp, z);
    z.onclick = function () { inp.click(); };
    inp.onchange = function () { readAuto(inp.files); };
    z.ondragover = function (e) { e.preventDefault(); z.classList.add('over'); };
    z.ondragleave = function () { z.classList.remove('over'); };
    z.ondrop = function (e) {
      e.preventDefault(); z.classList.remove('over');
      readAuto(e.dataTransfer.files);
    };
    var go = el('qz-ago'); if (go) go.onclick = function () { autoPicked = []; sendAuto(false); };
  }

  function readAuto(list) {
    var arr = Array.prototype.slice.call(list).slice(0, 5);
    if (!arr.length) return;
    autoPicked = []; var left = arr.length;
    arr.forEach(function (f) {
      var r = new FileReader();
      r.onload = function () {
        autoPicked.push({ name: f.name, data: r.result });
        if (--left === 0) sendAuto(false);
      };
      r.onerror = function () { if (--left === 0) sendAuto(false); };
      r.readAsDataURL(f);
    });
  }

  function sendAuto(apply) {
    var box = el('qz-ares');
    if (box) box.innerHTML = '<div class="busy">' +
      (apply ? '入れています…' : '見ています… 書類を渡した時は40秒ほどかかります') + '</div>';
    post('/api/auto', { files: autoPicked, apply: apply }).then(function (r) {
      renderAuto(r, apply);
    }).catch(function () {
      if (box) box.innerHTML = '<div class="err">うまくいきませんでした</div>';
    });
  }

  function renderAuto(r, applied) {
    var box = el('qz-ares'); if (!box) return;
    if (r.error) { box.innerHTML = '<div class="err">' + esc(r.error) + '</div>'; return; }
    var steps = r.steps || [];
    if (!steps.length) {
      box.innerHTML = '<div class="knownote">埋める所はありませんでした。</div>';
      return;
    }
    var h = '<div class="knowhd">' + (applied ? '入れました（' + r.written + ' 箇所）' : 'これを入れます') + '</div><ul class="kl">';
    steps.forEach(function (s) {
      var val = s.new.length > 48 ? s.new.slice(0, 45) + '…' : s.new;
      h += '<li><b>' + esc(s.what) + '</b> ' + esc(val.replace(/\n/g, ' / ')) +
             '<span class="src">' + esc(s.source) + '</span>';
      if (s.overwrite) h += '<span class="src">今は: ' + esc(s.now.replace(/\n/g, ' / ').slice(0, 40)) + '</span>';
      h += '</li>';
    });
    h += '</ul>';
    (r.notes || []).forEach(function (n) { h += '<div class="knownote">' + esc(n) + '</div>'; });
    if (!applied) h += '<div class="btns"><button class="pri" id="qz-aap">これで入れる</button></div>';
    box.innerHTML = h;
    if (!applied) {
      el('qz-aap').onclick = function () {
        var b = el('qz-aap'); b.disabled = true; b.textContent = '入れています';
        sendAuto(true);
      };
    } else {
      setTimeout(function () { st.view = null; load(); }, 900);
    }
  }

  function dropZoneHtml() {
    return '<input type="file" id="qz-file" multiple accept="image/*,.txt,.csv" style="display:none"' +
      ' data-fd-title="Suica の履歴のスクショを、ここに放り込む" data-fd-note="何枚でも。テキストや CSV でも読めます">' +
      '<div class="drop" id="qz-drop" style="display:none"></div>' +
      '<ul class="files" id="qz-files"></ul>' +
      '<div id="qz-result"></div>';
  }

  function fmtYen(n) { return Number(n).toLocaleString('ja-JP') + '円'; }

  function showFiles() {
    var ul = el('qz-files'); if (!ul) return;
    ul.innerHTML = picked.map(function (f) { return '<li>' + esc(f.name) + '</li>'; }).join('');
  }

  function readFiles(list) {
    var arr = Array.prototype.slice.call(list || []).slice(0, 30);
    if (!arr.length) return;
    var left = arr.length;
    arr.forEach(function (f) {
      var r = new FileReader();
      r.onload = function () {
        picked.push({ name: f.name, data: String(r.result) });
        if (--left === 0) { showFiles(); sendFiles(false); }
      };
      r.onerror = function () { if (--left === 0) { showFiles(); sendFiles(false); } };
      r.readAsDataURL(f);
    });
  }

  function renderSummary(sm, applied) {
    var box = el('qz-result'); if (!box) return;
    var h = '';
    function group(cls, title, items, tail) {
      if (!items || !items.length) return '';
      var s2 = '<h5 class="' + cls + '">' + title + '（' + items.length + '件）' + (tail || '') + '</h5>';
      items.slice(0, 12).forEach(function (x) {
        var amt = x.amount != null ? fmtYen(x.amount) : x.amounts.map(fmtYen).join(' / ');
        var arrow = x.kind === 'bus' ? '' : ' → ' + esc(x.to);
        s2 += '<div>' + esc(x.from) + arrow + '　' + amt + '　' + x.times + '回</div>';
      });
      if (items.length > 12) s2 += '<div>…ほか ' + (items.length - 12) + '件</div>';
      return '<div class="rows">' + s2 + '</div>';
    }
    h += group('sure', '確定にする', sm.sure);
    h += group('wait', '確認待ち', sm.wait, '… 2回以上出てこないと書類には使いません');
    h += group('clash', '額が食い違う', sm.clash, '… 取り込みません');
    h += group('clash', '怪しい', sm.odd, '… 同じ駅どうし');
    if (applied) {
      h += '<div class="rows sure">運賃表に入れました</div>';
    } else if (sm.sure && sm.sure.length) {
      h += '<div class="btns"><button class="pri" id="qz-apply">この ' + sm.sure.length + ' 区間を入れる</button></div>';
    }
    box.innerHTML = h;
    var ap = el('qz-apply');
    if (ap) ap.onclick = function () { ap.disabled = true; ap.textContent = '入れています'; sendFiles(true); };
  }

  function sendFiles(apply) {
    var box = el('qz-result');
    if (box) box.innerHTML = '<div class="busy">' + (apply ? '入れています…' : '読んでいます… 画像1枚に10秒ほどかかります') + '</div>';
    post('/api/fare/import', { files: picked, apply: !!apply }).then(function (r) {
      if (r.error) {
        if (box) box.innerHTML = '<div class="note">' + esc(r.error) + '<br>' + (r.notes || []).map(esc).join('<br>') + '</div>';
        return;
      }
      renderSummary(r.summary, !!apply);
      if (apply) { picked = []; showFiles(); load(); }
    }).catch(function () {
      if (box) box.innerHTML = '<div class="note">読み込みに失敗しました</div>';
    });
  }

  function wireDropZone() {
    var dz = el('qz-drop'), fi = el('qz-file');
    if (!dz || !fi) return;
    picked = [];
    dz.onclick = function () { fi.click(); };
    fi.onchange = function () { readFiles(fi.files); fi.value = ''; };
    ['dragenter', 'dragover'].forEach(function (n) {
      dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.add('on'); });
    });
    ['dragleave', 'drop'].forEach(function (n) {
      dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.remove('on'); });
    });
    dz.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files) readFiles(e.dataTransfer.files);
    });
  }

  var knowPicked = [];

  function knowZoneHtml() {
    return '<input type="file" id="qz-kfile" multiple style="display:none"' +
      ' data-fd-title="契約書や、前に出した見積をここに放り込む" data-fd-note="PDF・画像・テキスト。何件でも">' +
      '<div class="drop" id="qz-kdrop" style="display:none"></div>' +
      '<ul class="files" id="qz-kfiles"></ul>' +
      '<div id="qz-kresult"></div>';
  }

  function renderKnow(sm, applied) {
    var box = el('qz-kresult'); if (!box) return;
    var h = '<div class="rows">';
    (sm.docs || []).forEach(function (d) {
      h += '<h5 class="sure">' + esc(d.title || d.source) + '（' + esc(d.kind) + '）' +
           (d.date ? ' ' + esc(d.date) : '') + '</h5>';
      if (d.client && d.client.name) h += '<div>相手先: ' + esc(d.client.name) + ' ' + esc(d.client.address || '') + '</div>';
      (d.items || []).slice(0, 5).forEach(function (it) {
        h += '<div>品目: ' + esc(it.name) + '　' + Number(it.price || 0).toLocaleString('ja-JP') + '円</div>';
      });
      if ((d.clauses || []).length) h += '<div>条項: ' + d.clauses.length + ' 本（' + esc(d.clauses[0].heading || '') + ' ほか）</div>';
    });
    h += '<div style="margin-top:5px">取引先 ' + (sm.clients || []).length +
         '／品目 ' + (sm.items || []).length + '／条項 ' + (sm.clauses || []).length + '</div></div>';
    if (applied) h += '<div class="rows sure">控えに入れました</div>';
    else h += '<div class="btns"><button class="pri" id="qz-kapply">控えに入れる</button></div>';
    box.innerHTML = h;
    var ap = el('qz-kapply');
    if (ap) ap.onclick = function () { ap.disabled = true; ap.textContent = '入れています'; sendKnow(true); };
  }

  function sendKnow(apply) {
    var box = el('qz-kresult');
    if (box) box.innerHTML = '<div class="busy">' + (apply ? '入れています…' : '読んでいます… 1件20秒ほどかかります') + '</div>';
    post('/api/knowledge', { files: knowPicked, apply: !!apply }).then(function (r) {
      if (r.error) {
        if (box) box.innerHTML = '<div class="note">' + esc(r.error) + '<br>' + (r.notes || []).map(esc).join('<br>') + '</div>';
        return;
      }
      renderKnow(r.summary, !!apply);
      if (apply) { knowPicked = []; el('qz-kfiles').innerHTML = ''; setTimeout(load, 600); }
    }).catch(function () {
      if (box) box.innerHTML = '<div class="note">読み込みに失敗しました</div>';
    });
  }

  function wireKnowZone() {
    var dz = el('qz-kdrop'), fi = el('qz-kfile');
    if (!dz || !fi) return;
    knowPicked = [];
    var read = function (list) {
      var arr = Array.prototype.slice.call(list || []).slice(0, 20);
      if (!arr.length) return;
      var left = arr.length;
      arr.forEach(function (f) {
        var r = new FileReader();
        r.onload = function () {
          knowPicked.push({ name: f.name, data: String(r.result) });
          if (--left === 0) {
            el('qz-kfiles').innerHTML = knowPicked.map(function (x) { return '<li>' + esc(x.name) + '</li>'; }).join('');
            sendKnow(false);
          }
        };
        r.onerror = function () { if (--left === 0) sendKnow(false); };
        r.readAsDataURL(f);
      });
    };
    dz.onclick = function () { fi.click(); };
    fi.onchange = function () { read(fi.files); fi.value = ''; };
    ['dragenter', 'dragover'].forEach(function (n) {
      dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.add('on'); });
    });
    ['dragleave', 'drop'].forEach(function (n) {
      dz.addEventListener(n, function (e) { e.preventDefault(); dz.classList.remove('on'); });
    });
    dz.addEventListener('drop', function (e) { if (e.dataTransfer && e.dataTransfer.files) read(e.dataTransfer.files); });
  }

  function loadAiBox() {
    var box = el('qz-ai'); if (!box) return;
    fetch('/api/ai').then(function (r) { return r.json(); }).then(function (d) {
      var opts = d.presets.map(function (p) {
        return '<option value="' + p.id + '"' + (p.id === d.provider ? ' selected' : '') + '>' + esc(p.label) + '</option>';
      }).join('');
      box.innerHTML =
        '<label>どこに繋ぐか</label><select id="qz-ai-prov">' + opts + '</select>' +
        '<div id="qz-ai-modelwrap"><label>モデル</label><input id="qz-ai-model" value="' + esc(d.model) + '"></div>' +
        '<div id="qz-ai-epwrap" style="display:none"><label>繋ぎ先のURL（OpenAI 互換）</label>' +
        '<input id="qz-ai-ep" value="' + esc(d.endpoint) + '" placeholder="https://…/v1/chat/completions"></div>' +
        '<div id="qz-ai-cmdwrap" style="display:none"><label>走らせるコマンド</label>' +
        '<input id="qz-ai-cmd" value="' + esc(d.command || '') + '" placeholder="例: ollama run llama3"></div>' +
        '<div id="qz-ai-keywrap"><label>鍵（<span id="qz-ai-keyname">' + esc(d.keyName) + '</span>）</label>' +
        '<input id="qz-ai-key" type="password" placeholder="' + (d.hasKey ? '入っています。変えるときだけ打つ' : 'ここに貼る') + '"></div>' +
        '<div class="where" id="qz-ai-where"></div>' +
        '<div class="btns"><button class="pri" id="qz-ai-try">試す</button></div>' +
        '<div class="aires" id="qz-ai-res"></div>';
      var prov = el('qz-ai-prov'), model = el('qz-ai-model'), where = el('qz-ai-where');
      var byId = {};
      d.presets.forEach(function (p) { byId[p.id] = p; });
      function refresh(changed) {
        var p = byId[prov.value] || {};
        var isCli = p.style === 'cli';
        where.textContent = p.where || '';
        el('qz-ai-epwrap').style.display = p.needEndpoint ? '' : 'none';
        el('qz-ai-cmdwrap').style.display = isCli ? '' : 'none';
        el('qz-ai-keywrap').style.display = isCli ? 'none' : '';
        el('qz-ai-modelwrap').style.display = isCli ? 'none' : '';
        if (changed) {
          model.value = p.model || '';
          el('qz-ai-cmd').value = p.command || '';
          el('qz-ai-keyname').textContent = p.keyName || '';
          el('qz-ai-key').placeholder = p.id === d.provider && d.hasKey ? '入っています。変えるときだけ打つ' : 'ここに貼る';
        }
      }
      prov.onchange = function () { refresh(true); };
      refresh(false);
      el('qz-ai-try').onclick = function () {
        var b = el('qz-ai-try'), res = el('qz-ai-res');
        b.disabled = true; b.textContent = '試しています（CLIは1分ほどかかります）';
        res.className = 'aires'; res.textContent = '';
        post('/api/ai', {
          provider: prov.value, model: model.value.trim(),
          endpoint: (el('qz-ai-ep') || {}).value || '',
          command: (el('qz-ai-cmd') || {}).value || '',
          key: el('qz-ai-key').value.trim(), check: true
        }).then(function (r) {
          b.disabled = false; b.textContent = '試す';
          res.className = 'aires ' + (r.ok ? 'ok' : 'ng');
          res.textContent = r.error || r.message || '';
          if (r.ok) { el('qz-ai-key').value = ''; setTimeout(load, 400); }
        }).catch(function () {
          b.disabled = false; b.textContent = '試す';
          res.className = 'aires ng'; res.textContent = '繋がりませんでした';
        });
      };
    }).catch(function () { box.textContent = 'AI の設定を読めませんでした'; });
  }

  function load() {
    fetch('/api/quest').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d) return;
      st.data = d;
      if (d.finished && localStorage.getItem('pm_quest_done') === '1') { var w = el('qz'); if (w) w.remove(); return; }
      if (!el('qz')) { mount(); checkUpdate(); }
      render();
    }).catch(function () {});
  }

  if (localStorage.getItem('pm_quest_done') === '1') {
    // 一度閉じていても、未達が残っていれば静かに出し直す
    fetch('/api/quest').then(function (r) { return r.json(); }).then(function (d) {
      if (d && !d.finished) { localStorage.removeItem('pm_quest_done'); load(); }
    }).catch(function () {});
  } else {
    load();
  }
  // 設定を保存した直後に見直す（保存したのに進まない、を作らない）
  window.addEventListener('pm-profile-saved', function () { setTimeout(load, 150); });
  window.addEventListener('focus', function () { if (el('qz')) load(); });
})();
