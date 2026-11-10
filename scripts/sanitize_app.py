#!/usr/bin/env python3
"""社内版 index.html から配布版 app/index.html を作る。

社内版を直したら、これを流し直せば配布版に反映される。
やること：個人情報の直書きを消す／プロファイル・日当表・拠点をデータから読む／key.js をやめて bridge から受ける。
最後に配布物に残ってはいけない語を grep して、1つでも残っていれば失敗にする。

    python3 scripts/sanitize_app.py <社内版 index.html> [出力先]
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 配布物に残ってはいけない語。汎用パターンは repo 内、作者固有の語は repo の外（~/.paper-maker-dev/forbidden.txt）に置く。
# 固有語を repo に書くと、それ自体が個人情報の持ち込みになるため。
FORBIDDEN_PATTERNS = [r"AIza[0-9A-Za-z_\-]{20,}", r"0\d{1,3}-\d{2,4}-\d{4}", r"普通\s*\d{7}"]
_ALLOW = ("example.com", "0000-0000", "0000000", "1234567")


def load_forbidden_words():
    import os
    f = pathlib.Path(os.environ.get("PAPER_MAKER_FORBIDDEN", "~/.paper-maker-dev/forbidden.txt")).expanduser()
    if not f.exists():
        return []
    return [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]

# 作者固有の直書き（会社名・氏名・住所の文字列）を置き換える表は repo の外に置く：
#   ~/.paper-maker-dev/replacements.json  … [{"from": "...", "to": "..."}, ...]
# repo に元文字列を書くと、それ自体が個人情報の持ち込みになるため。
def load_replacements():
    import os
    f = pathlib.Path(os.environ.get("PAPER_MAKER_REPLACEMENTS", "~/.paper-maker-dev/replacements.json")).expanduser()
    if not f.exists():
        sys.exit("置換表がありません: %s" % f)
    import json
    return [(r["from"], r["to"]) for r in json.loads(f.read_text(encoding="utf-8"))]

DEFAULT_PROFILES_NEW = """const DEFAULT_PROFILES = {
  corp: {
    name: '', rep: '',
    address: '', tel: '', email: '',
    invoiceNo: '', bank: '', sealText: '', sealType: 'square'
  },
  personal: {
    name: '', rep: '',
    address: '', tel: '', email: '',
    invoiceNo: '', bank: '', sealText: '', sealType: 'round'
  }
};"""

SEAL_JS = """
/* ========== 判子の画像 ========== */
/* 白い紙に押して撮った写真は、周りが白いまま重なって書類を隠す。
   白い所を透かしてから使う。朱色はそのまま残す。 */
function sealFromImage(file, cb){
  const r = new FileReader();
  r.onload = function(){
    const img = new Image();
    img.onload = function(){
      const side = 512;
      const c = document.createElement('canvas');
      c.width = c.height = side;
      const g = c.getContext('2d');
      const sc = Math.min(side / img.width, side / img.height);
      const w = img.width * sc, h = img.height * sc;
      g.drawImage(img, (side - w) / 2, (side - h) / 2, w, h);
      const d = g.getImageData(0, 0, side, side), a = d.data;
      for (let i = 0; i < a.length; i += 4) {
        const R = a[i], G = a[i+1], B = a[i+2];
        const mx = Math.max(R, G, B), mn = Math.min(R, G, B);
        // 明るくて色みが薄い所＝紙。透かす
        if (mx > 150 && mx - mn < 42) { a[i+3] = 0; continue; }
        // 残った所は朱色に寄せる。スキャンの色かぶりを揃える
        const k = Math.min(255, Math.round(255 - mn * 0.55));
        a[i] = Math.max(R, 150); a[i+1] = Math.round(G * 0.45); a[i+2] = Math.round(B * 0.4);
        a[i+3] = Math.min(255, Math.round(k * 0.95));
      }
      g.putImageData(d, 0, 0);
      cb(c.toDataURL('image/png'));
    };
    img.onerror = function(){ alert('画像を読めませんでした'); };
    img.src = String(r.result);
  };
  r.readAsDataURL(file);
}

