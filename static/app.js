// Global variables
let wallet = null;
let tokens = {};
let prices = {};
let customTokens = [];

document.addEventListener("DOMContentLoaded", function () {
  // Check if MetaMask is installed
  if (typeof window.ethereum !== "undefined") {
    console.log("MetaMask is installed!");
    setupEventListeners();
    checkConnection();
  } else {
    document.getElementById("wallet-status").innerHTML =
      '<div class="alert alert-danger">MetaMask is not installed. Please install MetaMask to use this application.</div>';
    document.getElementById("connect-wallet").disabled = true;
  }
});

function setupEventListeners() {
  // Connect wallet button
  document
    .getElementById("connect-wallet")
    .addEventListener("click", connectWallet);

  // Disconnect wallet button
  document
    .getElementById("disconnect-wallet")
    .addEventListener("click", disconnectWallet);

  // Calculate rebalance button
  document
    .getElementById("calculate-rebalance")
    .addEventListener("click", calculateRebalance);

  // Calculate rebalance button
  document
    .getElementById("initiate-rebalance")
    .addEventListener("click", executeTransactions);

  // Add token button in modal
  document
    .getElementById("addTokenBtn")
    .addEventListener("click", addCustomToken);

  // Parse natural language query button
  document
    .getElementById("parse-query")
    .addEventListener("click", parseNaturalLanguageQuery);
}

async function checkConnection() {
  try {
    // Check if already connected
    const accounts = await ethereum.request({ method: "eth_accounts" });
    if (accounts.length !== 0) {
      connectWallet(null, accounts[0]);
    }
  } catch (error) {
    console.error(error);
  }
}

async function connectWallet(event, existingAccount = null) {
  try {
    let accounts;
    if (existingAccount) {
      accounts = [existingAccount];
    } else {
      accounts = await ethereum.request({ method: "eth_requestAccounts" });
    }

    wallet = accounts[0];
    document.getElementById(
      "wallet-status"
    ).innerHTML = `<div class="alert alert-success">Connected: ${shortenAddress(
      wallet
    )}</div>`;

    document.getElementById("connect-wallet").classList.add("d-none");
    document.getElementById("disconnect-wallet").classList.remove("d-none");
    document.getElementById("portfolio-section").classList.remove("d-none");

    // Detect the network
    const chainId = await ethereum.request({ method: "eth_chainId" });
    if (chainId !== "0xaa36a7") {
      // Sepolia is 0xaa36a7
      document.getElementById("wallet-status").innerHTML +=
        '<div class="alert alert-warning mt-2">Please switch to Sepolia Testnet to use this application.</div>';

      // Add a button to switch networks
      const switchButton = document.createElement("button");
      switchButton.innerText = "Switch to Sepolia";
      switchButton.className = "btn btn-warning mt-2";
      switchButton.onclick = switchToSepolia;
      document.getElementById("wallet-status").appendChild(switchButton);
      return;
    }

    // Detect tokens
    detectTokens();
  } catch (error) {
    console.error(error);
    document.getElementById(
      "wallet-status"
    ).innerHTML = `<div class="alert alert-danger">Error connecting to wallet: ${error.message}</div>`;
  }
}

async function switchToSepolia() {
  try {
    await ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0xaa36a7" }], // Sepolia chainId
    });
  } catch (switchError) {
    // If the network is not added, add it
    if (switchError.code === 4902) {
      try {
        await ethereum.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: "0xaa36a7",
              chainName: "Sepolia Testnet",
              nativeCurrency: {
                name: "Sepolia ETH",
                symbol: "ETH",
                decimals: 18,
              },
              rpcUrls: ["https://rpc.sepolia.org"],
              blockExplorerUrls: ["https://sepolia.etherscan.io"],
            },
          ],
        });
      } catch (addError) {
        console.error(addError);
      }
    }
    console.error(switchError);
  }
}

function disconnectWallet() {
  wallet = null;
  tokens = {};
  document.getElementById("wallet-status").innerHTML =
    '<div class="alert alert-secondary">Not connected to MetaMask</div>';

  document.getElementById("connect-wallet").classList.remove("d-none");
  document.getElementById("disconnect-wallet").classList.add("d-none");
  document.getElementById("portfolio-section").classList.add("d-none");
  document.getElementById("rebalance-card").classList.add("d-none");
}

