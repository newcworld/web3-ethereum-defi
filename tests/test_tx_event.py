import pytest
from web3 import Web3, EthereumTesterProvider
from web3_multi_provider import MultiProvider

from eth_defi.event import get_tx_events


@pytest.fixture
def web3() -> Web3:
    # https://web3py.readthedocs.io/en/stable/examples.html#contract-unit-tests-in-python
    web3 = Web3(MultiProvider(["https://1rpc.io/base"]))
    return web3


@pytest.fixture
def tx_hash() -> str:
    return "0xe3e1a99274369608be9453084435f9d67464088c4cb10537ea952b0016a26245"


def test_tx_event(web3: Web3, tx_hash: str):
    """Set up the Anvil Web3 connection.
    Also perform the Anvil state reset for each test.
    """
    event_list = get_tx_events(web3, tx_hash=tx_hash)
    for event in event_list:
        print(event)
