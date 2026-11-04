# -*- coding: utf-8 -*-
"""讀取內政部預售屋實價登錄 ZIP，建立資料來源清單。

輸入：data/raw/ 中的官方 ZIP。
輸出：data/source_inventory.csv，記錄來源、日期範圍及檔案指紋。
本程式只確認原始資料可讀，不進行成交紀錄去重與統計。
"""

from pathlib import Path
from datetime import datetime
import csv
import hashlib
import io
import zipfile

import pandas as pd


# 從程式所在的 src 資料夾往上一層，找到整個專案。
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "source_inventory.csv"
SOURCE = "https://plvr.land.moi.gov.tw/DownloadOpenData"

# 本專題只讀取臺北市和新北市的預售屋交易主檔。
CITY_FILES = {
    "a_lvr_land_b.csv": "臺北市",
    "f_lvr_land_b.csv": "新北市",
}


def zip_hash(zip_path):
    """計算 ZIP 的 SHA-256，用來確認來源檔案是否相同。"""
    # 分段讀取大型 ZIP，避免一次將整個壓縮檔載入記憶體。
    digest = hashlib.sha256()
    with open(zip_path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(archive, csv_name):
    """嘗試常見中文編碼讀取 CSV，必要時處理已確認的欄位錯誤。"""
    # ZIP 內的 CSV 可能使用不同中文字元編碼，依序嘗試。
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            with archive.open(csv_name) as file:
                data = pd.read_csv(
                    file, encoding=encoding, dtype=str, keep_default_na=False
                )
            return data, encoding, 0, ""

        except UnicodeDecodeError:
            # 編碼不符合時，再嘗試下一種常見的中文編碼。
            continue

        except pd.errors.ParserError:
            # pandas 無法正確切分欄位時，以標準 csv.reader 逐列檢查。
            # 讀取異常不等於紀錄無效，不能直接跳過該筆資料。
            with archive.open(csv_name) as file:
                text = io.TextIOWrapper(file, encoding=encoding, newline="")
                csv.field_size_limit(10_000_000)
                reader = csv.reader(text, strict=True)
                header = next(reader)
                rows = []
                fixed = 0

                for line_number, row in enumerate(reader, start=2):
                    if not row:  # 與 pandas 預設行為一致：忽略完全空白行。
                        continue

                    # 特定官方批次中，一筆「棟及號」含未加引號的逗號。
                    # 下列多項條件必須同時符合，才會合併被拆開的欄位。
                    # 這樣可以避免將其他來源或不同版本的資料錯誤地合併。
                    # 已核實：臺北市 2026Q1 的棟及號含未加引號的英文逗號。
                    # 僅在行號、欄名及欄位內容全部相符時，合併被拆開的兩欄。
                    known_error = (
                        csv_name.replace("\\", "/").split("/")[-1].lower() == "a_lvr_land_b.csv"
                        and line_number == 883
                        and len(row) == 32
                        and len(header) == 31
                        and header[27:31] == ["編號", "建案名稱", "棟及號", "解約情形"]
                        and row[27:32] == [
                            "RPPNMLQLJHLGFAA37CB", "碩樺拾景", "A棟A3-1", "2F號", ""
                        ]
                    )
                    if known_error:
                        row[29:31] = ["A棟A3-1,2F號"]
                        fixed += 1

                    # 其他異常不能擅自跳過或修復，以免影響成交資料。
                    if len(row) != len(header):
                        raise RuntimeError(
                            f"{csv_name} 第 {line_number} 筆有 {len(row)} 欄，"
                            f"應為 {len(header)} 欄，請檢查原始 ZIP。"
                        )
                    rows.append(row)

            data = pd.DataFrame(rows, columns=header, dtype=str)
            note = ""
            if fixed:
                note = (
                    "A_lvr_land_B.csv 第883筆：棟及號原文A棟A3-1,2F號含未加引號逗號；"
                    "讀取時合併欄位，官方原始ZIP保持不變"
                )
                print("已修正第 883 筆『棟及號』被逗號拆成兩欄的問題。")
            return data, encoding, fixed, note

    raise RuntimeError(f"無法以 utf-8-sig、cp950 或 big5 讀取：{csv_name}")


def parse_dates(values):
    """把民國與西元數字日期統一轉為 pandas 日期，無效值記為缺值。"""
    text = values.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    text = text.where(text.str.fullmatch(r"\d{5,8}"), "")
    size = text.str.len()
    year = pd.to_numeric(text.str[:-4], errors="coerce")
    month = pd.to_numeric(text.str[-4:-2], errors="coerce")
    day = pd.to_numeric(text.str[-2:], errors="coerce")
    # 8 位數視為西元年；其餘年份加 1911 換算為西元。
    year = year.where(size == 8, year + 1911)
    return pd.to_datetime(
        {"year": year, "month": month, "day": day}, errors="coerce"
    )


def main():
    """逐個讀取官方 ZIP，記錄每份雙北預售屋主檔的來源資訊。"""
    zip_files = sorted(RAW_DIR.glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(f"請先將官方 ZIP 放入資料夾：{RAW_DIR}")

    # results 是來源紀錄的清單，最後將轉成 DataFrame 輸出 CSV。
    results = []
    for zip_path in zip_files:
        print(f"\n檢查 ZIP：{zip_path.name}")
        fingerprint = zip_hash(zip_path)

        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            print(f"壓縮檔內檔案數：{len([n for n in names if not n.endswith('/')])}")
            print("前 12 個檔案名稱：", names[:12])

            for csv_name in names:
                # ZIP 內可能還有土地、車位等附表，此處只讀交易主檔。
                filename = csv_name.replace("\\", "/").split("/")[-1]
                city = CITY_FILES.get(filename.lower())
                if city is None:
                    continue

                data, encoding, fixed, note = read_csv(archive, csv_name)
                print(f"\n{city}：{filename}，編碼：{encoding}")
                print(f"原始列數：{len(data):,}，欄位數：{len(data.columns)}")
                print("欄位名稱：", list(data.columns))
                print("前 3 列、前 8 欄：")
                print(data.iloc[:3, :8].to_string(index=False))

                # 使用實際讀到的欄位尋找交易日期，不預設欄位一定存在。
                date_columns = [
                    name for name in data.columns if "交易" in name and "日" in name
                ]
                # 只有找到唯一的交易日期欄時才使用；避免誤選相似欄名。
                date_col = date_columns[0] if len(date_columns) == 1 else None
                count, first, last = 0, "", ""
                if date_col:
                    dates = parse_dates(data[date_col])
                    count = int(dates.notna().sum())
                    if count:
                        first = dates.min().strftime("%Y-%m-%d")
                        last = dates.max().strftime("%Y-%m-%d")
                print(f"日期可解析列數：{count:,}，日期範圍：{first} ～ {last}")

                results.append({
                    "檢查日期": datetime.now().strftime("%Y-%m-%d"),
                    "來源入口": SOURCE,
                    "本機ZIP名稱": zip_path.name,
                    "ZIP_SHA256": fingerprint,
                    "壓縮內CSV名稱": csv_name,
                    "城市": city,
                    "檔案編碼": encoding,
                    "讀入列數_未清理": len(data),
                    "欄位數": len(data.columns),
                    "交易日期欄": date_col or "待確認",
                    "日期可解析列數": count,
                    "最早交易日期_初步": first,
                    "最晚交易日期_初步": last,
                    "欄位解析修正筆數": fixed,
                    "欄位解析修正說明": note,
                })

    if not results:
        raise RuntimeError("ZIP 中找不到雙北預售屋交易主檔，請檢查下載內容。")

    # utf-8-sig 方便在 Windows 的 Excel 中檢視中文 CSV。
    pd.DataFrame(results).to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"\n已建立來源紀錄：{OUTPUT}")
    print("以上為原始資料檢查結果，尚未清理、去重或處理解約。")


if __name__ == "__main__":
    main()
