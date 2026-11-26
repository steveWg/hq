import requests
from shapely.geometry import Polygon, mapping
import geojson

query = """
[out:json];
(
  way["aeroway"="aerodrome"]["name"="上海虹桥国际机场"];
);
out body;
>;
out skel qt;
"""

response = requests.get("http://overpass-api.de/api/interpreter", params={"data": query})
data = response.json()
with open("hongqiao_airport.json", "w") as f:
    geojson.dump(data, f)

boundaries = []
# 转换为GeoJSON（增加字段检查）
for element in data["elements"]:
    if element["type"] == "way" and "nodes" in element:
        # 通过节点ID获取坐标（需预处理所有节点）
        coords = []
        for node_id in element["nodes"]:
            # 从nodes元素中查找坐标（需先建立node_id到坐标的映射）
            node = next((n for n in data["elements"] if n["type"] == "node" and n["id"] == node_id), None)
            if node:
                coords.append((node["lon"], node["lat"]))  # 注意顺序：经度在前
        
        if coords:
            boundaries.append(Polygon(coords))  # 创建Shapely多边形[[8]]

features = []
for polygon in boundaries:
    feature = geojson.Feature(
        geometry=mapping(polygon),  # 使用Shapely的mapping转换[[2]]
        properties={"name": "虹桥机场边界"}
    )
    features.append(feature)

geojson_data = geojson.FeatureCollection(features)

# 保存为GeoJSON文件
with open("hongqiao_airport.geojson", "w") as f:
    geojson.dump(geojson_data, f)

# 验证有效性（使用Shapely检查多边形闭合性）
for polygon in boundaries:
    print(f"多边形是否闭合：{polygon.is_valid}")  # 输出True表示有效[[8]]

