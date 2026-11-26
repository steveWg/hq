# 虹桥机场点位标记程序

基于 Python + Folium / Leaflet 的虹桥机场航班轨迹可视化工具。生成的地图可在浏览器中查看，并支持在高德街道图 / 卫星影像底图上手工标注不规则区域。

## 功能

- WGS-84 → GCJ-02 坐标转换
- 起飞 / 落地航线分别着色
- 按轨迹插值生成 150m / 450m（起飞）、60m / 300m（落地）关键高度点位
- 虹桥机场边界、周边 6km 圆圈
- 高德街道图 / 卫星影像底图切换
- **区域标注**：在地图上逐点绘制不规则多边形，可设置名称、颜色、填充透明度
- **标注版本**：保存 v1 / v2 / … 快照，可切换恢复；数据自动保存在浏览器 `localStorage` 中，刷新或重新生成地图后自动恢复

## 目录结构

```text
.
├─ img_folium.py               # 主程序：读取轨迹并生成地图
├─ geo_transformer.py          # WGS-84 / GCJ-02 / BD-09 坐标转换
├─ getline.py                  # 从 航线/*.xlsx 生成 line.json
├─ getdata.py                  # 从 hotpoints.csv 生成热力图数据
├─ get_geocoders.py            # 从 OSM Overpass 获取机场边界
├─ map_annotations.js          # 区域标注 / 版本快照前端逻辑
├─ map_annotations.css         # 区域标注面板与图形样式
├─ hongqiao_airport.geojson    # 机场边界（WGS-84）
├─ hongqiao_gcj02.geojson      # 机场边界（GCJ-02，生成）
├─ hongqiao_airport.json       # OSM 原始边界数据
├─ hongqiao_airport_map.html   # 生成的地图成果
├─ annotations.json            # 标注数据（生成时内置到地图）
├─ 航线/                       # 起飞 / 落地航班轨迹 Excel
│  ├─ 虹桥起飞/
│  └─ 虹桥落地/
├─ hotpoints.csv               # 鸟击点位数据
├─ row.xlsx                    # 原始数据表
├─ line.json                   # 轨迹线数据（由 getline.py 生成）
└─ requirements.txt
```

> 雷达原始数据（`雷达/`）、鸟击分析文档（`*.docx`）、调试图片、独立演示页 `amap.html` 等与地图生成无关的文件未纳入仓库。

## 运行

```bash
pip install -r requirements.txt
python img_folium.py
```

运行后会重新生成 `hongqiao_airport_map.html`，用浏览器打开即可。地图底图和 Leaflet 资源通过 CDN 加载，需要联网。

轨迹 Excel 需要包含以下列：

```text
航班号、经度、纬度、高度、时间
```

## 区域标注使用

1. 右上角「区域标注」面板填写名称，选择颜色和透明度；
2. 点击「开始绘制」，依次单击多边形顶点，双击闭合；
3. 点击图形可重命名或删除；
4. 左上角铅笔工具可拖动顶点修改形状，垃圾桶工具可删除；
5. 点击「保存为新版本」生成 v1、v2…；下拉框可切换历史版本；
6. 点击「导出标注」可下载 JSON 备份，点击「导入标注」可恢复备份。

标注数据保存在当前浏览器的 `localStorage` 中，与底图无关。切换浏览器或清除浏览器数据会导致标注丢失，重要标注建议定期导出备份。

`annotations.json` 是标注快照：运行 `python img_folium.py` 时会自动把它内置进生成的 HTML，因此换电脑或换浏览器打开地图也能看到这些标注。如果当前浏览器里已经有更新的本地标注，则优先显示本地数据，不会覆盖。
