# -*- coding: utf-8 -*-
"""將清理後的雙北預售屋資料匯入 MySQL 並核對筆數。

輸入：data/processed/cleaned_transactions.csv。
資料表：database/schema.sql 中建立的 presale_transactions。
流程：讀入 CSV → 檢查欄位 → 輸入連線密碼 → 批次匯入 → SQL 核對。
"""

from pathlib import Path
from getpass import getpass

import pandas as pd
import mysql.connector


# 以程式檔位置取得專案根目錄，避免受到 Spyder 工作目錄影響。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "cleaned_transactions.csv"

DB_HOST = "localhost"
DB_PORT = 3306
DB_NAME = "presale_analysis"
DB_USER = "root"  # MySQL 連線帳號，依本機資料庫設定調整。
# 每 1,000 筆送到資料庫一次，避免一次執行過大的 INSERT。
BATCH_SIZE = 1000

START_DATE = pd.Timestamp("2023-09-21")
END_DATE = pd.Timestamp("2026-09-20")
CITIES = ["臺北市", "新北市"]


def convert_numbers(values, column_name):
    """將可轉換的數值讀成數字；若存在不明文字，停止匯入。"""
    text = values.astype("string").str.strip()
    text = text.str.replace(",", "", regex=False)
    numbers = pd.to_numeric(text, errors="coerce")

    # 有內容卻無法轉成數字，代表資料需要檢查；不能直接忽略。
    invalid = text.notna() & text.ne("") & numbers.isna()
    if invalid.any():
        raise ValueError(
            f"欄位「{column_name}」有 {int(invalid.sum())} 筆無法轉成數字，"
            "請先核對清理後的 CSV。"
        )
    return numbers


def load_data():
    """讀取既有清理結果，確認資料符合研究範圍，並選出分析欄位。"""
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"找不到清理後的資料：{INPUT_FILE}")

    raw = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", low_memory=False)
    if raw.empty:
        raise ValueError("清理後的 CSV 沒有資料，停止匯入。")

    # 這些欄名沿用既有繪圖程式；實際 CSV 缺欄時不猜測或自動補值。
    required = [
        "城市", "交易日期_西元", "交易標的", "統計單價_萬元坪",
        "總價元", "建物移轉總面積平方公尺"
    ]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError("清理後 CSV 缺少欄位：" + "、".join(missing))

    if "行政區" in raw.columns:
        district_column = "行政區"
    elif "鄉鎮市區" in raw.columns:
        district_column = "鄉鎮市區"
    else:
        raise ValueError("找不到行政區欄位（行政區／鄉鎮市區）。")

    # MySQL 亦只匯入房地交易；總價與建物面積保留官方原始值供查核。
    if not raw["交易標的"].str.startswith("房地", na=False).all():
        raise ValueError("清理後 CSV 出現非房地交易，請重新執行清理程式。")

    cities = raw["城市"].astype("string").str.strip()
    districts = raw[district_column].astype("string").str.strip()
    dates = pd.to_datetime(raw["交易日期_西元"], errors="coerce").dt.normalize()

    if not cities.isin(CITIES).all():
        raise ValueError("發現非雙北城市或空白城市，請檢查資料篩選結果。")
    if districts.isna().any() or districts.eq("").any():
        raise ValueError("行政區存在空值，請檢查清理結果。")
    if not dates.between(START_DATE, END_DATE).all():
        raise ValueError("交易日期不在 2023/09/21～2026/09/20 或日期無法解析。")

    prices = convert_numbers(raw["統計單價_萬元坪"], "統計單價_萬元坪")
    totals = convert_numbers(raw["總價元"], "總價元")
    areas = convert_numbers(raw["建物移轉總面積平方公尺"], "建物移轉總面積平方公尺")

    # 與繪圖程式一致：單價可缺值，非空白的單價不得小於等於零。
    # 總價與建物面積若小於等於零，資料庫記為 NULL，不納入數值平均。
    if prices.dropna().le(0).any():
        raise ValueError("統計單價有零或負數，請先核對清理結果。")
    totals = totals.where(totals > 0)
    areas = areas.where(areas > 0)

    # 來源欄位若在前面清理時有保留，就一起寫入資料庫。
    source_zip = raw["來源ZIP"] if "來源ZIP" in raw.columns else pd.Series("", index=raw.index)
    source_csv = raw["來源CSV"] if "來源CSV" in raw.columns else pd.Series("", index=raw.index)

    # DataFrame 的欄名對應 MySQL Schema 使用的英文欄名。
    # SQL 資料表保留的是官方原始總價／面積供核對，非繪圖用的拆車位欄位。
    data = pd.DataFrame({
        "city": cities,
        "district": districts,
        "trade_date": dates,
        "unit_price_10k_ping": prices,
        "total_price_yuan": totals,
        "building_area_m2": areas,
        "source_zip": source_zip.fillna("").astype(str).str.strip(),
        "source_csv": source_csv.fillna("").astype(str).str.strip(),
    })

    # 避免超過 MySQL 建表時宣告的字元長度。
    max_lengths = {"city": 10, "district": 30, "source_zip": 255, "source_csv": 255}
    for column, max_length in max_lengths.items():
        if data[column].astype(str).str.len().gt(max_length).any():
            raise ValueError(f"欄位「{column}」有文字超過 {max_length} 字元。")

    print(f"準備匯入 {len(data):,} 筆清理後資料。")
    print("研究期間：", START_DATE.date(), "～", END_DATE.date())
    print("有效單價樣本：", int(data["unit_price_10k_ping"].notna().sum()))
    return data


