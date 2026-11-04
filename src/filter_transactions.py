# -*- coding: utf-8 -*-
"""從已確認的來源 ZIP 中篩選雙北市三年期間的預售屋交易。

輸入：data/raw/ 官方 ZIP、data/source_inventory.csv。
輸出：data/filtered_transactions.csv、data/filter_summary.csv。
這裡只篩選城市及交易日期；解約和重複資料交給後續清理程式處理。
"""

from pathlib import Path
import csv
import io
import zipfile

import pandas as pd


# 依程式所在位置取得專案資料夾，不受 Spyder 工作目錄影響。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INVENTORY_FILE = PROJECT_ROOT / "data" / "source_inventory.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "filtered_transactions.csv"
SUMMARY_FILE = PROJECT_ROOT / "data" / "filter_summary.csv"

# 研究期間：民國112年9月21日至115年9月20日，包含起始日和結束日。
# 依目前已取得的資料範圍選定；仍需核對各來源批次的完整度與揭露延遲。
START_DATE = pd.Timestamp("2023-09-21")
END_DATE = pd.Timestamp("2026-09-20")


def convert_trade_dates(values):
    """將文字日期轉為西元日期，方便使用日期區間篩選。"""
    text = values.astype("string").fillna("").str.strip()
    text = text.str.replace(r"\.0$", "", regex=True)

    # 不符合日期長度的值（例如英文欄位說明）會轉為空字串。
    correct_format = text.str.fullmatch(r"\d{5,8}").fillna(False)
    text = text.where(correct_format, "")

    year = pd.to_numeric(text.str[:-4], errors="coerce")
    month = pd.to_numeric(text.str[-4:-2], errors="coerce")
    day = pd.to_numeric(text.str[-2:], errors="coerce")

    # 八位數視為西元；其餘符合格式的數字視為民國年。
    # 8 位數表示西元年月日；其餘數字日期使用民國年，需加上 1911。
    year = year.where(text.str.len() == 8, year + 1911)
    return pd.to_datetime(
        {"year": year, "month": month, "day": day}, errors="coerce"
    )


