# Budget Updater - Data Formats Overview

## Översikt
Detta dokument ger en komplett översikt över alla dataformat som används i Budget Updater-projektet. Varje bank/kort har sina egna specifika format och krav som måste hanteras korrekt för att säkerställa korrekt databehandling.

**Datum:** 2025-05-25  
**Projekt:** Budget_updater Data Warehouse Implementation  
**Syfte:** Centraliserad referens för alla dataformat och transformationsregler

---

## Stödda Datakällor

### 1. SEB Bank (`seb_all.xlsx`)
- **Filformat:** Excel (.xlsx)
- **Datumintervall:** 2020-05-02 till 2025-04-30
- **Antal transaktioner:** ~3688 rader
- **Beloppslogik:** Negativa = utgifter, positiva = inkomster
- **Detaljerad dokumentation:** [SEB_DATA_FORMAT.md](SEB_DATA_FORMAT.md)

### 2. Revolut (`revolut_all_merged.xlsx`)
- **Filformat:** Excel (.xlsx)
- **Datumintervall:** 2021-10-11 till 2025-04-22
- **Antal transaktioner:** 293 rader (35 från Google Sheets + 258 från Excel)
- **Beloppslogik:** Negativa = utgifter, positiva = inkomster + avgifter
- **Detaljerad dokumentation:** [REVOLUT_MERGED_DATA_FORMAT.md](REVOLUT_MERGED_DATA_FORMAT.md)

### 3. FirstCard (`firstcard_250523.xlsx` + merged)
- **Filformat:** Excel (.xlsx)
- **Datumintervall:** 2021-10-11 till 2025-05-21 (merged)
- **Antal transaktioner:** 1,741 rader (merged)
- **Beloppslogik:** Positiva = utgifter, negativa = inkomster
- **Detaljerad dokumentation:** [FIRSTCARD_DATA_FORMATS.md](FIRSTCARD_DATA_FORMATS.md)

### 4. Strawberry Card (`strawberry.xls` + merged)
- **Filformat:** Excel (.xls/.xlsx)
- **Datumintervall:** 2023-09-24 till 2025-04-30 (merged)
- **Antal transaktioner:** 1,189 rader (merged)
- **Beloppslogik:** Positiva = utgifter, negativa = inkomster
- **Detaljerad dokumentation:** [STRAWBERRY_DATA_FORMAT.md](STRAWBERRY_DATA_FORMAT.md)

---

## Gemensamma Transformationsregler

### Datum Standardisering
Alla datum konverteras till `YYYY-MM-DD` format för BigQuery-kompatibilitet:
- **SEB:** Redan i korrekt format
- **Revolut:** Extraherar datum från `YYYY-MM-DD HH:MM:SS`
- **FirstCard:** Redan i korrekt format
- **Strawberry:** Konverterar från Excel serial dates

### Beloppslogik per Bank
| Bank | Positiva Belopp | Negativa Belopp | Avgifter |
|------|----------------|-----------------|----------|
| **SEB** | Inkomster | Utgifter | N/A |
| **Revolut** | Inkomster | Utgifter | Läggs till utgifter |
| **FirstCard** | Utgifter | Inkomster | N/A |
| **Strawberry** | Utgifter | Inkomster | N/A |

### Google Sheets Integration
Historisk data från Google Sheets transformeras till Excel-format:
- **OUTFLOW** → Positiva belopp (utgifter)
- **INFLOW** → Negativa belopp (inkomster)
- **CATEGORY + MEMO** → Beskrivning med ":" separator

---

## BigQuery Data Warehouse Struktur

### Staging Layer (Raw Data)
- `seb_transactions_raw` - SEB Excel struktur exakt
- `revolut_transactions_raw` - Revolut Excel struktur exakt
- `firstcard_transactions_raw` - FirstCard Excel struktur exakt
- `strawberry_transactions_raw` - Strawberry Excel struktur exakt

### Clean Layer
- `transactions_standardized` - Enhetligt format från alla banker
- `sheet_transactions` - Google Sheets-kompatibelt format

### Business Layer
- `transaction_categories` - Kategorireferenstabell
- `categorization_rules` - Automatiska kategoriseringsregler

### Analysis Layer
- `monthly_summary` - Månadssammanfattningar per bank
- `category_summary` - Kategoribaserad analys

