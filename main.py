import os, random, time, sys
from web3 import Web3
from eth_account import Account
from web3.middleware import ExtraDataToPOAMiddleware

sys.stdout.reconfigure(line_buffering=True)
print("🚀 Pharos Farm v1 запущен!", flush=True)

RPC      = "https://atlantic.dplabs-internal.com"
CHAIN_ID = 688688

WPHRS_ADDR = "0x76aaada469d23216be5f7c596fa25f282ff9b364"
USDC_ADDR  = "0xad902cf99c2de2f1ba5ec4d642fd7e49cae9ee37"
USDT_ADDR  = "0xed59de2d7ad9c043442e381231ee3646fc3c2939"
ROUTER     = "0x1a4de519154ae51200b0ad7c90f7fac75547888a"

import sys as _sys; _sys.path.insert(0, '/root/bin')
from proxy_utils import load_proxies, find_working_proxy
PROXIES = load_proxies()

import os as _os
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(_os.path.join(_os.path.dirname(__file__), '.env'))
_raw_keys = _os.getenv("PRIVATE_KEYS", "")
PRIVATE_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

WPHRS_ABI = [
    {"name": "deposit",  "inputs": [], "outputs": [], "type": "function", "stateMutability": "payable"},
    {"name": "withdraw", "inputs": [{"name": "wad", "type": "uint256"}], "outputs": [], "type": "function", "stateMutability": "nonpayable"},
    {"name": "balanceOf","inputs": [{"name": "a", "type": "address"}],   "outputs": [{"type": "uint256"}], "type": "function", "stateMutability": "view"},
]
ERC20_ABI = [
    {"name": "approve",  "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "outputs": [{"type": "bool"}], "type": "function", "stateMutability": "nonpayable"},
    {"name": "balanceOf","inputs": [{"name": "a", "type": "address"}],   "outputs": [{"type": "uint256"}], "type": "function", "stateMutability": "view"},
    {"name": "transfer", "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "outputs": [{"type": "bool"}], "type": "function", "stateMutability": "nonpayable"},
]
SWAP_ROUTER_ABI = [
    {"name": "exactInputSingle", "inputs": [{"name": "params", "type": "tuple", "components": [
        {"name": "tokenIn",            "type": "address"},
        {"name": "tokenOut",           "type": "address"},
        {"name": "fee",                "type": "uint24"},
        {"name": "recipient",          "type": "address"},
        {"name": "deadline",           "type": "uint256"},
        {"name": "amountIn",           "type": "uint256"},
        {"name": "amountOutMinimum",   "type": "uint256"},
        {"name": "sqrtPriceLimitX96",  "type": "uint160"},
    ]}], "outputs": [{"name": "amountOut", "type": "uint256"}],
    "type": "function", "stateMutability": "nonpayable"},
]

DUMMY_BYTECODE = (
    "0x608060405234801561001057600080fd5b5060c0806100206000396000f3fe"
    "6080604052348015600f57600080fd5b506004361060285760003560e01c8063"
    "2e64cec114602d5780636057361d14603f575b600080fd5b60005460405190"
    "815260200160405180910390f35b604e60596004803603810190604a919060"
    "9c565b605b565b005b8060008190555050565b60008135905060968160b2565b"
    "92915050565b60006020828403121560ad5760ac60ad565b5b600060b984828"
    "50160876090565b91505092915050565b60bb8160c1565b811460c557600080"
    "fd5b50565b600081905091905056fea264697066735822122035f1b69e8af68"
    "9f7b15b0b2e6a4df0e9a8d2c7d3f4e5a6b7c8d9e0f1a2b3c464736f6c6343"
    "00081300 33"
).replace(" ", "")


def make_w3(proxy_url):
    kwargs = {'timeout': 30}
    if proxy_url:
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs=kwargs))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_tx_params(w3, sender, value=0, gas=300_000):
    try:
        block = w3.eth.get_block('latest')
        base_fee = block.get('baseFeePerGas')
        if base_fee:
            max_fee  = int(base_fee * 1.5) + w3.to_wei(0.001, 'gwei')
            priority = int(w3.to_wei(random.uniform(0.001, 0.005), 'gwei'))
            return {'from': sender, 'nonce': w3.eth.get_transaction_count(sender),
                    'maxFeePerGas': max_fee, 'maxPriorityFeePerGas': priority,
                    'chainId': CHAIN_ID, 'value': value, 'gas': gas}
    except Exception:
        pass
    return {'from': sender, 'nonce': w3.eth.get_transaction_count(sender),
            'gasPrice': int(w3.eth.gas_price * 1.3),
            'chainId': CHAIN_ID, 'value': value, 'gas': gas}


