/* バーコードから備蓄品登録フォームの「品名」を入力する(無料: ZXing + Open Food Facts)
 *
 * 使い方
 *   - [data-barcode-open] が付いたボタンを押すと、読み取り画面が開く
 *   - URL に ?scan=1 が付いていて、登録フォームがあれば、自動で開く
 *   - カメラが使えなくても、数字を入力して検索できる
 */
(function () {
  "use strict";

  var LIB_URL = "https://unpkg.com/@zxing/library@0.21.3/umd/index.min.js";
  var API = "https://world.openfoodfacts.org/api/v2/product/";
  var session = null;   // 動いているカメラ { stream, timer }
  var overlay = null;
  var libPromise = null;

  // ---------- バーコードの数字が正しいか(チェックデジット) ----------
  function isValidJan(code) {
    if (!/^(\d{8}|\d{13})$/.test(code)) return false;
    var digits = code.split("").map(Number);
    var check = digits.pop();
    var sum = 0;
    for (var i = digits.length - 1, w = 3; i >= 0; i--, w = 4 - w) sum += digits[i] * w;
    return (10 - (sum % 10)) % 10 === check;
  }

  // ---------- 画面 ----------
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    for (var k in attrs || {}) node.setAttribute(k, attrs[k]);
    if (text) node.textContent = text;
    return node;
  }

  function buildOverlay() {
    var box = el("div", { class: "barcode-overlay", role: "dialog", "aria-modal": "true", "aria-label": "バーコードを読み取る" });
    var panel = el("div", { class: "barcode-panel" });
    var head = el("div", { class: "barcode-head" });
    head.appendChild(el("strong", {}, "バーコードを読み取る"));
    var close = el("button", { type: "button", class: "barcode-close", "aria-label": "閉じる" }, "×");
    head.appendChild(close);
    var readerBox = el("div", { id: "barcode-reader", class: "barcode-reader" });
    var video = el("video", { class: "barcode-video", playsinline: "true", muted: "true", autoplay: "true" });
    video.muted = true;
    readerBox.appendChild(video);
    readerBox.appendChild(el("div", { class: "barcode-guide", "aria-hidden": "true" }));
    var camera = el("select", { class: "select barcode-camera", "aria-label": "使うカメラ", hidden: "hidden" });
    var status = el("p", { class: "barcode-status", "aria-live": "polite" }, "バーコードを、枠の中に映してください。");
    var manual = el("form", { class: "barcode-manual" });
    var input = el("input", { type: "text", inputmode: "numeric", class: "field-input", placeholder: "数字を入力(例: 4901234567894)", "aria-label": "バーコードの数字", maxlength: "13" });
    var go = el("button", { type: "submit", class: "btn" }, "検索");
    manual.appendChild(input);
    manual.appendChild(go);
    panel.appendChild(head);
    panel.appendChild(readerBox);
    panel.appendChild(camera);
    panel.appendChild(status);
    panel.appendChild(manual);
    box.appendChild(panel);
    box._parts = { close: close, status: status, manual: manual, input: input, camera: camera, video: video };
    return box;
  }

  function setStatus(text, isError) {
    overlay._parts.status.textContent = text;
    overlay._parts.status.className = "barcode-status" + (isError ? " is-error" : "");
  }

  // ---------- カメラ ----------
  function loadLib() {
    if (window.ZXing) return Promise.resolve();
    if (libPromise) return libPromise;
    libPromise = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = LIB_URL;
      s.onload = resolve;
      s.onerror = function () { libPromise = null; reject(new Error("lib")); };
      document.head.appendChild(s);
    });
    return libPromise;
  }

  function startCamera(cameraId) {
    if (!window.isSecureContext || !navigator.mediaDevices) {
      setStatus("この接続ではカメラを使えません。下の欄に、バーコードの数字を入力してください。", true);
      return;
    }
    var mine = {};            // この開始の目印(途中で閉じたら、止める)
    session = mine;
    var size = { width: { ideal: 1280 }, height: { ideal: 720 } };  // 解像度が高いほど、読み取りやすい
    var video = cameraId
      ? Object.assign({ deviceId: { exact: cameraId } }, size)
      : Object.assign({ facingMode: { ideal: "environment" } }, size);

    Promise.all([loadLib(), navigator.mediaDevices.getUserMedia({ video: video })]).then(function (r) {
      var stream = r[1];
      if (session !== mine || !overlay) { stream.getTracks().forEach(function (t) { t.stop(); }); return; }
      mine.stream = stream;
      var v = overlay._parts.video;
      v.srcObject = stream;
      return v.play().then(function () {
        setStatus("バーコードを、枠の中に映してください。", false);
        listCameras(cameraId);
        scanLoop(mine, v);
      });
    }).catch(function (err) {
      if (session !== mine) return;
      var denied = err && (err.name === "NotAllowedError" || /denied|permission/i.test(String(err)));
      setStatus(denied
        ? "カメラの使用が許可されていません。ブラウザの設定を確認するか、下の欄に数字を入力してください。"
        : "カメラを開始できませんでした。下の欄に、バーコードの数字を入力してください。", true);
    });
  }

  // 映像を0.1秒ごとに1コマ取り出して、バーコードを探す(全体 → 中央を拡大 → …を交互に)
  function scanLoop(mine, video) {
    var hints = new Map();
    hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8]);
    hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
    var decoder = new ZXing.MultiFormatReader();
    decoder.setHints(hints);
    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d", { willReadFrequently: true });
    var n = 0;

    function tryDecode(useGlobal) {
      try {
        var lum = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
        var bin = useGlobal ? new ZXing.GlobalHistogramBinarizer(lum) : new ZXing.HybridBinarizer(lum);
        return decoder.decode(new ZXing.BinaryBitmap(bin)).getText();
      } catch (e) { return null; }
    }

    // 試し方を順番に変える: 全体 / 中央を拡大 / 中央をさらに拡大 / 全体(別の白黒判定)
    var steps = [
      { crop: null, global: false },
      { crop: [0.8, 0.4, 1.5], global: false },
      { crop: [0.6, 0.3, 2.5], global: false },
      { crop: [0.8, 0.4, 1.5], global: true }
    ];

    function tick() {
      if (session !== mine || !overlay) return;
      var w = video.videoWidth, h = video.videoHeight;
      if (w && h) {
        var step = steps[n++ % steps.length];
        if (!step.crop) {
          canvas.width = w; canvas.height = h;
          ctx.drawImage(video, 0, 0);
        } else {
          var cw = Math.round(w * step.crop[0]), ch = Math.round(h * step.crop[1]);
          canvas.width = Math.round(cw * step.crop[2]); canvas.height = Math.round(ch * step.crop[2]);
          ctx.imageSmoothingQuality = "high";
          ctx.drawImage(video, (w - cw) / 2, (h - ch) / 2, cw, ch, 0, 0, canvas.width, canvas.height);
        }
        var text = tryDecode(step.global);
        if (text && isValidJan(text)) {
          stopCamera();
          lookup(text);
          return;
        }
      }
      mine.timer = setTimeout(tick, 80);
    }
    tick();
  }

  // カメラが2台以上あるときだけ、選べるようにする(黒い画面のときは、別のカメラを選ぶ)
  function listCameras(current) {
    var select = overlay && overlay._parts.camera;
    if (!select || select.options.length) return;
    navigator.mediaDevices.enumerateDevices().then(function (devices) {
      var cams = devices.filter(function (d) { return d.kind === "videoinput"; });
      if (!overlay || cams.length < 2) return;
      var active = session && session.stream && session.stream.getVideoTracks()[0];
      var activeId = active && active.getSettings && active.getSettings().deviceId;
      cams.forEach(function (c, i) {
        var o = el("option", { value: c.deviceId }, c.label || ("カメラ " + (i + 1)));
        if (c.deviceId === (current || activeId)) o.selected = true;
        select.appendChild(o);
      });
      select.hidden = false;
      select.addEventListener("change", function () {
        setStatus("カメラを切り替えています…", false);
        stopCamera();
        startCamera(select.value);
      });
    }).catch(function () {});
  }

  function stopCamera() {
    var s = session;
    session = null;
    if (!s) return Promise.resolve();
    if (s.timer) clearTimeout(s.timer);
    if (s.stream) s.stream.getTracks().forEach(function (t) { t.stop(); });
    if (overlay) overlay._parts.video.srcObject = null;
    return Promise.resolve();
  }

  // ---------- 商品情報の検索と、フォームへの入力 ----------
  function findField(name) {
    return document.querySelector('form [name="' + name + '"]');
  }

  function fillForm(product, code) {
    var nameField = findField("name");
    var name = (product.product_name_ja || product.product_name || "").trim();
    if (!name) return false;
    if (nameField) {
      if (nameField.value && nameField.value !== name &&
          !window.confirm("品名を「" + name + "」に置き換えますか?")) return true;
      nameField.value = name;
      nameField.dispatchEvent(new Event("input", { bubbles: true }));
    }
    var notes = findField("notes");
    if (notes && !notes.value) {
      var parts = [];
      if (product.brands) parts.push("ブランド: " + product.brands);
      if (product.quantity) parts.push("内容量: " + product.quantity);
      parts.push("JAN: " + code);
      notes.value = parts.join(" / ");
    }
    return true;
  }

  function lookup(code) {
    setStatus("商品情報を検索しています…", false);
    var ctrl = window.AbortController ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 8000) : null;
    fetch(API + code + ".json?fields=product_name,product_name_ja,brands,quantity",
          ctrl ? { signal: ctrl.signal } : {})
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.status === 1 && data.product && fillForm(data.product, code)) {
          closeOverlay();
          announce("商品情報を入力しました。数量や消費期限などを入力してください。");
        } else {
          setStatus("商品情報が見つかりませんでした(コード: " + code + ")。閉じて、品名を入力してください。", true);
          var nf = findField("notes");
          if (nf && !nf.value) nf.value = "JAN: " + code;
        }
      })
      .catch(function () {
        setStatus("商品情報を取得できませんでした。通信を確認するか、品名を入力してください。", true);
      })
      .then(function () { if (timer) clearTimeout(timer); });
  }

  function announce(text) {
    var old = document.querySelector(".barcode-toast");
    if (old) old.remove();
    var t = el("div", { class: "barcode-toast", role: "status" }, text);
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 6000);
  }

  // ---------- 開く・閉じる ----------
  function openOverlay() {
    if (overlay) return;
    overlay = buildOverlay();
    document.body.appendChild(overlay);
    overlay._parts.close.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeOverlay(); });
    overlay._parts.manual.addEventListener("submit", function (e) {
      e.preventDefault();
      var code = overlay._parts.input.value.replace(/\s/g, "");
      if (!isValidJan(code)) { setStatus("バーコードの数字が正しくありません(8桁または13桁)。", true); return; }
      stopCamera().then(function () { lookup(code); });
    });
    document.addEventListener("keydown", onKey);
    startCamera();
  }

  function onKey(e) { if (e.key === "Escape") closeOverlay(); }

  function closeOverlay() {
    if (!overlay) return;
    stopCamera();
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    overlay = null;
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-barcode-open]");
    if (btn) { e.preventDefault(); openOverlay(); }
  });

  if (/[?&]scan=1(&|$)/.test(location.search) && findField("name")) openOverlay();

  window.__barcode = { isValidJan: isValidJan };
})();