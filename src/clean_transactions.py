# -*- coding: utf-8 -*-
"""清理預售屋交易資料，計算房地價格、面積並輸出統計資料。

輸入：data/filtered_transactions.csv、data/filter_summary.csv。
輸出：data/processed/ 下的清理結果、待複核紀錄與各類統計表。
清理重點：解約、重複資料、特殊備註、車位價金和面積。
"""

from pathlib import Path
import pandas as pd


# 以程式位置尋找專案根目錄，避免 Spyder 工作目錄影響檔案路徑。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "filtered_transactions.csv"
FILTER_SUMMARY_FILE = PROJECT_ROOT / "data" / "filter_summary.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
START_DATE = pd.Timestamp("2023-09-21")
END_DATE = pd.Timestamp("2026-09-20")


def add_reason(data, condition, column, reason):
    """為符合條件的紀錄寫下排除原因，同筆資料可有多個原因。"""
    data.loc[condition, column] += reason + "；"


def make_statistics(data, group_columns):
    """依指定欄位分組，計算筆數、單價及房地總價統計。"""
    # size 計算全部成交筆數；count 只計算單價不是缺值的紀錄。
    # mean 是平均值、median 是中位數。
    result = data.groupby(group_columns).agg(
        成交筆數=("城市", "size"),
        單價樣本數=("統計單價_萬元坪", "count"),
        平均單價_萬元坪=("統計單價_萬元坪", "mean"),
        中位數單價_萬元坪=("統計單價_萬元坪", "median"),
        平均房地總價_萬元=("房地總價_萬元", "mean"),
    ).reset_index()

    # 統計值保留小數兩位；原始資料的數值換算不先四捨五入。
    columns = ["平均單價_萬元坪", "中位數單價_萬元坪", "平均房地總價_萬元"]
    result[columns] = result[columns].round(2)
    return result


