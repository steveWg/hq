import folium
import geojson
import pandas as pd
import geo_transformer
import os
import math
import json
import warnings

# https://cdn.bootcss.com/bootstrap/3.0.0/css/bootstrap-glyphicons.css
warnings.filterwarnings("ignore", category=UserWarning, message="Workbook contains no default style, apply openpyxl's default")

# 创建地图中心点（虹桥机场大致坐标）
shanghai_hongqiao_wgs84 = [121.33447114043761, 31.198254707588664]
shanghai_hongqiao_gcj02 = geo_transformer.wgs84_to_gcj02(shanghai_hongqiao_wgs84[0], shanghai_hongqiao_wgs84[1])

# ============ 关键高度与配色 ============
# 起飞关注 150m / 450m，落地关注 60m / 300m
KEY_HEIGHTS = {
    "起飞": (150, 450),
    "落地": (60, 300),
}
# 4 种点位颜色：起飞 150/450，落地 60/300
POINT_COLORS = {
    ("起飞", 150): "#00A651",   # 绿色
    ("起飞", 450): "#FF7A00",   # 橙色
    ("落地", 60): "#8E24AA",    # 紫色
    ("落地", 300): "#00ACC1",   # 青色
}
# 航线颜色：起飞 / 落地
ROUTE_COLORS = {
    "起飞": "#1565C0",  # 蓝色
    "落地": "#C62828",  # 红色
}
PHASE_FOLDERS = {
    "起飞": os.path.join("航线", "虹桥起飞"),
    "落地": os.path.join("航线", "虹桥落地"),
}
# 航线绘制 / 高度插值只关注虹桥周边范围（公里），避免远端混杂数据把线拉成“色带”
ROUTE_CLIP_KM = 50

# ============ 地图交互资源（区域标注） ============
LEAFLET_DRAW_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css"
LEAFLET_DRAW_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js"
ANNOTATION_CSS_FILE = "map_annotations.css"
ANNOTATION_JS_FILE = "map_annotations.js"
ANNOTATIONS_FILE = "annotations.json"


def transform_coordinates(geometry):
    """递归转换GeoJSON几何对象的坐标"""
    if isinstance(geometry, geojson.Point):
        lon, lat = geometry.coordinates
        x, y = geo_transformer.wgs84_to_gcj02(lon, lat)
        return geojson.Point((x, y))

    elif isinstance(geometry, geojson.Polygon):
        new_coords = []
        for ring in geometry.coordinates:
            transformed_ring = []
            for lon, lat in ring:
                x, y = geo_transformer.wgs84_to_gcj02(lon, lat)
                transformed_ring.append((x, y))
            new_coords.append(transformed_ring)
        return geojson.Polygon(new_coords)

    else:
        return geometry  # 不支持的类型保持原样


def haversine_km(lon1, lat1, lon2, lat2):
    """计算两点间球面距离（公里）"""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def clip_route_segments(coords, center_lon, center_lat, radius_km):
    """把轨迹裁剪为虹桥周边 radius_km 内的连续线段，避免远端数据干扰"""
    segments = []
    current = []
    for lon, lat in coords:
        if haversine_km(lon, lat, center_lon, center_lat) <= radius_km:
            current.append([lat, lon])
        else:
            if len(current) >= 2:
                segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)
    return segments


