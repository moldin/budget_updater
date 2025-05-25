# Revolut Data Format Documentation

## Översikt
Detta dokument beskriver detaljerat Revoluts dataformat för transaktionsexporter som används i Budget Updater-projektet.

**Datum:** 2025-05-25  
**Bank:** Revolut Ltd  
**Filformat:** Excel (.xlsx)  
**Syfte:** Detaljerad referens för Revolut-datahantering

---

## 1. Filstruktur

### Filnamn
- `data/revolut.xlsx` (Revolut transaktionsdata)

### Excel-struktur
- **Sheet:** Standard sheet (första sheet)
- **Engine:** `openpyxl` (för .xlsx-filer)
- **Header:** Rad 1 innehåller kolumnnamn
- **Data:** Börjar på rad 2

---

## 2. Kolumnstruktur

### Fullständig Schema
| Kolumn | Datatyp | Obligatorisk | Beskrivning | Exempel |
|--------|---------|--------------|-------------|---------|
| `Type` | String | ✅ | Transaktionstyp | `CARD_PAYMENT` |
| `Product` | String | ✅ | Produkttyp | `Current` |
| `Started Date` | DateTime | ✅ | Startdatum för transaktion | `2022-01-02 17:47:13` |
| `Completed Date` | DateTime | ✅ | Slutförd datum | `2022-01-03 09:13:08` |
| `Description` | String | ✅ | Transaktionsbeskrivning | `APPLE.COM/BILL` |
| `Amount` | Float | ✅ | Transaktionsbelopp | `-139.0` |
| `Fee` | Float | ✅ | Avgift för transaktion | `3.21` |
| `Currency` | String | ✅ | Valuta | `SEK` |
| `State` | String | ✅ | Transaktionsstatus | `COMPLETED` |
| `Balance` | Float | ✅ | Saldo efter transaktion | `980.42` |

### Obligatoriska Kolumner för Parser
- `Completed Date` (används som primärt datum)
- `Description` (används som beskrivning)
- `Amount` (används som transaktionsbelopp)
- `Fee` (används för avgiftsberäkning)

---

## 3. Dataformat och Konventioner

### Datumformat
- **Format:** `YYYY-MM-DD HH:MM:SS` (ISO 8601 med tid)
- **Timezone:** UTC (Revolut använder UTC)
- **Parser-hantering:** Extraherar endast datum-delen för standardisering
- **Exempel:** `2022-01-03 09:13:08` → `2022-01-03`

### Beloppslogik
- **Negativa belopp:** Utgifter/debiteringar (vanligast)
- **Positiva belopp:** Inkomster/krediteringar
- **Nollbelopp:** Informationstransaktioner
- **Valuta:** Primärt SEK, men kan vara andra valutor
- **Decimaler:** 2 decimaler

### Avgiftshantering (Unikt för Revolut)
- **Fee-kolumn:** Separata avgifter för transaktioner
- **Beräkning:** `Final_Amount = Amount - Fee`
- **Logik:** Avgifter läggs alltid till utgifter (gör belopp mer negativt)
- **Exempel:** Amount: -139.0, Fee: 3.21 → Final: -142.21

### Transaktionstyper
- `CARD_PAYMENT` - Kortbetalningar
- `TRANSFER` - Överföringar
- `EXCHANGE` - Valutaväxling
- `TOPUP` - Påfyllningar
- `ATM` - Uttag från bankomat

---

## 4. Parser Implementation

### Konfiguration
```python
def parse_revolut(file_path: str | Path) -> pd.DataFrame | None:
    # Grundläggande parsing
    parsed_df = parse_excel_generic(
        file_path,
        engine='openpyxl',
        column_map={
            'date': ['Completed Date'],
            'desc': ['Description'],
            'amount': ['Amount'],
        },
        date_type='string',
        required_columns=['date', 'desc', 'amount']
    )
    
    # Specialhantering för avgifter
    if parsed_df is not None:
        # Läs Fee-kolumn separat
        df = pd.read_excel(file_path, engine='openpyxl')
        fee_col = find_fee_column(df)
        
        if fee_col:
            parsed_df['Fee'] = pd.to_numeric(df[fee_col], errors='coerce').fillna(0)
            # Subtrahera avgifter från belopp
            parsed_df['ParsedAmount'] = parsed_df['ParsedAmount'] - parsed_df['Fee']
            parsed_df.drop('Fee', axis=1, inplace=True)
    
    return parsed_df
```

### Transformationsregler
1. **Datum:** `Completed Date` → `ParsedDate` (endast datum-del)
2. **Beskrivning:** `Description` → `ParsedDescription`
3. **Belopp:** `Amount - Fee` → `ParsedAmount`

---

## 5. BigQuery Staging Schema