---

## Filstruktur och Namnkonventioner

### Original Excel-filer
```
data/
├── seb_all.xlsx              # SEB original data
├── revolut.xlsx              # Revolut original data  
├── firstcard_250523.xlsx     # FirstCard original data
└── strawberry.xls            # Strawberry original data
```

### Merged-filer (Excel + Google Sheets)
```
data/
├── revolut_all_merged.xlsx     # Revolut: 2021-2025 (293 rader)
├── firstcard_all_merged.xlsx   # FirstCard: 2021-2025 (1,741 rader)
└── strawberry_all_merged.xlsx  # Strawberry: 2023-2025 (1,189 rader)
```

### Dokumentation
```
data/
├── DATA_FORMATS_OVERVIEW.md         # Detta dokument
├── SEB_DATA_FORMAT.md               # SEB-specifik dokumentation
├── REVOLUT_DATA_FORMAT.md           # Revolut original format
├── REVOLUT_MERGED_DATA_FORMAT.md    # Revolut merged format (rekommenderad)
├── FIRSTCARD_DATA_FORMATS.md        # FirstCard-specifik dokumentation
└── STRAWBERRY_DATA_FORMAT.md        # Strawberry-specifik dokumentation
```

---

## Parser Implementation

### Generic Parser
Alla banker använder `parse_excel_generic()` med bankspecifika konfigurationer:

```python
def parse_excel_generic(
    file_path: str | Path,
    *,
    engine: str = None,
    sheet_name: str = None,
    column_map: Dict[str, List[str]],
    date_type: str = 'string',  # 'string' or 'excel_serial'
    date_origin: str = '1899-12-30',
    required_columns: List[str] = None,
) -> pd.DataFrame | None
```

### Bank-specifika Parsers
- `parse_seb()` - SEB Excel-format
- `parse_revolut()` - Revolut Excel-format med avgiftshantering
- `parse_firstcard()` - FirstCard Excel-format
- `parse_strawberry()` - Strawberry Excel-format med serial dates

---

## Kvalitetskontroll

### Datavalidering
- **Datum:** Måste vara giltiga datum inom rimliga intervall
- **Belopp:** Måste vara numeriska värden
- **Beskrivning:** Får inte vara tomma
- **Dubbletter:** Identifieras via business_key

### Merge-validering
- **Datumöverlappning:** Kontrolleras mellan Excel och Google Sheets data
- **Beloppsbalans:** Totalsummor valideras
- **Transaktionsantal:** Förväntat antal transaktioner per period

### BigQuery-validering
- **Schema-kompatibilitet:** Alla kolumner mappar korrekt
- **Datatyper:** Korrekt konvertering till BigQuery-typer
- **Partitionering:** Datum-baserad partitionering för prestanda

---

## Framtida Utveckling

### Nya Banker
För att lägga till nya banker:
1. Skapa bankspecifik dokumentation i `data/`
2. Implementera parser i `src/budget_updater/parsers.py`
3. Lägg till staging-tabell i BigQuery
4. Uppdatera transformationslogik

### Dataformat-ändringar
Vid ändringar i bankernas exportformat:
1. Uppdatera relevant dokumentation
2. Anpassa parser-konfiguration
3. Testa med nya datafiler
4. Uppdatera BigQuery-schema vid behov

### Historisk Data
För att lägga till äldre data:
1. Analysera Google Sheets-struktur
2. Implementera reverse engineering-script
3. Skapa merged-fil
4. Validera dataintegration

---

## Tekniska Detaljer

### Dependencies
- **pandas:** Excel/CSV-hantering
- **google-cloud-bigquery:** BigQuery-integration
- **google-api-python-client:** Google Sheets API
- **openpyxl:** Excel-filhantering

### Logging
Alla operationer loggas med:
- **INFO:** Framgångsrika operationer
- **WARNING:** Potentiella problem
- **ERROR:** Fel som kräver uppmärksamhet

### Error Handling
- **Graceful degradation:** Fortsätt vid enskilda fel
- **Detaljerad felrapportering:** Logga specifika problem
- **Rollback-möjlighet:** Säker datahantering

---

*Dokumentet uppdaterat: 2025-05-25*  
*Författare: AI Assistant*  
*Projekt: Budget_updater Data Warehouse Implementation* 