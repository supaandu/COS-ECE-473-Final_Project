import os
import json
import requests
import time
import re
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from web3 import Web3
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Flask app
app = Flask(__name__)
CORS(app, supports_credentials=True)

# API Keys, URLs
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
INFURA_URL = os.getenv("INFURA_URL")
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# ABI for ERC20 tokens
ERC20_ABI = [
    # balanceOf function
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    # decimals function
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    # symbol function
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/detect_tokens', methods=['POST'])
def detect_tokens():
    data = request.json
    wallet_address = data.get('wallet_address')
    
    if not wallet_address:
        return jsonify({'error': 'No wallet address provided'}), 400
    
    # Normalize the address
    try:
        wallet_address = Web3.to_checksum_address(wallet_address)
    except:
        return jsonify({'error': 'Invalid wallet address'}), 400
        
    # Get ETH balance
    eth_balance = w3.eth.get_balance(wallet_address)
    eth_balance_in_eth = eth_balance / 10**18
    
    # Initialize tokens dictionary with ETH
    detected_tokens = {
        "ETH": {
            "address": None,  # Native ETH
            "decimals": 18,
            "balance": eth_balance_in_eth,
            "symbol": "ETH"
        }
    }
    
    # STEP 1: Use Etherscan API to get all tokens the address has interacted with
    # This will find ALL tokens, not just ETH
    network = "api-sepolia"  # Correct API endpoint for Sepolia
    token_addresses_to_check = []
    
    print(f"[DEBUG] Fetching ALL tokens for wallet {wallet_address}")
    
    try:
        # Method 1: Get token transactions (works better for testnets than tokenlist)
        tokentx_url = f"https://{network}.etherscan.io/api?module=account&action=tokentx&address={wallet_address}&sort=desc&apikey={ETHERSCAN_API_KEY}"
        print(f"[DEBUG] Calling Etherscan API: {tokentx_url}")
        response = requests.get(tokentx_url).json()
        
        if response.get('status') == '1' and 'result' in response:
            token_txs = response['result']
            print(f"[DEBUG] Found {len(token_txs)} token transactions")
            
            # Extract unique token addresses from transactions
            for tx in token_txs:
                if 'contractAddress' in tx and tx['contractAddress']:
                    token_address = Web3.to_checksum_address(tx['contractAddress'])
                    if token_address not in token_addresses_to_check:
                        token_addresses_to_check.append(token_address)
            
            print(f"[DEBUG] Found {len(token_addresses_to_check)} unique token addresses from transactions")
        else:
            print(f"[DEBUG] Etherscan tokentx API error: {response.get('message', 'Unknown error')}")
        
        # Method 2: Try the tokenlist API too (better for mainnet)
        tokenlist_url = f"https://{network}.etherscan.io/api?module=account&action=tokenlist&address={wallet_address}&apikey={ETHERSCAN_API_KEY}"
        print(f"[DEBUG] Calling Etherscan tokenlist API: {tokenlist_url}")
        tokenlist_response = requests.get(tokenlist_url).json()
        
        if tokenlist_response.get('status') == '1' and 'result' in tokenlist_response:
            tokens_data = tokenlist_response['result']
            print(f"[DEBUG] Found {len(tokens_data)} tokens from tokenlist")
            
            for token_data in tokens_data:
                try:
                    if 'contractAddress' in token_data and token_data['contractAddress']:
                        token_address = Web3.to_checksum_address(token_data['contractAddress'])
                        if token_address not in token_addresses_to_check:
                            token_addresses_to_check.append(token_address)
                except Exception as e:
                    print(f"[DEBUG] Error processing tokenlist data: {str(e)}")
        else:
            print(f"[DEBUG] Etherscan tokenlist API error: {tokenlist_response.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"[DEBUG] Error fetching token data from Etherscan: {str(e)}")
    
    # STEP 2: Now check the balance of each token address we found
    print(f"[DEBUG] Checking balances for {len(token_addresses_to_check)} tokens")
    for token_address in token_addresses_to_check:
        try:
            token_contract = w3.eth.contract(
                address=token_address,
                abi=ERC20_ABI
            )
            
            # Get token info
            symbol = token_contract.functions.symbol().call()
            decimals = token_contract.functions.decimals().call()
            raw_balance = token_contract.functions.balanceOf(wallet_address).call()
            token_balance = raw_balance / (10 ** decimals)
            
            print(f"[DEBUG] Token {symbol} at {token_address} has balance: {token_balance}")
            
            # Only add tokens with non-zero balance
            if token_balance > 0:
                detected_tokens[symbol] = {
                    "address": token_address,
                    "decimals": decimals,
                    "balance": token_balance,
                    "symbol": symbol,
                    "coingecko_id": token_address.lower()
                }
                print(f"[DEBUG] Added token {symbol} with balance {token_balance}")
        except Exception as e:
            print(f"[DEBUG] Error checking token {token_address}: {str(e)}")
    
    # As a fallback or supplement, also check token addresses provided by the frontend
    if 'token_addresses' in data and isinstance(data['token_addresses'], list):
        for token_address in data['token_addresses']:
            # Skip if we already have this token
            token_address = Web3.to_checksum_address(token_address)
            token_address_lower = token_address.lower()
            
            # Check if we already have this token
            already_added = False
            for symbol, token in detected_tokens.items():
                if token.get('address') and token['address'].lower() == token_address_lower:
                    already_added = True
                    break
            
            if already_added:
                continue
                
            try:
                token_contract = w3.eth.contract(
                    address=token_address,
                    abi=ERC20_ABI
                )
                
                # Get token info
                symbol = token_contract.functions.symbol().call()
                decimals = token_contract.functions.decimals().call()
                raw_balance = token_contract.functions.balanceOf(wallet_address).call()
                token_balance = raw_balance / (10 ** decimals)
                
                # Only add tokens with non-zero balance
                if token_balance > 0:
                    detected_tokens[symbol] = {
                        "address": token_address,
                        "decimals": decimals,
                        "balance": token_balance,
                        "symbol": symbol,
                        "coingecko_id": token_address_lower
                    }
            except Exception as e:
                print(f"Error getting token data for {token_address}: {str(e)}")
    
    return jsonify({
        'wallet': wallet_address,
        'tokens': detected_tokens
    })

@app.route('/api/calculate_rebalance', methods=['POST'])
def calculate_rebalance():
    try:
        data = request.json
        print(f"[DEBUG] /api/calculate_rebalance received data: {data}")
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        if not data.get('tokens'):
            return jsonify({'error': 'Missing tokens data'}), 400
            
        if not data.get('target_allocation'):
            return jsonify({'error': 'Missing target allocation data'}), 400
        
        tokens = data['tokens']
        target_allocation = data['target_allocation']
        
        print(f"[DEBUG] Tokens: {tokens}")
        print(f"[DEBUG] Target allocation: {target_allocation}")
        
        # Get token prices from CoinGecko
        token_prices = {}
        
        # Get ETH price
        try:
            eth_response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd').json()
            token_prices['ETH'] = eth_response['ethereum']['usd']
        except Exception as e:
            print(f"Error fetching ETH price: {e}")
            token_prices['ETH'] = 1500  # Fallback price
    
        # For all other tokens, try to get prices from CoinGecko
        # First, collect CoinGecko IDs or contract addresses
        token_addresses = []
        for symbol, token_data in tokens.items():
            if symbol != 'ETH' and token_data.get('address'):
                token_addresses.append(token_data['address'].lower())
    
        if token_addresses:
            try:
                # Use CoinGecko contract address endpoint
                addresses_str = ','.join(token_addresses)
                token_response = requests.get(
                    f'https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={addresses_str}&vs_currencies=usd'
                ).json()
                
                # Process response and map back to symbols
                for symbol, token_data in tokens.items():
                    if symbol != 'ETH' and token_data.get('address'):
                        address_key = token_data['address'].lower()
                        if address_key in token_response and 'usd' in token_response[address_key]:
                            token_prices[symbol] = token_response[address_key]['usd']
                        else:
                            # If price not found, use fallback
                            token_prices[symbol] = 1.0  # Fallback price
            except Exception as e:
                print(f"Error fetching token prices: {e}")
    
        # Add fallback prices for any tokens that weren't found
        for symbol in tokens:
            if symbol not in token_prices:
                token_prices[symbol] = 1.0  # Fallback price
    
        # Calculate total portfolio value
        try:
            total_value = sum(tokens[token]['balance'] * token_prices[token] for token in tokens)
            if total_value == 0:
                return jsonify({'error': 'Total portfolio value is zero'}), 400
        except Exception as e:
            print(f"[ERROR] Failed to calculate total value: {str(e)}")
            # Print the tokens and prices for debugging
            for token in tokens:
                print(f"[DEBUG] Token: {token}, Balance: {tokens[token].get('balance')}, Price: {token_prices.get(token)}")
            return jsonify({'error': f'Error calculating portfolio value: {str(e)}'}), 500
    
        # Calculate current allocation percentages
        current_allocation = {
            token: (tokens[token]['balance'] * token_prices[token]) / total_value * 100 if total_value != 0 else 0
            for token in tokens
        }
    
        # Generate rebalance actions
        actions = []
        for token in tokens:
            if token in target_allocation:
                diff = current_allocation[token] - target_allocation[token]
                if abs(diff) > 0.0000001:  # Only suggest changes if difference is significant
                    direction = "sell" if diff > 0 else "buy"
                    amount_usd = abs(diff) * total_value / 100
                    token_price = token_prices[token]
                    token_amount = amount_usd / token_price
                    print(f"[DEBUG] {token} diff: {diff}, amount_usd: {amount_usd}, token_amount: {token_amount}")
                    actions.append({
                        'token': token,
                        'action': direction,
                        'amount': token_amount,
                        'percentage_change': abs(diff)
                    })
    
        response_data = {
            'total_value': total_value,
            'current_allocation': current_allocation,
            'target_allocation': target_allocation,
            'rebalance_actions': actions,
            'token_prices': token_prices
        }
        
        print(f"[DEBUG] Sending response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[ERROR] Unhandled exception in calculate_rebalance: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500

@app.route('/api/parse_query', methods=['POST'])
def parse_query():
    data = request.json
    user_query = data.get('query')
    
    if not user_query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Use OpenAI to parse the query and extract target allocations
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # Using gpt-3.5-turbo for better compatibility
            messages=[
                {"role": "system", "content": "You are a financial assistant that extracts target portfolio allocations from user queries. Extract token symbols and their target percentage allocations. Return ONLY a valid JSON object with token symbols as keys and percentage values as numbers. Format: {\"TOKEN1\": 25, \"TOKEN2\": 75}. The response must be valid JSON with no additional text, markdown, or formatting."},
                {"role": "user", "content": user_query}
            ]
            # Removed response_format parameter that was causing errors
        )
        
        # Extract the response content and parse it as JSON
        content = response.choices[0].message.content.strip()
        
        # Clean the response in case it contains markdown or other formatting
        if content.startswith('```json'):
            content = content.split('```json')[1]
        if content.endswith('```'):
            content = content.split('```')[0]
        content = content.strip()
        
        try:
            target_allocation = json.loads(content)
        
            # Validate the response to ensure it contains percentages that sum to approximately 100%
            total_percentage = sum(target_allocation.values())
            if not (95 <= total_percentage <= 105):  # Allow for small rounding errors
                # Normalize to 100%
                target_allocation = {k: (v / total_percentage * 100) for k, v in target_allocation.items()}
        except json.JSONDecodeError as json_error:
            print(f"Error parsing JSON from OpenAI response: {json_error}")
            print(f"Raw content: {content}")
            raise Exception(f"Failed to parse JSON from AI response: {content}")
        
        return jsonify({
            'query': user_query,
            'parsed_allocation': target_allocation
        })
    
    except Exception as e:
        print(f"Error parsing query with OpenAI: {str(e)}")
        return jsonify({'error': f'Failed to parse query: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