async function detectTokens() {
  if (!wallet) return;

  document.getElementById("loading-portfolio").classList.remove("d-none");
  document.getElementById("portfolio-content").classList.add("d-none");

  try {
    // Get the token list from MetaMask
    const ethereumProvider = window.ethereum;

    // Request user assets from MetaMask
    // Note: This is a MetaMask-specific API
    const assets = await ethereumProvider
      .request({
        method: "wallet_getAssets",
      })
      .catch(() => []);

    // This fallback is used as wallet_getAssets might not be available in all MetaMask versions
    const tokenAddresses = [];

    // If we have assets, use them
    if (assets && assets.length > 0) {
      for (const asset of assets) {
        if (asset.type === "ERC20" && asset.address) {
          tokenAddresses.push(asset.address);
        }
      }
    }

    // Add custom tokens
    customTokens.forEach((token) => {
      if (!tokenAddresses.includes(token)) {
        tokenAddresses.push(token);
      }
    });

    // Call our backend API
    const response = await fetch("/api/detect_tokens", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        wallet_address: wallet,
        token_addresses: tokenAddresses,
      }),
    });

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    tokens = data.tokens;

    // Display tokens
    displayTokens();
  } catch (error) {
    console.error("Error detecting tokens:", error);
    document.getElementById(
      "loading-portfolio"
    ).innerHTML = `<div class="alert alert-danger">Error detecting tokens: ${error.message}</div>`;
  }
}

function displayTokens() {
  const tokensTable = document.getElementById("tokens-table");
  tokensTable.innerHTML = "";

  // Clear allocation form
  const allocationForm = document.getElementById("allocation-form");
  allocationForm.innerHTML = "";

  // First, calculate total value and display tokens
  // We'll get real prices when we calculate rebalance
  let totalValue = 0;

  // Make a placeholder call to calculate_rebalance to get prices
  const target_allocation = {};
  Object.keys(tokens).forEach((symbol) => {
    // Set default target to current distribution
    target_allocation[symbol] = 100 / Object.keys(tokens).length;
  });

  fetchPrices(target_allocation)
    .then((priceData) => {
      prices = priceData.token_prices;
      updateTokenDisplay(priceData.current_allocation, priceData.total_value);
    })
    .catch((error) => {
      console.error("Error fetching prices:", error);
      // Fallback to placeholder prices if API call fails
      const tempPrices = {};
      Object.keys(tokens).forEach((symbol) => {
        tempPrices[symbol] = symbol === "ETH" ? 1500 : 1.0;
      });
      prices = tempPrices;

      // Calculate total value with placeholder prices
      totalValue = Object.keys(tokens).reduce((sum, symbol) => {
        return sum + tokens[symbol].balance * prices[symbol];
      }, 0);

      // Calculate current allocation percentages with placeholders
      const currentAllocation = {};
      Object.keys(tokens).forEach((symbol) => {
        const value = tokens[symbol].balance * prices[symbol];
        currentAllocation[symbol] = (value / totalValue) * 100;
      });

      updateTokenDisplay(currentAllocation, totalValue);
    });
}

