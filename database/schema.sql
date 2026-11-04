-- 預售屋成交資料表：存放完成清理的交易資料，供 SQL 統計核對。
-- 不包含密碼或任何私人連線設定。

-- 建立預售屋成交分析使用的資料庫。
CREATE DATABASE IF NOT EXISTS presale_analysis
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE presale_analysis;

-- 每一列代表清理後 CSV 的一筆房地交易（純車位已在清理階段排除）。
-- total_price_yuan 與 building_area_m2 保留官方原始值，可能含車位；
-- 房地總價及面積分析請使用清理 CSV 中扣除可拆分車位的欄位。
-- record_id 是資料庫自動產生的識別碼，不是官方實價登錄交易編號。
CREATE TABLE IF NOT EXISTS presale_transactions (
    record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    city VARCHAR(10) NOT NULL,
    district VARCHAR(30) NOT NULL,
    trade_date DATE NOT NULL,
    unit_price_10k_ping DECIMAL(14,4) NULL,
    total_price_yuan DECIMAL(18,2) NULL,
    building_area_m2 DECIMAL(16,4) NULL,
    source_zip VARCHAR(255) NULL,
    source_csv VARCHAR(255) NULL,
    PRIMARY KEY (record_id),
    INDEX idx_city_date (city, trade_date),
    INDEX idx_city_district (city, district)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

-- 檢查是否成功建立資料表。
SHOW TABLES;
SHOW COLUMNS FROM presale_transactions;
