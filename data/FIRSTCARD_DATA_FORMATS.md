# FirstCard Data Formats Documentation

## Översikt
Detta dokument beskriver detaljerat alla dataformat som upptäckts under FirstCard-projektet för att lösa dubblettproblemet och skapa en ren merged datafil.

**Datum:** 2025-05-25  
**Projekt:** Budget_updater FirstCard Duplicate Resolution  
**Syfte:** Dokumentera filformat för framtida arbete

---

## 1. FirstCard Excel Format (Källformat)

### Filnamn
- `data/firstcard_250523.xlsx` (ren Excel-data från 2023-05-01 till 2025-05-21)
- `data/firstcard_all_merged.xlsx` (merged fil i Excel-format)

### Kolumnstruktur
| Kolumn | Datatyp | Beskrivning | Exempel |
|--------|---------|-------------|---------|
| `Datum` | Date | Transaktionsdatum | `2023-05-01` |
| `Ytterligare information` | String | Extra information (oftast tom) | `""` |
| `Reseinformation / Inköpsplats` | String | Beskrivning av transaktion | `"APPLE COM BILL"` |
| `Valuta` | String | Valuta (alltid SEK) | `"SEK"` |
| `växlingskurs` | String | Växlingskurs (oftast tom) | `""` |
| `Utländskt belopp` | String | Belopp i utländsk valuta (oftast tom) | `""` |
| `Belopp` | Float | Transaktionsbelopp i SEK | `129.00` |
| `Moms` | String | Moms (oftast tom) | `""` |
| `Kort` | String | Kortidentifikation | `"*1234"` eller `"unknown"` |

### Beloppslogik
- **Positiva belopp:** Utgifter (OUTFLOW)
- **Negativa belopp:** Inkomster/återbetalningar (INFLOW)
- **Nollbelopp:** Informationstransaktioner eller startbalanser

### Datumformat
- **Format:** `YYYY-MM-DD` (ISO 8601)
- **Timezone:** Lokal tid (Sverige)
- **Pandas:** `pd.to_datetime()` kompatibel
- **⚠️ Viktigt:** Datum sparas som `date` objekt, INTE `datetime` för att matcha FirstCard Excel-format

---

## 2. Google Sheets Format (Historisk data)

### Källa
- **Sheet:** Transactions (Google Sheets)
- **Datumintervall:** 2021-10-11 till 2023-04-30
- **Rader:** Header på rad 7, data börjar rad 8

### Kolumnstruktur
| Kolumn | Datatyp | Beskrivning | Exempel |
|--------|---------|-------------|---------|
| `DATE` | Date | Transaktionsdatum | `2021-10-11` |
| `OUTFLOW` | String | Utgifter med svensk formatering | `"1 234,56 kr"` |
| `INFLOW` | String | Inkomster med svensk formatering | `"500,00 kr"` |
| `CATEGORY` | String | Transaktionskategori | `"Äta ute Mats"` |
| `ACCOUNT` | String | Kontotyp | `"💳 First Card"` |
| `MEMO` | String | Transaktionsbeskrivning | `"Jobblunch"` |
| `STATUS` | String | Transaktionsstatus | `"✅"` |

### Beloppsformat (Svenska)
- **Format:** `"1 234,56 kr"`
- **Tusentalsavskiljare:** Mellanslag
- **Decimaltecken:** Komma (`,`)
- **Valutasuffix:** `" kr"`
- **Exempel:** `"23 000,00 kr"` = 23000.00

### Filterlogik
- **Konto:** Endast `ACCOUNT == "💳 First Card"`
- **Datum:** Endast inom specificerat intervall
- **Validering:** Aldrig både OUTFLOW och INFLOW på samma rad

---

## 3. BigQuery Database Format

### Tabell
- **Dataset:** `budget_data_warehouse` (EU region)
- **Tabell:** `transactions`

### Kolumnstruktur (Upptäckt via tidigare analys)
| Kolumn | Datatyp | Beskrivning | Exempel |
|--------|---------|-------------|---------|
| `business_key` | STRING | Unik identifierare | `"firstcard_2023-05-01_129.00_APPLE"` |
| `date` | DATE | Transaktionsdatum | `2023-05-01` |
| `amount` | FLOAT64 | Belopp i SEK | `129.00` |
| `description` | STRING | Transaktionsbeskrivning | `"APPLE COM BILL"` |
| `account` | STRING | Kontotyp | `"FirstCard"` |
| `category` | STRING | Kategori | `"Teknik"` |
| `source` | STRING | Datakälla | `"firstcard.xlsx"` |
| `upload_timestamp` | TIMESTAMP | Uppladdningstid | `2024-01-15 10:30:00` |

### Dubblettproblem (Löst)
- **Orsak:** Samma Excel-fil uppladdad flera gånger
- **Identifiering:** Identiska `business_key` värden
- **Omfattning:** 7 dubbletter → 21 extra rader, 13 sets → 35 extra transaktioner
- **Lösning:** Skapad ren merged fil utan dubbletter

---

## 4. Reverse Engineering Process

### Mappning: Google Sheets → Excel Format
| Google Sheets | Excel Format | Transformation |
|---------------|--------------|----------------|
| `DATE` | `Datum` | Direkt kopiering |
| `OUTFLOW` | `Belopp` (positiv) | Svensk formatering → Float |
| `INFLOW` | `Belopp` (negativ) | Svensk formatering → -Float |
| `CATEGORY + MEMO` | `Reseinformation / Inköpsplats` | `"Category: Memo"` |
| - | `Valuta` | Fast värde: `"SEK"` |
| - | `Kort` | Fast värde: `"unknown"` |
| - | Övriga kolumner | Tomma strängar |