def main():
    """依來源清單讀取官方資料，輸出期間篩選結果及筆數摘要。"""
    if not INVENTORY_FILE.is_file():
        raise FileNotFoundError("找不到 data/source_inventory.csv，請先執行資料讀取程式。")

    # 每次新增官方 ZIP 後，先重新執行讀取程式，更新這份來源清單。
    inventory = pd.read_csv(
        INVENTORY_FILE, encoding="utf-8-sig", dtype=str, keep_default_na=False
    )
    needed = [
        "本機ZIP名稱", "壓縮內CSV名稱", "城市", "檔案編碼",
        "交易日期欄", "讀入列數_未清理", "日期可解析列數"
    ]
    for column in needed:
        if column not in inventory.columns:
            raise ValueError(f"來源清單缺少欄位：{column}，請檢查讀取程式的輸出。")

    # 只保留臺北市、新北市，其他縣市不在研究範圍內。
    inventory = inventory[inventory["城市"].isin(["臺北市", "新北市"])]
    if inventory.empty:
        raise ValueError("來源清單中沒有臺北市或新北市的資料。")

    csv.field_size_limit(10_000_000)
    # 一份 ZIP 可以含多個 CSV；先分別讀取，最後再合併。
    filtered_tables = []
    summary_rows = []

    for _, source in inventory.iterrows():
        # 來源清單已包含每個 CSV 所在的 ZIP、檔名、城市及編碼。
        zip_name = source["本機ZIP名稱"]
        member = source["壓縮內CSV名稱"]
        city = source["城市"]
        encoding = source["檔案編碼"]
        date_column = source["交易日期欄"]
        zip_path = RAW_DIR / zip_name

        print(f"\n讀取：{city}｜{zip_name}｜{member}")
        if not zip_path.is_file():
            raise FileNotFoundError(f"找不到原始壓縮檔：{zip_path}")

        # 使用 csv.reader 保留欄位原始文字，且能檢查每筆的欄位數。
        with zipfile.ZipFile(zip_path) as archive:
            with archive.open(member) as binary:
                with io.TextIOWrapper(binary, encoding=encoding, newline="") as file:
                    reader = csv.reader(file, strict=True)
                    header = next(reader)
                    rows = []
                    repair_count = 0

                    for number, fields in enumerate(reader, start=2):
                        if not fields:
                            continue

                        # 僅修正已核實的原始 CSV 異常，不修改 ZIP 本身。
                        # 該筆「棟及號」有未加引號的逗號，因而多出一個欄位。
                        known_issue = (
                            member.replace("\\", "/").split("/")[-1].lower()
                            == "a_lvr_land_b.csv"
                            and number == 883
                            and len(header) == 31
                            and header[27:31] == ["編號", "建案名稱", "棟及號", "解約情形"]
                            and fields[27:32] == [
                                "RPPNMLQLJHLGFAA37CB", "碩樺拾景",
                                "A棟A3-1", "2F號", ""
                            ]
                        )
                        if known_issue:
                            fields = fields[:29] + [fields[29] + "," + fields[30]] + fields[31:]
                            repair_count += 1

                        # 其他未確認的異常不得略過，以免影響正式統計。
                        if len(fields) != len(header):
                            raise ValueError(
                                f"{zip_name} / {member} 第 {number} 筆："
                                f"應有 {len(header)} 欄，實際 {len(fields)} 欄。"
                            )
                        rows.append(fields)

        data = pd.DataFrame(rows, columns=header)
        if date_column not in data.columns:
            raise ValueError(f"找不到交易日期欄：{date_column}（{member}）")

        # 和前一步的來源清單核對列數，避免重新讀取時漏掉紀錄。
        if len(data) != int(source["讀入列數_未清理"]):
            raise ValueError(f"{member}：讀取列數與 source_inventory.csv 不一致。")

        dates = convert_trade_dates(data[date_column])
        readable_count = int(dates.notna().sum())
        if readable_count != int(source["日期可解析列數"]):
            raise ValueError(f"{member}：可解析日期列數與來源清單不一致。")

        # between 會同時包含起始日與結束日；無法解析的日期不會被選入。
        # 選出落在正式研究期間內的交易，日期左右端都包含。
        selected = dates.between(START_DATE, END_DATE)
        filtered = data.loc[selected].copy()
        filtered.insert(0, "城市", city)
        filtered.insert(1, "來源ZIP", zip_name)
        filtered.insert(2, "來源CSV", member)
        filtered["交易日期_西元"] = dates.loc[selected].dt.strftime("%Y-%m-%d")
        filtered_tables.append(filtered)

        summary_rows.append({
            "城市": city,
            "來源ZIP": zip_name,
            "來源CSV": member,
            "原始列數_未清理": len(data),
            "日期可解析列數": readable_count,
            "日期無法解析列數": len(data) - readable_count,
            "期間內列數_未清理": len(filtered),
            "篩選開始日": START_DATE.strftime("%Y-%m-%d"),
            "篩選結束日": END_DATE.strftime("%Y-%m-%d"),
            "來源最早交易日期": dates.min().strftime("%Y-%m-%d") if readable_count else "",
            "來源最晚交易日期": dates.max().strftime("%Y-%m-%d") if readable_count else "",
            "讀取時已核實修正筆數": repair_count,
        })
        print(f"原始列數：{len(data):,}；期間內列數（未清理）：{len(filtered):,}")

    # concat() 把不同來源批次的結果上下合併。
    # 此時尚未去重，因此不能直接把筆數視為正式有效成交數。
    result = pd.concat(filtered_tables, ignore_index=True)
    summary = pd.DataFrame(summary_rows)

    # 匯出的資料仍可能包含解約、重複及特殊交易，不視為正式有效成交樣本。
    result.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_FILE, index=False, encoding="utf-8-sig")

    print("\n依城市加總（尚未去重、未處理解約）：")
    print(summary.groupby("城市")[
        ["原始列數_未清理", "日期無法解析列數", "期間內列數_未清理"]
    ].sum().to_string())
    print(f"\n共輸出 {len(result):,} 列到：{OUTPUT_FILE}")
    print(f"來源及篩選摘要：{SUMMARY_FILE}")
    print("注意：這是三年期間的已揭露篩選樣本，不代表市場全部成交。")


if __name__ == "__main__":
    main()
