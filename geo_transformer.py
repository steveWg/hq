import math

#定义常数
x_PI = math.pi / 180
PI = math.pi
# WGS-84 标准参数
aa = 6378137.0  # 长半轴 
f = 1 / 298.257223563  # 扁率 
ee = 2 * f - f ** 2  # 第一偏心率平方

"""
  *百度坐标系(BD-09) 与火星坐标系(GCJ-02)的转换
  *即百度转谷歌(国内)、高德、腾讯
  * @ parambd_lon
  * @ parambd_lat
  * @ returns{*[]}
"""
def bd09_to_gcj02(bd_lon, bd_lat):
    x = bd_lon - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_PI)
    gg_lng = z * math.cos(theta)
    gg_lat = z * math.sin(theta)
    return [gg_lng, gg_lat]

# print(bd09togcj02(120.199672, 30.331184))

"""
  * 火星坐标系 (GCJ-02) 与百度坐标系 (BD-09) 的转换
  * 即谷歌、高德 转 百度
  * @param lng
  * @param lat
  * @returns {*[]}
"""

def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * x_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * x_PI)
    bd_lng = z * math.cos(theta) + 0.0065
    bd_lat = z * math.sin(theta) + 0.006
    return [bd_lng, bd_lat]

# print(gcj02tobd09(120.19312059585862, 30.325466905933578))

"""
  * 判断是否在国内，不在国内则不做偏移
  * @param lng
  * @param lat
  * @returns {boolean}
"""


def out_of_china(lng, lat):
    # 纬度3.86~53.55,经度73.66~135.05
    if 73.66 < lng < 135.05 and 3.86 < lat < 53.55:
        return False


"""
  * 经纬度偏移转换
"""


def transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 * math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 * math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 * math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret

"""
  * GCJ02 转换为 WGS84
  * @param lng
  * @param lat
  * @returns {*[]}
"""


def gcj02_to_wgs84(lng, lat):
    # 判断是否为国外坐标
    if out_of_china(lng, lat):
        return [lng, lat]
    else:
        dlat = transform_lat(lng - 105.0, lat - 35.0)
        dlng = transform_lng(lng - 105.0, lat - 35.0)
        radlat = lat / 180.0 * PI
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((aa * (1 - ee)) / (magic * sqrtmagic) * PI)
        dlng = (dlng * 180.0) / (aa / sqrtmagic * math.cos(radlat) * PI)
        mglat = lat + dlat
        mglng = lng + dlng
        return [lng * 2 - mglng, lat * 2 - mglat]

"""
  * WGS84转GCj02
  * @param lng
  *  @param lat
  *  @returns {*[]}
"""


def wgs84_to_gcj02(lng, lat):
    if out_of_china(lng, lat):
        return [lng, lat]
    else:
        dlat = transform_lat(lng - 105.0, lat - 35.0)
        dlng = transform_lng(lng - 105.0, lat - 35.0)
        radlat = lat / 180.0 * PI
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((aa * (1 - ee)) / (magic * sqrtmagic) * PI)
        dlng = (dlng * 180.0) / (aa / sqrtmagic * math.cos(radlat) * PI)
        mglat = lat + dlat
        mglng = lng + dlng
        return [mglng, mglat]

"""
  *WGS84 百度坐标系 (BD-09) 的转换
  *@param lng
  *@param lat
  *@returns {*[]}
"""


def wgs84_to_bd09(lng, lat):
    point = wgs84_to_gcj02(lng, lat)
    bdpoint = gcj02_to_bd09(point[0], point[1])
    return [bdpoint[0], bdpoint[1], point[0], point[1]]

"""
  * 百度坐标系 (BD-09) WGS84 的转换
  * @param lng
  * @param lat
  * @returns {*[]}
"""

def bd09_to_wgs84(lng, lat):
    point = bd09_to_gcj02(lng, lat)
    wgs84point = gcj02_to_wgs84(point[0], point[1])
    return [wgs84point[0], wgs84point[1]]

if __name__ == '__main__':
    print(wgs84_to_gcj02(121.331618, 31.177092))
    print(gcj02_to_wgs84(121.339036,31.196332))	
    