function updateTokenDisplay(currentAllocation, totalValue) {
  const tokensTable = document.getElementById("tokens-table");
  tokensTable.innerHTML = "";

  // Clear allocation form
  const allocationForm = document.getElementById("allocation-form");
  allocationForm.innerHTML = "";

  // Update total value display
  document.getElementById("total-value").textContent = totalValue.toFixed(2);

  // Display tokens and create allocation inputs
  Object.keys(tokens).forEach((symbol) => {
    const token = tokens[symbol];
    const price = prices[symbol];
    const value = token.balance * price;
    const percentage = currentAllocation[symbol];

    // Create token row
    const row = document.createElement("tr");
    row.className = "token-row";
    row.innerHTML = `
            <td>${symbol}</td>
            <td>${token.balance.toFixed(6)}</td>
            <td>$${value.toFixed(2)} ($${price.toFixed(2)}/token)</td>
            <td>${percentage.toFixed(2)}%</td>
            <td id="target-${symbol}">0%</td>
        `;
    tokensTable.appendChild(row);

    // Create allocation input
    const inputGroup = document.createElement("div");
    inputGroup.className = "input-group mb-2";
    inputGroup.innerHTML = `
            <span class="input-group-text">${symbol}</span>
            <input type="number" class="form-control allocation-input" id="allocation-${symbol}" 
                   min="0" max="100" step="0.1" value="${Math.round(
                     percentage
                   )}" 
                   data-token="${symbol}">
            <span class="input-group-text">%</span>
        `;
    allocationForm.appendChild(inputGroup);

    // Update target display
    document.getElementById(`target-${symbol}`).textContent = `${Math.round(
      percentage
    )}%`;
  });

  // Add button to add custom token
  const addTokenDiv = document.createElement("div");
  addTokenDiv.className = "mt-3";
  addTokenDiv.innerHTML = `
        <button type="button" class="btn btn-outline-primary btn-sm" 
                data-bs-toggle="modal" data-bs-target="#addTokenModal">
            + Add Custom Token
        </button>
    `;
  allocationForm.appendChild(addTokenDiv);

  // Add event listeners to allocation inputs
  document.querySelectorAll(".allocation-input").forEach((input) => {
    input.addEventListener("input", updateAllocationTotal);
    input.addEventListener("change", function () {
      const symbol = this.getAttribute("data-token");
      document.getElementById(
        `target-${symbol}`
      ).textContent = `${this.value}%`;
      updateAllocationTotal();
    });
  });

  // Update allocation total
  updateAllocationTotal();

  // Show portfolio content
  document.getElementById("loading-portfolio").classList.add("d-none");
  document.getElementById("portfolio-content").classList.remove("d-none");
}

function updateAllocationTotal() {
  let total = 0;
  document.querySelectorAll(".allocation-input").forEach((input) => {
    total += parseFloat(input.value || 0);
  });

  document.getElementById("allocation-total").textContent = total.toFixed(1);

  // Enable/disable calculate button based on total
  const calculateButton = document.getElementById("calculate-rebalance");
  const initiateButton = document.getElementById("initiate-rebalance");
  if (Math.abs(total - 100) < 0.1) {
    calculateButton.disabled = false;
    initiateButton.disabled = false;
  } else {
    calculateButton.disabled = true;
    initiateButton.disabled = true;
  }
}

async function fetchPrices(targetAllocation) {
  // Call our backend API to get prices
  const response = await fetch("/api/calculate_rebalance", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tokens: tokens,
      target_allocation: targetAllocation,
    }),
  });

  return await response.json();
}

async function parseNaturalLanguageQuery() {
  const queryInput = document.getElementById("natural-language-query");
  const query = queryInput.value.trim();

  if (!query) {
    alert("Please enter a query");
    return;
  }

  document.getElementById("query-status").innerHTML =
    '<div class="alert alert-info">Processing your query...</div>';

  // Send request to backend
  fetch("/api/parse_query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.error) {
        document.getElementById(
          "query-status"
        ).innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        return;
      }

      // Fill in the allocation inputs with the parsed values
      const allocations = data.parsed_allocation;
      document.getElementById(
        "query-status"
      ).innerHTML = `<div class="alert alert-success">Successfully parsed your request!</div>`;

      // Clear existing allocations
      const tokenInputs = document.querySelectorAll(".allocation-input");
      tokenInputs.forEach((input) => {
        input.value = "";
      });

      // Set new allocations from the parsed query
      Object.entries(allocations).forEach(([symbol, percentage]) => {
        const inputElement = document.querySelector(
          `.allocation-input[data-token="${symbol}"]`
        );
        if (inputElement) {
          inputElement.value = percentage.toFixed(1);
        } else {
          console.warn(`Token ${symbol} from query not found in portfolio`);
        }
      });

      // Update total
      updateAllocationTotal();
    })
    .catch((error) => {
      console.error("Error parsing query:", error);
      document.getElementById(
        "query-status"
      ).innerHTML = `<div class="alert alert-danger">Error parsing your query: ${error.message}</div>`;
    });
}

