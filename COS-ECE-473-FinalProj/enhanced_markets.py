import pandas as pd
import json
import requests
import ast
import time
from tqdm import tqdm  # For progress bar

def get_market_outcomes(market_id):
    """Get detailed information for a specific market ID"""
    url = f"https://gamma-api.polymarket.com/markets/{market_id}"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

# Load the existing ETH markets dataframe
try:
    # Try to load from CSV file first
    df = pd.read_csv("eth_betting_markets.csv")
    print(f"Loaded dataframe with {len(df)} ETH markets")
except FileNotFoundError:
    print("CSV file not found. Please run the initial code block first.")
    exit()

# Save original column names
original_columns = df.columns.tolist()

# New columns to extract from the detailed market data
additional_columns = [
    "outcomes", "outcomePrices", "volumeNum", "liquidityNum", 
    "endDateIso", "volume24hr", "clobTokenIds", "fpmmLive", 
    "competitive", "approved", "spread", "oneDayPriceChange", 
    "lastTradePrice", "bestBid", "bestAsk"
]

# Initialize new columns
for col in additional_columns:
    df[col] = None

# Add explicit percentage columns
df['yes_percentage'] = None
df['no_percentage'] = None
df['outcome_details'] = None

# Fetch detailed information for each market and update the dataframe
print(f"Fetching detailed information for {len(df)} markets...")
for idx, row in tqdm(df.iterrows(), total=len(df)):
    market_id = row['id']
    market_data = get_market_outcomes(market_id)
    
    if market_data:
        # Update dataframe with additional columns
        for col in additional_columns:
            if col in market_data:
                df.at[idx, col] = market_data[col]
        
        # Add processed outcome information
        try:
            outcomes_raw = market_data.get("outcomes", [])
            prices_raw = market_data.get("outcomePrices", [])
            
            if outcomes_raw and prices_raw:
                outcomes = ast.literal_eval(outcomes_raw)
                prices = ast.literal_eval(prices_raw)
                
                # Store all outcome details in a readable format
                outcome_details = []
                for i, (outcome, price) in enumerate(zip(outcomes, prices)):
                    price_pct = float(price) * 100
                    outcome_details.append(f"{outcome}: {price_pct:.2f}%")
                df.at[idx, 'outcome_details'] = " | ".join(outcome_details)
                
                # Specifically handle Yes/No percentages if present
                if 'Yes' in outcomes and 'No' in outcomes:
                    yes_idx = outcomes.index('Yes')
                    no_idx = outcomes.index('No')
                    df.at[idx, 'yes_percentage'] = float(prices[yes_idx]) * 100
                    df.at[idx, 'no_percentage'] = float(prices[no_idx]) * 100
                    
        except (SyntaxError, ValueError) as e:
            print(f"Error processing outcomes for market {market_id}: {e}")
    
    # Add a small delay to avoid hitting rate limits
    time.sleep(0.2)

# Rename columns to be more descriptive
column_renames = {
    'volumeNum': 'total_volume',
    'liquidityNum': 'total_liquidity',
    'endDateIso': 'end_date_iso',
    'volume24hr': 'volume_24hr',
    'oneDayPriceChange': 'one_day_price_change',
    'lastTradePrice': 'last_trade_price',
}
df = df.rename(columns=column_renames)

# Reorder columns to keep original columns first, followed by new columns
new_columns = original_columns + [
    'yes_percentage', 'no_percentage', 'outcome_details',
    'total_volume', 'total_liquidity', 'end_date_iso', 'volume_24hr',
    'spread', 'one_day_price_change', 'last_trade_price', 'bestBid', 'bestAsk'
]

# Only include columns that actually exist in the dataframe
new_columns = [col for col in new_columns if col in df.columns]
df = df[new_columns]

# Save the enhanced dataframe
df.to_csv("enhanced_eth_markets.csv", index=False)
print(f"✅ Saved enhanced dataframe with {len(df)} ETH markets and additional columns.")

# Display the first few rows with the new columns
print("\nSample of enhanced dataframe:")
pd.set_option('display.max_columns', None)  # Show all columns
print(df.head(3))
