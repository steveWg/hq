import pandas as pd
points = pd.read_csv("hotpoints.csv", encoding="gbk")
# coordinates = points[["经度", "纬度", "鸟种","日期","高度"]].values.tolist()
heatmap_data = points.apply(lambda row: {
    'lng': float(row['经度']),
    'lat': float(row['纬度']),
    'count': 1
}, axis=1).tolist()

print("const heatmapData = [")
for item in heatmap_data:
    print(f"  {{ lng: {item['lng']}, lat: {item['lat']}, count: {item['count']} }},")
print("];")