def main():
    """核對篩選成果、清理資料並匯出後續作圖需要的 CSV。"""
    if not INPUT_FILE.is_file():
        raise FileNotFoundError("找不到 filtered_transactions.csv，請先執行篩選程式。")
    if not FILTER_SUMMARY_FILE.is_file():
        raise FileNotFoundError("找不到 filter_summary.csv，請先執行篩選程式。")

    # 全部先按文字讀取，以免編號、棟及號或原始數字被自動改寫。
    data = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig")
    filter_summary = pd.read_csv(FILTER_SUMMARY_FILE, encoding="utf-8-sig")

    # 這些欄名須與實際官方資料相同；有差異時先停止，不猜測欄位。
    required = [
        "城市", "來源ZIP", "來源CSV", "交易日期_西元", "鄉鎮市區",
        "交易標的", "總價元", "單價元平方公尺", "建物移轉總面積平方公尺",
        "編號", "解約情形", "備註"
    ]
    for column in required:
        if column not in data.columns:
            raise ValueError(f"篩選檔案缺少必要欄位：{column}。請先核對實際 CSV 表頭。")
    if "期間內列數_未清理" not in filter_summary.columns:
        raise ValueError("filter_summary.csv 缺少期間內列數_未清理。")

    expected_count = filter_summary["期間內列數_未清理"].sum()
    if len(data) != expected_count:
        raise ValueError("篩選資料筆數與 filter_summary.csv 不一致，請先重新核對。")
    if data.empty:
        raise ValueError("篩選結果是空的，無法執行清理與統計。")

    # 清除字串前後的空白；保留所有原始欄位及來源資訊。
    for column in data.columns:
        data[column] = data[column].str.strip()

    dates = pd.to_datetime(data["交易日期_西元"], errors="coerce")
    if dates.isna().any() or not dates.between(START_DATE, END_DATE).all():
        raise ValueError("交易日期不全在研究期間，請先確認篩選程式的結果。")

    # 不同 ZIP 可能重複揭露相同交易，所以比對內容時不看來源檔名。
    # duplicated(keep="first") 僅保留相同內容的第一筆；其他列記錄排除原因。
    content_columns = [col for col in data.columns if col not in ["來源ZIP", "來源CSV"]]
    exact_duplicate = data.duplicated(subset=content_columns, keep="first")

    # 相同交易編號但資料內容不同，可能來自更正或批次更新。
    # 不自行決定保留哪一筆，先列入待複核，避免誤判。
    remaining = data.loc[~exact_duplicate]
    id_collision = remaining["編號"].ne("") & remaining.duplicated(
        subset=["城市", "編號"], keep=False
    )
    conflicting_id = pd.Series(False, index=data.index)
    conflicting_id.loc[id_collision.index] = id_collision

    # 將真正需要計算的數值轉換，無法解析的資料轉為 NaN。
    number_columns = ["總價元", "單價元平方公尺", "建物移轉總面積平方公尺"]
    for column in number_columns:
        data[column + "_數值"] = pd.to_numeric(
            data[column].str.replace(",", "", regex=False), errors="coerce"
        )

    # 車位價格、面積若未提供，不能假設官方單價已扣除車位。
    for column in ["車位總價元", "車位移轉總面積平方公尺"]:
        if column in data.columns:
            values = data[column]
        else:
            values = pd.Series("", index=data.index)
        data[column + "_數值"] = pd.to_numeric(
            values.str.replace(",", "", regex=False), errors="coerce"
        )

    price = data["總價元_數值"]
    unit_price = data["單價元平方公尺_數值"]
    area = data["建物移轉總面積平方公尺_數值"]

    # 以下用布林條件找出異常資料，再把原因寫入文字欄。
    # 不直接從原始資料刪除紀錄，方便核對排除規則。
    data["交易排除原因"] = ""
    add_reason(data, ~data["城市"].isin(["臺北市", "新北市"]),
               "交易排除原因", "城市不符")
    add_reason(data, data["鄉鎮市區"].eq(""), "交易排除原因", "行政區缺失")
    add_reason(data, data["編號"].eq(""), "交易排除原因", "編號缺失")
    add_reason(data, ~data["交易標的"].str.startswith("房地"),
               "交易排除原因", "非房地交易")
    add_reason(data, price.isna() | price.le(0), "交易排除原因", "總價缺失或非正數")
    add_reason(data, area.isna() | area.le(0), "交易排除原因", "面積缺失或非正數")
    add_reason(data, data["解約情形"].ne(""), "交易排除原因", "解約欄有資料待核對")
    add_reason(data, data["備註"].ne(""), "交易排除原因", "備註需人工判讀")
    add_reason(data, exact_duplicate, "交易排除原因", "跨來源內容重複")
    add_reason(data, conflicting_id, "交易排除原因", "相同編號內容不同")

    # 有效成交筆數與有效單價筆數並不一定相同。
    # 如果含車位但無法清楚拆分車位價格與面積，仍可能計入成交筆數，
    # 但不會納入房地單價、房地總價與房地面積的比較。
    has_parking = (data["交易標的"].str.startswith("房地", na=False)
                   & data["交易標的"].str.contains("車位", na=False))
    parking_price = data["車位總價元_數值"]
    parking_area = data["車位移轉總面積平方公尺_數值"]
    parking_unclear = has_parking & (
        parking_price.isna() | parking_price.le(0)
        | parking_area.isna() | parking_area.le(0)
        | price.le(parking_price) | area.le(parking_area)
    )
    data["單價排除原因"] = ""
    add_reason(data, unit_price.isna() | unit_price.le(0),
               "單價排除原因", "官方單價缺失或非正數")
    add_reason(data, parking_unclear, "單價排除原因", "含車位且分價或面積資料不足")

    # 單位換算：1 坪 = 3.305785 平方公尺、1 萬元 = 10,000 元。
    # 將政府資料的元／平方公尺轉為萬元／坪，計算時保留原始精度。
    data["總價_萬元"] = price / 10000
    data["建物面積_坪"] = area / 3.305785
    data["單價_萬元坪"] = unit_price * 3.305785 / 10000

    # 房地總價與建物面積使用可拆分車位的數值進行比較。
    # 含車位交易：原始總價／面積減去車位價金／面積；
    # 不含車位交易：直接使用原始總價／面積。
    # 無法拆分車位的紀錄保留成交筆數，但不納入房地總價與面積比較。
    parking_price = parking_price.where(has_parking, 0)
    parking_area = parking_area.where(has_parking, 0)
    house_total = (price - parking_price).where(~parking_unclear)
    house_area = (area - parking_area).where(~parking_unclear)
    data["房地總價_萬元"] = house_total.where(house_total > 0) / 10000
    data["房地建物面積_坪"] = house_area.where(house_area > 0) / 3.305785
    data["交易月份"] = dates.dt.strftime("%Y-%m")

    # 供檢查的記錄：交易不合格，或交易合格但單價仍不可比較。
    needs_review = (data["交易排除原因"].ne("")
                    | data["單價排除原因"].ne(""))
    review = data.loc[needs_review].copy()
    cleaned = data.loc[data["交易排除原因"].eq("")].copy()

    # where() 會讓不符合單價計算條件的紀錄變成 NaN（缺值）。
    # 這樣可以在統計單價時跳過該筆，但不會減少有效成交的筆數。
    cleaned["統計單價_萬元坪"] = cleaned["單價_萬元坪"].where(
        cleaned["單價排除原因"].eq("")
    )

    city_stats = make_statistics(cleaned, ["城市"])
    district_stats = make_statistics(cleaned, ["城市", "鄉鎮市區"])
    monthly_stats = make_statistics(cleaned, ["城市", "交易月份"])

    # 統計表直接保留日期範圍、來源批次與計算規則，方便後續圖表註記。
    batches = "；".join(sorted(data["來源ZIP"].unique()))
    for stats in [city_stats, district_stats, monthly_stats]:
        stats["研究開始日"] = START_DATE.strftime("%Y-%m-%d")
        stats["研究結束日"] = END_DATE.strftime("%Y-%m-%d")
        stats["來源ZIP批次"] = batches
        stats["成交筆數口徑"] = "僅房地交易，排除解約、備註待複核與重複紀錄"
        stats["單價口徑"] = "官方房地單價（萬元/坪）；車位分價不明不納入單價比較"
        stats["總價口徑"] = "房地總價扣除可拆分車位價金；不可拆分者不納入總價平均"

    # 一筆交易可能同時存在「重複」和「備註待複核」等情況。
    # 因此各種原因的筆數不能直接加總，否則會重複計算。
    quality_rows = [
        {"檢查項目": "期間內原始列數", "筆數": len(data)},
        {"檢查項目": "可用成交筆數（含單價待複核）", "筆數": len(cleaned)},
        {"檢查項目": "交易排除或待複核列數", "筆數": len(data) - len(cleaned)},
        {"檢查項目": "單價可比樣本數", "筆數": int(cleaned["統計單價_萬元坪"].notna().sum())},
        {"檢查項目": "房地總價與建物面積可比樣本數", "筆數": int(
            cleaned[["房地總價_萬元", "房地建物面積_坪"]].notna().all(axis=1).sum()
        )},
        {"檢查項目": "跨來源內容重複", "筆數": int(exact_duplicate.sum())},
        {"檢查項目": "相同編號內容不同", "筆數": int(conflicting_id.sum())},
        {"檢查項目": "解約欄非空白", "筆數": int(data["解約情形"].ne("").sum())},
        {"檢查項目": "備註需人工判讀", "筆數": int(data["備註"].ne("").sum())},
        {"檢查項目": "含車位且分價或面積資料不足", "筆數": int(parking_unclear.sum())},
    ]
    quality = pd.DataFrame(quality_rows)
    quality["研究開始日"] = START_DATE.strftime("%Y-%m-%d")
    quality["研究結束日"] = END_DATE.strftime("%Y-%m-%d")
    quality["來源ZIP批次"] = batches

    # 儲存清理結果與品質統計；原始 ZIP 保存在 data/raw/，不會被覆寫。
    # review_transactions.csv 保存待複核紀錄，方便對照排除原因。
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(OUTPUT_DIR / "cleaned_transactions.csv", index=False,
                   encoding="utf-8-sig")
    review.to_csv(OUTPUT_DIR / "review_transactions.csv", index=False,
                  encoding="utf-8-sig")
    quality.to_csv(OUTPUT_DIR / "data_quality_summary.csv", index=False,
                   encoding="utf-8-sig")
    city_stats.to_csv(OUTPUT_DIR / "city_statistics.csv", index=False,
                      encoding="utf-8-sig")
    district_stats.to_csv(OUTPUT_DIR / "district_statistics.csv", index=False,
                          encoding="utf-8-sig")
    monthly_stats.to_csv(OUTPUT_DIR / "monthly_statistics.csv", index=False,
                         encoding="utf-8-sig")

    print("\n資料品質摘要：")
    print(quality[["檢查項目", "筆數"]].to_string(index=False))
    print("\n雙北市基礎統計：")
    columns = ["城市", "成交筆數", "單價樣本數", "平均單價_萬元坪",
               "中位數單價_萬元坪", "平均房地總價_萬元"]
    print(city_stats[columns].to_string(index=False))
    print(f"\n檔案已輸出到：{OUTPUT_DIR}")
    print("備註與解約欄保守排除；房地總價、面積已扣除可拆分車位。")
    print("所有數據僅代表當次取得的官方公開批次，不等於市場全部成交。")


if __name__ == "__main__":
    main()
