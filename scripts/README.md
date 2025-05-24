# BigQuery Data Warehouse för Budget Updater

Detta är den **förbättrade versionen** av BigQuery-implementationen som följer korrekt data warehouse-design med separata lager för staging, clean data och business logic.

## 🏗️ **Arkitektur (V2 - Data Warehouse Approach)**

### **📦 STAGING LAYER - Raw Data**
Separata tabeller per bank med exakt samma struktur som Excel-filerna:
- `seb_transactions_raw` - SEB data precis som i Excel
- `revolut_transactions_raw` - Revolut data precis som i Excel  
- `firstcard_transactions_raw` - FirstCard data precis som i Excel
- `strawberry_transactions_raw` - Strawberry data precis som i Excel

### **🧹 CLEAN LAYER - Standardized Data**
- `transactions_standardized` - Enhetlig struktur från alla banker
- Standardiserade kolumner: `transaction_date`, `description`, `amount`, `currency`
- Referenser tillbaka till staging-tabeller för spårbarhet

### **📊 BUSINESS LAYER - Categories & Rules**
- `transaction_categories` - Kategorier för budgetklassificering
- `categorization_rules` - Automatiska kategoriseringsregler
- `monthly_summary` (view) - Månatlig sammanfattning
- `category_summary` (view) - Kategorivis analys

### **⚙️ OPERATIONAL LAYER**
- `file_processing_log` - Logg över bearbetade filer

## 📋 **Översikt Scripts**

| Script | Beskrivning |
|--------|-------------|
| `setup_bigquery_tables_v2.py` | **ANVÄND DENNA** - Skapar korrekt data warehouse-struktur |
| `upload_transactions_v2.py` | **ANVÄND DENNA** - Laddar upp med staging → standardized approach |
| `query_transactions.py` | Kör fördefinierade queries på standardized data |

## 🚀 **Kom igång**

### **1. Förutsättningar**

```bash
pip install google-cloud-bigquery pandas openpyxl
```

Se till att du har:
- ✅ Google Cloud Project konfigurerat
- ✅ BigQuery API aktiverat  
- ✅ Autentisering konfigurerad (service account eller `gcloud auth`)
- ✅ Korrekt `config.py` med dina GCP-inställningar

### **2. Skapa BigQuery Data Warehouse**

```bash
# Skapa alla tabeller och views (använd V2!)
python scripts/setup_bigquery_tables_v2.py
```

Detta skapar:
- ✅ 4 staging-tabeller (en per bank)
- ✅ 1 standardized transactions-tabell
- ✅ Category och rules-tabeller
- ✅ Analysis views
- ✅ Default kategorier

### **3. Ladda upp transaktionsdata**

```bash
# Ladda upp en fil (staging + transformation)
python scripts/upload_transactions_v2.py data/seb.xlsx --bank seb

# Ladda upp alla filer i en mapp
python scripts/upload_transactions_v2.py data/ --bank all

# Bara staging (ingen transformation till standardized)
python scripts/upload_transactions_v2.py data/revolut_new.xlsx --bank revolut --stage-only

# Dry run för att se vad som skulle hända
python scripts/upload_transactions_v2.py data/seb.xlsx --bank seb --dry-run
```

### **4. Query:a och analysera data**

```bash
# Översikt över all data
python scripts/query_transactions.py summary

# Senaste transaktioner
python scripts/query_transactions.py recent --limit 20

# Transaktioner för specifik bank
python scripts/query_transactions.py by_bank --bank seb

# Månatlig sammanfattning
python scripts/query_transactions.py monthly

# Stora transaktioner
python scripts/query_transactions.py large --threshold 5000

# Sök i beskrivningar
python scripts/query_transactions.py search --search "ICA"

# Exportera till CSV
python scripts/query_transactions.py summary --output csv
```

## 💡 **Fördelar med V2-arkitekturen**

### **✅ Korrekt Data Warehouse Design**
- **Staging**: Raw data exakt som från källan
- **Clean**: Standardiserat format för analys  
- **Business**: Kategorier och regler
- **Analysis**: Views för rapportering

### **✅ Flexibilitet**
- Lätt att lägga till nya banker
- Kan ändra transformationslogik utan att påverka raw data
- Enkel att spåra data från källa till slutresultat

### **✅ Data Quality**
- Fullständig audit trail
- Möjlighet att "replay" transformationer
- Separation av concerns

### **✅ Performance**
- BigQuery-optimerad med partitionering och clustering
- Effektiva queries med rätt joins
- Ingen waste på NULL-kolumner

## 📊 **Exempel Queries**

### **Direktaccess till standardized data:**
```sql
-- Alla transaktioner senaste månaden
SELECT transaction_date, source_bank, description, amount
FROM `project.dataset.transactions_standardized` 
WHERE transaction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH)
ORDER BY transaction_date DESC;

-- Total utgifter per bank
SELECT source_bank, 
       SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses
FROM `project.dataset.transactions_standardized`
GROUP BY source_bank;
```

### **Analysis via views:**
```sql
-- Använd färdiga views
SELECT * FROM `project.dataset.monthly_summary` 
WHERE year = 2024;

SELECT * FROM `project.dataset.category_summary`
WHERE budget_type = 'EXPENSE'
ORDER BY total_amount DESC;
```

### **Raw data access för debugging:**
```sql
-- Kolla raw SEB data
SELECT * FROM `project.dataset.seb_transactions_raw` 
WHERE file_hash = 'abc123...'
LIMIT 10;
```

## 🔧 **ETL Workflow**

1. **Extract**: Läs Excel-filer
2. **Load → Staging**: Ladda raw data till bank-specifika tabeller
3. **Transform → Clean**: Standardisera till enhetligt format
4. **Business Logic**: Kategorisera transaktioner
5. **Analysis**: Query:a via views och standardized tables

## 🆚 **V1 vs V2 Jämförelse**

| Aspekt | V1 (En stor tabell) | V2 (Data Warehouse) |
|--------|---------------------|---------------------|
| **Design** | ❌ Monolitisk | ✅ Layered architecture |
| **Flexibilitet** | ❌ Rigid schema | ✅ Modulär design |  
| **Storage** | ❌ Många NULL kolumner | ✅ Optimerad storage |
| **Underhåll** | ❌ Svårt att ändra | ✅ Enkelt att utveckla |
| **Audit Trail** | ❌ Begränsad | ✅ Fullständig spårbarhet |
| **Best Practices** | ❌ Inte följda | ✅ Korrekt DW-design |

## 🏃‍♂️ **Quick Start**

```bash
# 1. Skapa data warehouse
python scripts/setup_bigquery_tables_v2.py

# 2. Ladda upp SEB data  
python scripts/upload_transactions_v2.py data/seb.xlsx --bank seb

# 3. Se resultatet
python scripts/query_transactions.py summary
```

🎉 **Nu har du en professionell BigQuery data warehouse för dina transaktioner!** 