#!/usr/bin/env python3
"""
Quick diagnostic test for Google Trends API connectivity
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from datetime import date
from services.trends_fetcher import TrendsFetcher
from lib.config import FetcherConfig

print("=== Diagnostic Test ===")
print("1. Loading config...")
config = FetcherConfig()
print(f"   ✓ Config loaded: {len(config.keywords)} keywords for {config.province}")

print("\n2. Initializing TrendsFetcher...")
fetcher = TrendsFetcher(province=config.province, config=config)
print(f"   ✓ Fetcher initialized with retry config: max_retries={config.max_retries}")

print("\n3. Testing pytrends connection...")
print("   Attempting to fetch data for 2025-11-01...")
print("   (This may take 10-60 seconds or fail with rate limiting)")

try:
    records = fetcher.fetch_daily_rsv(
        keywords=['ไข้'],  # Just one keyword for test
        start_date=date(2025, 11, 1),
        end_date=date(2025, 11, 1),
        batch_id='diagnostic_test'
    )
    print(f"\n   ✓ SUCCESS! Fetched {len(records)} records")
    if records:
        r = records[0]
        print(f"     Sample: {r.keyword} on {r.date} = RSV {r.rsv_raw}")
except Exception as e:
    print(f"\n   ✗ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Test Complete ===")