### Tabell: `revolut_transactions_raw`
```sql
CREATE TABLE `revolut_transactions_raw` (
    -- Metadata
    file_hash STRING NOT NULL,
    source_file STRING NOT NULL,
    upload_timestamp TIMESTAMP NOT NULL,
    row_number INT64 NOT NULL,
    business_key STRING NOT NULL,
    
    -- Revolut-specifika kolumner (exakt som Excel)
    type STRING,
    product STRING,
    started_date TIMESTAMP,
    completed_date TIMESTAMP,
    description STRING,
    amount FLOAT64,
    fee FLOAT64,
    currency STRING,
    state STRING,
    balance FLOAT64
)
PARTITION BY DATE(completed_date)
CLUSTER BY business_key;
```

### Kolumnmappning Excel → BigQuery
| Excel Kolumn | BigQuery Kolumn | Transformation |
|--------------|-----------------|----------------|
| `Type` | `type` | Direkt kopiering |
| `Product` | `product` | Direkt kopiering |
| `Started Date` | `started_date` | `PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', ...)` |
| `Completed Date` | `completed_date` | `PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', ...)` |
| `Description` | `description` | Direkt kopiering |
| `Amount` | `amount` | Direkt kopiering |
| `Fee` | `fee` | Direkt kopiering |
| `Currency` | `currency` | Direkt kopiering |
| `State` | `state` | Direkt kopiering |
| `Balance` | `balance` | Direkt kopiering |

---

## 6. Business Key Generation

### Algoritm
```python
def create_business_key(row):
    date_str = str(row['completed_date'])[:10]
    amount_str = f"{row['amount']:.2f}"
    fee_str = f"{row['fee']:.2f}"
    desc_normalized = str(row['description']).strip().lower()[:50]
    
    key_components = f"revolut|{date_str}|{amount_str}|{fee_str}|{desc_normalized}"
    return hashlib.md5(key_components.encode('utf-8')).hexdigest()
```

### Unikhet
- Kombinerar datum, belopp, avgift och beskrivning
- Inkluderar avgift för att säkerställa unikhet
- Medelhög risk för kollisioner (Revolut har mindre unika identifierare)

---

## 7. Transformation till Standardformat

### SQL för `transactions_standardized`
```sql
INSERT INTO `transactions_standardized`
SELECT 
    business_key,
    'revolut' as source_bank,
    DATE(completed_date) as transaction_date,
    description as description,
    (amount - COALESCE(fee, 0)) as amount,  -- Subtrahera avgifter
    CASE 
        WHEN (amount - COALESCE(fee, 0)) < 0 THEN 'OUTFLOW'
        WHEN (amount - COALESCE(fee, 0)) > 0 THEN 'INFLOW'
        ELSE 'ZERO'
    END as transaction_type,
    source_file,
    upload_timestamp
FROM `revolut_transactions_raw`
WHERE completed_date IS NOT NULL
AND state = 'COMPLETED';
```

### Google Sheets Format Transformation
```sql
INSERT INTO `sheet_transactions`
SELECT 
    DATE(completed_date) as date,
    CASE 
        WHEN (amount - COALESCE(fee, 0)) < 0 THEN FORMAT("%.2f", ABS(amount - COALESCE(fee, 0)))
        ELSE ""
    END as outflow,
    CASE 
        WHEN (amount - COALESCE(fee, 0)) > 0 THEN FORMAT("%.2f", amount - COALESCE(fee, 0))
        ELSE ""
    END as inflow,
    "" as category,  -- To be categorized later
    "💳 Revolut" as account,
    CONCAT(description, 
           CASE WHEN COALESCE(fee, 0) > 0 THEN CONCAT(" (Fee: ", FORMAT("%.2f", fee), ")") ELSE "" END
    ) as memo,
    "✅" as status,
    business_key,
    'revolut' as source_bank
FROM `revolut_transactions_raw`
WHERE state = 'COMPLETED';
```

---

## 8. Avgiftshantering (Revolut-specifik)

### Avgiftstyper
- **Utlandsavgifter:** För transaktioner utanför EU
- **Valutaväxlingsavgifter:** För icke-SEK transaktioner
- **ATM-avgifter:** För uttag över månadsgräns
- **Premiumavgifter:** För vissa tjänster

### Beräkningslogik
```python
def calculate_final_amount(amount: float, fee: float) -> float:
    """
    Beräkna slutligt belopp inklusive avgifter.
    Avgifter läggs alltid till utgifter (gör belopp mer negativt).
    """
    if pd.isna(fee) or fee == 0:
        return amount
    
    # Avgifter subtraheras alltid (läggs till utgifter)
    return amount - fee
```

### Avgiftsrapportering
```sql
-- Sammanfattning av avgifter per månad
SELECT 
    DATE_TRUNC(DATE(completed_date), MONTH) as month,
    COUNT(*) as transactions_with_fees,
    SUM(fee) as total_fees,
    AVG(fee) as avg_fee
FROM `revolut_transactions_raw`
WHERE fee > 0
GROUP BY month
ORDER BY month;
```

---

## 9. Datavalidering

