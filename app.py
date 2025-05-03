import os
import json
import requests
import time
from typing import List, Dict, Any
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
    
    # Initialize tokens dictionary
    detected_tokens = {}
    
    # Only add ETH if the balance is greater than 0
    if eth_balance_in_eth > 0:
        detected_tokens["ETH"] = {
            "address": None,  # Native ETH
            "decimals": 18,
            "balance": eth_balance_in_eth,
            "symbol": "ETH"
        }
        print(f"Added ETH with balance: {eth_balance_in_eth}")
    
    # STEP 1: Use Etherscan API to get all tokens the address has interacted with
    # This will find ALL tokens, not just ETH
    network = "api-sepolia"  # Correct API endpoint for Sepolia
    token_addresses_to_check = []
    
    print(f"Fetching ALL tokens for wallet {wallet_address}")
    
    try:
        # Method 1: Get token transactions (works better for testnets than tokenlist)
        tokentx_url = f"https://{network}.etherscan.io/api?module=account&action=tokentx&address={wallet_address}&sort=desc&apikey={ETHERSCAN_API_KEY}"
        print(f"Calling Etherscan API: {tokentx_url}")
        response = requests.get(tokentx_url).json()
        
        if response.get('status') == '1' and 'result' in response:
            token_txs = response['result']
            print(f"Found {len(token_txs)} token transactions")
            
            # Extract unique token addresses from transactions
            for tx in token_txs:
                if 'contractAddress' in tx and tx['contractAddress']:
                    token_address = Web3.to_checksum_address(tx['contractAddress'])
                    if token_address not in token_addresses_to_check:
                        token_addresses_to_check.append(token_address)
            
            print(f"Found {len(token_addresses_to_check)} unique token addresses from transactions")
        else:
            print(f"Etherscan tokentx API error: {response.get('message', 'Unknown error')}")
        
        # Method 2: Try the tokenlist API too (better for mainnet)
        tokenlist_url = f"https://{network}.etherscan.io/api?module=account&action=tokenlist&address={wallet_address}&apikey={ETHERSCAN_API_KEY}"
        print(f"Calling Etherscan tokenlist API: {tokenlist_url}")
        tokenlist_response = requests.get(tokenlist_url).json()
        
        if tokenlist_response.get('status') == '1' and 'result' in tokenlist_response:
            tokens_data = tokenlist_response['result']
            print(f"Found {len(tokens_data)} tokens from tokenlist")
            
            for token_data in tokens_data:
                try:
                    if 'contractAddress' in token_data and token_data['contractAddress']:
                        token_address = Web3.to_checksum_address(token_data['contractAddress'])
                        if token_address not in token_addresses_to_check:
                            token_addresses_to_check.append(token_address)
                except Exception as e:
                    print(f"Error processing tokenlist data: {str(e)}")
        else:
            print(f"Etherscan tokenlist API error: {tokenlist_response.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"Error fetching token data from Etherscan: {str(e)}")
    
    # STEP 2: Now check the balance of each token address we found
    print(f"Checking balances for {len(token_addresses_to_check)} tokens")
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
            
            print(f"Token {symbol} at {token_address} has balance: {token_balance}")
            
            # Only add tokens with non-zero balance
            if token_balance > 0:
                detected_tokens[symbol] = {
                    "address": token_address,
                    "decimals": decimals,
                    "balance": token_balance,
                    "symbol": symbol,
                    "coingecko_id": token_address.lower()
                }
                print(f"Added token {symbol} with balance {token_balance}")
        except Exception as e:
            print(f"Error checking token {token_address}: {str(e)}")
    
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
    
    # Get live prices for all tokens using the same function that the AI agent uses
    token_symbols = list(detected_tokens.keys())
    print(f"Getting live prices for {len(token_symbols)} tokens: {token_symbols}")
    
    try:
        # Get accurate prices using the same function the AI agent uses
        token_prices = get_live_prices(token_symbols)
        print(f"Got prices: {token_prices}")
        
        # Return both tokens and their live prices
        return jsonify({
            'wallet': wallet_address,
            'tokens': detected_tokens,
            'prices': token_prices  # Add real prices to the response
        })
    except Exception as e:
        print(f"Failed to get live prices: {str(e)}")
        # Fall back to just tokens if price fetch fails
        return jsonify({
            'wallet': wallet_address,
            'tokens': detected_tokens
        })

@app.route('/api/calculate_rebalance', methods=['POST'])
def calculate_rebalance():
    try:
        data = request.json
        print(f"/api/calculate_rebalance received data: {data}")
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        if not data.get('tokens'):
            return jsonify({'error': 'Missing tokens data'}), 400
            
        if not data.get('target_allocation'):
            return jsonify({'error': 'Missing target allocation data'}), 400
        
        tokens = data['tokens']
        target_allocation = data['target_allocation']
        
        print(f"Tokens: {tokens}")
        print(f"Target allocation: {target_allocation}")
        
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
            print(f"Failed to calculate total value: {str(e)}")
            # Print the tokens and prices for debugging
            for token in tokens:
                print(f"Token: {token}, Balance: {tokens[token].get('balance')}, Price: {token_prices.get(token)}")
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
                    print(f"{token} diff: {diff}, amount_usd: {amount_usd}, token_amount: {token_amount}")
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
        
        print(f"Sending response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Unhandled exception in calculate_rebalance: {str(e)}")
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

# AI Agent Functions

# Tool: Get wallet tokens
def get_wallet_tokens(wallet_address: str = None) -> List[Dict[str, Any]]:
    """Fetches ERC-20 token balances from the user's wallet"""
    try:
        # If wallet_address not specified, we'll use the one from request
        if not wallet_address and request and hasattr(request, 'json'):
            data = request.json
            wallet_address = data.get('wallet_address')
            
        if not wallet_address:
            return []
            
        # Normalize the address
        try:
            wallet_address = Web3.to_checksum_address(wallet_address)
        except:
            print(f"Invalid wallet address: {wallet_address}")
            return []
            
        # Get ETH balance
        eth_balance = w3.eth.get_balance(wallet_address)
        eth_balance_in_eth = eth_balance / 10**18
        
        # Initialize token list with ETH
        token_balances = [{
            "symbol": "ETH",
            "balance": eth_balance_in_eth
        }]
        
        # Get ERC-20 tokens
        network = "api-sepolia"  # Change to mainnet in production
        token_addresses_to_check = []
        
        # Method 1: Get token transactions
        tokentx_url = f"https://{network}.etherscan.io/api?module=account&action=tokentx&address={wallet_address}&sort=desc&apikey={ETHERSCAN_API_KEY}"
        response = requests.get(tokentx_url).json()
        
        if response.get('status') == '1' and 'result' in response:
            token_txs = response['result']
            # Extract unique token addresses from transactions
            for tx in token_txs:
                if 'contractAddress' in tx and tx['contractAddress']:
                    token_address = Web3.to_checksum_address(tx['contractAddress'])
                    if token_address not in token_addresses_to_check:
                        token_addresses_to_check.append(token_address)
        
        # Method 2: Try the tokenlist API too
        tokenlist_url = f"https://{network}.etherscan.io/api?module=account&action=tokenlist&address={wallet_address}&apikey={ETHERSCAN_API_KEY}"
        tokenlist_response = requests.get(tokenlist_url).json()
        
        if tokenlist_response.get('status') == '1' and 'result' in tokenlist_response:
            for token in tokenlist_response['result']:
                if 'contractAddress' in token and token['contractAddress']:
                    token_address = Web3.to_checksum_address(token['contractAddress'])
                    if token_address not in token_addresses_to_check:
                        token_addresses_to_check.append(token_address)
        
        # Check balances for each token
        for token_address in token_addresses_to_check:
            try:
                token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
                symbol = token_contract.functions.symbol().call()
                decimals = token_contract.functions.decimals().call()
                balance_wei = token_contract.functions.balanceOf(wallet_address).call()
                balance = balance_wei / (10 ** decimals)
                
                # Only include tokens with non-zero balance
                if balance > 0:
                    token_balances.append({
                        "symbol": symbol,
                        "balance": balance
                    })
            except Exception as e:
                print(f"Error getting token data for {token_address}: {str(e)}")
                continue
        
        return token_balances
    except Exception as e:
        print(f"Error in get_wallet_tokens: {str(e)}")
        return []

# Tool: Get live token prices
def get_live_prices(symbols: List[str]) -> Dict[str, float]:
    """Returns current USD prices for each token symbol"""
    try:
        # Create a dictionary to store prices
        prices = {}
        
        # Define fallback prices for test tokens
        test_token_prices = {
            "ETH": 3500.00,
            "USDC": 1.00,
            "USDT": 1.00,
            "DAI": 1.00,
            "WETH": 3500.00,
            "WBTC": 62000.00,
            "LUSD": 1.00,
            "EUSD": 1.00,
            "LUSDG": 1.00,
            "TIGER": 5.00,
            "WLETH": 3500.00,
            "aEthWETH": 3500.00,
        }
        
        # Handle ETH price separately
        if "ETH" in symbols:
            # Get ETH price from CoinGecko API
            eth_price_url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
            try:
                eth_response = requests.get(eth_price_url).json()
                if "ethereum" in eth_response:
                    prices["ETH"] = eth_response["ethereum"]["usd"]
                    print(f"[INFO] Got ETH price from CoinGecko: ${prices['ETH']}")
                else:
                    # Fallback price if API fails
                    prices["ETH"] = test_token_prices["ETH"]
                    print(f"[INFO] Using fallback ETH price: ${prices['ETH']}")
            except Exception as e:
                # Fallback price if API fails
                prices["ETH"] = test_token_prices["ETH"]
                print(f"[INFO] Error getting ETH price, using fallback: ${prices['ETH']}. Error: {str(e)}")
        
        # For other tokens, try to get prices or use reasonable fallbacks
        for symbol in symbols:
            # Skip ETH since we already handled it
            if symbol == "ETH" or symbol in prices:
                continue
                
            # First check if we have a fallback price for this token
            if symbol in test_token_prices:
                prices[symbol] = test_token_prices[symbol]
                print(f"[INFO] Using predefined price for {symbol}: ${prices[symbol]}")
                continue
                
            # Known tokens with CoinGecko IDs
            token_lookup = {
                "USDC": "usd-coin",
                "USDT": "tether",
                "DAI": "dai",
                "WETH": "weth",
                "WBTC": "wrapped-bitcoin",
            }
            
            if symbol in token_lookup:
                # This is a known token with a CoinGecko ID
                coingecko_id = token_lookup[symbol]
                price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
                
                try:
                    response = requests.get(price_url).json()
                    if coingecko_id in response:
                        prices[symbol] = response[coingecko_id]["usd"]
                        print(f"[INFO] Got {symbol} price from CoinGecko: ${prices[symbol]}")
                    else:
                        # Use fallback from our predefined list or reasonable defaults
                        prices[symbol] = test_token_prices.get(symbol, 1.0)
                        print(f"[INFO] No price data for {symbol}, using fallback: ${prices[symbol]}")
                except Exception as e:
                    # Use fallback from our list
                    prices[symbol] = test_token_prices.get(symbol, 1.0)
                    print(f"[INFO] Error getting {symbol} price, using fallback: ${prices[symbol]}. Error: {str(e)}")
            else:
                # For unknown tokens, try to search by name
                try:
                    search_url = f"https://api.coingecko.com/api/v3/search?query={symbol}"
                    search_results = requests.get(search_url).json()
                    
                    if search_results.get("coins") and len(search_results["coins"]) > 0:
                        # Take the first result
                        coin_id = search_results["coins"][0]["id"]
                        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
                        price_data = requests.get(price_url).json()
                        
                        if coin_id in price_data:
                            prices[symbol] = price_data[coin_id]["usd"]
                            print(f"[INFO] Found {symbol} via search, price: ${prices[symbol]}")
                        else:
                            # Default to our predefined list or fallback value
                            prices[symbol] = test_token_prices.get(symbol, 1.0)
                            print(f"[INFO] Found {symbol} via search but no price, using fallback: ${prices[symbol]}")
                    else:
                        # No search results - this is likely a test token
                        prices[symbol] = test_token_prices.get(symbol, 1.0)
                        print(f"[INFO] {symbol} not found in CoinGecko, using fallback: ${prices[symbol]}")
                except Exception as e:
                    # Use fallback from our list or default
                    prices[symbol] = test_token_prices.get(symbol, 1.0)
                    print(f"[INFO] Error searching for {symbol}, using fallback: ${prices[symbol]}. Error: {str(e)}")
        
        return prices
    except Exception as e:
        print(f"Error in get_live_prices: {str(e)}")
        # Return best-effort prices or fallbacks
        fallback_prices = {}
        for symbol in symbols:
            fallback_prices[symbol] = test_token_prices.get(symbol, 1.0)
        return fallback_prices

# Tool: Get trending tokens
def get_trending_tokens() -> List[Dict[str, Any]]:
    """Returns currently trending cryptocurrencies with price data"""
    try:
        # Use CoinGecko's trending API
        url = "https://api.coingecko.com/api/v3/search/trending"
        response = requests.get(url).json()
        
        trending_tokens = []
        if "coins" in response:
            # Extract relevant data for each trending token
            for item in response["coins"][:10]:  # Limit to top 10
                coin = item["item"]
                trending_tokens.append({
                    "symbol": coin["symbol"],
                    "name": coin["name"],
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "price_btc": coin.get("price_btc", 0)
                })
            
            # Get USD prices for these tokens
            symbols = [token["symbol"] for token in trending_tokens]
            prices = get_live_prices(symbols)
            
            # Add USD prices to the trending tokens
            for token in trending_tokens:
                token["price_usd"] = prices.get(token["symbol"], 0)
        
        return trending_tokens
    except Exception as e:
        print(f"Error in get_trending_tokens: {str(e)}")
        return []

# The AI Portfolio Agent endpoint
@app.route('/api/portfolio-agent', methods=['POST'])
def portfolio_agent():
    """Process user queries about their portfolio using an AI agent with tool calling"""
    try:
        data = request.json
        user_message = data.get('user_message', '')
        wallet_address = data.get('wallet_address', '')
        
        if not wallet_address:
            return jsonify({
                'response': "Please connect your wallet first. I need to access your token balances to analyze your portfolio."
            })
        
        # Define the tools available to the AI agent
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_wallet_tokens",
                    "description": "Returns the user's ERC-20 token balances from their wallet.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_live_prices",
                    "description": "Returns current USD prices for each token symbol.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbols": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List of token symbols to get prices for."
                            }
                        },
                        "required": ["symbols"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_trending_tokens",
                    "description": "Returns currently trending cryptocurrencies with price data.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
        
        # Initialize the AI agent conversation
        system_message = """
        You are CryptoPortfolioAgent — an AI assistant embedded in a web app. Your job is to help users analyze the tokens in their MetaMask wallet and advise whether their portfolio is balanced, underweight, or overweight using live market prices. Always think in clear, numbered "Thought:" steps. Whenever you need on-chain balances or market data, call the appropriate tool.
        
        Guidelines:
        - Start every response with "Thought: 1. ..." and enumerate your reasoning steps.
        - After you receive function output, continue your chain of thought.
        - Compute USD value for each token and its percentage of total portfolio.
        - If % > 30%, label overweight; if % < 5%, label underweight; otherwise OK.
        - In your final "Answer:" section, provide clear analysis and rebalancing suggestions.
        - When asked about hot/trending tokens, call get_trending_tokens() to identify potential investments.
        - Remember, the portfolio might be of Test Tokens which don't actually have real prices. In this case use fall back prices.
        
        Remember, users are looking for actionable portfolio advice. Be specific and reasoned in your analysis.
        """
        
        # Begin the conversation with the AI
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        # Process user message and manage tool calling flow
        full_response = ""
        response_data = {}
        
        while True:
            # Call OpenAI API
            response = openai_client.chat.completions.create(
                model="gpt-4-0125-preview",  # Or other model with function calling
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            assistant_message = response.choices[0].message
            messages.append(assistant_message)
            full_response += assistant_message.content if assistant_message.content else ""
            
            # Check if tool calling is required
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    function_response = None
                    if function_name == "get_wallet_tokens":
                        function_response = get_wallet_tokens(wallet_address)
                    elif function_name == "get_live_prices":
                        function_response = get_live_prices(function_args.get("symbols", []))
                    elif function_name == "get_trending_tokens":
                        function_response = get_trending_tokens()
                    
                    # Add the function response to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(function_response)
                    })
                    
                    # For portfolio analysis, store relevant data to return to frontend
                    if function_name == "get_wallet_tokens":
                        response_data["wallet_tokens"] = function_response
                    elif function_name == "get_live_prices":
                        response_data["token_prices"] = function_response
                    elif function_name == "get_trending_tokens":
                        response_data["trending_tokens"] = function_response
            else:
                # No more tool calls needed
                break
        
        # When calculating portfolio, perform additional analysis
        if "wallet_tokens" in response_data and "token_prices" in response_data:
            # Calculate portfolio value and allocations
            tokens = response_data["wallet_tokens"]
            prices = response_data["token_prices"]
            
            total_value = 0
            portfolio_analysis = []
            
            for token in tokens:
                symbol = token["symbol"]
                balance = token["balance"]
                price = prices.get(symbol, 0)
                usd_value = balance * price
                total_value += usd_value
            
            for token in tokens:
                symbol = token["symbol"]
                balance = token["balance"]
                price = prices.get(symbol, 0)
                usd_value = balance * price
                percentage = (usd_value / total_value * 100) if total_value > 0 else 0
                status = "overweight" if percentage > 30 else "underweight" if percentage < 5 else "balanced"
                
                portfolio_analysis.append({
                    "symbol": symbol,
                    "balance": balance,
                    "price": price,
                    "usd_value": usd_value,
                    "percentage": percentage,
                    "status": status
                })
            
            # Sort by percentage (descending)
            portfolio_analysis.sort(key=lambda x: x["percentage"], reverse=True)
            response_data["portfolio_analysis"] = portfolio_analysis
            response_data["total_value"] = total_value
        
        return jsonify({
            'response': full_response,
            'data': response_data
        })
        
    except Exception as e:
        print(f"Error in portfolio_agent: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'response': f"An error occurred: {str(e)}. Please try again."
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
