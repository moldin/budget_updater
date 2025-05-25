#!/usr/bin/env python3
"""
Inspect the merged FirstCard Excel file to verify format and content.
"""

import pandas as pd
from pathlib import Path

def inspect_merged_file():
    """Inspect the merged FirstCard Excel file."""
    file_path = Path("data/firstcard_all_merged.xlsx")
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    print(f"📖 Reading merged file: {file_path}")
    
    # Read Excel file
    df = pd.read_excel(file_path)
    
    print(f"\n📊 File Summary:")
    print(f"   Total rows: {len(df):,}")
    print(f"   Columns: {list(df.columns)}")
    
    # Date range
    if 'Datum' in df.columns:
        df['Datum'] = pd.to_datetime(df['Datum'])
        min_date = df['Datum'].min()
        max_date = df['Datum'].max()
        print(f"   Date range: {min_date.date()} to {max_date.date()}")
    
    # Amount statistics
    if 'Belopp' in df.columns:
        total_amount = df['Belopp'].sum()
        positive_amount = df[df['Belopp'] > 0]['Belopp'].sum()
        negative_amount = df[df['Belopp'] < 0]['Belopp'].sum()
        zero_amount_count = len(df[df['Belopp'] == 0])
        
        print(f"\n💰 Amount Statistics:")
        print(f"   Total amount: {total_amount:,.2f} kr")
        print(f"   Positive (outflow): {positive_amount:,.2f} kr")
        print(f"   Negative (inflow): {negative_amount:,.2f} kr")
        print(f"   Zero amounts: {zero_amount_count} transactions")
    
    # Sample data
    print(f"\n📋 First 10 rows:")
    for i, row in df.head(10).iterrows():
        date_str = row['Datum'].strftime('%Y-%m-%d') if pd.notna(row['Datum']) else 'N/A'
        amount = row['Belopp'] if pd.notna(row['Belopp']) else 0
        description = str(row['Reseinformation / Inköpsplats'])[:50] if pd.notna(row['Reseinformation / Inköpsplats']) else ''
        print(f"   {date_str} | {amount:8.2f} kr | {description}")
    
    print(f"\n📋 Last 10 rows:")
    for i, row in df.tail(10).iterrows():
        date_str = row['Datum'].strftime('%Y-%m-%d') if pd.notna(row['Datum']) else 'N/A'
        amount = row['Belopp'] if pd.notna(row['Belopp']) else 0
        description = str(row['Reseinformation / Inköpsplats'])[:50] if pd.notna(row['Reseinformation / Inköpsplats']) else ''
        print(f"   {date_str} | {amount:8.2f} kr | {description}")
    
    # Check for potential issues
    print(f"\n🔍 Data Quality Checks:")
    
    # Missing dates
    missing_dates = df['Datum'].isna().sum()
    print(f"   Missing dates: {missing_dates}")
    
    # Missing amounts
    missing_amounts = df['Belopp'].isna().sum()
    print(f"   Missing amounts: {missing_amounts}")
    
    # Empty descriptions
    empty_descriptions = df['Reseinformation / Inköpsplats'].isna().sum()
    print(f"   Empty descriptions: {empty_descriptions}")
    
    # Check for duplicates (same date, amount, description)
    duplicates = df.duplicated(subset=['Datum', 'Belopp', 'Reseinformation / Inköpsplats']).sum()
    print(f"   Potential duplicates: {duplicates}")
    
    # Check date distribution
    print(f"\n📅 Date Distribution:")
    df['Year'] = df['Datum'].dt.year
    year_counts = df['Year'].value_counts().sort_index()
    for year, count in year_counts.items():
        print(f"   {year}: {count:,} transactions")

if __name__ == "__main__":
    inspect_merged_file() 