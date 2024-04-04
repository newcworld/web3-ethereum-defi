import pytest
from hexbytes import HexBytes
from web3 import Web3, EthereumTesterProvider
from web3_multi_provider import MultiProvider

from eth_defi.event import get_tx_events
from eth_defi.uniswap_universal.analysis import analyse_trade_by_hash
from eth_defi.swap.analysis import analyse_trade_by_hash as swap_analyse_trade_by_hash

@pytest.fixture
def web3() -> Web3:
    # https://web3py.readthedocs.io/en/stable/examples.html#contract-unit-tests-in-python
    web3 = Web3(MultiProvider(["https://1rpc.io/base"]))
    return web3


@pytest.fixture
def tx_hash() -> HexBytes:
    return HexBytes("0xe3e1a99274369608be9453084435f9d67464088c4cb10537ea952b0016a26245")


def test_uniswap(web3: Web3, tx_hash: HexBytes):
    """Set up the Anvil Web3 connection.
    Also perform the Anvil state reset for each test.
    """
    result = analyse_trade_by_hash(web3, tx_hash=tx_hash)
    print(result)

def test_swap(web3: Web3, tx_hash: HexBytes):
    """Set up the Anvil Web3 connection.
    Also perform the Anvil state reset for each test.
    """
    result = swap_analyse_trade_by_hash(web3, tx_hash=tx_hash)
    print(result)