def read_route_file(file_path, phase):
    """读取单个航班轨迹文件并做清洗"""
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"[跳过] 读取轨迹失败 {file_path}: {e}")
        return None

    required = ["经度", "纬度", "高度", "时间"]
    if not all(col in df.columns for col in required):
        print(f"[跳过] 轨迹文件列不完整 {file_path}")
        return None

    flight = str(df["航班号"].iloc[0]).strip().upper() if "航班号" in df.columns else ""
    keep_cols = required + (["航班号"] if "航班号" in df.columns else [])
    df = df[keep_cols].copy()
    for col in ["经度", "纬度", "高度"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["_dt"] = pd.to_datetime(df["时间"], errors="coerce")
    df = df.dropna(subset=["经度", "纬度", "高度"])
    # 过滤明显异常的坐标
    df = df[(df["经度"].between(70, 140)) & (df["纬度"].between(3, 54))]
    if len(df) < 2:
        return None

    # 按时间排序（无有效时间时保持原顺序）
    if df["_dt"].notna().any():
        df = df.sort_values("_dt", kind="mergesort").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    valid_dt = df["_dt"].dropna()
    dates = sorted({d.date() for d in valid_dt})
    return {
        "phase": phase,
        "flight": flight,
        "df": df,
        "dates": dates,
        "dt": valid_dt.sort_values().reset_index(drop=True),
        "file": os.path.basename(file_path),
    }


def load_routes():
    """加载起飞、落地文件夹下的全部轨迹"""
    routes = []
    for phase, folder in PHASE_FOLDERS.items():
        if not os.path.isdir(folder):
            print(f"[警告] 航线文件夹不存在: {folder}")
            continue
        for filename in sorted(os.listdir(folder)):
            if not filename.lower().endswith((".xls", ".xlsx")):
                continue
            file_path = os.path.join(folder, filename)
            route = read_route_file(file_path, phase)
            if route and route["flight"]:
                routes.append(route)
            elif route:
                print(f"[跳过] 轨迹缺少航班号 {filename}")
    return routes


def interpolate_at_height(df, target_height, phase):
    """
    在轨迹中寻找目标高度对应的位置。
    起飞取爬升段、落地取下降段中距离虹桥最近的穿越点，并用线性插值计算经纬度。
    """
    lons = df["经度"].to_numpy(dtype=float)
    lats = df["纬度"].to_numpy(dtype=float)
    alts = df["高度"].to_numpy(dtype=float)
    times = df["_dt"].to_numpy()

    best = None
    for i in range(len(df) - 1):
        h1, h2 = alts[i], alts[i + 1]
        if not (math.isfinite(h1) and math.isfinite(h2)) or h1 == h2:
            continue
        # 起飞只看爬升段，落地只看下降段，避免滑行/复飞造成误判
        if phase == "起飞" and h2 <= h1:
            continue
        if phase == "落地" and h2 >= h1:
            continue
        # 目标高度不在本段区间内
        if (h1 - target_height) * (h2 - target_height) > 0:
            continue

        t = (target_height - h1) / (h2 - h1)
        t = min(1.0, max(0.0, t))
        lon = lons[i] + t * (lons[i + 1] - lons[i])
        lat = lats[i] + t * (lats[i + 1] - lats[i])
        dist = haversine_km(lon, lat, shanghai_hongqiao_wgs84[0], shanghai_hongqiao_wgs84[1])
        # 只接受虹桥周边范围内的穿越点，过滤远端机场/混杂数据的升降段
        if dist > ROUTE_CLIP_KM:
            continue

        # 同高度可能有多次穿越，取距离虹桥最近的一次
        if best is None or dist < best["dist"]:
            best = {
                "lon": lon,
                "lat": lat,
                "dist": dist,
                "interpolated": True,
                "track_index": i,
                "track_time": times[i] if i < len(times) else None,
            }

    if best is not None:
        return best

    # 没有找到对应高度的轨迹点（轨迹被截断或该高度缺失），退化为最近高度采样点
    idx = int(pd.Series(alts).sub(target_height).abs().idxmin())
    lon, lat = lons[idx], lats[idx]
    return {
        "lon": lon,
        "lat": lat,
        "dist": haversine_km(lon, lat, shanghai_hongqiao_wgs84[0], shanghai_hongqiao_wgs84[1]),
        "interpolated": False,
        "track_index": idx,
        "track_time": times[idx] if idx < len(times) else None,
    }


def build_popup(phase, target_height, flight, track_date_text, interpolated, lon, lat):
    """生成点位弹窗 HTML"""
    interpolated_text = "是" if interpolated else "否（使用最近高度采样点）"
    return folium.Popup(
        f"""
        <div style="font-family:Microsoft YaHei,Arial; font-size:13px; min-width:200px;">
            <div style="font-size:15px; font-weight:bold; color:{POINT_COLORS[(phase, target_height)]}; margin-bottom:6px;">
                {flight} · {phase} {target_height}m 高度点
            </div>
            <div>航班号：<b>{flight}</b></div>
            <div>起降类型：{phase}</div>
            <div>关键高度：{target_height} m</div>
            <div>轨迹日期：{track_date_text}</div>
            <div>插值计算：{interpolated_text}</div>
            <div>坐标：{lon:.6f}, {lat:.6f}</div>
        </div>
        """,
        max_width=300,
    )


def add_legend(m, group_counts):
    """添加图例"""
    route_items = "".join(
        f"<div><span style='display:inline-block;width:20px;height:4px;background:{ROUTE_COLORS[p]};"
        f"vertical-align:middle;margin-right:8px;'></span>{p}航线</div>"
        for p in ("起飞", "落地")
    )
    point_items = "".join(
        f"<div><span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
        f"background:{POINT_COLORS[(p, h)]};border:1px solid #fff;box-shadow:0 0 2px rgba(0,0,0,.5);"
        f"vertical-align:middle;margin-right:8px;'></span>{p} {h}m"
        f"<span style='color:#888;'>（{group_counts.get((p, h), 0)}）</span></div>"
        for p in ("起飞", "落地")
        for h in KEY_HEIGHTS[p]
    )
    legend_html = f"""
    <div style="position: fixed; left: 24px; bottom: 24px; z-index: 9999;
                background: rgba(255,255,255,0.94); padding: 10px 14px; border-radius: 8px;
                box-shadow: 0 1px 8px rgba(0,0,0,0.35);
                font-family: Microsoft YaHei, Arial; font-size: 13px; line-height: 1.7; color:#333;">
        <div style="font-weight:bold; margin-bottom:4px;">图例</div>
        {route_items}
        <div style="height:1px;background:#ddd;margin:5px 0;"></div>
        {point_items}
        <div style="color:#777;font-size:11px;margin-top:4px;">点位为轨迹在关键高度的插值位置</div>
        <div style="color:#777;font-size:11px;">航线仅显示虹桥周边 {ROUTE_CLIP_KM}km</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


def inject_annotation_tools(html_path, map_name):
    """把区域标注面板和版本化标注脚本内联进生成的 HTML（生成文件可单独分发）。"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    if LEAFLET_DRAW_JS not in content:
        head_assets = (
            f'    <link rel="stylesheet" href="{LEAFLET_DRAW_CSS}"/>\n'
            f'    <script src="{LEAFLET_DRAW_JS}"></script>\n'
        )
        content = content.replace("</head>", head_assets + "</head>", 1)

    with open(ANNOTATION_CSS_FILE, "r", encoding="utf-8") as f:
        annotation_css = f.read()
    with open(ANNOTATION_JS_FILE, "r", encoding="utf-8") as f:
        annotation_js = f.read()

    annotations_js = ""
    if os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            annotations_data = json.load(f)
        payload = json.dumps(annotations_data, ensure_ascii=False, separators=(",", ":"))
        payload = payload.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        annotations_js = "window.__HQ_ANNOTATIONS__ = " + payload + ";\n"
        shape_count = len(annotations_data.get("working", {}).get("shapes", []))
        print(f"[标注] 已内置 {ANNOTATIONS_FILE} 中的 {shape_count} 个标注区域")

    if "window.__hqMap" not in content:
        injection = (
            "\n<style>\n" + annotation_css + "\n</style>\n"
            "<script>\nwindow.__hqMap = " + map_name + ";\n" + annotations_js + annotation_js + "\n</script>\n"
        )
        content = content.replace("</html>", injection + "</html>", 1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[标注] 已加入不规则区域绘制（颜色 / 透明度 / 名称 / 版本快照）")


# ============ 加载机场边界 ============
with open("hongqiao_airport.geojson", "r", encoding="utf-8") as f:
    geojson_data = geojson.load(f)

transformed_features = []
for feature in geojson_data.features:
    new_geometry = transform_coordinates(feature.geometry)
    transformed_features.append(geojson.Feature(geometry=new_geometry, properties=feature.properties))

transformed_geojson = geojson.FeatureCollection(transformed_features)

with open("hongqiao_gcj02.geojson", "w", encoding="utf-8") as f:
    geojson.dump(transformed_geojson, f)

# ============ 初始化地图 ============
m = folium.Map(
    location=shanghai_hongqiao_gcj02[::-1],
    zoom_start=13,
    tiles=None,
    attr='高德地图'
)

# 高德街道图（默认底图）
folium.TileLayer(
    tiles='http://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    name='高德地图',
    attr='高德地图'
).add_to(m)

# 卫星图层（可切换）
folium.TileLayer(
    tiles='http://webst02.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
    name='卫星影像',
    attr='高德卫星图',
    show=False
).add_to(m)

# 6公里圆形区域
folium.Circle(
    location=shanghai_hongqiao_gcj02[::-1],
    radius=6000,
    color="purple",
    weight=3,
    fill=True,
    fill_opacity=0.15,
    fill_color="purple",
    opacity=1,
    **{"overlay": True, "smooth_factor": 0}
).add_to(m)

# 虹桥机场边界
folium.GeoJson(
    transformed_geojson,
    name="虹桥机场边界",
    style_function=lambda x: {"color": "#FF0000", "weight": 2, "fillOpacity": 0.2}
).add_to(m)

# ============ 加载航线（起飞/落地分别着色） ============
routes = load_routes()
route_groups = {
    "起飞": folium.FeatureGroup(name="起飞航线", show=True),
    "落地": folium.FeatureGroup(name="落地航线", show=True),
}

for route in routes:
    gcj_coords = []
    for lon, lat in zip(route["df"]["经度"], route["df"]["纬度"]):
        x, y = geo_transformer.wgs84_to_gcj02(lon, lat)
        gcj_coords.append([x, y])
    date_text = "、".join(str(d) for d in route["dates"][:2]) or "日期未知"
    segments = clip_route_segments(
        gcj_coords,
        shanghai_hongqiao_gcj02[0],
        shanghai_hongqiao_gcj02[1],
        ROUTE_CLIP_KM,
    )
    for segment in segments:
        folium.PolyLine(
            segment,
            color=ROUTE_COLORS[route["phase"]],
            weight=2,
            opacity=0.45,
            tooltip=f"{route['phase']} {route['flight']}　{date_text}",
        ).add_to(route_groups[route["phase"]])

for group in route_groups.values():
    group.add_to(m)

print(f"[航线] 起飞 {len([r for r in routes if r['phase'] == '起飞'])} 条，"
      f"落地 {len([r for r in routes if r['phase'] == '落地'])} 条")

# ============ 按轨迹生成关键高度点位 ============
point_groups = {
    key: folium.FeatureGroup(
        name=f"{key[0]} {key[1]}m",
        show=True,
    )
    for key in POINT_COLORS
}
fallback_count = 0
counts = {}

for route in routes:
    phase = route["phase"]
    track_dates = "、".join(str(d) for d in route["dates"][:2]) or "未知"
    for target_height in KEY_HEIGHTS[phase]:
        hit = interpolate_at_height(route["df"], target_height, phase)
        x, y = geo_transformer.wgs84_to_gcj02(hit["lon"], hit["lat"])
        popup = build_popup(phase, target_height, route["flight"], track_dates,
                            hit["interpolated"], hit["lon"], hit["lat"])
        folium.CircleMarker(
            location=[y, x],
            radius=8,
            color="#ffffff",
            weight=1.5,
            fill=True,
            fill_color=POINT_COLORS[(phase, target_height)],
            fill_opacity=0.9,
            tooltip=folium.Tooltip(
                f"<b>航班 {route['flight']}</b><br>{phase} {target_height}m",
                sticky=True,
            ),
            popup=popup,
            rise_on_hover=True,
        ).add_to(point_groups[(phase, target_height)])
        counts[(phase, target_height)] = counts.get((phase, target_height), 0) + 1
        if not hit["interpolated"]:
            fallback_count += 1

# 更新图层名称，显示点位数量
for key, group in point_groups.items():
    group.layer_name = f"{key[0]} {key[1]}m（{counts.get(key, 0)}）"
    group.add_to(m)

print("[点位] " + "，".join(f"{k[0]} {k[1]}m: {counts.get(k, 0)} 个" for k in POINT_COLORS))
if fallback_count:
    print(f"[提示] 其中 {fallback_count} 个点位未找到精确高度，使用了最近高度采样点")

add_legend(m, counts)

# 图层控制（放右下角，避免遮挡右上角的区域标注面板）
folium.LayerControl(collapsed=True, position="bottomright").add_to(m)
m.save("hongqiao_airport_map.html")

# 注入不规则区域标注（颜色 / 透明度 / 名称 / 浏览器内版本快照）
inject_annotation_tools("hongqiao_airport_map.html", m.get_name())

# 替换 bootstrap 图标 CDN
with open("hongqiao_airport_map.html", "r", encoding="utf-8") as f:
    content = f.read()
content = content.replace(
    'https://netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap-glyphicons.css',
    'https://cdn.bootcss.com/bootstrap/3.0.0/css/bootstrap-glyphicons.css'
)
with open("hongqiao_airport_map.html", "w", encoding="utf-8") as f:
    f.write(content)

print("已生成 hongqiao_airport_map.html")