def check_results(cursor, data):
    """核對資料庫與 pandas 的城市筆數、單價樣本數及平均單價。"""
    # SELECT 的結果與 pandas groupby 的結果逐一比較。
    # COUNT(*) 計算所有列，COUNT(單價欄) 不計算 NULL。
    cursor.execute("""
        SELECT city,
               COUNT(*) AS transaction_count,
               COUNT(unit_price_10k_ping) AS price_count,
               AVG(unit_price_10k_ping) AS avg_price
        FROM presale_transactions
        GROUP BY city
        ORDER BY city
    """)
    sql_results = cursor.fetchall()

    pandas_results = data.groupby("city")["unit_price_10k_ping"].agg(
        ["size", "count", "mean"]
    )
    if len(sql_results) != len(pandas_results):
        raise RuntimeError("MySQL 與 pandas 的城市分組數不一致。")

    for city, sql_count, sql_price_count, sql_mean in sql_results:
        if city not in pandas_results.index:
            raise RuntimeError("MySQL 出現 pandas 中不存在的城市：" + city)

        pandas_count = int(pandas_results.loc[city, "size"])
        pandas_price_count = int(pandas_results.loc[city, "count"])
        pandas_mean = pandas_results.loc[city, "mean"]

        if sql_count != pandas_count or sql_price_count != pandas_price_count:
            raise RuntimeError(f"{city} 的資料筆數或單價樣本數不一致。")

        # MySQL DECIMAL 儲存至小數第 4 位，容許極微小四捨五入差距。
        if pandas_price_count > 0 and abs(float(sql_mean) - float(pandas_mean)) > 0.01:
            raise RuntimeError(f"{city} 的單價平均值不一致。")

        print(f"{city}：成交 {sql_count:,} 筆；單價樣本 {sql_price_count:,} 筆")
        if sql_mean is not None:
            print(f"  SQL 平均單價：{float(sql_mean):.2f} 萬元/坪")


def main():
    """重新匯入完整清理結果，失敗時回復原有資料。"""
    data = load_data()
    # 密碼在執行時輸入，不存入程式、設定檔或公開 GitHub。
    password = getpass("請輸入本機 MySQL 密碼（輸入時不顯示）：")

    # 資料庫及資料表需先由 database/schema.sql 建立完成。
    connection = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=password,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=False,
    )
    cursor = connection.cursor()

    insert_sql = """
        INSERT INTO presale_transactions
            (city, district, trade_date, unit_price_10k_ping,
             total_price_yuan, building_area_m2, source_zip, source_csv)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        # DELETE 與匯入放在同一個交易中，避免重複匯入。
        # 只有全部資料與統計驗證成功，才會正式 commit。
        # 若匯入或核對失敗，rollback 可以恢復匯入之前的紀錄。
        cursor.execute("DELETE FROM presale_transactions")
        for start in range(0, len(data), BATCH_SIZE):
            batch = data.iloc[start:start + BATCH_SIZE]
            records = []

            # itertuples() 逐列讀取要匯入的資料。
            # pandas 的 NaN 需要轉成 None，MySQL 才能存成 NULL。
            for row in batch.itertuples(index=False, name=None):
                city, district, trade_date, price, total, area, zip_name, csv_name = row
                records.append((
                    city,
                    district,
                    trade_date.date(),
                    None if pd.isna(price) else float(price),
                    None if pd.isna(total) else float(total),
                    None if pd.isna(area) else float(area),
                    zip_name,
                    csv_name,
                ))

            cursor.executemany(insert_sql, records)
            print(f"已處理 {min(start + BATCH_SIZE, len(data)):,} / {len(data):,} 筆")

        cursor.execute("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM presale_transactions
        """)
        sql_count, sql_first_date, sql_last_date = cursor.fetchone()
        if sql_count != len(data):
            raise RuntimeError("MySQL 總筆數與 pandas 不一致，停止提交。")
        if sql_first_date != data["trade_date"].min().date():
            raise RuntimeError("MySQL 最早交易日期與 pandas 不一致。")
        if sql_last_date != data["trade_date"].max().date():
            raise RuntimeError("MySQL 最晚交易日期與 pandas 不一致。")

        check_results(cursor, data)
        # 到這裡代表筆數、日期、平均單價均已通過核對。
        connection.commit()
        print("\n匯入完成，總筆數、日期與各城市統計均已核對一致。")
        print("MySQL 實際交易日期：", sql_first_date, "～", sql_last_date)

    except Exception:
        connection.rollback()
        print("匯入未完成；本次資料庫變更已回復。")
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