### Beloppskonvertering
```python
def clean_swedish_amount(amount_str):
    """Konvertera '1 234,56 kr' → 1234.56"""
    # Ta bort 'kr' suffix
    amount_clean = amount_str.replace(' kr', '').replace('kr', '')
    # Ta bort mellanslag (tusentalsavskiljare)
    amount_clean = amount_clean.replace(' ', '')
    # Ersätt komma med punkt
    amount_clean = amount_clean.replace(',', '.')
    return float(amount_clean)
```

### Validering
- **OUTFLOW/INFLOW:** Aldrig båda på samma rad
- **Datum:** Måste vara giltigt datum
- **Belopp:** Måste kunna konverteras till float

---

## 5. Merged File Specifications

### Fil: `data/firstcard_all_merged.xlsx`

#### Innehåll
- **Total transaktioner:** 1,741
- **Reverse engineered data:** 1,006 rader (2021-10-11 till 2023-04-30)
- **Excel data:** 735 rader (2023-05-01 till 2025-05-21)
- **Datumintervall:** 2021-10-11 till 2025-05-21

#### Statistik
- **Total summa:** 823,384.44 kr
- **Utgifter (positiva):** 867,946.03 kr
- **Inkomster (negativa):** -44,561.59 kr
- **Nolltransaktioner:** 136 st
- **Potentiella dubbletter:** 38 st (samma datum, belopp, beskrivning)

#### Fördelning per år
- **2021:** 171 transaktioner
- **2022:** 640 transaktioner
- **2023:** 507 transaktioner
- **2024:** 311 transaktioner
- **2025:** 112 transaktioner

#### Kvalitetskontroll
- ✅ Inga saknade datum
- ✅ Inga saknade belopp
- ✅ Inga tomma beskrivningar
- ✅ Inga överlappande datum mellan källor
- ⚠️ 38 potentiella dubbletter (kräver manuell granskning)

---

## 6. Tekniska Detaljer

### Python Libraries
- **pandas:** Excel/CSV-hantering
- **google-api-python-client:** Google Sheets API
- **openpyxl:** Excel-filhantering

### Filhantering
```python
# Läsa Excel
df = pd.read_excel("data/firstcard_250523.xlsx")

# Läsa Google Sheets (via API)
sheet_data = sheets_client.get_all_sheet_data(sheet_id)

# Spara Excel
df.to_excel("output.xlsx", index=False)
```

### Datumhantering
```python
# Konvertera datum
df['Datum'] = pd.to_datetime(df['Datum'])

# Filtrera datumintervall
filtered = df[(df['Datum'] >= start_date) & (df['Datum'] <= end_date)]

# VIKTIGT: Konvertera till date objekt för Excel-kompatibilitet
df['Datum'] = pd.to_datetime(df['Datum']).dt.date  # Ger YYYY-MM-DD format
```

### Datumformat-fix
**Problem:** Pandas skapar automatiskt `datetime` objekt med timestamp (`2021-10-11 00:00:00`)  
**Lösning:** Konvertera till `date` objekt med `.dt.date` för att matcha FirstCard Excel-format (`2021-10-11`)  
**Kod:**
```python
df_copy['Datum'] = pd.to_datetime(df_copy['Datum']).dt.date
```

---

## 7. Framtida Användning

### BigQuery Import
1. Använd `data/firstcard_all_merged.xlsx` som källa
2. Mappa kolumner enligt BigQuery-schema
3. Generera nya `business_key` för att undvika dubbletter
4. Sätt `source = "merged_clean_data"`

### Dubbletthantering
- **Identifiering:** Samma datum + belopp + beskrivning
- **Lösning:** Manuell granskning av 38 potentiella dubbletter
- **Prevention:** Använd unika `business_key` i framtiden

### Datavalidering
```python
# Kontrollera dubbletter
duplicates = df.duplicated(subset=['Datum', 'Belopp', 'Reseinformation / Inköpsplats'])

# Kontrollera datumintervall
date_range = (df['Datum'].min(), df['Datum'].max())

# Kontrollera beloppsbalans
total_outflow = df[df['Belopp'] > 0]['Belopp'].sum()
total_inflow = df[df['Belopp'] < 0]['Belopp'].sum()
```

---

## 8. Scripts och Verktyg

### Skapade Scripts
1. **`create_firstcard_merged.py`** - Huvudscript för att skapa merged fil
2. **`inspect_merged_file.py`** - Inspektionsscript för kvalitetskontroll
3. **`check_firstcard_duplicates.py`** - Dubblettanalys (tidigare)

### Användning
```bash
# Skapa merged fil
python create_firstcard_merged.py

# Inspektera resultat
python inspect_merged_file.py
```

---

## 9. Viktiga Observationer

### Dataformat-skillnader
- **Excel:** Engelska kolumnnamn, punkt som decimaltecken
- **Google Sheets:** Svenska belopp med komma och "kr"-suffix
- **BigQuery:** Normaliserat format med business_key

### Datumöverlappning
- **Ingen överlappning** mellan Excel-data (2023-05-01+) och Google Sheets-data (till 2023-04-30)
- **Säker sammanslagning** utan risk för dubbletter från olika källor

### Beloppslogik
- **Konsistent:** Positiva = utgifter, negativa = inkomster
- **Validerad:** Aldrig både OUTFLOW och INFLOW på samma rad
- **Balanserad:** Total summa reflekterar nettoutflöde som förväntat för kreditkort

---

*Dokumentet uppdaterat: 2025-05-25 (Datumformat-fix tillagd)*  
*Författare: AI Assistant*  
*Projekt: Budget_updater FirstCard Data Cleanup* 