def send_tx(w3, account, tx, tag, retries=3):
    for attempt in range(1, retries + 1):
        try:
            signed  = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            ok = receipt.status == 1
            print(f"{tag} {'✅' if ok else '❌ FAIL'} | {tx_hash.hex()[:16]}...", flush=True)
            return ok
        except Exception as e:
            err = str(e)
            if attempt < retries and ('nonce' in err.lower() or 'underpriced' in err.lower()):
                tx['nonce'] = w3.eth.get_transaction_count(account.address)
                time.sleep(8)
                continue
            print(f"{tag} ❌ {err[:120]}", flush=True)
            return False


def apause(a=60, b=240):
    time.sleep(random.randint(a, b))


def rand_sleep(min_m=54, max_m=120):
    d = random.randint(min_m * 60, max_m * 60)
    h, m = divmod(d // 60, 60)
    print(f"⏳ Пауза ~{h}ч {m}мин...", flush=True)
    time.sleep(d)


# ── Actions ──────────────────────────────────────────────────────────────────

def act_wrap(w3, acc, tag):
    bal     = w3.eth.get_balance(acc.address)
    reserve = int(0.003 * 1e18)
    if bal < reserve + int(0.0001 * 1e18):
        print(f"{tag} Wrap: мало PHRS", flush=True); return
    amt = random.randint(int(0.0001 * 1e18), min(int(0.002 * 1e18), bal - reserve))
    c   = w3.eth.contract(WPHRS_ADDR, abi=WPHRS_ABI)
    print(f"{tag} 🔄 Wrap {amt/1e18:.5f} PHRS → WPHRS", flush=True)
    send_tx(w3, acc, c.functions.deposit().build_transaction(get_tx_params(w3, acc.address, value=amt)), tag)


def act_unwrap(w3, acc, tag):
    c    = w3.eth.contract(WPHRS_ADDR, abi=WPHRS_ABI)
    wbal = c.functions.balanceOf(acc.address).call()
    if wbal < int(0.00005 * 1e18):
        print(f"{tag} Unwrap: мало WPHRS", flush=True); return
    amt = random.randint(int(0.00005 * 1e18), min(wbal, int(0.002 * 1e18)))
    print(f"{tag} 🔄 Unwrap {amt/1e18:.5f} WPHRS → PHRS", flush=True)
    send_tx(w3, acc, c.functions.withdraw(amt).build_transaction(get_tx_params(w3, acc.address)), tag)


def act_wrap_unwrap_cycle(w3, acc, tag):
    act_wrap(w3, acc, tag)
    apause(90, 300)
    act_unwrap(w3, acc, tag)


def act_approve_usdc(w3, acc, tag):
    amt = random.randint(1, 500) * 10**6
    c   = w3.eth.contract(USDC_ADDR, abi=ERC20_ABI)
    print(f"{tag} ✍️ Approve USDC {amt//10**6}", flush=True)
    send_tx(w3, acc, c.functions.approve(ROUTER, amt).build_transaction(get_tx_params(w3, acc.address)), tag)
    apause(60, 200)
    print(f"{tag} ✍️ Revoke USDC", flush=True)
    send_tx(w3, acc, c.functions.approve(ROUTER, 0).build_transaction(get_tx_params(w3, acc.address)), tag)


def act_approve_usdt(w3, acc, tag):
    amt = random.randint(1, 500) * 10**6
    c   = w3.eth.contract(USDT_ADDR, abi=ERC20_ABI)
    print(f"{tag} ✍️ Approve USDT {amt//10**6}", flush=True)
    send_tx(w3, acc, c.functions.approve(ROUTER, amt).build_transaction(get_tx_params(w3, acc.address)), tag)
    apause(60, 200)
    print(f"{tag} ✍️ Revoke USDT", flush=True)
    send_tx(w3, acc, c.functions.approve(ROUTER, 0).build_transaction(get_tx_params(w3, acc.address)), tag)


def act_multi_approve(w3, acc, tag):
    for addr, name, dec in [(USDC_ADDR, "USDC", 6), (USDT_ADDR, "USDT", 6)]:
        c   = w3.eth.contract(addr, abi=ERC20_ABI)
        amt = random.randint(5, 200) * 10**dec
        print(f"{tag} ✍️ Multi-approve {name}", flush=True)
        send_tx(w3, acc, c.functions.approve(ROUTER, amt).build_transaction(get_tx_params(w3, acc.address)), tag)
        apause(30, 90)
    apause(60, 180)
    for addr, name in [(USDC_ADDR, "USDC"), (USDT_ADDR, "USDT")]:
        c = w3.eth.contract(addr, abi=ERC20_ABI)
        print(f"{tag} ✍️ Revoke {name}", flush=True)
        send_tx(w3, acc, c.functions.approve(ROUTER, 0).build_transaction(get_tx_params(w3, acc.address)), tag)


def act_self_transfer(w3, acc, tag):
    bal     = w3.eth.get_balance(acc.address)
    reserve = int(0.003 * 1e18)
    if bal < reserve:
        print(f"{tag} Self-transfer: мало PHRS", flush=True); return
    amt = random.randint(int(0.00005 * 1e18), min(int(0.001 * 1e18), bal - reserve))
    tx  = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
    print(f"{tag} 📤 Self-transfer {amt/1e18:.6f} PHRS", flush=True)
    send_tx(w3, acc, tx, tag)


def act_deploy(w3, acc, tag):
    print(f"{tag} 🚀 Deploy контракта", flush=True)
    send_tx(w3, acc, {'data': DUMMY_BYTECODE, **get_tx_params(w3, acc.address)}, tag)


def act_multi_deploy(w3, acc, tag):
    count = random.randint(2, 3)
    for i in range(count):
        print(f"{tag} 🚀 Multi-deploy [{i+1}/{count}]", flush=True)
        send_tx(w3, acc, {'data': DUMMY_BYTECODE, **get_tx_params(w3, acc.address)}, tag)
        if i < count - 1:
            apause(40, 120)


def act_incremental(w3, acc, tag):
    for base in [0.00005, 0.00015, 0.0005]:
        bal = w3.eth.get_balance(acc.address)
        amt = int((base + random.uniform(0, base * 0.5)) * 1e18)
        if amt > bal - int(0.003 * 1e18):
            continue
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} 📤 Incremental {amt/1e18:.6f} PHRS", flush=True)
        send_tx(w3, acc, tx, tag)
        apause(45, 120)