async function calculateRebalance() {
  if (!wallet || Object.keys(tokens).length === 0) {
    alert("Please connect your wallet and detect tokens first");
    return;
  }

  // Get allocation percentages
  const tokenInputs = document.querySelectorAll(".allocation-input");
  const targetAllocation = {};

  tokenInputs.forEach((input) => {
    const symbol = input.getAttribute("data-token");
    const percentage = parseFloat(input.value);

    if (!isNaN(percentage) && percentage > 0) {
      targetAllocation[symbol] = percentage;
    }
  });

  // Validate that we have target allocations
  if (Object.keys(targetAllocation).length === 0) {
    alert("Please enter at least one target allocation percentage");
    return;
  }

  console.log("Tokens being sent to backend:", tokens);
  console.log("Target allocation being sent to backend:", targetAllocation);

  // Display loading indicator
  document.getElementById("rebalance-results").innerHTML = `
        <div class="text-center">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p>Calculating rebalance strategy...</p>
        </div>
    `;
  document.getElementById("rebalance-card").classList.remove("d-none");

  // Make sure we have valid token data
  if (!tokens || Object.keys(tokens).length === 0) {
    console.error("Token data is missing or empty");
    document.getElementById("rebalance-results").innerHTML = `
            <div class="alert alert-danger">Error: Token data is missing or empty. Please refresh the page and try again.</div>
        `;
    return;
  }

  // Send request to backend
  try {
    const response = await fetch("/api/calculate_rebalance", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tokens,
        target_allocation: targetAllocation,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server responded with status: ${response.status}`);
    }

    const data = await response.json();
    if (data.error) {
      throw new Error(data.error);
    }

    displayRebalanceResults(data);
  } catch (error) {
    console.error("Error calculating rebalance:", error);
    document.getElementById("rebalance-results").innerHTML = `
            <div class="alert alert-danger">Error calculating rebalance strategy: ${error.message}</div>
        `;
  }
}

function displayRebalanceResults(data) {
  const resultsContainer = document.getElementById("rebalance-results");
  resultsContainer.innerHTML = "";

  // Show the rebalance card
  document.getElementById("rebalance-card").classList.remove("d-none");

  // Display rebalance actions
  const actions = data.rebalance_actions;

  if (actions.length === 0) {
    resultsContainer.innerHTML = `
            <div class="alert alert-success">
                Your portfolio is already balanced according to your target allocation!
            </div>
        `;
    return;
  }

  // Create header
  const header = document.createElement("h4");
  header.textContent = "Suggested Actions";
  resultsContainer.appendChild(header);

  // Create actions list
  actions.forEach((action) => {
    const actionDiv = document.createElement("div");
    actionDiv.className = `rebalance-action ${action.action}`;
    // Add null checks to prevent errors
    const amount = action.amount !== undefined ? action.amount.toFixed(6) : "0";
    const percentage =
      action.percentage_change !== undefined
        ? action.percentage_change.toFixed(2)
        : "0";
    actionDiv.innerHTML = `
            <strong>${action.action.toUpperCase()} ${action.token}:</strong> 
            ${amount} ${action.token} 
            <span class="text-muted">(${percentage}% adjustment)</span>
        `;
    resultsContainer.appendChild(actionDiv);
  });

  // Add explanation
  const explanationDiv = document.createElement("div");
  explanationDiv.id = "rebalance-explanation";
  explanationDiv.className = "mt-4";
  explanationDiv.innerHTML = `
        <h5>Explanation</h5>
        <p>These rebalancing suggestions will help align your portfolio with your target allocation. The suggestions minimize the number of trades while ensuring your portfolio reaches the desired balance.</p>
        <p>Keep in mind that transaction fees and market conditions may affect the optimal execution of these trades.</p>
    `;
  resultsContainer.appendChild(explanationDiv);

  // Add allocation comparison chart
  const chartDiv = document.createElement("div");
  chartDiv.className = "mt-4";
  chartDiv.innerHTML = `
        <h5>Allocation Comparison</h5>
        <div id="allocation-chart"></div>
    `;
  resultsContainer.appendChild(chartDiv);

  // Create simple bar chart
  const chartContainer = document.getElementById("allocation-chart");
  Object.keys(data.current_allocation).forEach((token) => {
    const current = data.current_allocation[token] || 0;
    const target = data.target_allocation[token] || 0;

    const row = document.createElement("div");
    row.className = "mb-3";
    // Format with null checks
    const currentFormatted = current !== undefined ? current.toFixed(1) : "0.0";
    const targetFormatted = target !== undefined ? target.toFixed(1) : "0.0";

    row.innerHTML = `
            <div class="d-flex justify-content-between">
                <span>${token}</span>
                <span>Current: ${currentFormatted}% | Target: ${targetFormatted}%</span>
            </div>
            <div class="progress">
                <div class="progress-bar" role="progressbar" 
                     style="width: ${target || 0}%; background-color: #28a745;" 
                     aria-valuenow="${
                       target || 0
                     }" aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <div class="current-allocation">
                <div class="current-marker" style="left: ${
                  current || 0
                }%;"></div>
            </div>
        `;
    chartContainer.appendChild(row);
  });
}

async function addCustomToken() {
  const tokenAddress = document.getElementById("tokenAddress").value;

  if (!tokenAddress) {
    alert("Please enter a token address");
    return;
  }

  try {
    // Add to custom tokens list
    customTokens.push(tokenAddress);

    // Close modal
    const modal = bootstrap.Modal.getInstance(
      document.getElementById("addTokenModal")
    );
    modal.hide();

    // Clear input
    document.getElementById("tokenAddress").value = "";

    // Refresh tokens
    detectTokens();
  } catch (error) {
    console.error("Error adding custom token:", error);
    alert(`Error adding custom token: ${error.message}`);
  }
}

// Helper function to shorten address
function shortenAddress(address) {
  return `${address.substring(0, 6)}...${address.substring(
    address.length - 4
  )}`;
}

// -----------------------------------------------------------------------

const UNISWAP_ROUTER_ADDRESS = "0xeE567Fe1712Faf6149d80dA1E6934E354124CfE3"; // Sepolia router
const WETH_ADDRESS = "0x5f207d42f869fd1c71d7f0f81a2a67fc20ff7323"; // WETH Sepolia (or your deployed version)

const ERC20_ABI = [
  {
    name: "approve",
    type: "function",
    inputs: [
      { name: "_spender", type: "address" },
      { name: "_value", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "transfer",
    type: "function",
    inputs: [
      { name: "_to", type: "address" },
      { name: "_value", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
];

const UNISWAP_ROUTER_ABI = [
  {
    inputs: [
      { internalType: "uint256", name: "amountOutMin", type: "uint256" },
      { internalType: "address[]", name: "path", type: "address[]" },
      { internalType: "address", name: "to", type: "address" },
      { internalType: "uint256", name: "deadline", type: "uint256" },
    ],
    name: "swapExactETHForTokens",
    outputs: [
      { internalType: "uint256[]", name: "amounts", type: "uint256[]" },
    ],
    stateMutability: "payable",
    type: "function",
  },
  {
    name: "swapExactTokensForETH",
    type: "function",
    inputs: [
      { name: "amountIn", type: "uint256" },
      { name: "amountOutMin", type: "uint256" },
      { name: "path", type: "address[]" },
      { name: "to", type: "address" },
      { name: "deadline", type: "uint256" },
    ],
    outputs: [{ name: "amounts", type: "uint256[]" }],
    stateMutability: "nonpayable",
  },
];

async function sellTokenForETH(tokenAddress, amount) {
  const web3 = new Web3(window.ethereum);
  const accounts = await web3.eth.requestAccounts();
  const userAddress = accounts[0];

  const tokenContract = new web3.eth.Contract(ERC20_ABI, tokenAddress);
  const uniswapRouter = new web3.eth.Contract(
    UNISWAP_ROUTER_ABI,
    UNISWAP_ROUTER_ADDRESS
  );

  const rawAmount = web3.utils.toWei(amount.toString(), "ether");

  // Approve Uniswap router to spend your tokens
  await tokenContract.methods
    .approve(UNISWAP_ROUTER_ADDRESS, rawAmount)
    .send({ from: userAddress });

  console.log("Approved token for Uniswap.");

  // Perform the swap (token -> ETH)
  const minETHOut = 0; // Accept any amount of ETH (for testing purposes)
  const deadline = Math.floor(Date.now() / 1000) + 60 * 10; // 10 minutes from now
  const path = [tokenAddress, WETH_ADDRESS];

  const tx = await uniswapRouter.methods
    .swapExactTokensForETH(rawAmount, minETHOut, path, userAddress, deadline)
    .send({ from: userAddress });

  console.log("Token sold successfully! Tx hash:", tx.transactionHash);
}

async function buyTokenWithETH(tokenAddress, ethAmount) {
  const web3 = new Web3(window.ethereum);
  const accounts = await web3.eth.requestAccounts();
  const userAddress = accounts[0];

  const router = new web3.eth.Contract(
    UNISWAP_ROUTER_ABI,
    UNISWAP_ROUTER_ADDRESS
  );

  const path = [WETH_ADDRESS, tokenAddress]; // ETH -> Token
  const deadline = Math.floor(Date.now() / 1000) + 60 * 10; // 10 minutes from now
  const minTokensOut = 0; // accept any amount for now (not for production)
  const rawETH = web3.utils.toWei(ethAmount.toString(), "ether");

  try {
    const tx = await router.methods
      .swapExactETHForTokens(minTokensOut, path, userAddress, deadline)
      .send({
        from: userAddress,
        value: rawETH,
      });

    console.log("Token bought! Tx hash:", tx.transactionHash);
  } catch (error) {
    console.error("Buy failed:", error);
  }
}

async function executeTransactions() {
  let tokens = await getTokens();
  let actions = await getActions();

  actions = actions["rebalance_actions"];

  for (const action of actions) {
    if (action.action === "buy") {
      buyTokenWithETH(tokens[action.token].address, action.amount);
    } else {
      sellTokenForETH(tokens[action.token].address, action.amount);
    }
  }

  displayTokens();
}

async function getTokens() {
  if (!wallet) return {};

  document.getElementById("loading-portfolio").classList.remove("d-none");
  document.getElementById("portfolio-content").classList.add("d-none");

  try {
    // Get the token list from MetaMask
    const ethereumProvider = window.ethereum;

    // Request user assets from MetaMask
    // Note: This is a MetaMask-specific API
    const assets = await ethereumProvider
      .request({
        method: "wallet_getAssets",
      })
      .catch(() => []);

    // This fallback is used as wallet_getAssets might not be available in all MetaMask versions
    const tokenAddresses = [];

    // If we have assets, use them
    if (assets && assets.length > 0) {
      for (const asset of assets) {
        if (asset.type === "ERC20" && asset.address) {
          tokenAddresses.push(asset.address);
        }
      }
    }

    // Add custom tokens
    customTokens.forEach((token) => {
      if (!tokenAddresses.includes(token)) {
        tokenAddresses.push(token);
      }
    });

    // Call our backend API
    const response = await fetch("/api/detect_tokens", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        wallet_address: wallet,
        token_addresses: tokenAddresses,
      }),
    });

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    return data.tokens;
  } catch (error) {
    console.error("Error detecting tokens:", error);
    return {};
  }
}

async function getActions() {
  if (!wallet || Object.keys(tokens).length === 0) {
    alert("Please connect your wallet and detect tokens first");
    return;
  }

  // Get allocation percentages
  const tokenInputs = document.querySelectorAll(".allocation-input");
  const targetAllocation = {};

  tokenInputs.forEach((input) => {
    const symbol = input.getAttribute("data-token");
    const percentage = parseFloat(input.value);

    if (!isNaN(percentage) && percentage > 0) {
      targetAllocation[symbol] = percentage;
    }
  });

  // Validate that we have target allocations
  if (Object.keys(targetAllocation).length === 0) {
    alert("Please enter at least one target allocation percentage");
    return;
  }

  console.log("Tokens being sent to backend:", tokens);
  console.log("Target allocation being sent to backend:", targetAllocation);

  // Make sure we have valid token data
  if (!tokens || Object.keys(tokens).length === 0) {
    console.error("Token data is missing or empty");
    document.getElementById("rebalance-results").innerHTML = `
            <div class="alert alert-danger">Error: Token data is missing or empty. Please refresh the page and try again.</div>
        `;
    return;
  }

  // Send request to backend
  try {
    const response = await fetch("/api/calculate_rebalance", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tokens,
        target_allocation: targetAllocation,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server responded with status: ${response.status}`);
    }

    const data = await response.json();
    if (data.error) {
      throw new Error(data.error);
    }

    return data;
  } catch (error) {
    console.error("Error calculating rebalance:", error);
    return [];
  }
}
