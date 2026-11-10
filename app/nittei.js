/* 日程調整（TONARY）。上の帯に「📅 日程調整」を足し、リンク・受付の設定・入った予約を1枚で見せる。
   予約した人の名前やメモは外から入ってくる文字なので、innerHTML には入れず textContent で置く。 */
(function () {
  if (!/^https?:/.test(location.protocol)) return;

  var W = ['日', '月', '火', '水', '木', '金', '土'];
  var CSS = [
    '#nt-modal .modal{max-width:720px}',
    '#nt-modal h3{font-size:13px;margin:16px 0 6px;color:#333}',
    '#nt-modal .nt-link{display:flex;gap:8px;align-items:center;border:1px solid #e3e3e6;border-radius:8px;padding:8px 10px;margin:5px 0}',
    '#nt-modal .nt-link b{font-weight:600;font-size:13px}',
    '#nt-modal .nt-link code{font-size:11px;color:#555;word-break:break-all;flex:1}',
    '#nt-modal .nt-link button{font-size:12px;padding:4px 10px;border:1px solid #c9c9cf;background:#fff;border-radius:6px;cursor:pointer;white-space:nowrap}',
    '#nt-modal .nt-days{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0}',
    '#nt-modal .nt-days label{display:flex;gap:4px;align-items:center;font-size:13px;cursor:pointer}',
    '#nt-modal .nt-grid{display:grid;grid-template-columns:150px 1fr;gap:6px 10px;align-items:center;font-size:13px}',
    '#nt-modal .nt-grid input,#nt-modal .nt-grid select{padding:5px 7px;border:1px solid #d5d5d8;border-radius:6px;font:inherit;width:120px}',
    '#nt-modal .nt-note{font-size:12px;color:#555;background:#f6f7f9;border-radius:6px;padding:7px 10px;margin:6px 0}',
    '#nt-modal .nt-bk{border:1px solid #e3e3e6;border-radius:8px;padding:8px 10px;margin:5px 0;font-size:13px}',
    '#nt-modal .nt-bk.cx{opacity:.55}',
    '#nt-modal .nt-bk .t{font-weight:600;font-variant-numeric:tabular-nums}',
    '#nt-modal .nt-bk .m{color:#555;font-size:12px;white-space:pre-wrap;margin-top:2px}',
    '#nt-modal .nt-msg{font-size:12px;margin-top:6px;min-height:1em}',
    '#nt-modal .nt-msg.err{color:#c33}'
  ].join('');

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === 'text') e.textContent = attrs[k];
      else if (k === 'cls') e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }
  function fmt(ms) {
    var d = new Date(ms + 9 * 3600e3);
    return (d.getUTCMonth() + 1) + '/' + d.getUTCDate() + '（' + W[d.getUTCDay()] + '）' +
      d.getUTCHours() + ':' + String(d.getUTCMinutes()).padStart(2, '0');
  }
  function hm(ms) {
    var d = new Date(ms + 9 * 3600e3);
    return d.getUTCHours() + ':' + String(d.getUTCMinutes()).padStart(2, '0');
  }

  var st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);

  var back = el('div', { cls: 'modal-back', id: 'nt-modal' });
  var box = el('div', { cls: 'modal' });
  box.appendChild(el('button', { cls: 'close-x', 'data-close': '', text: '✕' }));
  box.appendChild(el('h2', { text: '日程調整' }));
  var body = el('div', { text: '読み込み中…' });
  box.appendChild(body);
  back.appendChild(box);
  document.body.appendChild(back);
  back.addEventListener('click', function (e) {
    if (e.target === back || e.target.hasAttribute('data-close')) back.classList.remove('show');
  });

  var tabs = document.getElementById('tabs');
  if (tabs) {
    var btn = el('button', { cls: 'tab-extra', id: 'tab-nittei', title: '予約リンク・受付の設定・入った予約', text: '📅 日程調整' });
    btn.addEventListener('click', function () { back.classList.add('show'); load(); });
    tabs.appendChild(btn);
  }

  function load() {
    fetch('/api/nittei').then(function (r) { return r.json(); }).then(render)
      .catch(function () { body.textContent = '読み込めませんでした'; });
  }

  function render(d) {
    body.textContent = '';
    if (d.error) { body.textContent = d.error; return; }
    if (!d.configured && d.error) { body.textContent = d.error; return; }
    if (!d.configured) {
      body.appendChild(el('p', { text: 'まだ日程調整の設定がありません。' + d.home + '/nittei.json を置くと、ここに出ます。見本は examples/nittei.example.json です。' }));
      return;
    }

    body.appendChild(el('div', { cls: 'nt-note', text:
      '相手にリンクを送ると、空いている枠から選んでもらえます。決まった予定は、カレンダー「' + d.calendar +
      '」に Zoom のリンク付きで入ります。カレンダーにある予定は、終日の出張も含めて全部「埋まり」として扱います。' }));

    // リンク
    body.appendChild(el('h3', { text: '相手に送るリンク' }));
    var enabled = {};
    d.links.forEach(function (l) {
      var on = el('input', { type: 'checkbox' }); on.checked = l.enabled !== false;
      enabled[l.token] = on;
      var copy = el('button', { type: 'button', text: 'コピー' });
      copy.addEventListener('click', function () {
        navigator.clipboard.writeText(l.url).then(function () { copy.textContent = 'コピーしました'; });
      });
      body.appendChild(el('div', { cls: 'nt-link' }, [
        el('label', { title: '外すと、このリンクでは予約できなくなります' }, [on]),
        el('b', { text: l.title }), el('code', { text: l.url }), copy]));
    });

    // 受付の設定
    var s = d.settings;
    body.appendChild(el('h3', { text: '受け付ける日と時間' }));
    var dayBoxes = {};
    var days = el('div', { cls: 'nt-days' });
    [1, 2, 3, 4, 5, 6, 0].forEach(function (w) {
      var c = el('input', { type: 'checkbox' }); c.checked = s.days.indexOf(w) >= 0; dayBoxes[w] = c;
      days.appendChild(el('label', null, [c, el('span', { text: W[w] })]));
    });
    var hol = el('input', { type: 'checkbox' }); hol.checked = s.holidays !== false;
    days.appendChild(el('label', null, [hol, el('span', { text: '祝日も枠を出す' })]));
    body.appendChild(days);

    function timeSel(v) {
      var x = el('select');
      for (var i = 0; i < 48; i++) {
        var t = Math.floor(i / 2) + ':' + (i % 2 ? '30' : '00');
        var o = el('option', { value: t, text: t }); if (t === v) o.selected = true; x.appendChild(o);
      }
      return x;
    }
    function num(v, min, max, step) { return el('input', { type: 'number', value: v, min: min, max: max, step: step || 1 }); }
    var fs = timeSel(s.start), fe = timeSel(s.end);
    var fb = num(s.buffer, 0, 120, 5), fn = num(s.noticeHours, 0, 168), fh = num(s.horizonDays, 1, 90);
    body.appendChild(el('div', { cls: 'nt-grid' }, [
      el('span', { text: '開始' }), fs, el('span', { text: '終了' }), fe,
      el('span', { text: '前後の余白（分）' }), fb,
      el('span', { text: '何時間前まで受け付けるか' }), fn,
      el('span', { text: '何日先まで出すか' }), fh]));
    var msg = el('div', { cls: 'nt-msg' });
    var save = el('button', { cls: 'save-btn', type: 'button', text: '保存する' });
    save.addEventListener('click', function () {
      var en = {}; for (var t in enabled) en[t] = enabled[t].checked;
      var payload = {
        days: Object.keys(dayBoxes).filter(function (w) { return dayBoxes[w].checked; }).map(Number),
        holidays: hol.checked, start: fs.value, end: fe.value,
        buffer: +fb.value, noticeHours: +fn.value, horizonDays: +fh.value, enabled: en
      };
      save.disabled = true; msg.className = 'nt-msg'; msg.textContent = '保存しています…';
      fetch('/api/nittei', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(function (r) { return r.json(); }).then(function (j) {
          save.disabled = false;
          if (j.error) { msg.className = 'nt-msg err'; msg.textContent = j.error; return; }
          msg.textContent = '保存しました。2分ほどで予約ページに反映されます。';
        }).catch(function () { save.disabled = false; msg.className = 'nt-msg err'; msg.textContent = '保存できませんでした'; });
    });
    body.appendChild(save); body.appendChild(msg);

    // 入った予約
    body.appendChild(el('h3', { text: '入った予約' }));
    if (d.bookingsError) body.appendChild(el('div', { cls: 'nt-msg err', text: d.bookingsError }));
    var now = Date.now();
    var list = (d.bookings || []).filter(function (b) { return b.end > now - 7 * 86400e3; });
    if (!list.length) body.appendChild(el('div', { cls: 'nt-note', text: 'これからの予約はまだありません。' }));
    list.forEach(function (b) {
      var head = fmt(b.start) + '〜' + hm(b.end) + '　' + b.name + ' 様　' + b.title + (b.status === 'cancelled' ? '（取り消し）' : '');
      var sub = [b.email, b.memo].filter(Boolean).join('\n');
      body.appendChild(el('div', { cls: 'nt-bk' + (b.status === 'cancelled' ? ' cx' : '') }, [
        el('div', { cls: 't', text: head }), sub ? el('div', { cls: 'm', text: sub }) : null]));
    });

    if (d.demo) body.appendChild(el('div', { cls: 'nt-note', text: 'いまは見本のデータです。リンクを開いても予約はできません。' }));
    var su = d.status || {};
    body.appendChild(el('div', { cls: 'nt-note', text:
      '空き時間の送信：' + (su.updated ? new Date(su.updated).toLocaleString('ja-JP') : 'まだ') +
      '（パソコン側の常駐アプリが送っています。パソコンを閉じている間は止まります）' }));
  }
})();