def act_swap_usdc_wphrs(w3, acc, tag):
    c_usdc   = w3.eth.contract(USDC_ADDR, abi=ERC20_ABI)
    usdc_bal = c_usdc.functions.balanceOf(acc.address).call()
    if usdc_bal < 10**6:
        print(f"{tag} Swap: мало USDC", flush=True); return
    amt = min(usdc_bal, random.randint(1, 5) * 10**6)
    print(f"{tag} ✍️ Approve USDC for swap", flush=True)
    if not send_tx(w3, acc, c_usdc.functions.approve(ROUTER, amt).build_transaction(
            get_tx_params(w3, acc.address)), tag):
        return
    apause(20, 60)
    router   = w3.eth.contract(ROUTER, abi=SWAP_ROUTER_ABI)
    deadline = int(time.time()) + 600
    for fee in [500, 3000, 10000]:
        try:
            params = (USDC_ADDR, WPHRS_ADDR, fee, acc.address, deadline, amt, 0, 0)
            tx     = router.functions.exactInputSingle(params).build_transaction(
                get_tx_params(w3, acc.address, gas=400_000))
            print(f"{tag} 📈 Swap USDC→WPHRS fee={fee}", flush=True)
            if send_tx(w3, acc, tx, tag):
                break
        except Exception as e:
            print(f"{tag} swap fee={fee}: {str(e)[:60]}", flush=True)


