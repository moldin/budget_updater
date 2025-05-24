# GCP Setup Checklist for BigQuery Data Warehouse

Innan du kör BigQuery setup-skripten behöver du förbereda några saker i Google Cloud Platform (GCP).

## 📋 Checklist

### 1. ✅ **GCP Project Setup**
- [x] Du har ett GCP-projekt (nuvarande: `aspiro-budget-analysis`)
- [x] Billing är aktiverat på projektet (BigQuery kostar pengar!)
- [x] Du har ägarrättigheter eller Editor-rättigheter till projektet

### 2. 🔌 **Aktivera APIs**
I [GCP Console](https://console.cloud.google.com/) → "APIs & Services" → "Library":

- [x] **BigQuery API** - Sök efter "BigQuery API" och klicka "Enable"
- [x] **BigQuery Data Transfer API** (optional, för framtida automatisering)

### 3. 🔐 **Service Account & Authentication**

#### Option A: Service Account (Rekommenderat för produktion)
1. [ ] Gå till [IAM & Admin](https://console.cloud.google.com/iam-admin/serviceaccounts) → "Service Accounts"
2. [ ] Klicka "Create Service Account"
3. [ ] Namn: `budget-updater-bigquery` 
4. [ ] Tilldela följande roller:
   - [ ] **BigQuery Admin** (för att skapa tabeller/dataset)
   - [ ] **BigQuery Data Editor** (för att ladda upp data)
   - [ ] **BigQuery Job User** (för att köra queries)
5. [ ] Klicka "Create and Continue"
6. [ ] Under "Keys" → "Add Key" → "Create new key" → JSON
7. [ ] Ladda ner JSON-filen till `Budget_updater/credentials/bigquery-service-account.json`

#### Option B: User Account (Enklare för development)
1. [x] Kör: `gcloud auth application-default login`
2. [x] Kontrollera att du har rätt projekt: `gcloud config get-value project`

### 4. 🌍 **Sätt Environment Variables**

Skapa eller uppdatera `.env` filen i projektets root:

```bash
# GCP Configuration
GOOGLE_CLOUD_PROJECT=aspiro-budget-analysis
GOOGLE_CLOUD_LOCATION=us-central1

# BigQuery Configuration  
BIGQUERY_DATASET_ID=budget_data_warehouse
BIGQUERY_LOCATION=EU

# Authentication (endast om du använder Service Account)
GOOGLE_APPLICATION_CREDENTIALS=./credentials/bigquery-service-account.json
```

### 5. 📍 **Välj Region**

BigQuery location bör matcha ditt projekt och var din data kommer användas:
- [ ] **EU** (Europa) - Rekommenderat för svenska användare
- [ ] **US** (United States) - Billigare men data lämnar EU
- [ ] Uppdatera `BIGQUERY_LOCATION` i `.env` efter ditt val

### 6. 💰 **Kostnadskontroll** 

BigQuery kostar pengar baserat på:
- **Storage**: ~$0.02 per GB/månad (mycket billigt)
- **Queries**: ~$5 per TB processad data (kan bli dyrt)

Sätt upp budget alerts:
- [ ] Gå till [Billing](https://console.cloud.google.com/billing/budgets)
- [ ] Skapa budget för BigQuery (förslag: $10-50/månad beroende på användning)

## 🧪 **Testa Installation**

Efter att du har genomfört ovanstående, testa att allt fungerar:

```bash
# Aktivera virtual environment
source venv/bin/activate  # eller ditt venv

# Installera dependencies
pip install -r requirements.txt

# Testa BigQuery connection
python -c "
from google.cloud import bigquery
from src.budget_updater.config import Config

config = Config()
client = bigquery.Client(project=config.gcp_project_id)
print(f'✅ Connected to project: {client.project}')
print(f'✅ Dataset will be: {config.bigquery_dataset_id}')
print(f'✅ Location: {config.bigquery_location}')
"
```

Om detta fungerar utan fel är du redo att köra:
```bash
python scripts/setup_bigquery_tables_v2.py
```

## ❌ **Vanliga Problem**

### Authentication Error
```
DefaultCredentialsError: Could not automatically determine credentials
```
**Lösning**: Kontrollera att `GOOGLE_APPLICATION_CREDENTIALS` pekar på rätt fil eller kör `gcloud auth application-default login`

### Permission Denied
```
403 Access Denied: BigQuery BigQuery: Permission denied
```
**Lösning**: Kontrollera att din Service Account eller användare har rätt BigQuery-rättigheter

### Project Not Found
```
404 Not found: Project
```
**Lösning**: Kontrollera att `GOOGLE_CLOUD_PROJECT` är rätt och att du har tillgång till projektet

### Billing Not Enabled
```
BigQuery has not been used in project before or it is disabled
```
**Lösning**: Aktivera billing på projektet i GCP Console

## 📞 **Support**

Om du får problem:
1. Dubbelkolla denna checklist
2. Kolla [BigQuery Quickstart](https://cloud.google.com/bigquery/docs/quickstarts)
3. Använd `gcloud auth list` och `gcloud config list` för att debugga authentication 