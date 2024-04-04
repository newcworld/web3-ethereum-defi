"""Uniswap v2 individual trade analysis."""
from decimal import Decimal
from typing import Union

from hexbytes import HexBytes

from eth_defi.revert_reason import fetch_transaction_revert_reason
from web3 import Web3
from web3.logs import DISCARD

from eth_defi.abi import get_deployed_contract
from eth_defi.token import fetch_erc20_details
from eth_defi.uniswap_v2.deployment import UniswapV2Deployment
from eth_defi.trade import TradeFail, TradeSuccess
from eth_defi.uniswap_v2.analysis import analyse_trade_by_receipt as v2_analyse_trade_by_receipt
from eth_defi.uniswap_v2.deployment import mock_partial_deployment_for_analysis as v2_analysis
from eth_defi.uniswap_v3.analysis import analyse_trade_by_receipt as v3_analyse_trade_by_receipt
from eth_defi.uniswap_v3.deployment import mock_partial_deployment_for_analysis as v3_analysis
from eth_defi.uniswap_v2.constant import contains_v2_router
from eth_defi.uniswap_v3.constant import contains_v3_router
from eth_defi.uniswap_universal.constant import contains_universal_router


def analyse_trade_by_hash(web3: Web3, chain: str, tx_hash: str) -> Union[TradeSuccess, TradeFail]:
    """Analyse details of a Uniswap trade based on a transaction id.

    Analyses trade fees, etc. based on the event signatures in the transaction.
    Works only simp;e trades.

    Currently only supports simple analysis where there is one input token
    and one output token.

    Example:

    .. code-block:: python

        analysis = analyse_trade(web3, uniswap_v2, tx_hash)
        assert isinstance(analysis, TradeSuccess)  # Trade was successful
        assert analysis.price == pytest.approx(Decimal('1744.899124998896692270848706'))  # ETC/USDC price
        assert analysis.get_effective_gas_price_gwei() == 1  # What gas was paid for this price

    .. note ::

        This code is still much under development and unlikely to support any
        advanced use cases yet.

    :param web3:
        Web3 instance
    :param chain:
        chain name
    :param tx_hash:
        Transaction hash as a string
    :return:
        :py:class:`TradeSuccess` or :py:class:`TradeFail` instance
    """

    # Example tx https://etherscan.io/tx/0xa8e6d47fb1429c7aec9d30332eafaeb515c8dfa73ab413c48560d8d6060c3193#eventlog
    # swapExactTokensForTokens
    if isinstance(tx_hash, str):
        tx_hash = HexBytes(tx_hash)
    tx = web3.eth.get_transaction(tx_hash)
    tx_receipt = web3.eth.get_transaction_receipt(tx_hash)
    return analyse_trade_by_receipt(web3, chain, tx, tx_hash, tx_receipt)


def analyse_trade_by_receipt(web3: Web3, chain: str, tx: dict, tx_hash: Union[str, HexBytes], tx_receipt: dict,
                             pair_fee: float = None) -> Union[TradeSuccess, TradeFail]:
    """Analyse details of a Uniswap trade based on already received receipt.

    See also :py:func:`analyse_trade_by_hash`.
    This function is more ideal for the cases where you know your transaction is already confirmed
    and you do not need to poll the chain for a receipt.

    .. warning::

        Assumes one trade per TX - cannot decode TXs with multiple trades in them.

    Example:

    .. code-block:: python

        tx_hash = router.functions.swapExactTokensForTokens(
            all_weth_amount,
            0,
            reverse_path,
            user_1,
            FOREVER_DEADLINE,
        ).transact({"from": user_1})

        tx = web3.eth.get_transaction(tx_hash)
        receipt = web3.eth.get_transaction_receipt(tx_hash)

        analysis = analyse_trade_by_receipt(web3, uniswap_v2, tx, tx_hash, receipt)
        assert isinstance(analysis, TradeSuccess)
        assert analysis.price == pytest.approx(Decimal("1744.899124998896692270848706"))

    :param web3:
        Web3 instance
    :param chain:
        chain name
    :param router_addr:
        Uniswap deployment description
    :param tx:
        Transaction data as a dictionary: needs to have `data` or `input` field to decode
    :param tx_hash:
        Transaction hash: needed for the call for the revert reason)
    :param tx_receipt:
        Transaction receipt to analyse
    :param pair_fee:
        The lp fee for this pair.
    :return:
        :py:class:`TradeSuccess` or :py:class:`TradeFail` instance
    """
    router_addr = tx["to"]
    if contains_v2_router(chain, router_addr):
        # TODO 加缓存
        v2 = v2_analysis(web3, router_addr)
        return v2_analyse_trade_by_receipt(web3, v2, tx, tx_hash, tx_receipt)
    elif contains_v3_router(chain, router_addr):
        v3 = v3_analysis(web3, router_addr)
        return v3_analyse_trade_by_receipt(web3, v3, tx, tx_hash, tx_receipt)
    elif contains_universal_router(chain, router_addr):
        raise NotImplementedError("Universal router not implemented")
    else:
        raise ValueError(f"Unknown router {router_addr}")


_GOOD_TRANSFER_SIGNATURES = (
    # https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/token/ERC20/IERC20.sol#L75
    "Transfer(address,address,uint)",
    # WETH9 wtf Transfer()
    # https://github.com/gnosis/canonical-weth/blob/master/contracts/WETH9.sol#L24
    "Transfer(address,address,uint,uint)",
)
