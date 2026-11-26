import os
import glob
import pandas as pd
import json

def get_routes_from_folder(folder_path):
    routes = []
    xlsx_files = glob.glob(os.path.join(folder_path, "*.xlsx"))
    for file in xlsx_files:
        df = pd.read_excel(file)
        # Assume columns are named '经度' and '纬度'
        if '经度' in df.columns and '纬度' in df.columns:
            route = df[['经度', '纬度']].values.tolist()
            routes.append(route)
    return routes

if __name__ == "__main__":
    folder = "航线"
    routes = get_routes_from_folder(folder)
    # Save the routes to a file named "line"
    with open("line.json", "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=2)
