# Revolut Merged Data Format Documentation

## Översikt
Detta dokument beskriver detaljerat den merged Revolut-datafilen som kombinerar Excel-data med historisk Google Sheets-data enligt specifika transformationsregler.

**Datum:** 2025-05-25  
**Bank:** Revolut Ltd  
**Filformat:** Excel (.xlsx)  
**Merged fil:** `data/revolut_all_merged.xlsx`  
**Syfte:** Komplett Revolut-datahistorik från 2021-10-11 till 2025-04-22

---

## 1. Filstruktur

### Datakällor
- **Excel-data:** `revolut_init.xlsx` (2022-01-03 till 2025-04-22) - 258 transaktioner
- **Google Sheets-data:** Historisk data (2021-10-11 till 2022-01-02) - 35 transaktioner
- **Total merged:** 293 transaktioner

### Merge-process
1. Läs recent data från `revolut_init.xlsx`
2. Läs historisk data från Google Sheets för Revolut-konto
3. Reverse engineer Google Sheets-data till Revolut Excel-format
4. Merge och sortera kronologiskt
5. Spara som `revolut_all_merged.xlsx`

---

## 2. Transformationsregler från Google Sheets

### Grundläggande Mappning
| Google Sheets | Revolut Excel | Transformation |
|---------------|---------------|----------------|
| `DATE` | `Started Date` | Lägg till ` 0:00:00` tid |
| `DATE` | `Completed Date` | Lägg till ` 0:00:00` tid |
| `OUTFLOW` | `Amount` | Negativ (300 kr → -300.0) |
| `INFLOW` | `Amount` | Positiv (300 kr → 300.0) |
| `CATEGORY: MEMO` | `Description` | Konkatenering med ":" |

### Type-bestämning (Avancerade Regler)
| Villkor | Type | Beskrivning |
|---------|------|-------------|
| OUTFLOW innehåller data | `CARD_PAYMENT` | Kortbetalningar/utgifter |
| INFLOW + Category = "↕️ Account Transfer" | `TOPUP` | Påfyllningar från andra konton |
| Category = "Bankavgifter" | `FEE` | Bankavgifter (oavsett INFLOW/OUTFLOW) |
| INFLOW + Category ≠ "↕️ Account Transfer" | `REFUND` | Återbetalningar/krediteringar |

### Fasta Värden
- `Product` → `"Current"`
- `Fee` → `0.00`
- `Currency` → `"SEK"`
- `State` → `"COMPLETED"`
- `Balance` → `""` (tom)

---

## 3. Kolumnstruktur (Merged File)

### Fullständig Schema
| Kolumn | Datatyp | Källa | Beskrivning | Exempel |
|--------|---------|-------|-------------|---------|
| `Type` | String | Beräknad | Transaktionstyp | `CARD_PAYMENT` |
| `Product` | String | Fast/Excel | Produkttyp | `Current` |
| `Started Date` | DateTime | Transformerad/Excel | Startdatum | `2021-10-18 0:00:00` |
| `Completed Date` | DateTime | Transformerad/Excel | Slutdatum | `2021-10-18 0:00:00` |
| `Description` | String | Transformerad/Excel | Beskrivning | `Spotify: Månadspren` |
| `Amount` | Float | Transformerad/Excel | Belopp | `-189.0` |
| `Fee` | Float | Fast/Excel | Avgift | `0.0` |
| `Currency` | String | Fast/Excel | Valuta | `SEK` |
| `State` | String | Fast/Excel | Status | `COMPLETED` |
| `Balance` | String | Tom/Excel | Saldo | `""` |

---

## 4. Statistik och Kvalitetsmätningar

### Merged File Statistics
- **Total transaktioner:** 293
- **Datumintervall:** 2021-10-11 till 2025-04-22
- **Google Sheets bidrag:** 35 transaktioner (12%)
- **Excel bidrag:** 258 transaktioner (88%)

### Transaktionstyp-fördelning
| Type | Antal | Procent | Beskrivning |
|------|-------|---------|-------------|
| `CARD_PAYMENT` | 193 | 65.9% | Kortbetalningar och utgifter |
| `TOPUP` | 51 | 17.4% | Påfyllningar från andra konton |
| `FEE` | 22 | 7.5% | Bankavgifter |
| `EXCHANGE` | 16 | 5.5% | Valutaväxlingar (från Excel) |
| `TRANSFER` | 6 | 2.0% | Överföringar (från Excel) |
| `REFUND` | 3 | 1.0% | Återbetalningar |
| `CARD_REFUND` | 2 | 0.7% | Kortåterbetalningar (från Excel) |

---

## 5. Reverse Engineering Process

### Google Sheets → Excel Transformation
```python
def reverse_engineer_to_excel_format(sheet_df):
    for row in sheet_df:
        # Parse amounts
        outflow = clean_swedish_amount(row['OUTFLOW'])  # "189,00 kr" → 189.0
        inflow = clean_swedish_amount(row['INFLOW'])    # "2 660,19 kr" → 2660.19
        
        # Calculate amount
        if outflow > 0:
            amount = -outflow  # Negative for expenses
        elif inflow > 0:
            amount = inflow    # Positive for income
        
        # Determine type
        type = determine_transaction_type(outflow, inflow, category)
        
        # Create description
        description = f"{category}: {memo}"
        
        # Create Excel row
        excel_row = {
            'Type': type,
            'Started Date': f"{date} 0:00:00",
            'Completed Date': f"{date} 0:00:00",
            'Description': description,
            'Amount': amount,
            # ... other fields
        }
```

