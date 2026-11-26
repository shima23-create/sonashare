(() => {
  const searchForm = document.querySelector("[data-place-search]");
  if (!searchForm) {
    return;
  }

  const keywordInput = document.getElementById("place-keyword");
  const searchButton = searchForm.querySelector("[data-search-button]");
  const status = document.querySelector("[data-route-status]");
  const resultsList = document.querySelector("[data-place-results]");
  const currentLocationButton = document.querySelector(
    "[data-use-current-location]",
  );
  const startLabel = document.querySelector("[data-start-label]");
  const mapElement = document.getElementById("route-map");
  const googleRouteLink = document.querySelector("[data-google-route-link]");
  const prefSelect = document.querySelector("[data-pref-select]");
  const currentLocationBadge = document.querySelector(
    "[data-current-location-badge]",
  );
  const currentLocationText = document.querySelector(
    "[data-current-location-text]",
  );
  const recenterBtn = document.querySelector("[data-recenter-btn]");
  const nearbyRadiusSelect = document.querySelector("[data-nearby-radius]");
  const nearbyResults = document.querySelector("[data-nearby-results]");
  const nearbySummary = document.querySelector("[data-nearby-summary]");
  const nearbyList = document.querySelector("[data-nearby-list]");
  const inventorySearchUrl = mapElement
    ? mapElement.dataset.inventorySearchUrl
    : null;

  if (!status) {
    return;
  }

  if (
    !window.L ||
    !keywordInput ||
    !searchButton ||
    !status ||
    !resultsList ||
    !currentLocationButton ||
    !mapElement ||
    !inventorySearchUrl
  ) {
    status.textContent = "地図を読み込めませんでした。時間をおいて再度お試しください。";
    if (searchButton) {
      searchButton.disabled = true;
    }
    if (currentLocationButton) {
      currentLocationButton.disabled = true;
    }
    return;
  }

  // スポットデータと都道府県座標のパース
  let mapSpots = [];
  try {
    if (mapElement.dataset.mapSpots) {
      mapSpots = JSON.parse(mapElement.dataset.mapSpots);
    }
  } catch (e) {
    console.error("マップスポットの読み込みに失敗しました:", e);
  }

  let prefCoords = null;
  try {
    if (mapElement.dataset.prefCoords) {
      prefCoords = JSON.parse(mapElement.dataset.prefCoords);
    }
  } catch (e) {
    console.error("都道府県座標の読み込みに失敗しました:", e);
  }

  // 初期表示の中心座標
  let initialCenter = [35.6895, 139.6917]; // デフォルト東京
  let initialZoom = 12;

  if (prefCoords && prefCoords.length === 2) {
    initialCenter = prefCoords;
    initialZoom = 11;
  } else if (mapSpots.length > 0) {
    initialCenter = [mapSpots[0].lat, mapSpots[0].lng];
    initialZoom = 13;
  }

  const map = window.L.map(mapElement, {
    scrollWheelZoom: true,
    doubleClickZoom: true,
    touchZoom: true,
    maxZoom: 22,
  }).setView(
    initialCenter,
    initialZoom,
  );
  if (
    window.matchMedia &&
    window.matchMedia("(pointer: coarse)").matches
  ) {
    map.dragging.disable();
  }

  // マップ上でのホイール操作によるブラウザ全体の拡大（Ctrl+ホイール / トラックパッドピンチ）を防止し、マップのみを拡大
  mapElement.addEventListener(
    "wheel",
    (event) => {
      if (event.ctrlKey) {
        event.preventDefault();
      }
    },
    { capture: true, passive: false },
  );

  // Safari / iOS 等のジェスチャーズームによる画面全体の拡大も防止
  ["gesturestart", "gesturechange", "gestureend"].forEach((evtName) => {
    mapElement.addEventListener(
      evtName,
      (event) => {
        event.preventDefault();
      },
      { capture: true, passive: false },
    );
  });

  window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxNativeZoom: 19,
    maxZoom: 22,
    detectRetina: true,
    referrerPolicy: "strict-origin-when-cross-origin",
  }).addTo(map);

  // マーカー管理
  let spotMarkers = [];
  let userLocationMarker = null;
  let userLatLng = null;
  let startPoint = window.L.latLng(initialCenter[0], initialCenter[1]);
  let routeControl = null;
  let activeRequest = null;
  let inventoryMarker = null;
  let inventoryRequest = null;
  let lastSearchAt = 0;

  // 緑色の備蓄拠点用カスタムアイコン
  const greenIcon = window.L.divIcon({
    className: "custom-stock-marker",
    html: `<div class="marker-pin-green"><span class="marker-icon">📦</span></div>`,
    iconSize: [36, 42],
    iconAnchor: [18, 42],
    popupAnchor: [0, -38],
  });

  // 青色の現在地用カスタムアイコン（Googleマップ風の青いドットとパルスアニメーション）
  const userIcon = window.L.divIcon({
    className: "custom-user-dot-container",
    html: `<div class="user-pulse-ring"></div><div class="user-dot-core"></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  });

  let accuracyCircle = null;

  function setStatus(message) {
    status.textContent = message;
  }

  // 距離計算（km）
  function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return (R * c).toFixed(1);
  }

  function calculateDistanceMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function getNearbyRadius() {
    const radius = nearbyRadiusSelect
      ? Number(nearbyRadiusSelect.value)
      : 200;
    return Number.isFinite(radius) && radius > 0 ? radius : 200;
  }

  function matchesPref(spot, filterPref) {
    if (!filterPref) {
      return true;
    }
    return Boolean(
      (spot.address && spot.address.includes(filterPref)) ||
        (spot.name && spot.name.includes(filterPref)),
    );
  }

  function renderNearbyBusinesses() {
    if (!nearbyResults || !nearbySummary || !nearbyList || !userLatLng) {
      return;
    }

    const radius = getNearbyRadius();
    const filterPref = prefSelect ? prefSelect.value.trim() : "";
    const nearbySpots = mapSpots
      .filter(
        (spot) =>
          matchesPref(spot, filterPref) &&
          Number.isFinite(Number(spot.lat)) &&
          Number.isFinite(Number(spot.lng)),
      )
      .map((spot) => ({
        spot,
        distance: calculateDistanceMeters(
          userLatLng.lat,
          userLatLng.lng,
          Number(spot.lat),
          Number(spot.lng),
        ),
      }))
      .filter(({ distance }) => distance <= radius)
      .sort((a, b) => a.distance - b.distance);

    nearbyResults.hidden = false;
    const radiusLabel = radius >= 1000 ? `${radius / 1000}km` : `${radius}m`;
    nearbySummary.textContent = `${radiusLabel}以内の提供拠点（${nearbySpots.length}件）`;
    nearbyList.replaceChildren();

    if (nearbySpots.length === 0) {
      const empty = document.createElement("li");
      empty.textContent =
        "この範囲に位置情報が登録された提供企業はありません。距離を広げてお試しください。";
      nearbyList.append(empty);
      return;
    }

    nearbySpots.forEach(({ spot, distance }) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const name = document.createElement("strong");
      const detail = document.createElement("small");

      button.type = "button";
      button.className = "route-search-result";
      name.textContent = spot.org_name || spot.name || "提供企業";
      detail.textContent = `${spot.address || "住所情報なし"}・現在地から約${Math.round(distance)}m`;
      button.append(name, detail);
      button.addEventListener("click", () => {
        const latLng = [Number(spot.lat), Number(spot.lng)];
        map.setView(latLng, Math.max(map.getZoom(), 16));
        const marker = spotMarkers.find((candidate) =>
          candidate.getLatLng().equals(latLng),
        );
        if (marker) {
          marker.openPopup();
        }
      });
      item.append(button);
      nearbyList.append(item);
    });
  }

  // ポップアップ内容の作成（備蓄量を一覧表示）
  function buildSpotPopupContent(spot, distKm = null) {
    const container = document.createElement("div");
    container.className = "stock-popup-content";

    const header = document.createElement("div");
    header.className = "stock-popup-header";

    const title = document.createElement("h3");
    title.className = "stock-popup-title";
    title.textContent = spot.name || spot.org_name || "受渡場所";
    header.append(title);

    if (spot.org_name && spot.org_name !== spot.name) {
      const org = document.createElement("p");
      org.className = "stock-popup-org";
      org.textContent = spot.org_name;
      header.append(org);
    }

    if (spot.address) {
      const addr = document.createElement("p");
      addr.className = "stock-popup-address";
      addr.textContent = `📍 ${spot.address}`;
      header.append(addr);
    }

    if (distKm !== null) {
      const distBadge = document.createElement("span");
      distBadge.className = "stock-popup-dist";
      distBadge.textContent = `現在地から約 ${distKm} km`;
      header.append(distBadge);
    }
    container.append(header);

    // 備蓄品リスト（備蓄量を大きく表示）
    const stockSection = document.createElement("div");
    stockSection.className = "stock-popup-body";

    const secTitle = document.createElement("div");
    secTitle.className = "stock-popup-sectitle";
    secTitle.textContent = `公開中の備蓄品（${spot.items.length}件）:`;
    stockSection.append(secTitle);

    const list = document.createElement("ul");
    list.className = "stock-popup-list";

    spot.items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "stock-popup-item";

      const itemInfo = document.createElement("div");
      itemInfo.className = "stock-item-info";

      const itemName = document.createElement("span");
      itemName.className = "stock-item-name";
      itemName.textContent = item.title;

      const itemCat = document.createElement("span");
      itemCat.className = "badge badge-ok badge-sm";
      itemCat.textContent = item.category;

      itemInfo.append(itemName, itemCat);

      const itemQty = document.createElement("div");
      itemQty.className = "stock-item-qty";
      const quantity = document.createElement("strong");
      quantity.textContent = String(item.quantity);
      itemQty.append(
        document.createTextNode("残り "),
        quantity,
        document.createTextNode(` ${item.unit}`),
      );

      li.append(itemInfo, itemQty);

      if (item.detail_url) {
        const link = document.createElement("a");
        link.className = "btn btn-primary btn-sm stock-apply-btn";
        link.href = item.detail_url;
        link.textContent = "詳細・申請";
        link.style.color = "#ffffff";
        li.append(link);
      }

      list.append(li);
    });

    stockSection.append(list);
    container.append(stockSection);

    return container;
  }

  // 備蓄スポットのピンを描画
  function renderSpotMarkers(filterPref = "") {
    // 既存マーカーを削除
    spotMarkers.forEach((m) => map.removeLayer(m));
    spotMarkers = [];

    const bounds = window.L.latLngBounds([]);
    let count = 0;

    mapSpots.forEach((spot) => {
      // 都道府県フィルター
      if (!matchesPref(spot, filterPref)) {
        return;
      }

      let dist = null;
      if (userLatLng) {
        dist = calculateDistance(
          userLatLng.lat,
          userLatLng.lng,
          spot.lat,
          spot.lng,
        );
      }

      const marker = window.L.marker([spot.lat, spot.lng], { icon: greenIcon })
        .addTo(map)
        .bindPopup(() => buildSpotPopupContent(spot, dist), {
          maxWidth: 320,
          className: "stock-leaflet-popup",
          autoClose: false,
          closeOnClick: false,
        });

      marker.on("click", (event) => {
        window.L.DomEvent.stopPropagation(event);
        marker.openPopup();
      });

      bounds.extend([spot.lat, spot.lng]);
      spotMarkers.push(marker);
      count++;
    });

    if (count > 0 && bounds.isValid() && !filterPref) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }

    if (count > 0) {
      setStatus(`地図上に備蓄拠点（${count}件）のピンを表示しています。ピンを押すと備蓄量を確認できます。`);
    } else {
      setStatus("指定された条件の備蓄拠点が見つかりませんでした。");
    }
  }

  // 初回ピン描画
  const initialPref = mapElement.dataset.selectedPref || "";
  renderSpotMarkers(initialPref);

  // 受渡し住所ごとの座標へ置き換え（推定座標の重複を防ぐ）
  async function geocodeSpotAddresses() {
    const cache = new Map();

    for (const spot of mapSpots) {
      const query = (spot.geocode_address || spot.address || "").trim();
      if (!query) {
        continue;
      }

      let places;
      if (cache.has(query)) {
        places = cache.get(query);
      } else {
        const controller = new AbortController();
        try {
          places = await searchGsi(query, controller.signal);
        } catch (error) {
          if (error.name !== "AbortError") {
            console.warn("受渡し住所の座標取得に失敗しました:", error);
          }
          places = [];
        }
        cache.set(query, places);
      }

      if (places.length > 0) {
        spot.lat = places[0].lat;
        spot.lng = places[0].lon;
        spot.coordinates_known = true;
      }
    }

    renderSpotMarkers(prefSelect ? prefSelect.value : initialPref);
  }

  geocodeSpotAddresses();

  // 都道府県絞り込みセレクトボックスの変更イベント
  if (prefSelect) {
    prefSelect.addEventListener("change", (e) => {
      const selectedPref = e.target.value.trim();
      setStatus(
        selectedPref
          ? `「${selectedPref}」で絞り込んでいます...`
          : "全国の備蓄品を表示しています...",
      );

      // 下部の検索フォームとも同期
      const formPref = document.getElementById("pref");
      if (formPref) {
        formPref.value = selectedPref;
      }

      // ピンを再描画
      renderSpotMarkers(selectedPref);
      renderNearbyBusinesses();

      // 都道府県の代表座標へスムーズ移動
      if (selectedPref) {
        // Nominatim で都道府県の座標を取得するか、既知のピンへズーム
        const matchingMarkers = spotMarkers;
        if (matchingMarkers.length > 0) {
          const group = window.L.featureGroup(matchingMarkers);
          map.fitBounds(group.getBounds().pad(0.3), { maxZoom: 13 });
        } else {
          // ジオコード検索で都道府県中心へ移動
          searchGsi(selectedPref, new AbortController().signal).then((places) => {
            if (places && places.length > 0) {
              map.setView([places[0].lat, places[0].lon], 10);
            }
          }).catch(() => {});
        }
      } else if (spotMarkers.length > 0) {
        const group = window.L.featureGroup(spotMarkers);
        map.fitBounds(group.getBounds(), { padding: [40, 40], maxZoom: 13 });
      }
    });
  }

  // 逆ジオコーディング（国土地理院・Nominatimからおおよその地名を取得）
  async function reverseGeocode(lat, lng) {
    try {
      const response = await fetch(
        `https://msearch.gsi.go.jp/address-search/AddressSearch?q=${lat},${lng}`,
        { referrerPolicy: "strict-origin" },
      );
      if (response.ok) {
        const data = await response.json();
        if (
          Array.isArray(data) &&
          data.length > 0 &&
          data[0].properties &&
          data[0].properties.title
        ) {
          return data[0].properties.title;
        }
      }
    } catch (e) {
      // GSIが失敗した場合はNominatimを試行
    }

    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&accept-language=ja`,
        { referrerPolicy: "strict-origin" },
      );
      if (response.ok) {
        const data = await response.json();
        if (data.address) {
          return formatJapaneseAddress(data.address, data.display_name);
        }
      }
    } catch (e) {
      // エラー時はnull
    }
    return null;
  }

  // 現在地取得＆マップ・バナー更新関数
  function locateUser(options = {}) {
    const {
      centerMap = true,
      notifyUser = true,
      openNearestPopup = true,
    } = options;

    if (!navigator.geolocation) {
      if (notifyUser) {
        setStatus("お使いのブラウザーは現在地取得に対応していません。");
      }
      return;
    }

    if (currentLocationButton) {
      currentLocationButton.disabled = true;
    }
    if (notifyUser) {
      setStatus("現在地を取得しています...");
    }

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const accuracy = position.coords.accuracy
          ? Math.round(position.coords.accuracy)
          : null;
        userLatLng = { lat, lng };
        startPoint = window.L.latLng(lat, lng);

        if (startLabel) {
          startLabel.textContent = "現在地（GPS取得済み）";
        }

        // 現在地ステータスバナーの表示更新
        if (currentLocationBadge) {
          currentLocationBadge.hidden = false;
        }
        if (currentLocationText) {
          currentLocationText.textContent = `緯度 ${lat.toFixed(4)}, 経度 ${lng.toFixed(4)} 付近${accuracy ? `（誤差 ±${accuracy}m）` : ""}`;
        }

        // 現在地マーカーと精度円の描画・更新
        if (userLocationMarker) {
          map.removeLayer(userLocationMarker);
        }
        if (accuracyCircle) {
          map.removeLayer(accuracyCircle);
        }

        const circleRadius = Math.min(position.coords.accuracy || 120, 1500);
        accuracyCircle = window.L.circle([lat, lng], {
          radius: circleRadius,
          color: "#1d6fd8",
          weight: 1,
          fillColor: "#1d6fd8",
          fillOpacity: 0.12,
        }).addTo(map);

        userLocationMarker = window.L.marker([lat, lng], {
          icon: userIcon,
          zIndexOffset: 1000,
        })
          .addTo(map)
          .bindPopup(
            `<div style="text-align:center;padding:4px 6px;">
              <strong style="color:#1d6fd8;font-size:14px;">📍 あなたの現在地</strong><br>
              <span style="font-size:12px;color:#555;">GPS取得位置</span><br>
              <small style="color:#888;">${accuracy ? `精度: ±${accuracy}m` : ""}</small>
            </div>`,
          );

        // 逆ジオコーディングで地名を非同期取得
        reverseGeocode(lat, lng)
          .then((placeName) => {
            if (placeName) {
              if (currentLocationText) {
                currentLocationText.textContent = `${placeName}${accuracy ? `（誤差 ±${accuracy}m）` : ""}`;
              }
              if (userLocationMarker) {
                userLocationMarker.setPopupContent(
                  `<div style="text-align:center;padding:4px 6px;">
                    <strong style="color:#1d6fd8;font-size:14px;">📍 あなたの現在地</strong><br>
                    <span style="font-size:12px;color:#333;font-weight:600;">${placeName}</span><br>
                    <small style="color:#888;">${accuracy ? `精度: ±${accuracy}m` : ""}</small>
                  </div>`,
                );
              }
            }
          })
          .catch(() => {});

        // ピンを再描画（現在地からの距離を反映）
        renderSpotMarkers(prefSelect ? prefSelect.value : "");
        renderNearbyBusinesses();

        // 最寄りの備蓄拠点を探索
        let nearestDist = Infinity;
        let nearestMarker = null;

        spotMarkers.forEach((marker) => {
          const mPos = marker.getLatLng();
          const d = calculateDistance(lat, lng, mPos.lat, mPos.lng);
          if (Number(d) < nearestDist) {
            nearestDist = Number(d);
            nearestMarker = marker;
          }
        });

        if (centerMap) {
          if (nearestMarker) {
            // 現在地と最寄りピンを含む範囲へズーム
            const bounds = window.L.latLngBounds([
              [lat, lng],
              nearestMarker.getLatLng(),
            ]);
            map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
            if (notifyUser) {
              setStatus(
                `現在地を取得しました。最寄りの備蓄拠点まで約 ${nearestDist} km です。`,
              );
            }
            if (openNearestPopup) {
              setTimeout(() => {
                nearestMarker.openPopup();
              }, 600);
            }
          } else {
            map.setView([lat, lng], 14);
            if (notifyUser) {
              setStatus(
                `現在地から${getNearbyRadius()}m以内に企業がありません。検索範囲を広げてください。`,
              );
            }
          }
        }

        if (currentLocationButton) {
          currentLocationButton.disabled = false;
        }
      },
      (error) => {
        console.warn("位置情報の取得に失敗しました:", error);
        if (notifyUser) {
          let errorMsg = "現在地を取得できませんでした。";
          if (error.code === 1) {
            errorMsg =
              "位置情報の利用が許可されていません。ブラウザのアドレスバー等から位置情報の利用を許可してください。";
          } else if (error.code === 2) {
            errorMsg =
              "現在地を特定できませんでした。電波環境の良い場所でお試しください。";
          } else if (error.code === 3) {
            errorMsg = "現在地の取得がタイムアウトしました。";
          }
          setStatus(errorMsg);
        }
        if (currentLocationButton) {
          currentLocationButton.disabled = false;
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }

  // 現在地から絞り込むボタン
  currentLocationButton.addEventListener("click", () => {
    locateUser({ centerMap: true, notifyUser: true, openNearestPopup: true });
  });

  if (nearbyRadiusSelect) {
    nearbyRadiusSelect.addEventListener("change", () => {
      if (!userLatLng) {
        return;
      }
      renderSpotMarkers(prefSelect ? prefSelect.value : "");
      renderNearbyBusinesses();
      const radius = getNearbyRadius();
      let zoom = 7;
      if (radius <= 200) {
        zoom = 16;
      } else if (radius <= 500) {
        zoom = 15;
      } else if (radius <= 1000) {
        zoom = 14;
      } else if (radius <= 5000) {
        zoom = 12;
      } else if (radius <= 10000) {
        zoom = 11;
      } else if (radius <= 20000) {
        zoom = 10;
      } else if (radius <= 50000) {
        zoom = 8;
      }
      map.setView([userLatLng.lat, userLatLng.lng], zoom);
      setStatus(
        `現在地から${radius >= 1000 ? `${radius / 1000}km` : `${radius}m`}以内の企業・施設に絞り込んでいます。`,
      );
    });
  }

  // バナー内の「現在地に移動」ボタン
  if (recenterBtn) {
    recenterBtn.addEventListener("click", () => {
      if (userLatLng) {
        map.setView([userLatLng.lat, userLatLng.lng], 15);
        if (userLocationMarker) {
          userLocationMarker.openPopup();
        }
        setStatus("現在地を中心表示しました。");
      } else {
        locateUser({
          centerMap: true,
          notifyUser: true,
          openNearestPopup: false,
        });
      }
    });
  }

  // 初回ロード時：位置情報の権限が既に許可されている場合は自動で現在地を取得・表示
  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions
      .query({ name: "geolocation" })
      .then((result) => {
        if (result.state === "granted") {
          locateUser({
            centerMap: false,
            notifyUser: false,
            openNearestPopup: false,
          });
        }
      })
      .catch(() => {});
  }

  // 検索欄クリア時に検索ピン・検索結果・ステータスをリセット
  function clearSearchPin() {
    if (inventoryMarker) {
      map.removeLayer(inventoryMarker);
      inventoryMarker = null;
    }
    if (inventoryRequest) {
      inventoryRequest.abort();
      inventoryRequest = null;
    }
    resultsList.replaceChildren();
    setStatus("地図上のピンを選択すると備蓄量を確認できます。");
  }

  keywordInput.addEventListener("input", () => {
    if (keywordInput.value.trim() === "") {
      if (activeRequest) {
        activeRequest.abort();
        activeRequest = null;
      }
      clearSearchPin();
    }
  });

  // 検索フォームの「×」（type=search のブラウザ標準クリアボタン）にも対応
  keywordInput.addEventListener("search", () => {
    if (keywordInput.value.trim() === "") {
      if (activeRequest) {
        activeRequest.abort();
        activeRequest = null;
      }
      clearSearchPin();
    }
  });

  // 施設名・住所検索フォーム
  searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = keywordInput.value.trim();
    if (!query) {
      clearSearchPin();
      return;
    }
    if (Date.now() - lastSearchAt < 800) {
      return;
    }
    lastSearchAt = Date.now();

    if (activeRequest) {
      activeRequest.abort();
    }
    const controller = new AbortController();
    activeRequest = controller;
    const { signal } = controller;

    searchButton.disabled = true;
    resultsList.replaceChildren();
    setStatus(`「${query}」を検索しています...`);

    try {
      let places = await searchNominatim(query, signal);
      if (places.length === 0) {
        places = await searchGsi(query, signal);
      }

      if (signal.aborted) {
        return;
      }
      if (places.length === 0) {
        setStatus("候補が見つかりませんでした。別の施設名や住所をお試しください。");
        return;
      }

      places.forEach(addPlaceResult);
      setStatus(`候補が${places.length}件見つかりました。候補を選ぶと地図上にピンが表示されます。`);
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      console.error("場所検索に失敗しました。", error);
      setStatus("場所検索に失敗しました。通信状況を確認して再度お試しください。");
    } finally {
      if (!signal.aborted) {
        searchButton.disabled = false;
      }
    }
  });

  async function searchNominatim(query, signal) {
    const params = new URLSearchParams({
      format: "jsonv2",
      q: query,
      countrycodes: "jp",
      limit: "5",
      addressdetails: "1",
      "accept-language": "ja",
    });
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?${params.toString()}`,
      { signal, referrerPolicy: "strict-origin" },
    );
    if (!response.ok) {
      throw new Error(`Nominatim returned ${response.status}`);
    }

    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error("Nominatim returned an invalid response");
    }

    return data
      .map((place) => ({
        name: place.name || place.display_name,
        address: formatJapaneseAddress(place.address, place.display_name),
        lat: Number(place.lat),
        lon: Number(place.lon),
      }))
      .filter((place) => Number.isFinite(place.lat) && Number.isFinite(place.lon));
  }

  async function searchGsi(query, signal) {
    const url = new URL("https://msearch.gsi.go.jp/address-search/AddressSearch");
    url.searchParams.set("q", query);
    const response = await fetch(url, {
      signal,
      referrerPolicy: "strict-origin",
    });
    if (!response.ok) {
      throw new Error(`GSI returned ${response.status}`);
    }

    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error("GSI returned an invalid response");
    }

    return data.slice(0, 5).map((item) => {
      const [lon, lat] = item.geometry.coordinates;
      return {
        name: item.properties.title,
        address: item.properties.title,
        lat: Number(lat),
        lon: Number(lon),
      };
    }).filter((place) => Number.isFinite(place.lat) && Number.isFinite(place.lon));
  }

  function addPlaceResult(place) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const name = document.createElement("strong");
    const address = document.createElement("small");

    button.type = "button";
    button.className = "route-search-result";
    name.textContent = place.name || place.address || "名称未設定";
    address.textContent = place.address;
    button.append(name, address);
    button.addEventListener("click", () => {
      selectPlace(place);
    });
    item.append(button);
    resultsList.append(item);
  }

  function selectPlace(place) {
    const dest = window.L.latLng(place.lat, place.lon);
    map.setView(dest, 14);

    if (inventoryMarker) {
      map.removeLayer(inventoryMarker);
    }

    const searchPopup = document.createElement("div");
    const searchTitle = document.createElement("strong");
    searchTitle.textContent = place.name || place.address;
    searchPopup.append(
      searchTitle,
      document.createElement("br"),
      document.createTextNode("この周辺の備蓄品を検索中..."),
    );
    inventoryMarker = window.L.marker(dest)
      .addTo(map)
      .bindPopup(searchPopup)
      .openPopup();

    // 周辺の備蓄在庫を問い合わせ
    showInventoryAtPlace(place, keywordInput.value.trim());

    if (googleRouteLink) {
      const googleRouteParams = new URLSearchParams({
        api: "1",
        origin: `${startPoint.lat},${startPoint.lng}`,
        destination: `${dest.lat},${dest.lng}`,
        travelmode: "driving",
      });
      googleRouteLink.href = `https://www.google.com/maps/dir/?${googleRouteParams.toString()}`;
      googleRouteLink.hidden = true;
    }
  }

  async function showInventoryAtPlace(place, query) {
    if (inventoryRequest) {
      inventoryRequest.abort();
    }
    const controller = new AbortController();
    inventoryRequest = controller;
    const params = new URLSearchParams({ q: query });

    try {
      const response = await fetch(
        `${inventorySearchUrl}?${params.toString()}`,
        {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        },
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "在庫情報を取得できませんでした。");
      }

      if (inventoryMarker) {
        inventoryMarker.setPopupContent(createInventoryPopup(data.organizations, place));
        inventoryMarker.openPopup();
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      console.warn("在庫情報の取得に失敗:", error);
      if (inventoryMarker) {
        inventoryMarker.setPopupContent(
          document.createTextNode(
            error.message || "この場所の在庫情報を取得できませんでした。",
          ),
        );
      }
    }
  }

  function createInventoryPopup(organizations, place) {
    const popup = document.createElement("div");
    popup.className = "inventory-map-popup";

    if (!Array.isArray(organizations) || organizations.length === 0) {
      const title = document.createElement("strong");
      title.textContent = place.name || place.address;
      const message = document.createElement("p");
      message.textContent = "この周辺に登録された公開中の備蓄品はありません。";
      popup.append(title, message);
      return popup;
    }

    const title = document.createElement("strong");
    title.textContent = "周辺の公開中備蓄品";
    popup.append(title);

    organizations.forEach((organization) => {
      const section = document.createElement("section");
      const heading = document.createElement("strong");
      heading.textContent = organization.name;
      section.append(heading);

      const itemList = document.createElement("ul");
      organization.items.forEach((item) => {
        const listItem = document.createElement("li");
        const quantity = document.createElement("strong");
        quantity.textContent = `${item.quantity}${item.unit}`;
        listItem.append(
          document.createTextNode(`${item.name}: `),
          quantity,
        );
        itemList.append(listItem);
      });
      section.append(itemList);
      popup.append(section);
    });

    return popup;
  }

  function formatJapaneseAddress(address, fallback) {
    if (!address || typeof address !== "object") {
      return fallback || "住所情報なし";
    }

    const parts = [
      address.postcode ? `〒${address.postcode} ` : "",
      address.province || address.state || "",
      address.city || address.town || address.village || "",
      address.suburb || address.neighbourhood || "",
      address.road || "",
      address.house_number || "",
    ];
    const formatted = parts.join("");
    return formatted.length > 5 ? formatted : fallback || "住所情報なし";
  }
})();
