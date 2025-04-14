# Portfolio Rebalancing Tool

Princeton COS/ECE 473 Final Project

## Overview

This web application allows users to:
1. Connect their Ethereum wallet
2. View their current token holdings
3. Set target allocations for their portfolio
4. Calculate rebalancing actions to reach those target allocations

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Git

### First-Time Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd COS-ECE-473-Final_Project
```

2. **Create and activate virtual environment**

On macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Set up environment variables**

Create a `.env` file in the root directory with the following content:
```
ETHERSCAN_API_KEY=your_etherscan_api_key
INFURA_URL=your_infura_url
```

You'll need to:
- Get an API key from [Etherscan](https://etherscan.io/apis)
- Create an account on [Infura](https://infura.io/) and get an Ethereum endpoint URL

### Running the Application

1. **Activate the virtual environment** (if not already activated)

On macOS/Linux:
```bash
source venv/bin/activate
```

On Windows:
```bash
venv\Scripts\activate
```

2. **Run the Flask application**

```bash
python app.py
```

3. **Open in browser**

Open http://localhost:5001 in your web browser

### Deactivating the Virtual Environment

When you're done working on the project, you can deactivate the virtual environment:

```bash
deactivate
``` 

source venv/bin/activate  # On macOS/Linux
deactivate

source .venv/bin/activate