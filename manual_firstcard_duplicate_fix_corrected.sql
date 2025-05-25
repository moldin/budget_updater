-- Corrected FirstCard Duplicate Fix SQL Queries
-- The issue is actual duplicates within the same source file, not overlapping sources

-- Step 1: Create backup table (execute first)
CREATE TABLE `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions_firstcard_backup_corrected` AS
SELECT *
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card';

-- Step 2: Check current state before fix
SELECT 
  'Current State' as status,
  COUNT(*) as total_transactions,
  SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as total_outflow,
  SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as total_inflow
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
  AND ((outflow IS NOT NULL AND outflow != '') OR (inflow IS NOT NULL AND inflow != ''));

-- Step 3: Count duplicate business_keys that will be cleaned
SELECT 
  'Duplicates to clean' as status,
  COUNT(DISTINCT business_key) as duplicate_business_keys,
  SUM(count - 1) as extra_duplicate_rows
FROM (
  SELECT business_key, COUNT(*) as count
  FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
  WHERE account = '💳 First Card'
  GROUP BY business_key
  HAVING COUNT(*) > 1
);

-- Step 4: Preview what transactions will be kept (one per business_key)
-- This uses ROW_NUMBER() to keep the first occurrence of each business_key
SELECT 
  business_key,
  date,
  outflow,
  inflow,
  memo,
  source_file,
  ROW_NUMBER() OVER (PARTITION BY business_key ORDER BY upload_timestamp, date) as row_num
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
  AND business_key IN (
    SELECT business_key 
    FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
    WHERE account = '💳 First Card'
    GROUP BY business_key
    HAVING COUNT(*) > 1
  )
ORDER BY business_key, row_num
LIMIT 20;

-- Step 5: Execute the duplicate removal (CAREFUL - this deletes data!)
-- This keeps only the first occurrence of each business_key based on upload_timestamp
DELETE FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
  AND CONCAT(business_key, '_', CAST(upload_timestamp AS STRING)) NOT IN (
    SELECT CONCAT(business_key, '_', CAST(MIN(upload_timestamp) AS STRING))
    FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
    WHERE account = '💳 First Card'
    GROUP BY business_key
  );

-- Step 6: Verify results after fix
SELECT 
  'After Fix' as status,
  COUNT(*) as total_transactions,
  SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as total_outflow,
  SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as total_inflow,
  SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) - 
  SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as net_balance
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
  AND ((outflow IS NOT NULL AND outflow != '') OR (inflow IS NOT NULL AND inflow != ''));

-- Step 7: Check for remaining duplicates (should be 0)
SELECT 
  'Remaining duplicates' as status,
  COUNT(*) as duplicate_business_keys
FROM (
  SELECT business_key, COUNT(*) as count
  FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
  WHERE account = '💳 First Card'
  GROUP BY business_key
  HAVING COUNT(*) > 1
);

-- Step 8: Final summary by source
SELECT 
  source_file,
  COUNT(*) as count,
  MIN(date) as min_date,
  MAX(date) as max_date
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
GROUP BY source_file
ORDER BY count DESC; 