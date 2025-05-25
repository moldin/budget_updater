# FirstCard Reverse Engineering Process

Detta är en 3-stegs säker process för att extrahera och ladda upp FirstCard historisk data från Google Sheet till BigQuery.

## 📋 Översikt

Processen är uppdelad i tre separata steg för maximal säkerhet:

1. **📤 Extraction (Staging)** - Extrahera data från Google Sheet till lokal fil
2. **🔍 Validation** - Validera att datan är korrekt och kompatibel med BigQuery
3. **📥 Upload** - Ladda upp validerad data till BigQuery med backup

## 🚀 Steg-för-steg Guide

### Steg 1: Extrahera till Staging Fil

Kör extraction scriptet för att hämta FirstCard data från Google Sheet:

```bash
python scripts/extract_firstcard_to_staging.py
```

**Alternativ:**
```bash
# Ändra cutoff datum (standard: 2023-05-01)
python scripts/extract_firstcard_to_staging.py --cutoff-date 2022-01-01
```

**Output:**
- Skapar en staging fil i `staging/` mappen
- Format: `firstcard_staging_YYYYMMDD_HHMMSS.json`
- Innehåller alla transaktioner FÖRE cutoff datumet
- Inkluderar debug information för granskning

### Steg 2: Validera Staging Fil

Validera att staging filen är korrekt och BigQuery-kompatibel:

```bash
python scripts/validate_firstcard_staging.py staging/firstcard_staging_20231201_143022.json
```

**Alternativ:**
```bash
# Spara en detaljerad valideringsrapport
python scripts/validate_firstcard_staging.py staging/firstcard_staging_20231201_143022.json --save-report
```

**Valideringen kontrollerar:**
- ✅ JSON struktur och schema
- ✅ Datatyper och fält
- ✅ Datum format (YYYY-MM-DD)
- ✅ Numeriska belopp
- ✅ Business key unikhet
- ✅ Duplikater mot befintlig BigQuery data

**Output:**
- Exit code 0 = Validering OK
- Exit code 1 = Valideringsfel
- Skapar optional `.validation_report.json`

### Steg 3: Ladda upp till BigQuery

Efter lyckad validering, ladda upp datan:

```bash
python scripts/upload_firstcard_staging.py staging/firstcard_staging_20231201_143022.json
```

**Alternativ:**
```bash
# Dry run (simulera utan att ladda upp)
python scripts/upload_firstcard_staging.py staging/firstcard_staging_20231201_143022.json --dry-run

# Hoppa över backup (ej rekommenderat)
python scripts/upload_firstcard_staging.py staging/firstcard_staging_20231201_143022.json --no-backup

# Tillåt duplikater (inte rekommenderat)
python scripts/upload_firstcard_staging.py staging/firstcard_staging_20231201_143022.json --allow-duplicates

# Force mode (ingen interaktion)
python scripts/upload_firstcard_staging.py staging/firstcard_staging_20231201_143022.json --force
```

**Upload processen:**
- ✅ Kontrollerar valideringsrapport
- ✅ Skapar backup av befintlig data
- ✅ Filtrerar bort duplikater
- ✅ Laddar upp nya transaktioner
- ✅ Skapar upload sammanfattning

## 📁 Fil Struktur

```
staging/
├── firstcard_staging_YYYYMMDD_HHMMSS.json           # Staging data
├── firstcard_staging_YYYYMMDD_HHMMSS.validation_report.json  # Validering
└── firstcard_staging_YYYYMMDD_HHMMSS.upload_summary.json     # Upload resultat
```

## 🔍 Data Transformation

### Google Sheet → FirstCard Raw Format

| Google Sheet Kolumn | FirstCard Raw Fält | Transformation |
|-------------------|-------------------|---------------|
| Date | datum | Direkt kopiering |
| Outflow | belopp | Positivt värde |
| Inflow | belopp | Negativt värde |
| Category + MEMO | reseinformation_inkopsplats | Kombinerat |
| MEMO | ytterligare_information | Direkt kopiering |
| - | valuta | "SEK" |
| - | kort | "unknown" |
| - | business_key | Genererad hash |

### Business Key Generation

```
business_key = "firstcard_rev_" + MD5(f"firstcard|{date}|{amount}|{description}")
```

## ⚠️ Säkerhetsfunktioner

### Automatiska Backups
- Skapar backup tabell före upload: `firstcard_transactions_raw_backup_YYYYMMDD_HHMMSS`
- Endast om befintlig data finns

### Duplicate Detection
- Kontrollerar business_key mot befintlig data
- Filtrerar automatiskt bort duplikater
- Varnar för potentiella konflikter

### Validation Checks
- Schema kompatibilitet med BigQuery
- Datum format validering
- Belopp range kontroll
- Business rule validering

## 🐛 Troubleshooting

### Validation Fel

**"Invalid date format"**
```bash
# Kontrollera datum format i Google Sheet (ska vara YYYY-MM-DD)
```

**"Amount must be numeric"**
```bash
# Kontrollera att belopp inte innehåller text eller specialtecken
```

**"Duplicate business_key"**
```bash
# Duplikater i staging filen - kontrollera Google Sheet för identiska rader
```

### Upload Fel

**"No validation report found"**
```bash
# Kör validation först
python scripts/validate_firstcard_staging.py staging/file.json
```

**"Validation report shows errors"**
```bash
# Fixa valideringsfel innan upload
```

## 📊 Efter Upload

Efter lyckad upload:

1. **Kontrollera datan i BigQuery:**
   ```sql
   SELECT COUNT(*), MIN(datum), MAX(datum) 
   FROM `project.dataset.firstcard_transactions_raw` 
   WHERE source_file = 'orig_google_sheet_rev_engineered'
   ```

2. **Uppdatera sheet_transactions tabellen:**
   ```bash
   python scripts/transform_to_sheet_transactions.py
   ```

3. **Verifiera i Google Sheet view:**
   - Kontrollera att historiska transaktioner syns
   - Verifiera summor och datum ranges

## 🔄 Återställning

Om något går fel:

```sql
-- Radera reverse engineered data
DELETE FROM `project.dataset.firstcard_transactions_raw` 
WHERE source_file = 'orig_google_sheet_rev_engineered';

-- Återställ från backup (om nödvändigt)
INSERT INTO `project.dataset.firstcard_transactions_raw`
SELECT * FROM `project.dataset.firstcard_transactions_raw_backup_YYYYMMDD_HHMMSS`;
```

## 📞 Support

Vid problem:
1. Kontrollera loggarna för detaljerade felmeddelanden
2. Verifiera Google Sheet format och access
3. Kontrollera BigQuery permissions
4. Använd `--dry-run` för att testa utan risk 