function wireSealBox(){
  const box = document.getElementById('seal-drop'), fi = document.getElementById('seal-file');
  if (!box || !fi) return;
  const take = function(f){
    if (!f) return;
    if (f.size > 12 * 1024 * 1024) { alert('画像が大きすぎます（12MBまで）'); return; }
    sealFromImage(f, function(dataUrl){
      profiles[profTab].sealImage = dataUrl;
      if (!profiles[profTab].sealSize) profiles[profTab].sealSize = 17;
      saveProfiles(); renderProfileForm(); renderPreview();
    });
  };
  box.onclick = function(){ fi.click(); };
  fi.onchange = function(){ take(fi.files[0]); fi.value = ''; };
  ['dragenter','dragover'].forEach(n => box.addEventListener(n, e => { e.preventDefault(); box.style.background = '#e9f1ff'; }));
  ['dragleave','drop'].forEach(n => box.addEventListener(n, e => { e.preventDefault(); box.style.background = '#f7faff'; }));
  box.addEventListener('drop', e => { if (e.dataTransfer && e.dataTransfer.files) take(e.dataTransfer.files[0]); });
  const sz = document.getElementById('seal-size');
  if (sz) sz.onchange = function(){
    profiles[profTab].sealSize = Math.max(8, Math.min(30, +sz.value || 17));
    saveProfiles(); renderPreview();
  };
  const cl = document.getElementById('seal-clear');
  if (cl) cl.onclick = function(){
    delete profiles[profTab].sealImage;
    saveProfiles(); renderProfileForm(); renderPreview();
  };
}
"""

LOADER = """
/* ========== 配布版：プロファイル・日当・拠点を外から受ける ========== */
/* 名義を直したら profile.json にも送る。GUI と CLI で設定が食い違わないように。 */
let _profSaveTimer = null;
function pushProfiles(){
  if (!/^https?:/.test(location.protocol)) return;
  clearTimeout(_profSaveTimer);
  _profSaveTimer = setTimeout(function(){
    fetch('/api/profile', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ profiles: profiles }) })
      .then(function(){ window.dispatchEvent(new Event('pm-profile-saved')); })
      .catch(function(){});
  }, 600);
}
function applyProfileLabels(){
  const cn = (profiles.corp && profiles.corp.name) || '会社名義';
  const pn = (profiles.personal && profiles.personal.name) ? '個人（' + profiles.personal.name + '）' : '個人名義';
  document.querySelectorAll('#issuer-select option[value="corp"], button[data-prof="corp"]').forEach(el => el.textContent = cn);
  document.querySelectorAll('#issuer-select option[value="personal"], button[data-prof="personal"]').forEach(el => el.textContent = pn);
}
function applyTravelConfig(t){
  if (!t) return;
  if (t.rates) TRAVEL_RATES = t.rates;
  if (t.bases) {
    BASES = {};
    Object.keys(t.bases).forEach(k => { const b = t.bases[k]; BASES[k] = { label: b.label || k, address: b.address || '', hub: b.station || '' }; });
  }
  if (Array.isArray(t.routes)) ROUTES = t.routes;
  if (t.currentBase && !state.travelBase) state.travelBase = t.currentBase;
}
(function loadFromBridge(){
  if (!/^https?:/.test(location.protocol)) return;
  fetch('/api/profile').then(r => r.ok ? r.json() : null).then(cfg => {
    if (!cfg) return;
    if (cfg.profiles) { profiles = Object.assign({}, profiles, cfg.profiles); saveProfiles(); }
    if (cfg.geminiKey) window.GEMINI_API_KEY = cfg.geminiKey;
    applyTravelConfig(cfg.travel);
    applyProfileLabels();
    if (typeof renderForm === 'function') renderForm();
    if (typeof renderPreview === 'function') renderPreview();
    if (typeof renderProfileForm === 'function') renderProfileForm();
  }).catch(() => {});
})();
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = pathlib.Path(sys.argv[1]).expanduser()
    dst = pathlib.Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else ROOT / "app" / "index.html"
    s = src.read_text(encoding="utf-8")

    for a, b in load_replacements():
        if a not in s:
            print("見つからない（社内版が変わった？）:", a[:60])
        s = s.replace(a, b)

    # DEFAULT_PROFILES を空に
    s = re.sub(r"const DEFAULT_PROFILES = \{.*?\n\};", DEFAULT_PROFILES_NEW, s, count=1, flags=re.S)
    # 日当表・拠点・経路をデータ駆動に
    s = re.sub(r"const TRAVEL_RATES = \{[^\n]*\};", "let TRAVEL_RATES = { '代表取締役':{day:5000,night:10000}, '取締役':{day:4000,night:8000}, '従業員':{day:3000,night:6000} };", s, count=1)
    s = re.sub(r"const BASES = \{.*?\n\};", "let BASES = {};", s, count=1, flags=re.S)
    s = re.sub(r"const ROUTES = \[.*?\n\];", "let ROUTES = [];", s, count=1, flags=re.S)
    # #doc= 読み込みで travel 設定も受ける
    s = s.replace("    if (payload.profiles) profiles = Object.assign({}, profiles, payload.profiles);\n",
                  "    if (payload.profiles) profiles = Object.assign({}, profiles, payload.profiles);\n    if (payload.travel) applyTravelConfig(payload.travel);\n")

    # 印影の画像を使えるようにする（配布版だけ）
    s = s.replace(
        """  .sheet .seal.round {
    width: 14mm; height: 14mm; border: 2.5px solid var(--seal-red); border-radius: 50%; font-size: 14px;
  }""",
        """  .sheet .seal.round {
    width: 14mm; height: 14mm; border: 2.5px solid var(--seal-red); border-radius: 50%; font-size: 14px;
  }
  /* 実物の判子を撮って登録した場合。枠も文字も出さず、画像だけ置く */
  .sheet .seal.image { border: none; background: none; padding: 0; }
  .sheet .seal.image img { width: 100%; height: 100%; object-fit: contain; mix-blend-mode: multiply; }""")

    s = s.replace(
        """  const seal = state.showSeal
    ? `<div class="seal ${p.sealType}">${esc(p.sealText)}</div>` : '';""",
        """  const seal = !state.showSeal ? ''
    : (p.sealImage
        ? `<div class="seal image" style="width:${p.sealSize||17}mm;height:${p.sealSize||17}mm"><img src="${p.sealImage}" alt=""></div>`
        : `<div class="seal ${p.sealType}">${esc(p.sealText)}</div>`);""")

    # 設定画面に、判子の画像を登録する欄を足す
    s = s.replace(
        """    `<div class="frow"><label>印影の形</label><select data-pf="sealType">
      <option value="square"${p.sealType==='square'?' selected':''}>角印（会社）</option>
      <option value="round"${p.sealType==='round'?' selected':''}>丸印（個人）</option></select></div>`;""",
        """    `<div class="frow"><label>印影の形</label><select data-pf="sealType">
      <option value="square"${p.sealType==='square'?' selected':''}>角印（会社）</option>
      <option value="round"${p.sealType==='round'?' selected':''}>丸印（個人）</option></select></div>` +
    `<div class="frow"><label>判子の画像</label><div style="flex:1">
      <div id="seal-drop" style="border:2px dashed #9fb3d4;border-radius:6px;background:#f7faff;padding:10px;text-align:center;cursor:pointer;color:#42618f;font-size:12px">
        ${p.sealImage ? '<img src="'+p.sealImage+'" style="max-height:56px">' : '実物の判子を押して撮った画像を、ここに放り込む'}
      </div>
      <input type="file" id="seal-file" accept="image/*" style="display:none">
      <div style="font-size:11px;color:#666;margin-top:4px">
        白い紙に押して撮る（またはスキャン）。白い所は自動で透かします。
        <span id="seal-size-wrap" ${p.sealImage?'':'style="display:none"'}>
          大きさ <input type="number" id="seal-size" value="${p.sealSize||17}" min="8" max="30" style="width:52px"> mm
        </span>
        ${p.sealImage ? '<button type="button" id="seal-clear" style="margin-left:6px">画像をやめる</button>' : ''}
      </div></div></div>`;"""
    )


    # 判子の画像を読む処理と、設定画面の配線
    s = s.replace("  $$('#profile-tabs button')", "  wireSealBox();\n  $$('#profile-tabs button')")

    # 配布版だけの機能：導入の道順パネル
    s = s.replace("</body>", '<script src="quest.js"></script>\n<script src="nittei.js"></script>\n</body>', 1)

    # ローダーを saveProfiles の直後に差し込む
    anchor = "function saveProfiles(){ localStorage.setItem(LS+'profiles', JSON.stringify(profiles)); }\n"
    assert anchor in s, "saveProfiles が見つからない"
    new_save = ("function saveProfiles(){ localStorage.setItem(LS+'profiles', JSON.stringify(profiles)); "
                "if (typeof pushProfiles === 'function') pushProfiles(); }\n")
    s = s.replace(anchor, new_save + SEAL_JS + LOADER, 1)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(s, encoding="utf-8")

    bad = []
    words = load_forbidden_words()
    if not words:
        print("注意: 作者固有の禁止語ファイルが無い（~/.paper-maker-dev/forbidden.txt）。汎用パターンだけで検査")
    for i, line in enumerate(s.splitlines(), 1):
        for w in words:
            if w in line:
                bad.append((i, "固有語", line.strip()[:100]))
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, line) and not any(a in line for a in _ALLOW):
                bad.append((i, pat, line.strip()[:100]))
    if bad:
        for b in bad:
            print("残っている: L%d [%s] %s" % b)
        sys.exit("配布不可の語が %d 箇所" % len(bad))
    print("OK:", dst, "(%d bytes)" % len(s.encode("utf-8")))


if __name__ == "__main__":
    main()
