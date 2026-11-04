-- 使用 MySQL 核對成交筆數、日期範圍與分組統計。
-- 本檔不會更動交易資料，可於 schema.sql 建立資料表後使用。

USE presale_analysis;

-- 1. 全部清理後有效樣本數與實際交易日期範圍。
SELECT COUNT(*) AS total_rows,
       MIN(trade_date) AS earliest_date,
       MAX(trade_date) AS latest_date
FROM presale_transactions;

-- 2. 依城市統計筆數、可比較單價樣本數、平均單價。
-- 單價為萬元/坪，NULL 不會列入 AVG 或 COUNT(欄位)。
SELECT city,
       COUNT(*) AS transaction_count,
       COUNT(unit_price_10k_ping) AS price_sample_count,
       ROUND(AVG(unit_price_10k_ping), 2) AS avg_price_10k_ping
FROM presale_transactions
GROUP BY city
ORDER BY city;

-- 3. 完整自然月每月已揭露成交筆數。
-- 與繪圖程式相同，僅納入 2023/10 至 2026/08。
SELECT DATE_FORMAT(trade_date, '%Y-%m') AS trade_month,
       city,
       COUNT(*) AS transaction_count
FROM presale_transactions
WHERE trade_date >= '2023-10-01'
  AND trade_date < '2026-09-01'
GROUP BY DATE_FORMAT(trade_date, '%Y-%m'), city
ORDER BY trade_month, city;

-- 4. 三個研究年度成交筆數：每年 9/21 至次年 9/20。
SELECT CASE
           WHEN trade_date BETWEEN '2023-09-21' AND '2024-09-20' THEN '第1研究年'
           WHEN trade_date BETWEEN '2024-09-21' AND '2025-09-20' THEN '第2研究年'
           WHEN trade_date BETWEEN '2025-09-21' AND '2026-09-20' THEN '第3研究年'
       END AS research_year,
       city,
       COUNT(*) AS transaction_count
FROM presale_transactions
GROUP BY research_year, city
ORDER BY research_year, city;

-- 5. 各行政區成交筆數、單價有效樣本數及平均單價。
-- 此查詢使用 AVG，與圖表的中位數屬不同統計指標。
SELECT city,
       district,
       COUNT(*) AS transaction_count,
       COUNT(unit_price_10k_ping) AS price_sample_count,
       ROUND(AVG(unit_price_10k_ping), 2) AS avg_price_10k_ping
FROM presale_transactions
GROUP BY city, district
ORDER BY city, transaction_count DESC, district;

-- 6. 檢查已保留來源 ZIP 資訊的資料筆數。
SELECT source_zip, COUNT(*) AS transaction_count
FROM presale_transactions
GROUP BY source_zip
ORDER BY source_zip;
