import requests
import pandas as pd
from datetime import datetime

# Endpoint
url = "https://api.thegraph.com/subgraphs/name/Polymarket/polymarket"

# GraphQL query — markets with ETH or BTC in question
query = """
{
  markets(first: 20, orderBy: creationTimestamp, orderDirection: desc, 
          where: {question_contains: "ETH"}) {
    id
    question
    creationTimestamp
    endTimestamp
    resolved
    outcomes {
      name
      price
    }
  }
}
"""

# Run query
response = requests.post(url, json={"query": query})
markets = response.json()['data']['markets']

# Clean and print
data = []

for m in markets:
    for outcome in m['outcomes']:
        data.append({
            "id": m['id'],
            "question": m['question'],
            "created": datetime.utcfromtimestamp(int(m['creationTimestamp'])),
            "ends": datetime.utcfromtimestamp(int(m['endTimestamp'])),
            "resolved": m['resolved'],
            "outcome": outcome['name'],
            "probability": float(outcome['price'])
        })

df = pd.DataFrame(data)
print(df.head())


df.to_csv("polymarket_eth_predictions.csv", index=False)
