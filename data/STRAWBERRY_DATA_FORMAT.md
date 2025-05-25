# Strawberry Card Data Format Documentation

## Översikt
Detta dokument beskriver detaljerat Strawberry Cards dataformat för transaktionsexporter som används i Budget Updater-projektet, inklusive merge-processen med historisk Google Sheets-data.

**Datum:** 2025-05-25  
**Bank:** Strawberry Card (Skandiabanken)  
**Filformat:** Excel (.xls/.xlsx)  
**Syfte:** Detaljerad referens för Strawberry-datahantering

---

## 1. Filstruktur

### Filnamn
- `data/strawberry.xls` (original Strawberry-data)
- `data/strawberry_all_merged.xlsx` (merged fil med historisk data)

### Excel-struktur
- **Sheet:** Standard sheet (första sheet)
- **Engine:** `xlrd` för .xls, `openpyxl` för .xlsx
- **Header:** Rad 1 innehåller kolumnnamn
- **Data:** Börjar på rad 2
- **Specialfall:** Innehåller valutakurs-rader som måste filtreras bort

---

## 2. Kolumnstruktur

### Fullständig Schema (Original Excel)
| Kolumn | Datatyp | Obligatorisk | Beskrivning | Exempel |
|--------|---------|--------------|-------------|---------|
| `Datum` | Date | ✅ | Transaktionsdatum | `2025-04-30` |
| `Bokfört` | Date | ✅ | Bokföringsdatum | `2025-04-30` |
| `Specifikation` | String | ✅ | Transaktionsbeskrivning | `APPLE.COM/BILL` |
| `Ort` | String | ❌ | Transaktionsort | `020100529` |
| `Valuta` | String | ❌ | Valuta (oftast tom) | `""` |
| `Utl.belopp/moms` | Float | ❌ | Utländskt belopp/moms | `0` |
| `Belopp` | Float | ✅ | Transaktionsbelopp i SEK | `245` |

### Obligatoriska Kolumner för Parser
- `Bokfört` (används som primärt datum)
- `Specifikation` (används som beskrivning)
- `Belopp` (används som transaktionsbelopp)

---

## 3. Dataformat och Konventioner

### Datumformat
- **Original format:** Excel serial dates (numeriska värden)
- **Konvertering:** `pd.to_datetime(serial_date, origin='1899-12-30')`
- **Standardiserat format:** `YYYY-MM-DD`
- **Exempel:** Excel serial `45674` → `2025-04-30`

### Beloppslogik
- **Positiva belopp:** Utgifter/debiteringar (vanligast för kreditkort)
- **Negativa belopp:** Inkomster/krediteringar (återbetalningar)
- **Nollbelopp:** Informationstransaktioner
- **Valuta:** Alltid SEK (Svenska kronor)
- **Decimaler:** Heltal eller 2 decimaler

### Datafiltrering
- **Valutakurs-rader:** Rader utan giltigt datum filtreras bort
- **Tomma rader:** Rader utan belopp eller beskrivning filtreras bort
- **Validering:** Endast rader med parsebara datum behålls

---

## 4. Parser Implementation

### Konfiguration
```python
def parse_strawberry(file_path: str | Path) -> pd.DataFrame | None:
    return parse_excel_generic(
        file_path,
        engine=None,  # Let pandas/xlrd decide
        column_map={
            'date': ['Bokfört'],
            'desc': ['Specifikation'],
            'amount': ['Belopp'],
        },
        date_type='excel_serial',
        date_origin='1899-12-30',
    )
```

### Transformationsregler
1. **Datum:** `Bokfört` → `ParsedDate` (Excel serial → YYYY-MM-DD)
2. **Beskrivning:** `Specifikation` → `ParsedDescription`
3. **Belopp:** `Belopp` → `ParsedAmount` (ingen transformation)

---

## 5. Merged File Process

### Datakällor för Merge
1. **Excel-data:** `strawberry.xls` (2024-08-06 till 2025-04-30)
2. **Google Sheets-data:** Historisk data (2023-09-24 till 2024-08-05)

