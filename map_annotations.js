/* ============================================================
 * 区域标注：不规则多边形绘制 + 颜色 / 透明度 / 名称 + 版本快照
 * 数据保存在浏览器 localStorage，重新生成地图后自动恢复。
 * ============================================================ */
(function () {
    "use strict";

    var map = window.__hqMap;
    if (!map || typeof L === "undefined" || !L.Draw) {
        console.warn("[区域标注] 地图或 leaflet.draw 未加载，标注功能已跳过");
        return;
    }

    var STORAGE_KEY = "hq_airport_annotations_v1";
    var DEFAULT_COLOR = "#e53935";
    var DEFAULT_OPACITY = 35;

    var shapes = [];
    var versions = [];
    var activeVersionId = null;
    var nextVersionNo = 1;
    var settings = { color: DEFAULT_COLOR, opacity: DEFAULT_OPACITY };
    var currentDrawer = null;
    var layersById = {};
    var flashTimer = null;

    var featureGroup = L.featureGroup().addTo(map);

    /* ---------------- 工具函数 ---------------- */
    function clamp(n, min, max) {
        return Math.min(max, Math.max(min, n));
    }

    function round6(n) {
        return Math.round(n * 1e6) / 1e6;
    }

    function esc(text) {
        return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }

    function formatTime(date) {
        function pad(n) { return n < 10 ? "0" + n : String(n); }
        return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
            " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
    }

    function clone(obj) {
        return JSON.parse(JSON.stringify(obj));
    }

    function findShape(id) {
        for (var i = 0; i < shapes.length; i++) {
            if (shapes[i].id === id) return shapes[i];
        }
        return null;
    }

    function findShapeIndex(id) {
        for (var i = 0; i < shapes.length; i++) {
            if (shapes[i].id === id) return i;
        }
        return -1;
    }

    function findVersion(id) {
        if (!id) return null;
        for (var i = 0; i < versions.length; i++) {
            if (versions[i].id === id) return versions[i];
        }
        return null;
    }

    function sanitizeShape(raw) {
        if (!raw || !Array.isArray(raw.coords) || raw.coords.length < 3) return null;
        var coords = [];
        for (var i = 0; i < raw.coords.length; i++) {
            var p = raw.coords[i];
            if (!Array.isArray(p) || p.length < 2) return null;
            var lat = parseFloat(p[0]);
            var lng = parseFloat(p[1]);
            if (!isFinite(lat) || !isFinite(lng)) return null;
            coords.push([lat, lng]);
        }
        var opacity = parseFloat(raw.fillOpacity);
        if (!isFinite(opacity)) opacity = 0.35;
        return {
            id: String(raw.id || ("s" + Date.now() + "_" + Math.random().toString(36).slice(2, 7))),
            name: String(raw.name == null ? "" : raw.name),
            color: /^#[0-9a-fA-F]{6}$/.test(raw.color) ? raw.color : DEFAULT_COLOR,
            fillOpacity: clamp(opacity, 0, 1),
            coords: coords
        };
    }

    function sanitizeVersion(raw) {
        if (!raw || typeof raw !== "object") return null;
        var no = parseInt(raw.no, 10);
        if (!isFinite(no) || no <= 0) return null;
        var list = [];
        if (Array.isArray(raw.shapes)) {
            for (var i = 0; i < raw.shapes.length; i++) {
                var s = sanitizeShape(raw.shapes[i]);
                if (s) list.push(s);
            }
        }
        return {
            id: String(raw.id || ("v" + no + "_" + Math.random().toString(36).slice(2, 7))),
            no: no,
            time: String(raw.time || ""),
            shapes: list
        };
    }

    function readStore() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var data = JSON.parse(raw);
            return data && typeof data === "object" ? data : null;
        } catch (err) {
            console.warn("[区域标注] 读取本地标注失败", err);
            return null;
        }
    }

    /* ---------------- 读取 / 应用标注数据 ---------------- */
    function applyStore(data) {
        versions = [];
        shapes = [];
        activeVersionId = null;
        nextVersionNo = 1;
        settings = { color: DEFAULT_COLOR, opacity: DEFAULT_OPACITY };
        if (!data || typeof data !== "object") return;

        if (Array.isArray(data.versions)) {
            for (var vi = 0; vi < data.versions.length; vi++) {
                var sv = sanitizeVersion(data.versions[vi]);
                if (sv) versions.push(sv);
            }
        }
        if (data.activeVersionId) {
            activeVersionId = findVersion(String(data.activeVersionId)) ? String(data.activeVersionId) : null;
        }
        if (data.working && Array.isArray(data.working.shapes)) {
            /* 优先恢复未保存的编辑 */
            for (var wi = 0; wi < data.working.shapes.length; wi++) {
                var ws = sanitizeShape(data.working.shapes[wi]);
                if (ws) shapes.push(ws);
            }
        } else if (activeVersionId) {
            var av = findVersion(activeVersionId);
            if (av) shapes = clone(av.shapes);
        }
        var maxNo = 0;
        for (var mi = 0; mi < versions.length; mi++) {
            if (versions[mi].no > maxNo) maxNo = versions[mi].no;
        }
        nextVersionNo = maxNo + 1;
        if (parseInt(data.nextVersionNo, 10) > nextVersionNo) {
            nextVersionNo = parseInt(data.nextVersionNo, 10);
        }
        if (data.settings) {
            if (/^#[0-9a-fA-F]{6}$/.test(data.settings.color || "")) {
                settings.color = data.settings.color;
            }
            var savedOpacity = parseInt(data.settings.opacity, 10);
            if (isFinite(savedOpacity)) settings.opacity = clamp(savedOpacity, 0, 100);
        }
    }

    var store = readStore();
    if (!store && window.__HQ_ANNOTATIONS__ && typeof window.__HQ_ANNOTATIONS__ === "object") {
        /* 换电脑/换浏览器时，加载随 HTML 内置的标注快照 */
        store = window.__HQ_ANNOTATIONS__;
    }
    applyStore(store);

    /* ---------------- 构建面板 ---------------- */
    var panel = document.createElement("div");
    panel.id = "anno-panel";
    panel.innerHTML = [
        '<div class="anno-header">',
        '  <span class="anno-title">区域标注</span>',
        '  <span class="anno-count" id="anno-count">0</span>',
        '  <button type="button" class="anno-fold" id="anno-fold" title="收起 / 展开">−</button>',
        '</div>',
        '<div class="anno-body" id="anno-body">',
        '  <div class="anno-field">',
        '    <label for="anno-name">名称</label>',
        '    <input type="text" id="anno-name" maxlength="40" placeholder="例如：净空保护区">',
        '  </div>',
        '  <div class="anno-row anno-row-settings">',
        '    <label class="anno-color-label" for="anno-color">颜色',
        '      <input type="color" id="anno-color" value="' + DEFAULT_COLOR + '">',
        '    </label>',
        '    <label class="anno-opacity-label" for="anno-opacity">透明度',
        '      <span id="anno-opacity-val">35%</span>',
        '    </label>',
        '  </div>',
        '  <input type="range" id="anno-opacity" min="0" max="100" step="5" value="' + DEFAULT_OPACITY + '">',
        '  <div class="anno-row">',
        '    <button type="button" id="anno-draw" class="anno-btn anno-btn-primary">开始绘制</button>',
        '    <button type="button" id="anno-cancel" class="anno-btn" style="display:none;">取消</button>',
        '  </div>',
        '  <div class="anno-hint">依次单击顶点，双击闭合。左上角工具可拖动顶点或删除图形。</div>',
        '  <div class="anno-sep"></div>',
        '  <div class="anno-field">',
        '    <label for="anno-version">版本</label>',
        '    <select id="anno-version"></select>',
        '  </div>',
        '  <div class="anno-row">',
        '    <button type="button" id="anno-save" class="anno-btn anno-btn-primary">保存为新版本</button>',
        '    <button type="button" id="anno-delete" class="anno-btn anno-btn-danger" title="删除当前选中的版本">删除版本</button>',
        '  </div>',
        '  <div class="anno-row" style="margin-top:6px;">',
        '    <button type="button" id="anno-export" class="anno-btn" title="导出为 JSON 备份">导出标注</button>',
        '    <button type="button" id="anno-import" class="anno-btn" title="从 JSON 文件导入">导入标注</button>',
        '    <input type="file" id="anno-import-file" accept=".json,application/json" style="display:none;">',
        '  </div>',
        '  <div class="anno-status" id="anno-status"></div>',
        '  <div id="anno-flash"></div>',
        '  <div class="anno-footer">标注自动保存在本机浏览器；重新生成地图后会恢复，可用导出文件备份</div>',
        '</div>'
    ].join("");
    document.body.appendChild(panel);

    var nameInput = document.getElementById("anno-name");
    var colorInput = document.getElementById("anno-color");
    var opacityInput = document.getElementById("anno-opacity");
    var opacityVal = document.getElementById("anno-opacity-val");
    var drawBtn = document.getElementById("anno-draw");
    var cancelBtn = document.getElementById("anno-cancel");
    var saveBtn = document.getElementById("anno-save");
    var deleteBtn = document.getElementById("anno-delete");
    var versionSelect = document.getElementById("anno-version");
    var statusEl = document.getElementById("anno-status");
    var countEl = document.getElementById("anno-count");
    var flashEl = document.getElementById("anno-flash");
    var foldBtn = document.getElementById("anno-fold");
    var exportBtn = document.getElementById("anno-export");
    var importBtn = document.getElementById("anno-import");
    var importFile = document.getElementById("anno-import-file");

    colorInput.value = settings.color;
    opacityInput.value = String(settings.opacity);
    updateOpacityLabel();

    /* ---------------- 面板交互 ---------------- */
    function updateOpacityLabel() {
        opacityVal.textContent = opacityInput.value + "%";
    }

    function flash(msg) {
        flashEl.textContent = msg;
        flashEl.classList.add("show");
        if (flashTimer) clearTimeout(flashTimer);
        flashTimer = setTimeout(function () {
            flashEl.classList.remove("show");
        }, 2200);
    }

    function isDirty() {
        var version = findVersion(activeVersionId);
        var saved = version ? JSON.stringify(version.shapes) : "[]";
        return JSON.stringify(shapes) !== saved;
    }

    function persist() {
        var data = {
            versions: versions,
            activeVersionId: activeVersionId,
            nextVersionNo: nextVersionNo,
            working: { shapes: shapes },
            settings: {
                color: colorInput.value,
                opacity: parseInt(opacityInput.value, 10)
            }
        };
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (err) {
            console.warn("[区域标注] 无法写入本地存储", err);
            flash("保存失败：浏览器不允许本地存储");
        }
    }

    function persistWorking() {
        persist();
        refreshVersionSelect();
        updateStatus();
    }

    function updateStatus() {
        var version = findVersion(activeVersionId);
        var label;
        if (version) {
            label = "版本 v" + version.no + (isDirty() ? "（有未保存修改）" : "");
        } else {
            label = shapes.length ? "未保存" : "暂无图形";
        }
        statusEl.textContent = label + " · " + shapes.length + " 个图形";
        countEl.textContent = String(shapes.length);
    }

    function refreshVersionSelect() {
        versionSelect.innerHTML = "";
        var dirty = isDirty();

        if (!versions.length && !shapes.length) {
            var placeholder = new Option("暂无已保存版本", "");
            placeholder.disabled = true;
            versionSelect.add(placeholder);
            versionSelect.disabled = true;
            return;
        }
        versionSelect.disabled = false;

        var showWorking = dirty || !activeVersionId;
        if (showWorking) {
            versionSelect.add(new Option(dirty ? "当前编辑（未保存修改）" : "当前编辑", "__working"));
        }
        var sorted = versions.slice().sort(function (a, b) { return a.no - b.no; });
        for (var i = 0; i < sorted.length; i++) {
            var v = sorted[i];
            var text = "v" + v.no + (v.time ? " · " + v.time : "") + " · " + v.shapes.length + "个";
            versionSelect.add(new Option(text, v.id));
        }
        if (showWorking) {
            versionSelect.value = "__working";
        } else if (findVersion(activeVersionId)) {
            versionSelect.value = activeVersionId;
        } else if (sorted.length) {
            versionSelect.value = sorted[sorted.length - 1].id;
        }
    }

    /* ---------------- 图形渲染 ---------------- */
    function layerCoords(layer) {
        var latlngs = layer.getLatLngs ? layer.getLatLngs() : [];
        while (Array.isArray(latlngs) && latlngs.length && Array.isArray(latlngs[0])) {
            latlngs = latlngs[0];
        }
        var out = [];
        for (var i = 0; i < latlngs.length; i++) {
            out.push([round6(latlngs[i].lat), round6(latlngs[i].lng)]);
        }
        return out;
    }

    function buildPopup(shape) {
        var box = document.createElement("div");
        box.className = "anno-popup";

        var title = document.createElement("div");
        title.className = "anno-popup-title";
        title.style.color = shape.color;
        title.textContent = shape.name || "未命名标注";
        box.appendChild(title);

        var meta = document.createElement("div");
        meta.className = "anno-popup-meta";
        meta.textContent = "填充颜色 " + shape.color + " · 透明度 " + Math.round(shape.fillOpacity * 100) + "%";
        box.appendChild(meta);

        var actions = document.createElement("div");
        actions.className = "anno-popup-actions";

        var renameBtn = document.createElement("button");
        renameBtn.type = "button";
        renameBtn.className = "anno-btn";
        renameBtn.textContent = "重命名";
        renameBtn.addEventListener("click", function () {
            var newName = window.prompt("输入新的标注名称", shape.name || "");
            if (newName === null) return;
            newName = newName.trim();
            if (!newName) return;
            shape.name = newName;
            var layer = layersById[shape.id];
            if (layer) {
                if (layer.getTooltip()) layer.unbindTooltip();
                layer.bindTooltip(esc(shape.name), {
                    permanent: true,
                    direction: "center",
                    className: "anno-label",
                    opacity: 1
                });
                layer.setPopupContent(buildPopup(shape));
            }
            persistWorking();
            map.closePopup();
            flash("已重命名为「" + newName + "」");
        });

        var delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "anno-btn anno-btn-danger";
        delBtn.textContent = "删除";
        delBtn.addEventListener("click", function () {
            if (!window.confirm("确定删除「" + (shape.name || "未命名标注") + "」？")) return;
            removeShape(shape.id);
            map.closePopup();
            flash("已删除「" + (shape.name || "未命名标注") + "」");
        });

        actions.appendChild(renameBtn);
        actions.appendChild(delBtn);
        box.appendChild(actions);
        return box;
    }

    function renderShape(shape) {
        var layer = L.polygon(shape.coords, {
            color: shape.color,
            weight: 2,
            opacity: 0.9,
            fillColor: shape.color,
            fillOpacity: shape.fillOpacity
        });
        layer._annoId = shape.id;
        if (shape.name) {
            layer.bindTooltip(esc(shape.name), {
                permanent: true,
                direction: "center",
                className: "anno-label",
                opacity: 1
            });
        }
        layer.bindPopup(buildPopup(shape));
        featureGroup.addLayer(layer);
        layersById[shape.id] = layer;
    }

    function renderAll() {
        featureGroup.clearLayers();
        layersById = {};
        for (var i = 0; i < shapes.length; i++) {
            renderShape(shapes[i]);
        }
        updateStatus();
    }

    function removeShape(id) {
        var idx = findShapeIndex(id);
        if (idx >= 0) shapes.splice(idx, 1);
        var layer = layersById[id];
        if (layer) {
            featureGroup.removeLayer(layer);
            delete layersById[id];
        }
        persistWorking();
    }

    /* ---------------- 绘制 ---------------- */
    function applyDrawStyle() {
        if (!currentDrawer) return;
        var options = currentDrawer.options.shapeOptions;
        options.color = colorInput.value;
        options.fillColor = colorInput.value;
        options.fillOpacity = parseInt(opacityInput.value, 10) / 100;
    }

    function stopDraw() {
        if (currentDrawer) {
            var drawer = currentDrawer;
            currentDrawer = null;
            try { drawer.disable(); } catch (err) { /* ignore */ }
        }
        drawBtn.textContent = "开始绘制";
        drawBtn.classList.remove("anno-btn-active");
        cancelBtn.style.display = "none";
    }

    function startDraw() {
        stopDraw();
        currentDrawer = new L.Draw.Polygon(map, {
            allowIntersection: false,
            showArea: true,
            guideline: true,
            shapeOptions: {
                color: colorInput.value,
                weight: 2,
                opacity: 0.9,
                fillColor: colorInput.value,
                fillOpacity: parseInt(opacityInput.value, 10) / 100
            }
        });
        currentDrawer.enable();
        drawBtn.textContent = "绘制中…（双击结束）";
        drawBtn.classList.add("anno-btn-active");
        cancelBtn.style.display = "";
    }

    drawBtn.addEventListener("click", function () {
        if (currentDrawer) {
            stopDraw();
        } else {
            startDraw();
        }
    });

    cancelBtn.addEventListener("click", stopDraw);

    colorInput.addEventListener("input", function () {
        settings.color = colorInput.value;
        applyDrawStyle();
    });
    colorInput.addEventListener("change", function () {
        settings.color = colorInput.value;
        persist();
    });

    opacityInput.addEventListener("input", function () {
        settings.opacity = parseInt(opacityInput.value, 10);
        updateOpacityLabel();
        applyDrawStyle();
    });
    opacityInput.addEventListener("change", function () {
        settings.opacity = parseInt(opacityInput.value, 10);
        persist();
    });

    foldBtn.addEventListener("click", function () {
        var collapsed = panel.classList.toggle("anno-collapsed");
        foldBtn.textContent = collapsed ? "+" : "−";
        foldBtn.title = collapsed ? "展开" : "收起";
    });

    /* ---------------- 地图事件 ---------------- */
    map.on("draw:created", function (e) {
        var coords = layerCoords(e.layer);
        if (coords.length < 3) {
            stopDraw();
            return;
        }
        var name = nameInput.value.trim();
        if (!name) name = "标注 " + (shapes.length + 1);
        var shape = {
            id: "s" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
            name: name,
            color: colorInput.value,
            fillOpacity: parseInt(opacityInput.value, 10) / 100,
            coords: coords
        };
        shapes.push(shape);
        renderShape(shape);
        nameInput.value = "";
        stopDraw();
        persistWorking();
        flash("已添加「" + name + "」");
    });

    map.on("draw:drawstop", function () {
        if (currentDrawer) currentDrawer = null;
        drawBtn.textContent = "开始绘制";
        drawBtn.classList.remove("anno-btn-active");
        cancelBtn.style.display = "none";
    });

    map.on("draw:editstart", function () {
        stopDraw();
        drawBtn.disabled = true;
        drawBtn.title = "请先保存或取消编辑";
    });

    map.on("draw:editstop", function () {
        drawBtn.disabled = false;
        drawBtn.title = "";
    });

    map.on("draw:edited", function (e) {
        var changed = 0;
        e.layers.eachLayer(function (layer) {
            var shape = findShape(layer._annoId);
            if (!shape) return;
            var coords = layerCoords(layer);
            if (coords.length >= 3) {
                shape.coords = coords;
                changed++;
            }
            if (layer.getTooltip()) {
                layer.getTooltip().setLatLng(layer.getBounds().getCenter());
            }
        });
        if (changed) {
            persistWorking();
            flash("已更新图形");
        }
    });

    map.on("draw:deleted", function (e) {
        var removed = 0;
        e.layers.eachLayer(function (layer) {
            var idx = findShapeIndex(layer._annoId);
            if (idx >= 0) {
                shapes.splice(idx, 1);
                removed++;
            }
            delete layersById[layer._annoId];
        });
        if (removed) {
            persistWorking();
            flash("已删除 " + removed + " 个图形");
        }
    });

    /* ---------------- 版本操作 ---------------- */
    saveBtn.addEventListener("click", function () {
        if (!shapes.length && !window.confirm("当前没有图形，仍要保存一个空版本吗？")) return;
        var version = {
            id: "v" + Date.now(),
            no: nextVersionNo++,
            time: formatTime(new Date()),
            shapes: clone(shapes)
        };
        versions.push(version);
        activeVersionId = version.id;
        persist();
        refreshVersionSelect();
        updateStatus();
        flash("已保存为 v" + version.no);
    });

    deleteBtn.addEventListener("click", function () {
        var version = findVersion(activeVersionId);
        if (!version) {
            flash("请先在版本列表中选择要删除的版本");
            return;
        }
        if (!window.confirm("确定删除版本 v" + version.no + "？地图上的图形仍保留在当前编辑中。")) return;
        versions = versions.filter(function (v) { return v.id !== version.id; });
        activeVersionId = null;
        persist();
        refreshVersionSelect();
        updateStatus();
        flash("已删除版本 v" + version.no);
    });

    versionSelect.addEventListener("change", function () {
        var value = versionSelect.value;
        if (value === "__working") return;
        var version = findVersion(value);
        if (!version) {
            refreshVersionSelect();
            return;
        }
        if (isDirty() && !window.confirm("当前有未保存的修改，切换到该版本会丢弃这些修改，是否继续？")) {
            refreshVersionSelect();
            return;
        }
        shapes = clone(version.shapes);
        activeVersionId = version.id;
        persist();
        renderAll();
        refreshVersionSelect();
        flash("已载入版本 v" + version.no);
    });

    /* ---------------- 导出 / 导入标注 ---------------- */
    function reloadSettingsUi() {
        colorInput.value = settings.color;
        opacityInput.value = String(settings.opacity);
        updateOpacityLabel();
    }

    function timestampText() {
        var d = new Date();
        function pad(n) { return n < 10 ? "0" + n : String(n); }
        return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) +
            "_" + pad(d.getHours()) + pad(d.getMinutes());
    }

    exportBtn.addEventListener("click", function () {
        var data = {
            app: "hongqiao-annotations",
            exportTime: formatTime(new Date()),
            versions: versions,
            activeVersionId: activeVersionId,
            nextVersionNo: nextVersionNo,
            working: { shapes: shapes },
            settings: { color: colorInput.value, opacity: parseInt(opacityInput.value, 10) }
        };
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "hq_annotations_" + timestampText() + ".json";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        flash("已导出标注文件");
    });

    importBtn.addEventListener("click", function () {
        importFile.click();
    });

    importFile.addEventListener("change", function () {
        var file = importFile.files && importFile.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function () {
            try {
                var data = JSON.parse(String(reader.result));
                if (!data || typeof data !== "object") throw new Error("文件格式不正确");
                var hasVersions = Array.isArray(data.versions);
                var hasWorking = data.working && Array.isArray(data.working.shapes);
                if (!hasVersions && !hasWorking) throw new Error("文件中没有可导入的标注");
                if (shapes.length && !window.confirm("导入会替换当前标注，是否继续？")) return;
                applyStore(data);
                reloadSettingsUi();
                persist();
                renderAll();
                refreshVersionSelect();
                updateStatus();
                flash("已导入标注");
            } catch (err) {
                window.alert("导入失败：" + err.message);
            } finally {
                importFile.value = "";
            }
        };
        reader.onerror = function () {
            window.alert("读取文件失败");
            importFile.value = "";
        };
        reader.readAsText(file, "utf-8");
    });

    /* ---------------- 编辑 / 删除工具 ---------------- */
    if (L.drawLocal && L.drawLocal.edit) {
        L.drawLocal.edit.toolbar.buttons.edit = "编辑图形（拖动顶点）";
        L.drawLocal.edit.toolbar.buttons.editDisabled = "没有可编辑的图形";
        L.drawLocal.edit.toolbar.buttons.remove = "删除图形";
        L.drawLocal.edit.toolbar.buttons.removeDisabled = "没有可删除的图形";
        L.drawLocal.edit.toolbar.actions.save.text = "保存修改";
        L.drawLocal.edit.toolbar.actions.save.title = "保存修改";
        L.drawLocal.edit.toolbar.actions.cancel.text = "取消";
        L.drawLocal.edit.toolbar.actions.cancel.title = "取消编辑";
        L.drawLocal.edit.toolbar.actions.clearAll.text = "全部删除";
        L.drawLocal.edit.toolbar.actions.clearAll.title = "删除所有图形";
        L.drawLocal.edit.handlers.edit.tooltip.text = "拖动顶点调整图形";
        L.drawLocal.edit.handlers.edit.tooltip.subtext = "完成后点击“保存修改”";
        L.drawLocal.edit.handlers.remove.tooltip.text = "点击图形将其删除";
    }

    map.addControl(new L.Control.Draw({
        position: "topleft",
        draw: false,
        edit: {
            featureGroup: featureGroup,
            remove: true
        }
    }));

    /* ---------------- 初始化 ---------------- */
    renderAll();
    refreshVersionSelect();
    updateStatus();
})();