### Exempel på Transformationer
| Google Sheets Data | Revolut Excel Result |
|-------------------|---------------------|
| `DATE: 2021-10-18`<br>`OUTFLOW: 189,00 kr`<br>`CATEGORY: Spotify`<br>`MEMO: Månadspren` | `Type: CARD_PAYMENT`<br>`Completed Date: 2021-10-18 0:00:00`<br>`Description: Spotify: Månadspren`<br>`Amount: -189.0` |
| `DATE: 2021-10-26`<br>`INFLOW: 2 000,00 kr`<br>`CATEGORY: ↕️ Account Transfer`<br>`MEMO: Överföring till Revolut` | `Type: TOPUP`<br>`Completed Date: 2021-10-26 0:00:00`<br>`Description: ↕️ Account Transfer: Överföring till Revolut`<br>`Amount: 2000.0` |

---

## 6. Datavalidering

### Kvalitetskontroller
- ✅ Inga saknade datum
- ✅ Alla belopp är numeriska
- ✅ Inga tomma beskrivningar
- ✅ Korrekt Type-mappning enligt regler
- ✅ Kronologisk sortering
- ✅ Ingen datumöverlappning mellan källor

### Merge-validering
```python
# Kontrollera datumintervall
excel_dates = pd.to_datetime(excel_df['Completed Date'])
sheet_dates = pd.to_datetime(sheet_excel_df['Completed Date'])

excel_min = excel_dates.min()  # 2022-01-03
sheet_max = sheet_dates.max()  # 2022-01-02

assert sheet_max < excel_min, "No date overlap between sources"
```

---

## 7. Användning med Befintliga Parsers

### Parser-kompatibilitet
Den merged filen är fullt kompatibel med befintlig `parse_revolut()` funktion:

```python
# Använd merged fil istället för original
merged_df = parse_revolut("data/revolut_all_merged.xlsx")

# Samma resultat som tidigare, men med komplett historik
print(f"Total transactions: {len(merged_df)}")  # 293 istället för 258
```

### BigQuery Upload
```python
# Upload merged data till BigQuery
uploader = TransactionUploaderV2(config)
uploader.upload_file("data/revolut_all_merged.xlsx", source_bank="revolut")
```

---

## 8. Kategorimappning från Google Sheets

### Vanligaste Kategorier (Historisk Data)
| Kategori | Antal | Type Mapping |
|----------|-------|--------------|
| `Spotify` | 3 | CARD_PAYMENT |
| `Netflix` | 3 | CARD_PAYMENT |
| `↕️ Account Transfer` | 8 | TOPUP |
| `Bankavgifter` | 2 | FEE |
| `Appar/Mjukvara` | 4 | CARD_PAYMENT |
| `Böcker` | 2 | CARD_PAYMENT |
| `➡️ Starting Balance` | 1 | REFUND |

### Beskrivningsformat
- **Pattern:** `{CATEGORY}: {MEMO}`
- **Exempel:** `"Spotify: Månadspren"`, `"↕️ Account Transfer: Överföring till Revolut"`
- **Fallback:** Om category eller memo saknas, använd det som finns

---

## 9. Framtida Utveckling

### Möjliga Förbättringar
1. **Automatisk Type-detektering:** Förbättra logiken för Type-bestämning
2. **Balans-beräkning:** Beräkna Balance-kolumn baserat på Amount
3. **Avgifts-hantering:** Hantera avgifter från Google Sheets-data
4. **Valuta-stöd:** Stöd för andra valutor än SEK

### Underhåll
- Vid nya Google Sheets-data: Uppdatera cutoff-datum
- Vid ändringar i Revolut-format: Uppdatera transformationsregler
- Vid nya kategorier: Uppdatera Type-mappning

---

## 10. Felsökning

### Vanliga Problem
1. **Datum-format:** Kontrollera att Google Sheets-datum parsas korrekt
2. **Belopps-parsing:** Svenska format med komma och mellanslag
3. **Type-mappning:** Kontrollera att alla kategorier mappar korrekt
4. **Encoding:** Svenska tecken i kategorier och beskrivningar

### Debug-tips
```python
# Kontrollera reverse engineering
sheet_df = read_google_sheet_revolut("2021-10-11", "2022-01-02")
excel_df = reverse_engineer_to_excel_format(sheet_df)

# Jämför original vs transformerad
for i, row in sheet_df.head().iterrows():
    print(f"Original: {row['OUTFLOW']} | {row['INFLOW']} | {row['CATEGORY']}")
    excel_row = excel_df.iloc[i]
    print(f"Transformed: {excel_row['Amount']} | {excel_row['Type']} | {excel_row['Description']}")
```

---

*Dokumentet uppdaterat: 2025-05-25*  
*Författare: AI Assistant*  
*Projekt: Budget_updater Revolut Merged Data Integration* 