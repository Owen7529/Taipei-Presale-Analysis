# -*- coding: utf-8 -*-
"""使用 pandas 與 Matplotlib 製作雙北市預售屋成交分析圖。

資料輸入：data/processed/cleaned_transactions.csv
圖表輸出：charts/ 下的八張 PNG 與三份統計 CSV
處理順序：讀入資料 → 檢查範圍 → 分組統計 → 繪圖 → 輸出。
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd


# __file__ 是目前這支 Python 檔案的位置。
# .parent.parent 表示從 src/ 回到專案根目錄，避免 Spyder 工作目錄不同時找不到檔案。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "cleaned_transactions.csv"
OUTPUT_DIR = PROJECT_ROOT / "charts"

START_DATE = pd.Timestamp("2023-09-21")
END_DATE = pd.Timestamp("2026-09-20")
CITIES = ["臺北市", "新北市"]
PRICE_COLUMN = "統計單價_萬元坪"
TOTAL_PRICE_COLUMN = "房地總價_萬元"
BUILDING_AREA_COLUMN = "房地建物面積_坪"

# 下列數字只用來設定圖表呈現方式，沒有修改清理資料。
# 行政區價格排行至少需要 30 筆有效單價，避免少量紀錄造成不穩定的排名。
MIN_DISTRICT_PRICE_N = 30
TOP_SHARE_DISTRICT_COUNT = 8
TOP_PRICE_DISTRICT_COUNT = 5
SHOW_FIGURES = False  # 若希望在 Spyder 畫面上逐張顯示，可改成 True。

CITY_COLORS = {"臺北市": "#124F95", "新北市": "#E18B31"}
# 總價級距具有大小順序，因此使用同一色系、不同深淺。
BAND_COLORS = ["#F2F8FF", "#C6DBEF", "#6BAED6", "#2171B5", "#08306B"]
# 行政區是獨立分類，使用不同色系區分；灰色專門代表「其他」。
SHARE_COLORS = ["#2D5F9A", "#E28D35", "#249B8D", "#8759A9",
                "#D75961", "#C8AA36", "#639A3C", "#D76BA1", "#8997A4"]

# Matplotlib 不一定能自動選擇繁體中文字型。
# 依序尋找 Windows／macOS／Linux 常見的中文字型，確保圖表中文正常顯示。
FONT_OPTIONS = [
    "Microsoft JhengHei", "Noto Sans CJK TC", "PingFang TC",
    "Microsoft YaHei", "Noto Sans CJK JP", "SimHei", "Arial Unicode MS"
]
FONTS = {font.name for font in font_manager.fontManager.ttflist}
FONT_NAME = next((name for name in FONT_OPTIONS if name in FONTS), None)
if FONT_NAME is None:
    raise RuntimeError("找不到可顯示中文的字型，請先確認 Windows／Spyder 的字型設定。")
plt.rcParams["font.sans-serif"] = [FONT_NAME]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 11

# 研究年度採 9 月 21 日到下一年 9 月 20 日，不是一般西元曆年。
YEAR_RANGES = [
    ("第1研究年", "2023-09-21", "2024-09-20"),
    ("第2研究年", "2024-09-21", "2025-09-20"),
    ("第3研究年", "2025-09-21", "2026-09-20"),
]

# 八張正式圖的檔名與用途，供整理程式使用。
CHARTS = [
    ("01_monthly_transaction_count.png", "每月成交筆數走勢"),
    ("02_monthly_median_price.png", "每月單價中位數走勢"),
    ("03_district_count_share.png", "各市前八名行政區成交占比"),
    ("04_district_median_price_top5.png", "各市行政區單價中位數前五名"),
    ("05_total_price_band_share.png", "各市成交總價級距占比"),
    ("06_area_band_distribution.png", "各市建物面積級距占比"),
    ("07_city_year_price_boxplot.png", "城市與研究年度單價箱型圖"),
    ("08_unit_price_band_distribution.png", "各市每坪單價級距分布"),
]


def convert_numbers(values, column):
    """把 CSV 文字轉成數值；非空白但無法轉換的內容視為資料問題。"""
    words = values.astype("string").str.strip().str.replace(",", "", regex=False)
    numbers = pd.to_numeric(words, errors="coerce")
    # 空白可以代表缺值；但不是空白、又不能轉成數字，就不能直接略過。
    invalid = words.notna() & words.ne("") & numbers.isna()
    if invalid.any():
        raise ValueError(f"欄位「{column}」有 {int(invalid.sum())} 筆無法轉成數字。")
    return numbers


def new_chart(left=0.10, right=0.96, top=0.86, bottom=0.14):
    """建立 16:9 圖片；四個參數控制圖表與圖片邊緣的距離。"""
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    return fig, ax


def save_chart(fig, filename, title, period_note="2023/09/21–2026/09/20"):
    """統一輸出標題、交易期間及來源，並儲存高解析 PNG。"""
    # 增加主標題與交易期間的垂直間距，避免文字緊貼。
    fig.suptitle(title, x=0.055, y=0.970, ha="left", fontsize=20, fontweight="bold")
    fig.text(0.055, 0.902, f"交易期間：{period_note}｜臺北市、新北市", fontsize=10)
    fig.text(0.055, 0.026, "資料來源：內政部實價登錄預售屋公開資料", fontsize=8.5, color="#666666")
    # 12.8 × 7.2 英吋、250 dpi，輸出為 3200 × 1800 像素。
    path = OUTPUT_DIR / filename
    fig.savefig(path, dpi=250, facecolor="white")
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)
    print("已輸出：", path.name)

def main():
    """依序完成資料檢查、八張圖表和三份統計表的輸出。"""
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"找不到清理後的資料：{INPUT_FILE}\n"
            "請先執行現有資料讀取、篩選及清理程式。"
        )

    # 讀入前一階段已清理完成的真實成交紀錄。
    # 這裡只做統計及作圖，不修改原始官方 ZIP 或逐筆交易資料。
    data = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", low_memory=False)
    if data.empty:
        raise ValueError("清理後 CSV 為空，無法製作正式圖表。")
    # 程式只使用現有清理結果的欄名；如果缺少必要欄位就停止。
    required = ["城市", "交易日期_西元", PRICE_COLUMN,
                TOTAL_PRICE_COLUMN, BUILDING_AREA_COLUMN]
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError("清理後 CSV 缺少欄位：" + "、".join(missing))

    if "行政區" in data.columns:
        district_column = "行政區"
    elif "鄉鎮市區" in data.columns:
        district_column = "鄉鎮市區"
    else:
        raise ValueError("清理後 CSV 缺少行政區／鄉鎮市區欄位。")

    # 只使用既有清理後可比較的房地總價與面積；不以原始含車位欄位取代。
    if "交易標的" in data.columns and not data["交易標的"].str.startswith("房地", na=False).all():
        raise ValueError("清理結果仍含非房地紀錄，請先核對資料。")

    data["城市"] = data["城市"].astype("string").str.strip()
    data[district_column] = data[district_column].astype("string").str.strip()
    data["交易日期_西元"] = pd.to_datetime(data["交易日期_西元"], errors="coerce")
    if not data["城市"].isin(CITIES).all():
        raise ValueError("清理後資料含有非雙北城市。")
    if data[district_column].isna().any() or data[district_column].eq("").any():
        raise ValueError("部分行政區缺失，請先檢查清理結果。")
    if not data["交易日期_西元"].between(START_DATE, END_DATE).all():
        raise ValueError("資料日期不在三年正式研究範圍，請先重新執行篩選與清理。")

    # 每個指標都使用自己的有效樣本：單價、總價、面積不一定有相同筆數。
    data[PRICE_COLUMN] = convert_numbers(data[PRICE_COLUMN], PRICE_COLUMN)
    data["總價_萬元_繪圖"] = convert_numbers(data[TOTAL_PRICE_COLUMN], TOTAL_PRICE_COLUMN)
    data["建物面積_坪_繪圖"] = convert_numbers(data[BUILDING_AREA_COLUMN], BUILDING_AREA_COLUMN)
    if data[PRICE_COLUMN].dropna().le(0).any():
        raise ValueError("統計單價含零或負數，請先核對資料。")

    prices = data.dropna(subset=[PRICE_COLUMN]).copy()
    totals = data.loc[data["總價_萬元_繪圖"] > 0].copy()
    areas = data.loc[data["建物面積_坪_繪圖"] > 0].copy()
    if any(data["城市"].eq(city).sum() == 0 for city in CITIES):
        raise ValueError("其中一市沒有有效成交資料。")
    if any(prices["城市"].eq(city).sum() == 0 for city in CITIES):
        raise ValueError("其中一市沒有有效房地單價資料。")
    if any(totals["城市"].eq(city).sum() == 0 for city in CITIES):
        raise ValueError("其中一市沒有有效房地總價資料。")
    if any(areas["城市"].eq(city).sum() == 0 for city in CITIES):
        raise ValueError("其中一市沒有有效房地建物面積資料。")
    if prices.empty or totals.empty or areas.empty:
        raise ValueError("單價、總價或面積缺少有效樣本，無法製作八張圖。")

    # 根據交易日期設定研究年度，保留實際日期供讀者理解時間區間。
    for year, start, end in YEAR_RANGES:
        selected = data["交易日期_西元"].between(start, end)
        data.loc[selected, "研究年度"] = year
    if data["研究年度"].isna().any():
        raise ValueError("有紀錄無法分配研究年度。")

    # 年度欄位剛加入 data，重新取得子集合，讓箱型圖可以按年度分組。
    prices = data.dropna(subset=[PRICE_COLUMN]).copy()
    totals = data.loc[data["總價_萬元_繪圖"] > 0].copy()
    areas = data.loc[data["建物面積_坪_繪圖"] > 0].copy()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("清理後有效成交筆數：", len(data))
    print("可比較單價筆數：", len(prices))

    # 01：每月成交筆數。
    # 只比較完整自然月：2023/09 及 2026/09 並非完整月份，因此不納入月度圖。
    full_months = pd.period_range("2023-10", "2026-08", freq="M")
    data["交易月份_繪圖"] = data["交易日期_西元"].dt.to_period("M")
    prices["交易月份_繪圖"] = prices["交易日期_西元"].dt.to_period("M")
    monthly_data = data[data["交易月份_繪圖"].isin(full_months)]
    monthly_prices = prices[prices["交易月份_繪圖"].isin(full_months)]

    fig, ax = new_chart(bottom=0.21)
    for city in CITIES:
        sub = monthly_data[monthly_data["城市"] == city]
        counts = sub.groupby("交易月份_繪圖").size().reindex(full_months)
        ax.plot(range(len(full_months)), counts, color=CITY_COLORS[city],
                marker="o", markersize=3.4, linewidth=2.3, label=city)
    ticks = list(range(0, len(full_months), 3))
    ax.set_xticks(ticks, [str(full_months[i]) for i in ticks], rotation=35, ha="right")
    ax.set_ylabel("已揭露有效成交筆數（筆）")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False)
    save_chart(fig, CHARTS[0][0], "雙北每月預售屋成交筆數走勢",
               period_note="2023/10–2026/08（完整月）")

    # 02：每月單價中位數。
    # median() 是中位數，不會像平均數那樣容易受到少數高價紀錄影響。
    # X 軸與圖 01 相同，便於對照。
    fig, ax = new_chart(bottom=0.21)
    for city in CITIES:
        sub = monthly_prices[monthly_prices["城市"] == city]
        medians = sub.groupby("交易月份_繪圖")[PRICE_COLUMN].median().reindex(full_months)
        ax.plot(range(len(full_months)), medians, color=CITY_COLORS[city],
                marker="o", markersize=3.4, linewidth=2.3, label=city)
    ax.set_xticks(ticks, [str(full_months[i]) for i in ticks], rotation=35, ha="right")
    ax.set_ylabel("可比較房地單價中位數（萬元／坪）")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False)
    save_chart(fig, CHARTS[1][0], "雙北每月預售屋單價中位數走勢",
               period_note="2023/10–2026/08（完整月）")

    # 03：行政區成交占比。
    # 每個城市獨立計算前八名，其餘行政區合併為「其他」。
    # 為了讓圖表清楚，直接把行政區名稱和百分比寫在圓環上。
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2))
    fig.subplots_adjust(left=0.03, right=0.97, top=0.86, bottom=0.12, wspace=0.08)

    for ax, city in zip(axes, CITIES):
        # value_counts()：計算每個行政區的成交筆數，預設由多至少排序。
        counts = data.loc[data["城市"] == city, district_column].value_counts()
        top = counts.head(TOP_SHARE_DISTRICT_COUNT)
        other = int(counts.iloc[TOP_SHARE_DISTRICT_COUNT:].sum())

        names = list(top.index.astype(str))
        values = list(top.values)
        if other > 0:
            names.append("其他")
            values.append(other)

        # width 控制圓環厚度；radius 控制圓環在圖片中的大小。
        wedges, _ = ax.pie(values, colors=SHARE_COLORS[:len(values)], radius=1.30,
                           startangle=90, counterclock=False,
                           wedgeprops={"width": 0.57, "edgecolor": "white", "linewidth": 1.2})
        ax.text(0, 0, city, ha="center", va="center", fontsize=16, fontweight="bold")
        ax.set(aspect="equal")

        total = sum(values)
        for wedge, name, count in zip(wedges, names, values):
            # 取得扇區的中間角度，計算標籤應放在哪個位置。
            angle = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
            x = 1.015 * np.cos(angle)
            y = 1.015 * np.sin(angle)
            percentage = count / total * 100

            # 小於 5% 的扇區空間比較窄，使用較小字級。
            # 這兩個字級是依目前八圖定稿版與實際資料核對後設定。
            # 若更換資料批次，仍應檢查文字有沒有超出扇區。
            if percentage < 5:
                font_size = 10.5
            else:
                font_size = 16

            # 淺色扇區使用深色字；其餘使用白字，避免看不清楚。
            red, green, blue = wedge.get_facecolor()[:3]
            brightness = 0.299 * red + 0.587 * green + 0.114 * blue
            font_color = "#1F1F1F" if brightness > 0.72 else "white"
            label = f"{name}\n{percentage:.1f}%"
            ax.text(x, y, label, ha="center", va="center", fontsize=font_size,
                    color=font_color, linespacing=1.00, fontweight="medium")

    save_chart(fig, CHARTS[2][0], "行政區成交筆數占比：前八名與其他")

    # 04：行政區單價排行。
    # groupby() 先把同行政區的資料分成一組，再計算中位數和有效樣本數。
    # 兩市各選符合門檻的前五名，並使用相同的價格刻度。
    summaries = []
    for city in CITIES:
        sub = prices[prices["城市"] == city]
        ranked = sub.groupby(district_column)[PRICE_COLUMN].agg(["median", "count"])
        ranked = ranked[ranked["count"] >= MIN_DISTRICT_PRICE_N]
        ranked = ranked.sort_values("median", ascending=False).head(TOP_PRICE_DISTRICT_COUNT)
        summaries.append(ranked)
    if all(s.empty for s in summaries):
        raise ValueError("沒有行政區達到單價樣本門檻，請檢查清理資料。")
    xmax = max((s["median"].max() if not s.empty else 0) for s in summaries) * 1.34
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), sharex=True)
    fig.subplots_adjust(left=0.10, right=0.96, top=0.82, bottom=0.18, wspace=0.30)
    for ax, city, ranked in zip(axes, CITIES, summaries):
        ax.set_title(city, fontsize=14)
        if ranked.empty:
            ax.text(0.5, 0.5, "無達門檻行政區", transform=ax.transAxes,
                    ha="center", va="center")
            continue
        ordered = ranked.iloc[::-1]
        ax.barh(ordered.index.astype(str), ordered["median"], color=CITY_COLORS[city], height=0.62)
        ax.set_xlim(0, xmax)
        for i, value in enumerate(ordered["median"]):
            ax.text(value, i, f" {value:.1f}", va="center", fontsize=10)
        ax.grid(axis="x", alpha=0.2)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", labelsize=10)
        ax.set_xlabel("萬元／坪")
    save_chart(fig, CHARTS[3][0], "雙北行政區單價中位數前五名")

    # 05：成交總價級距占比。
    # pd.cut() 將房地成交總價放入指定區間；np.inf 表示最後一組沒有上限。
    # pd.crosstab() 計算各市每個總價區間有多少筆。
    price_bins = [0, 1000, 2000, 3000, 5000, np.inf]
    price_labels = ["未滿1000萬", "1000–2000萬", "2000–3000萬", "3000–5000萬", "5000萬以上"]
    totals["總價級距"] = pd.cut(totals["總價_萬元_繪圖"], bins=price_bins,
                             labels=price_labels, right=False)
    total_table = pd.crosstab(totals["城市"], totals["總價級距"])
    total_table = total_table.reindex(index=CITIES, columns=price_labels, fill_value=0)
    # 每市各區間的筆數 ÷ 該市有效總價筆數 × 100，即為該市的百分比。
    total_percent = total_table.div(total_table.sum(axis=1).replace(0, np.nan), axis=0) * 100
    fig, ax = new_chart(left=0.11, right=0.90, top=0.74, bottom=0.22)
    bottoms = np.zeros(len(CITIES))
    for label, color in zip(price_labels, BAND_COLORS):
        values = total_percent[label].fillna(0).to_numpy()
        bars = ax.barh(CITIES, values, left=bottoms, color=color, height=0.58, label=label,
                       edgecolor="white", linewidth=1)
        for bar, val, left in zip(bars, values, bottoms):
            if val >= 8:
                ax.text(left + val/2, bar.get_y()+bar.get_height()/2,
                        f"{val:.1f}%", ha="center", va="center", fontsize=12,
                        color="white" if color in BAND_COLORS[2:] else "#162E4A")
        bottoms += values
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("各市有效總價樣本占比（%）")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, fontsize=9,
              frameon=False)
    ax.grid(axis="x", alpha=0.16)
    ax.set_axisbelow(True)
    save_chart(fig, CHARTS[4][0], "雙北房地成交總價級距分布")

    # 06：房地建物面積級距占比。
    # 這裡的面積不是室內坪數，而是清理後扣除可拆分車位的建物面積。
    # 兩市在同一個級距並排，較容易比較占比。
    area_bins = [0, 15, 25, 35, 50, np.inf]
    area_labels = ["未滿15坪", "15–25坪", "25–35坪", "35–50坪", "50坪以上"]
    areas["面積級距"] = pd.cut(areas["建物面積_坪_繪圖"], bins=area_bins,
                              labels=area_labels, right=False)
    area_table = pd.crosstab(areas["城市"], areas["面積級距"])
    area_table = area_table.reindex(index=CITIES, columns=area_labels, fill_value=0)
    area_percent = area_table.div(area_table.sum(axis=1).replace(0, np.nan), axis=0) * 100
    fig, ax = new_chart(left=0.10, bottom=0.18)
    x = np.arange(len(area_labels))
    for city, offset in [(CITIES[0], -0.19), (CITIES[1], 0.19)]:
        values = area_percent.loc[city].fillna(0).to_numpy()
        bars = ax.bar(x + offset, values, width=0.36, color=CITY_COLORS[city], label=city)
        ax.bar_label(bars, labels=[f"{val:.1f}%" for val in values], fontsize=9, padding=3)
    ax.set_xticks(x, area_labels)
    ax.set_ylabel("各市有效面積樣本占比（%）")
    ax.set_ylim(0, max(10, float(np.nanmax(area_percent.to_numpy())) * 1.18))
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    save_chart(fig, CHARTS[5][0], "雙北房地建物面積級距比較")

    # 07：研究年度單價箱型圖。
    # 箱內橫線表示中位數，箱體上下緣分別是第 1、3 四分位數。
    # showfliers=False 只是不繪製離群點符號，統計仍使用全部有效樣本。
    box_values = []
    box_positions = []
    box_colors = []
    year_labels = []
    for i, (year, start, end) in enumerate(YEAR_RANGES):
        year_labels.append(start.replace("-", "/") + "–\n" + end.replace("-", "/"))
        for j, city in enumerate(CITIES):
            values = prices.loc[(prices["城市"] == city) &
                                (prices["研究年度"] == year), PRICE_COLUMN]
            if not values.empty:
                box_values.append(values.to_numpy())
                box_positions.append(i * 3 + j + 1)
                box_colors.append(CITY_COLORS[city])
    fig, ax = new_chart(bottom=0.19, left=0.10)
    result = ax.boxplot(box_values, positions=box_positions, widths=0.65,
                        patch_artist=True, showfliers=False,
                        medianprops={"color": "#263645", "linewidth": 2})
    for patch, color in zip(result["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.82)
    ax.set_xticks([1.5, 4.5, 7.5], year_labels)
    ax.set_xlim(0.35, 8.65)
    ax.set_ylabel("單價（萬元／坪）")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=CITY_COLORS[c]) for c in CITIES],
              labels=CITIES, loc="upper right", frameon=False)
    save_chart(fig, CHARTS[6][0], "各研究年度單價分布比較")

    # 08：每坪單價級距分布。
    # 一般級距寬度為每坪 15 萬元；最高價的少量紀錄合併到「以上」。
    # 每一筆有效單價都有計入，不是截尾或刪除離群值。
    # 各市按自身分布選擇級距範圍；不更改原始單價或刪除高價交易。
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), sharey=True)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.82, bottom=0.13, wspace=0.14)
    all_values = {}
    for city in CITIES:
        all_values[city] = prices.loc[prices["城市"] == city, PRICE_COLUMN].to_numpy()
    for ax, city in zip(axes, CITIES):
        values = all_values[city]
        # 以全樣本第 99.5 百分位附近設定「以上」級距的起點。
        # 最後一組包含全部高價樣本，不是截尾或排除離群值。
        # floor() 向下取整、ceil() 向上取整，使級距起點是 15 的倍數。
        begin = int(np.floor(values.min() / 15) * 15)
        high = int(np.ceil(np.quantile(values, 0.995) / 15) * 15)
        # arange() 建立每隔 15 的級距邊界；inf 表示高價端不設上限。
        boundaries = np.arange(begin, high + 15, 15)
        counts, _ = np.histogram(values, bins=np.append(boundaries, np.inf))
        if int(counts.sum()) != len(values):
            raise ValueError("級距統計筆數與全部有效單價筆數不一致。")
        percentage = counts / len(values) * 100
        positions = np.arange(len(counts))
        ax.bar(positions, percentage, width=0.91, color=CITY_COLORS[city])
        # 橫軸只標必要刻度；末端的「以上」清楚標示為開放級距。
        tick_pos = list(range(0, len(counts)-1, 2))
        if len(counts)-1 not in tick_pos:
            tick_pos.append(len(counts)-1)
        tick_labels = [f"{int(boundaries[i])}" if i < len(counts)-1
                       else f"{high}以上" for i in tick_pos]
        ax.set_xticks(tick_pos, tick_labels)
        ax.set_xlim(-0.55, len(counts)-0.45)
        ax.set_title(city, fontsize=14)
        ax.set_xlabel("單價級距（萬元／坪）")
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("各市成交占比（%）")
    save_chart(fig, CHARTS[7][0], "雙北每坪單價級距分布")

    # 匯出統計摘要：將每市的成交筆數、單價中位數與有效樣本數記錄為 CSV。
    # 這些數值供文件與圖表核對，不把不同指標誤認為相同的有效母體。
    audit = []
    for city in CITIES:
        d = data[data["城市"] == city]
        p = prices[prices["城市"] == city]
        t = totals[totals["城市"] == city]
        a = areas[areas["城市"] == city]
        audit.append({
            "城市": city,
            "有效成交筆數": len(d),
            "有效單價筆數": len(p),
            "單價中位數_萬元坪": p[PRICE_COLUMN].median(),
            "有效總價筆數": len(t),
            "有效面積筆數": len(a),
            "研究開始日": START_DATE.date(),
            "研究結束日": END_DATE.date(),
        })
    pd.DataFrame(audit).to_csv(OUTPUT_DIR / "eight_chart_summary.csv",
                               index=False, encoding="utf-8-sig")

    # 輸出研究年度統計。依研究年度的實際日期順序排列，而非按文字排序。
    # 接著輸出完整月份的成交筆數與單價中位數，供圖 01、02 驗算。
    year_order = [name for name, _, _ in YEAR_RANGES]
    annual_counts = data.groupby(["研究年度", "城市"]).size().rename("成交筆數").reset_index()
    annual_prices = prices.groupby(["研究年度", "城市"])[PRICE_COLUMN].agg(
        單價中位數_萬元坪="median", 單價樣本數="count").reset_index()
    annual_audit = annual_counts.merge(annual_prices, on=["研究年度", "城市"], how="left")
    annual_audit["研究年度"] = pd.Categorical(annual_audit["研究年度"], categories=year_order, ordered=True)
    annual_audit = annual_audit.sort_values(["研究年度", "城市"])
    annual_audit.to_csv(OUTPUT_DIR / "research_year_statistics.csv", index=False, encoding="utf-8-sig")

    monthly_counts = monthly_data.groupby(["交易月份_繪圖", "城市"]).size().rename("成交筆數").reset_index()
    monthly_price_stats = monthly_prices.groupby(["交易月份_繪圖", "城市"])[PRICE_COLUMN].agg(
        單價中位數_萬元坪="median", 單價樣本數="count").reset_index()
    monthly_audit = monthly_counts.merge(monthly_price_stats,
                                        on=["交易月份_繪圖", "城市"], how="left")
    monthly_audit = monthly_audit.rename(columns={"交易月份_繪圖": "交易月份"})
    monthly_audit.to_csv(OUTPUT_DIR / "full_month_statistics.csv", index=False, encoding="utf-8-sig")

    print("完成：8 張 16:9 PNG 與 3 份統計摘要 CSV。")
    print("請在 Spyder 逐張核對標題、數字、字體、圖面是否過密及來源批次。")


if __name__ == "__main__":
    main()
