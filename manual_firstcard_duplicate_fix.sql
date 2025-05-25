-- Manual FirstCard Duplicate Fix SQL Queries
-- Execute these in BigQuery Console to fix the duplicate problem

-- Step 1: Create backup table (execute first)
CREATE TABLE `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions_firstcard_backup_manual` AS
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

-- Step 3: Check what will be removed
SELECT 
  'Will Remove' as status,
  COUNT(*) as transactions_to_remove,
  SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as outflow_to_remove,
  SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as inflow_to_remove
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card' 
  AND source_file = 'orig_google_sheet_rev_engineered'
  AND date >= '2023-05-01'
  AND ((outflow IS NOT NULL AND outflow != '') OR (inflow IS NOT NULL AND inflow != ''));

-- Step 4: Execute the duplicate removal (execute after reviewing above)
DELETE FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card' 
  AND source_file = 'orig_google_sheet_rev_engineered'
  AND date >= '2023-05-01';

-- Step 5: Verify results after fix
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

-- Step 6: Check for remaining duplicates
SELECT 
  business_key,
  COUNT(*) as count
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
GROUP BY business_key
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- Step 7: Final summary
SELECT 
  source_file,
  COUNT(*) as count,
  MIN(date) as min_date,
  MAX(date) as max_date
FROM `aspiro-budget-analysis.budget_data_warehouse.sheet_transactions`
WHERE account = '💳 First Card'
GROUP BY source_file
ORDER BY count DESC; 