### Google Sheets → Excel Transformation
| Google Sheets | Excel Format | Transformation |
|---------------|--------------|----------------|
| `DATE` | `Datum` | Direkt kopiering som date |
| `DATE` | `Bokfört` | Samma som Datum |
| `OUTFLOW` | `Belopp` (positiv) | Svensk formatering → Float |
| `INFLOW` | `Belopp` (negativ) | Svensk formatering → -Float |
| `CATEGORY: MEMO` | `Specifikation` | Konkatenering med ":" separator |
| - | `Ort` | Tom sträng |
| - | `Valuta` | Tom sträng |
| - | `Utl.belopp/moms` | Tom sträng |

### Beloppskonvertering från Google Sheets
```python
def clean_swedish_amount(amount_str):
    """Konvertera '1 234,56 kr' → 1234.56"""
    if not amount_str or pd.isna(amount_str):
        return 0.0
    
    # Ta bort 'kr' suffix och mellanslag
    amount_clean = str(amount_str).replace(' kr', '').replace('kr', '')
    amount_clean = amount_clean.replace(' ', '').replace('\xa0', '')
    
    # Ersätt komma med punkt
    amount_clean = amount_clean.replace(',', '.')
    
    try:
        return float(amount_clean)
    except ValueError:
        return 0.0
```

---

## 6. BigQuery Staging Schema

### Tabell: `strawberry_transactions_raw`
```sql
CREATE TABLE `strawberry_transactions_raw` (
    -- Metadata
    file_hash STRING NOT NULL,
    source_file STRING NOT NULL,
    upload_timestamp TIMESTAMP NOT NULL,
    row_number INT64 NOT NULL,
    business_key STRING NOT NULL,
    
    -- Strawberry-specifika kolumner (exakt som Excel)
    datum DATE,
    bokfort DATE,
    specifikation STRING,
    ort STRING,
    valuta STRING,
    utl_belopp_moms FLOAT64,
    belopp FLOAT64
)
PARTITION BY DATE(bokfort)
CLUSTER BY business_key;
```

### Kolumnmappning Excel → BigQuery
| Excel Kolumn | BigQuery Kolumn | Transformation |
|--------------|-----------------|----------------|
| `Datum` | `datum` | `PARSE_DATE('%Y-%m-%d', ...)` |
| `Bokfört` | `bokfort` | `PARSE_DATE('%Y-%m-%d', ...)` |
| `Specifikation` | `specifikation` | Direkt kopiering |
| `Ort` | `ort` | Direkt kopiering |
| `Valuta` | `valuta` | Direkt kopiering |
| `Utl.belopp/moms` | `utl_belopp_moms` | Direkt kopiering |
| `Belopp` | `belopp` | Direkt kopiering |

---

## 7. Business Key Generation

### Algoritm
```python
def create_business_key(row):
    date_str = str(row['bokfort'])[:10]
    amount_str = f"{row['belopp']:.2f}"
    desc_normalized = str(row['specifikation']).strip().lower()[:50]
    
    key_components = f"strawberry|{date_str}|{amount_str}|{desc_normalized}"
    return hashlib.md5(key_components.encode('utf-8')).hexdigest()
```

### Unikhet
- Kombinerar datum, belopp och beskrivning
- Strawberry har mindre unika identifierare än SEB
- Medelhög risk för kollisioner

---

## 8. Transformation till Standardformat

### SQL för `transactions_standardized`
```sql
INSERT INTO `transactions_standardized`
SELECT 
    business_key,
    'strawberry' as source_bank,
    bokfort as transaction_date,
    specifikation as description,
    belopp as amount,
    CASE 
        WHEN belopp > 0 THEN 'OUTFLOW'  -- Positiva = utgifter för kreditkort
        WHEN belopp < 0 THEN 'INFLOW'   -- Negativa = inkomster
        ELSE 'ZERO'
    END as transaction_type,
    source_file,
    upload_timestamp
FROM `strawberry_transactions_raw`
WHERE bokfort IS NOT NULL;
```

### Google Sheets Format Transformation
```sql
INSERT INTO `sheet_transactions`
SELECT 
    bokfort as date,
    CASE 
        WHEN belopp > 0 THEN FORMAT("%.2f", belopp)  -- Positiva = OUTFLOW
        ELSE ""
    END as outflow,
    CASE 
        WHEN belopp < 0 THEN FORMAT("%.2f", ABS(belopp))  -- Negativa = INFLOW
        ELSE ""
    END as inflow,
    "" as category,  -- To be categorized later
    "💳 Strawberry" as account,
    specifikation as memo,
    "✅" as status,
    business_key,
    'strawberry' as source_bank
FROM `strawberry_transactions_raw`;
```