### Obligatoriska Kontroller
```python
def validate_revolut_data(df: pd.DataFrame) -> List[str]:
    errors = []
    
    # Kontrollera obligatoriska kolumner
    required_cols = ['Completed Date', 'Description', 'Amount', 'Fee']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
    
    # Kontrollera datum
    invalid_dates = df['Completed Date'].isna().sum()
    if invalid_dates > 0:
        errors.append(f"Invalid dates found: {invalid_dates} rows")
    
    # Kontrollera belopp
    invalid_amounts = df['Amount'].isna().sum()
    if invalid_amounts > 0:
        errors.append(f"Invalid amounts found: {invalid_amounts} rows")
    
    # Kontrollera avgifter (ska vara numeriska eller 0)
    invalid_fees = pd.to_numeric(df['Fee'], errors='coerce').isna().sum()
    if invalid_fees > 0:
        errors.append(f"Invalid fees found: {invalid_fees} rows")
    
    # Kontrollera status
    invalid_states = df[~df['State'].isin(['COMPLETED', 'PENDING', 'DECLINED'])].shape[0]
    if invalid_states > 0:
        errors.append(f"Invalid states found: {invalid_states} rows")
    
    return errors
```

### Revolut-specifik Validering
- **Status-kontroll:** Endast 'COMPLETED' transaktioner processas
- **Valuta-kontroll:** Kontrollera att valuta är giltig
- **Avgifts-logik:** Avgifter ska aldrig vara negativa
- **Datum-logik:** `Completed Date` ska vara efter `Started Date`

---

## 10. Statistik och Kvalitetsmätningar

### Aktuell Data (revolut.xlsx)
- **Total transaktioner:** ~130 rader
- **Datumintervall:** 2022-01-02 till 2022-01-31
- **Genomsnittlig avgift:** Varierar per transaktionstyp
- **Vanligaste transaktionstyper:**
  - CARD_PAYMENT (kortbetalningar)
  - TRANSFER (överföringar)
  - EXCHANGE (valutaväxling)

### Avgiftsanalys
```sql
SELECT 
    type,
    COUNT(*) as transaction_count,
    SUM(CASE WHEN fee > 0 THEN 1 ELSE 0 END) as transactions_with_fees,
    AVG(fee) as avg_fee,
    SUM(fee) as total_fees
FROM `revolut_transactions_raw`
GROUP BY type
ORDER BY total_fees DESC;
```

---

## 11. Felsökning och Vanliga Problem

### Vanliga Fel
1. **Datum-parsing:** Revolut använder full timestamp, extrahera endast datum
2. **Avgifts-hantering:** Glöm inte att subtrahera avgifter från belopp
3. **Status-filtrering:** Inkludera endast 'COMPLETED' transaktioner
4. **Valuta-hantering:** Kontrollera att alla belopp är i samma valuta

### Debugging-tips
```python
# Kontrollera avgifts-distribution
print("Fee distribution:", df['Fee'].describe())

# Kontrollera status-fördelning
print("Status counts:", df['State'].value_counts())

# Kontrollera valuta-fördelning
print("Currency counts:", df['Currency'].value_counts())

# Kontrollera datum-format
print("Date sample:", df['Completed Date'].head())
```

### Avgifts-debugging
```python
# Hitta transaktioner med avgifter
fees_df = df[df['Fee'] > 0]
print(f"Transactions with fees: {len(fees_df)}")
print(f"Total fees: {fees_df['Fee'].sum()}")

# Kontrollera avgifts-beräkning
df['Final_Amount'] = df['Amount'] - df['Fee']
print("Amount vs Final Amount comparison:")
print(df[['Amount', 'Fee', 'Final_Amount']].head())
```

---

## 12. Framtida Utveckling

### Möjliga Förbättringar
1. **Valuta-konvertering:** Automatisk konvertering till SEK
2. **Avgifts-kategorisering:** Klassificera olika typer av avgifter
3. **Trend-analys:** Analys av avgifts-utveckling över tid
4. **Merchant-kategorisering:** Automatisk kategorisering baserat på beskrivning

### Schema-ändringar
Vid framtida ändringar i Revoluts exportformat:
1. Uppdatera `column_map` i parser
2. Hantera nya avgiftstyper
3. Uppdatera BigQuery-schema
4. Testa avgifts-beräkningar

---

## 13. Säkerhet och Integritet

### Känslig Data
- **Saldo:** Känslig finansiell information
- **Beskrivningar:** Kan innehålla merchant-information
- **Avgifter:** Kan avslöja användningsmönster

### GDPR-compliance
- Anonymisera merchant-data vid behov
- Säker lagring av avgiftsinformation
- Kontrollerad åtkomst till saldo-data

---

## 14. Revolut-specifika Funktioner

### Multi-valuta Support
```sql
-- Analys per valuta
SELECT 
    currency,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    SUM(fee) as total_fees
FROM `revolut_transactions_raw`
GROUP BY currency;
```

### Avgifts-optimering
```sql
-- Identifiera dyraste avgifter
SELECT 
    description,
    amount,
    fee,
    (fee / ABS(amount)) * 100 as fee_percentage
FROM `revolut_transactions_raw`
WHERE fee > 0
ORDER BY fee_percentage DESC
LIMIT 10;
```

---

*Dokumentet uppdaterat: 2025-05-25*  
*Författare: AI Assistant*  
*Projekt: Budget_updater Revolut Integration* 