# -*- coding: utf-8 -*-
"""檢查八張 PNG 的尺寸，建立圖表索引與查核清單。

輸入：charts/ 下的八張 PNG 與三份彙總 CSV。
輸出：docs/chart_catalog.md、docs/chart_inventory.csv。
只檢查圖表是否存在、尺寸是否正確，不更動成交資料或統計值。
"""

from pathlib import Path

import pandas as pd
from PIL import Image

# 由 src/ 往上一層找到專案根目錄，避免依賴 Spyder 的工作目錄。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHART_DIR = PROJECT_ROOT / "charts"
DOCS_DIR = PROJECT_ROOT / "docs"

# 每張圖各自回答一個問題，索引只收錄目前保留的八張主要圖表。
CHARTS = [
    ("01_monthly_transaction_count.png", "每月成交筆數走勢", "已揭露有效成交筆數如何逐月變化？"),
    ("02_monthly_median_price.png", "每月單價中位數走勢", "雙北單價中位數如何隨月份變化？"),
    ("03_district_count_share.png", "行政區成交集中程度", "各市前八名行政區合計占多少成交樣本？"),
    ("04_district_median_price_top5.png", "行政區單價中位數排行", "哪些行政區的房地單價中位數較高？"),
    ("05_total_price_band_share.png", "房地成交總價級距", "各市已揭露成交樣本以哪個房地總價帶為主？"),
    ("06_area_band_distribution.png", "房地建物面積級距", "各市已揭露成交樣本主要集中在哪個建物面積級距？"),
    ("07_city_year_price_boxplot.png", "城市與研究年度單價箱型圖", "不同城市與研究年度的單價分布差異如何？"),
    ("08_unit_price_band_distribution.png", "單價級距分布圖", "各市每坪單價集中在哪些級距？"),
]
STAT_FILES = ["charts/eight_chart_summary.csv", "charts/full_month_statistics.csv",
              "charts/research_year_statistics.csv"]


def main():
    """確認檔案及尺寸，建立與實際 PNG 一致的圖表清單。"""
    if not CHART_DIR.is_dir():
        raise FileNotFoundError("找不到 charts 資料夾，請先執行 create_charts.py。")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # records 用於 CSV 清單；lines 用於 Markdown 圖表索引。
    records = []
    lines = [
        "# 雙北預售屋成交分析｜八張圖表索引", "",
        "- **地區**：臺北市、新北市。", 
        "- **研究期間**：2023/09/21～2026/09/20（依交易日期）。",
        "- **完整自然月圖**：2023/10～2026/08。",
        "- **資料來源**：內政部實價登錄預售屋公開批次資料。",
        "- **統計對象**：依本專案既有清理規則取得的有效揭露交易；非全市場成交總量。",
        "", "## 圖表與分析目的", "",
    ]
    for number, (filename, title, purpose) in enumerate(CHARTS, start=1):
        path = CHART_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"正式圖表不存在：{path}")
        # 只讀取圖片寬度、高度，不修改 PNG 內容。
        with Image.open(path) as picture:
            width, height = picture.size
        # 長寬比須接近 16:9；不合格就停止產生正式索引。
        if abs(width / height - 16 / 9) > 0.01:
            raise ValueError(f"圖表不是 16:9：{filename}")
        records.append({"圖號": f"{number:02d}", "檔名": filename,
                        "圖表": title, "分析目的": purpose,
                        "檢查結果": "正常", "寬度px": width, "高度px": height})
        lines.extend([
            f"### {number:02d}｜{title}", "",
            f"**分析問題：**{purpose}", "",
            f"![{title}](../charts/{filename})", "",
        ])

    lines.extend(["## 相關統計表", ""])
    for name in STAT_FILES:
        if not (PROJECT_ROOT / name).is_file():
            raise FileNotFoundError(f"缺少彙總表：{name}")
        lines.append(f"- [`{name}`](../{name})")

    lines.extend([
        "", "## 圖表口徑與注意事項", "",
        "- 每張圖的樣本數依指標的有效值而定；單價、房地總價、面積可能不同。",
        "- 單價使用清理後的官方房地單價；房地總價與建物面積扣除可明確拆分的車位部分。",
        "- 行政區成交占比以各城市全部有效交易筆數為分母；『其他』包含未列出的行政區。",
        "- 單價排行只採有效單價樣本至少 30 筆的行政區。",
        "- 房地建物面積仍包含共有部分，不是室內實坪。",
        "- 箱型圖不顯示極端點符號，但仍以全部有效樣本計算統計值。",
        "- 單價級距圖採每 15 萬元／坪一級距，另以開放式末端級距收納全部更高價格，沒有排除任何單價樣本。",
        "- 價格及交易量受到已揭露資料與個案組成影響，不能推論為價格指數或因果效果。",
        "", "各圖的真實數值與解讀可參閱 [分析說明](analysis_notes.md)。",
    ])
    # 建立可用 Excel 開啟的清單，並輸出包含相對路徑圖片的 Markdown 索引。
    pd.DataFrame(records).to_csv(DOCS_DIR / "chart_inventory.csv", index=False,
                                 encoding="utf-8-sig")
    (DOCS_DIR / "chart_catalog.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"完成 {len(records)} 張 16:9 圖表檢查，圖表索引已更新。")


if __name__ == "__main__":
    main()