---

## 9. Merged File Specifications

### Fil: `data/strawberry_all_merged.xlsx`

#### Innehåll
- **Total transaktioner:** 1,189 rader
- **Excel data:** 499 rader (2024-08-06 till 2025-04-30)
- **Google Sheets data:** 690 rader (2023-09-24 till 2024-08-05)
- **Datumintervall:** 2023-09-24 till 2025-04-30

#### Statistik
- **Positiva belopp (utgifter):** 1,168 transaktioner
- **Negativa belopp (inkomster):** 21 transaktioner
- **Genomsnittligt belopp:** Varierar kraftigt
- **Filstorlek:** 50.3 KB

#### Kvalitetskontroll
- ✅ Inga saknade datum
- ✅ Inga saknade belopp
- ✅ Inga tomma beskrivningar
- ✅ Ingen datumöverlappning mellan källor
- ✅ Korrekt beloppslogik (positiva = utgifter)

---

## 10. Datavalidering

### Obligatoriska Kontroller
```python
def validate_strawberry_data(df: pd.DataFrame) -> List[str]:
    errors = []
    
    # Kontrollera obligatoriska kolumner
    required_cols = ['Bokfört', 'Specifikation', 'Belopp']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
    
    # Filtrera valutakurs-rader
    valid_dates = pd.to_datetime(df['Datum'], errors='coerce').notna()
    invalid_date_rows = (~valid_dates).sum()
    if invalid_date_rows > 0:
        errors.append(f"Currency rate rows to filter: {invalid_date_rows}")
    
    # Kontrollera belopp
    df_valid = df[valid_dates]
    invalid_amounts = df_valid['Belopp'].isna().sum()
    if invalid_amounts > 0:
        errors.append(f"Invalid amounts found: {invalid_amounts} rows")
    
    return errors
```

### Strawberry-specifik Validering
- **Valutakurs-filtrering:** Ta bort rader utan giltigt datum
- **Excel serial dates:** Kontrollera att datum konverteras korrekt
- **Beloppslogik:** Positiva = utgifter för kreditkort
- **Beskrivningar:** Kontrollera att specifikationer inte är tomma

---

## 11. Merge Process Implementation

### Huvudsteg
```python
class StrawberryMerger:
    def create_merged_file(self):
        # 1. Läs Excel-data (recent period)
        excel_df = self.read_excel_data()
        
        # 2. Läs Google Sheets-data (historical period)
        sheet_df = self.read_google_sheet_strawberry("2023-09-24", "2024-08-05")
        
        # 3. Reverse engineer Google Sheets data
        sheet_excel_df = self.reverse_engineer_to_excel_format(sheet_df)
        
        # 4. Merge data
        merged_df = self.merge_data(excel_df, sheet_excel_df)
        
        # 5. Save merged file
        return self.save_merged_file(merged_df)
```

### Reverse Engineering Process
```python
def reverse_engineer_to_excel_format(self, sheet_df: pd.DataFrame) -> pd.DataFrame:
    excel_rows = []
    
    for _, row in sheet_df.iterrows():
        # Parse amounts from Swedish format
        outflow = self.clean_swedish_amount(row.get('OUTFLOW', ''))
        inflow = self.clean_swedish_amount(row.get('INFLOW', ''))
        
        # Calculate belopp: OUTFLOW → positive, INFLOW → negative
        if outflow > 0:
            belopp = outflow
        elif inflow > 0:
            belopp = -inflow  # Negative for inflow
        else:
            belopp = 0.0
        
        # Create specifikation from category and memo
        category = str(row.get('CATEGORY', '')).strip()
        memo = str(row.get('MEMO', '')).strip()
        specifikation = ": ".join([category, memo]) if category and memo else category or memo
        
        # Create Excel row
        excel_row = {
            'Datum': pd.to_datetime(row['DATE']).date(),
            'Bokfört': pd.to_datetime(row['DATE']).date(),
            'Specifikation': specifikation,
            'Ort': '',
            'Valuta': '',
            'Utl.belopp/moms': '',
            'Belopp': belopp
        }
        
        excel_rows.append(excel_row)
    
    return pd.DataFrame(excel_rows)
```

---

## 12. Statistik och Kvalitetsmätningar