def act_burst_transfer(w3, acc, tag):
    count = random.randint(3, 5)
    for j in range(count):
        bal = w3.eth.get_balance(acc.address)
        amt = random.randint(int(0.00001 * 1e18), int(0.0001 * 1e18))
        if amt > bal - int(0.003 * 1e18):
            break
        tx = {**get_tx_params(w3, acc.address, value=amt, gas=21_000), 'to': acc.address}
        print(f"{tag} ⚡ Burst [{j+1}/{count}]", flush=True)
        send_tx(w3, acc, tx, tag)
        time.sleep(random.randint(10, 30))


ALL_ACTIONS = [
    (act_wrap,              13),
    (act_unwrap,            10),
    (act_wrap_unwrap_cycle, 10),
    (act_approve_usdc,      12),
    (act_approve_usdt,      10),
    (act_multi_approve,      8),
    (act_self_transfer,     11),
    (act_deploy,             9),
    (act_multi_deploy,       5),
    (act_incremental,        6),
    (act_swap_usdc_wphrs,    4),
    (act_burst_transfer,     2),
]


def process_wallet(pk, proxy_url, idx):
    w3  = make_w3(proxy_url)
    acc = Account.from_key(pk if pk.startswith('0x') else '0x' + pk)
    tag = f"[{acc.address[:8]}... w{idx+1:02d}]"
    try:
        bal = w3.eth.get_balance(acc.address)
    except Exception as e:
        print(f"{tag} ❌ RPC: {e}", flush=True); return

    print(f"\n{tag} 💰 {bal/1e18:.5f} PHRS", flush=True)
    if bal < int(0.003 * 1e18):
        print(f"{tag} ⚠️ Мало баланса, пропуск", flush=True); return

    fns, weights = zip(*ALL_ACTIONS)
    chosen = random.choices(fns, weights=weights, k=random.randint(3, 5))
    for i, fn in enumerate(chosen):
        try:
            fn(w3, acc, tag)
        except Exception as e:
            print(f"{tag} ❌ {fn.__name__}: {str(e)[:100]}", flush=True)
        if i < len(chosen) - 1:
            apause(90, 420)
    print(f"{tag} ✅ Готово", flush=True)


print(f"✅ {len(PRIVATE_KEYS)} кошельков | Chain ID: {CHAIN_ID}", flush=True)
print("🔄 Запуск...\n", flush=True)

while True:
    pool = list(range(len(PRIVATE_KEYS)))
    while pool:
        pick  = random.randrange(len(pool))
        idx   = pool.pop(pick)
        proxy = PROXIES[idx % len(PROXIES)] if PROXIES else None
        try:
            process_wallet(PRIVATE_KEYS[idx], proxy, idx)
        except Exception as e:
            _msg = str(e).lower()
            if any(x in _msg for x in ["proxy","connect","timeout","reset","refused","network","ssl"]):
                _new = find_working_proxy(exclude=proxy)
                if _new and _new != proxy:
                    print(f"[wallet-{idx}] 🔄 прокси сменён → {_new.split('@')[-1]}", flush=True)
                    try:
                        process_wallet(PRIVATE_KEYS[idx], _new, idx)
                    except Exception as e2:
                        print(f"[wallet-{idx}] ❌ {e2}", flush=True)
                else:
                    print(f"[wallet-{idx}] ❌ {e}", flush=True)
            else:
                print(f"[wallet-{idx}] ❌ {e}", flush=True)
        rand_sleep(54, 120)
    print("✅ Раунд завершён.\n", flush=True)
