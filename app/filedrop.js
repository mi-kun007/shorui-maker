/* ファイルの取り込み口。<input type="file"> に被せるだけで動く。選んだファイルは元の入力に渡して change を出すので、画面の処理は変えなくてよい。
   付けない入力は data-nodrop。文言は data-fd-title / data-fd-note。小さい形は data-fd-small。 */
(function () {
  var ICON = '<svg class="fd-icon" viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 8.5a4.75 4.75 0 0 1-.5 9.5"/><path d="M12 20v-8"/><path d="m8.5 15 3.5-3.5 3.5 3.5"/></svg>';
  function note(a) {
    if (!a) return '';
    var out = [];
    a.split(',').forEach(function (x) {
      x = x.trim();
      var n = x === 'image/*' ? '画像' : x === 'application/pdf' ? 'PDF' : x === 'video/*' ? '動画' : x === 'audio/*' ? '音声' : x === 'text/csv' ? 'CSV' : x === 'application/json' ? 'JSON' : x.charAt(0) === '.' ? x.slice(1).toUpperCase() : '';
      if (n && out.indexOf(n) < 0) out.push(n);
    });
    return out.join('・');
  }
  function fits(file, accept) {
    if (!accept) return true;
    return accept.split(',').some(function (x) {
      x = x.trim().toLowerCase();
      if (!x) return false;
      if (x.charAt(0) === '.') return file.name.toLowerCase().slice(-x.length) === x;
      if (x.slice(-2) === '/*') return (file.type || '').toLowerCase().indexOf(x.slice(0, -1)) === 0;
      return (file.type || '').toLowerCase() === x;
    });
  }
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function enhance(input) {
    if (!input || input.fdDone || input.hasAttribute('data-nodrop') || input.type !== 'file') return;
    input.fdDone = true;
    var z = document.createElement('div');
    z.className = 'fd' + (input.hasAttribute('data-fd-small') ? ' fd-small' : '');
    z.tabIndex = 0;
    z.setAttribute('role', 'button');
    z.setAttribute('aria-label', 'ファイルを選択');
    var n = input.getAttribute('data-fd-note') || note(input.accept);
    z.innerHTML = ICON + '<span class="fd-big">' + esc(input.getAttribute('data-fd-title') || 'ここにファイルをドラッグ＆ドロップ') + '</span><span class="fd-or">または</span><span class="fd-pick">ファイルを選択</span>' + (n ? '<span class="fd-note">' + esc(n) + '</span>' : '') + '<span class="fd-name"></span>';
    var label = input.closest('label');
    var anchor = label && !label.hasAttribute('data-fd-keep') ? label : input;
    anchor.parentNode.insertBefore(z, anchor);
    if (label && anchor === label) {            // label の中に入力があると 2 回開くので、入力を外へ出して label は隠す
      label.parentNode.insertBefore(input, label);
      label.style.display = 'none';
    }
    input.style.position = 'absolute'; input.style.width = '1px'; input.style.height = '1px'; input.style.opacity = '0'; input.style.pointerEvents = 'none';
    input.tabIndex = -1;
    var name = z.querySelector('.fd-name');
    var show = function () { name.textContent = Array.prototype.map.call(input.files || [], function (f) { return f.name; }).join('、'); };
    input.addEventListener('change', show);
    z.addEventListener('click', function () { if (!input.disabled) input.click(); });
    z.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    z.addEventListener('dragover', function (e) { e.preventDefault(); z.classList.add('fd-over'); });
    z.addEventListener('dragleave', function () { z.classList.remove('fd-over'); });
    z.addEventListener('drop', function (e) {
      e.preventDefault(); z.classList.remove('fd-over');
      var all = Array.prototype.slice.call(e.dataTransfer.files || []).filter(function (f) { return fits(f, input.accept); });
      if (!all.length) { name.textContent = 'この形式のファイルは入れられません'; return; }
      if (!input.multiple) all = all.slice(0, 1);
      var dt = new DataTransfer();
      all.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }
  function scan(root) { (root.querySelectorAll ? root.querySelectorAll('input[type=file]') : []).forEach(enhance); }
  function start() {
    scan(document);
    new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) { if (n.matches && n.matches('input[type=file]')) enhance(n); else scan(n); } }); }); }).observe(document.documentElement, { childList: true, subtree: true });
  }
  window.FileDrop = { enhance: enhance, scan: function () { scan(document); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
