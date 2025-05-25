# SEB Bank Data Format Documentation

## Översikt
Detta dokument beskriver detaljerat SEB Banks dataformat för transaktionsexporter som används i Budget Updater-projektet.

**Datum:** 2025-05-25  
**Bank:** SEB (Skandinaviska Enskilda Banken)  
**Filformat:** Excel (.xlsx)  
**Syfte:** Detaljerad referens för SEB-datahantering

---

## 1. Filstruktur

### Filnamn
- `data/seb_all.xlsx` (komplett SEB-data)

### Excel-struktur
- **Sheet:** `Sheet1` (standard Excel-sheet)
- **Engine:** `openpyxl` (för .xlsx-filer)
- **Header:** Rad 1 innehåller kolumnnamn
- **Data:** Börjar på rad 2

---

## 2. Kolumnstruktur

### Fullständig Schema
| Kolumn | Datatyp | Obligatorisk | Beskrivning | Exempel |
|--------|---------|--------------|-------------|---------|
| `Bokföringsdatum` | Date | ✅ | Transaktionsdatum | `2025-04-30` |
| `Valutadatum` | Date | ✅ | Valutadatum | `2025-04-30` |
| `Verifikationsnummer` | String | ✅ | Unikt verifikationsnummer | `9900002100` |
| `Text` | String | ✅ | Transaktionsbeskrivning | `SYNSAM` |
| `Belopp` | Float | ✅ | Transaktionsbelopp i SEK | `-665.0` |
| `Saldo` | Float | ✅ | Kontosaldo efter transaktion | `9260.12` |

### Obligatoriska Kolumner för Parser
- `Bokföringsdatum` (används som primärt datum)
- `Text` (används som beskrivning)
- `Belopp` (används som transaktionsbelopp)

---

## 3. Dataformat och Konventioner

### Datumformat
- **Format:** `YYYY-MM-DD` (ISO 8601)
- **Timezone:** Lokal tid (Sverige, CET/CEST)
- **Pandas-kompatibel:** Direkt parsning med `pd.to_datetime()`
- **Exempel:** `2025-04-30`

### Beloppslogik
- **Negativa belopp:** Utgifter/debiteringar (vanligast)
- **Positiva belopp:** Inkomster/krediteringar
- **Nollbelopp:** Informationstransaktioner
- **Valuta:** Alltid SEK (Svenska kronor)
- **Decimaler:** 2 decimaler (öre)

### Textformat
- **Encoding:** UTF-8
- **Beskrivning:** Fri text, kan innehålla svenska tecken
- **Längd:** Variabel, typiskt 10-50 tecken
- **Exempel:** `"SYNSAM"`, `"EASYPARK    /25-04-29"`

---

## 4. Parser Implementation

### Konfiguration
```python
def parse_seb(file_path: str | Path) -> pd.DataFrame | None:
    return parse_excel_generic(
        file_path,
        engine='openpyxl',
        sheet_name='Sheet1',
        column_map={
            'date': ['Bokföringsdatum'],
            'desc': ['Text'],
            'amount': ['Belopp'],
        },
        date_type='string',
    )
```

### Transformationsregler
1. **Datum:** `Bokföringsdatum` → `ParsedDate`
2. **Beskrivning:** `Text` → `ParsedDescription`
3. **Belopp:** `Belopp` → `ParsedAmount` (ingen transformation)

---

## 5. BigQuery Staging Schema

### Tabell: `seb_transactions_raw`
```sql
CREATE TABLE `seb_transactions_raw` (
    -- Metadata
    file_hash STRING NOT NULL,
    source_file STRING NOT NULL,
    upload_timestamp TIMESTAMP NOT NULL,
    row_number INT64 NOT NULL,
    business_key STRING NOT NULL,
    
    -- SEB-specifika kolumner (exakt som Excel)
    bokforingsdatum DATE,
    valutadatum DATE,
    verifikationsnummer STRING,
    text STRING,
    belopp FLOAT64,
    saldo FLOAT64
)
PARTITION BY DATE(bokforingsdatum)
CLUSTER BY business_key;
```

### Kolumnmappning Excel → BigQuery
| Excel Kolumn | BigQuery Kolumn | Transformation |
|--------------|-----------------|----------------|
| `Bokföringsdatum` | `bokforingsdatum` | `PARSE_DATE('%Y-%m-%d', ...)` |
| `Valutadatum` | `valutadatum` | `PARSE_DATE('%Y-%m-%d', ...)` |
| `Verifikationsnummer` | `verifikationsnummer` | Direkt kopiering |
| `Text` | `text` | Direkt kopiering |
| `Belopp` | `belopp` | Direkt kopiering |
| `Saldo` | `saldo` | Direkt kopiering |

---

## 6. Business Key Generation

### Algoritm
```python
def create_business_key(row):
    date_str = str(row['bokforingsdatum'])[:10]
    amount_str = f"{row['belopp']:.2f}"
    desc_normalized = str(row['text']).strip().lower()[:50]
    verification = str(row['verifikationsnummer'])
    
    key_components = f"seb|{date_str}|{amount_str}|{desc_normalized}|{verification}"
    return hashlib.md5(key_components.encode('utf-8')).hexdigest()
```

### Unikhet
- Kombinerar datum, belopp, beskrivning och verifikationsnummer
- Verifikationsnummer från SEB är unikt per transaktion
- Mycket låg risk för kollisioner