### Aktuell Data (strawberry_all_merged.xlsx)
- **Total transaktioner:** 1,189 rader
- **Datumintervall:** 2023-09-24 till 2025-04-30
- **Genomsnittligt belopp:** Varierar kraftigt
- **Vanligaste transaktionstyper:**
  - Kortköp (positiva belopp)
  - Återbetalningar (negativa belopp)
  - Månadsfakturor (stora positiva belopp)

### Fördelning per År
```sql
SELECT 
    EXTRACT(YEAR FROM bokfort) as year,
    COUNT(*) as transaction_count,
    SUM(CASE WHEN belopp > 0 THEN belopp ELSE 0 END) as total_outflow,
    SUM(CASE WHEN belopp < 0 THEN ABS(belopp) ELSE 0 END) as total_inflow
FROM `strawberry_transactions_raw`
GROUP BY year
ORDER BY year;
```

---

## 13. Felsökning och Vanliga Problem

### Vanliga Fel
1. **Excel serial dates:** Kontrollera att datum konverteras korrekt från numeriska värden
2. **Valutakurs-rader:** Filtrera bort rader utan giltigt datum
3. **Svenska beloppsformat:** Hantera komma som decimaltecken i Google Sheets
4. **Encoding-problem:** Använd korrekt encoding för svenska tecken

### Debugging-tips
```python
# Kontrollera datum-konvertering
print("Date conversion sample:")
print(pd.to_datetime(df['Bokfört'], origin='1899-12-30', errors='coerce').head())

# Kontrollera valutakurs-rader
invalid_dates = pd.to_datetime(df['Datum'], errors='coerce').isna()
print(f"Currency rate rows: {invalid_dates.sum()}")

# Kontrollera belopps-distribution
print("Amount distribution:", df['Belopp'].describe())

# Kontrollera specifikationer
print("Empty specifications:", df['Specifikation'].isna().sum())
```

### Merge-debugging
```python
# Kontrollera datumöverlappning
excel_dates = set(excel_df['Datum'])
sheet_dates = set(sheet_df['Datum'])
overlap = excel_dates.intersection(sheet_dates)
print(f"Date overlap: {len(overlap)} dates")

# Kontrollera belopps-konvertering
print("Swedish amount conversion test:")
test_amounts = ["1 234,56 kr", "500,00 kr", "23 000,00 kr"]
for amount in test_amounts:
    converted = clean_swedish_amount(amount)
    print(f"{amount} → {converted}")
```

---

## 14. Framtida Utveckling

### Möjliga Förbättringar
1. **Automatisk kategorisering:** Baserat på `Specifikation`-fältet
2. **Merchant-analys:** Identifiera återkommande handlare
3. **Utgiftsmönster:** Analys av månatliga utgifter
4. **Ort-analys:** Geografisk analys av transaktioner

### Schema-ändringar
Vid framtida ändringar i Strawberrys exportformat:
1. Uppdatera `column_map` i parser
2. Hantera nya datum-format
3. Uppdatera BigQuery-schema
4. Testa med nya datafiler

---

## 15. Säkerhet och Integritet

### Känslig Data
- **Specifikationer:** Kan innehålla känslig merchant-information
- **Ort:** Geografisk information
- **Belopp:** Finansiell information

### GDPR-compliance
- Anonymisera merchant-data vid behov
- Säker lagring av transaktionsdata
- Kontrollerad åtkomst till känsliga fält

---

## 16. Strawberry-specifika Funktioner

### Merchant-analys
```sql
-- Top merchants by transaction count
SELECT 
    specifikation,
    COUNT(*) as transaction_count,
    SUM(belopp) as total_amount,
    AVG(belopp) as avg_amount
FROM `strawberry_transactions_raw`
WHERE belopp > 0  -- Only outflows
GROUP BY specifikation
ORDER BY transaction_count DESC
LIMIT 10;
```

### Månadsanalys
```sql
-- Monthly spending analysis
SELECT 
    DATE_TRUNC(bokfort, MONTH) as month,
    COUNT(*) as transaction_count,
    SUM(CASE WHEN belopp > 0 THEN belopp ELSE 0 END) as monthly_spending,
    AVG(CASE WHEN belopp > 0 THEN belopp ELSE NULL END) as avg_transaction
FROM `strawberry_transactions_raw`
GROUP BY month
ORDER BY month;
```

---

*Dokumentet uppdaterat: 2025-05-25*  
*Författare: AI Assistant*  
*Projekt: Budget_updater Strawberry Integration* 