---

## 7. Transformation till Standardformat

### SQL för `transactions_standardized`
```sql
INSERT INTO `transactions_standardized`
SELECT 
    business_key,
    'seb' as source_bank,
    bokforingsdatum as transaction_date,
    text as description,
    belopp as amount,
    CASE 
        WHEN belopp < 0 THEN 'OUTFLOW'
        WHEN belopp > 0 THEN 'INFLOW'
        ELSE 'ZERO'
    END as transaction_type,
    source_file,
    upload_timestamp
FROM `seb_transactions_raw`
WHERE bokforingsdatum IS NOT NULL;
```

### Google Sheets Format Transformation
```sql
INSERT INTO `sheet_transactions`
SELECT 
    bokforingsdatum as date,
    CASE 
        WHEN belopp < 0 THEN FORMAT("%.2f", ABS(belopp))
        ELSE ""
    END as outflow,
    CASE 
        WHEN belopp > 0 THEN FORMAT("%.2f", belopp)
        ELSE ""
    END as inflow,
    "" as category,  -- To be categorized later
    "🏦 SEB" as account,
    text as memo,
    "✅" as status,
    business_key,
    'seb' as source_bank
FROM `seb_transactions_raw`;
```

---

## 8. Datavalidering

### Obligatoriska Kontroller
```python
def validate_seb_data(df: pd.DataFrame) -> List[str]:
    errors = []
    
    # Kontrollera obligatoriska kolumner
    required_cols = ['Bokföringsdatum', 'Text', 'Belopp']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
    
    # Kontrollera datum
    invalid_dates = df['Bokföringsdatum'].isna().sum()
    if invalid_dates > 0:
        errors.append(f"Invalid dates found: {invalid_dates} rows")
    
    # Kontrollera belopp
    invalid_amounts = df['Belopp'].isna().sum()
    if invalid_amounts > 0:
        errors.append(f"Invalid amounts found: {invalid_amounts} rows")
    
    # Kontrollera beskrivning
    empty_descriptions = df['Text'].isna().sum()
    if empty_descriptions > 0:
        errors.append(f"Empty descriptions found: {empty_descriptions} rows")
    
    return errors
```

### Datumintervall-validering
- **Rimligt intervall:** 2020-01-01 till dagens datum + 1 månad
- **Kronologisk ordning:** Kontrollera att datum är logiska
- **Helger/vardagar:** SEB transaktioner kan ske alla dagar

---

## 9. Statistik och Kvalitetsmätningar

### Aktuell Data (seb_all.xlsx)
- **Total transaktioner:** ~750 rader
- **Datumintervall:** 2024-01-01 till 2025-04-30
- **Genomsnittligt belopp:** Varierar kraftigt
- **Vanligaste transaktionstyper:**
  - Kortköp (negativa belopp)
  - Löneinsättningar (positiva belopp)
  - Överföringar (både positiva och negativa)

### Fördelning per Transaktionstyp
```sql
SELECT 
    CASE 
        WHEN belopp < 0 THEN 'OUTFLOW'
        WHEN belopp > 0 THEN 'INFLOW'
        ELSE 'ZERO'
    END as transaction_type,
    COUNT(*) as count,
    SUM(ABS(belopp)) as total_amount
FROM `seb_transactions_raw`
GROUP BY transaction_type;
```

---

## 10. Felsökning och Vanliga Problem

### Vanliga Fel
1. **Encoding-problem:** Använd UTF-8 för svenska tecken
2. **Datumformat:** Kontrollera att Excel-datum parsas korrekt
3. **Decimal-separator:** SEB använder punkt (.) som decimaltecken
4. **Tomma rader:** Filtrera bort rader utan datum eller belopp

### Debugging-tips
```python
# Kontrollera kolumnnamn
print("Columns:", df.columns.tolist())

# Kontrollera datatyper
print("Data types:", df.dtypes)

# Kontrollera första raderna
print("Sample data:", df.head())

# Kontrollera för NaN-värden
print("NaN values:", df.isna().sum())
```

---

## 11. Framtida Utveckling

### Möjliga Förbättringar
1. **Automatisk kategorisering:** Baserat på `Text`-fältet
2. **Saldo-validering:** Kontrollera att saldo-beräkningar stämmer
3. **Duplikatkontroll:** Använd `Verifikationsnummer` för exakt dublikatkontroll
4. **Trend-analys:** Månadsvis utgifts/inkomst-analys

### Schema-ändringar
Vid framtida ändringar i SEB:s exportformat:
1. Uppdatera `column_map` i parser
2. Lägg till nya kolumner i BigQuery-schema
3. Uppdatera transformationslogik
4. Testa med nya datafiler

---

## 12. Säkerhet och Integritet

### Känslig Data
- **Verifikationsnummer:** Kan vara känsligt, logga inte i klartext
- **Saldo:** Känslig information, hantera säkert
- **Beskrivningar:** Kan innehålla personlig information

### GDPR-compliance
- Anonymisera data vid behov
- Säker lagring i BigQuery
- Kontrollerad åtkomst till känsliga fält

---

*Dokumentet uppdaterat: 2025-05-25*  
*Författare: AI Assistant*  
*Projekt: Budget_updater SEB Integration* 