"""Uniswap Universal individual trade analysis."""
from decimal import Decimal
from typing import Union

from eth_typing import Hash32, HexStr
from hexbytes import HexBytes
from web3.types import EventData

from eth_defi.uniswap_v3.pool import fetch_pool_details

from eth_defi.event import get_tx_events
from eth_defi.uniswap_v3.deployment import UniswapV3Deployment

from eth_defi.revert_reason import fetch_transaction_revert_reason
from web3 import Web3
from web3.logs import DISCARD

from eth_defi.abi import get_deployed_contract
from eth_defi.token import fetch_erc20_details
from eth_defi.uniswap_v2.deployment import UniswapV2Deployment
from eth_defi.trade import TradeFail, TradeSuccess
from uniswap_universal_router_decoder import RouterCodec

codec = RouterCodec()


def analyse_trade_by_hash(web3: Web3, tx_hash: Union[Hash32, HexBytes, HexStr]) -> Union[TradeSuccess, TradeFail]:
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
    :param uniswap:
        Uniswap deployment description
    :param tx_hash:
        Transaction hash as a string
    :return:
        :py:class:`TradeSuccess` or :py:class:`TradeFail` instance
    """

    # Example tx https://etherscan.io/tx/0xa8e6d47fb1429c7aec9d30332eafaeb515c8dfa73ab413c48560d8d6060c3193#eventlog
    # swapExactTokensForTokens

    tx = web3.eth.get_transaction(tx_hash)
    tx_receipt = web3.eth.get_transaction_receipt(tx_hash)
    return analyse_trade_by_receipt(web3, tx, tx_hash, tx_receipt)


def analyse_trade_by_receipt(web3: Web3, tx: dict, tx_hash: str, tx_receipt: dict, pair_fee: float = None) -> Union[
    TradeSuccess, TradeFail]:
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
    :param uniswap:
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

    effective_gas_price = tx_receipt.get("effectiveGasPrice", 0)
    gas_used = tx_receipt["gasUsed"]

    # TODO: Unit test this code path
    # Tx reverted
    if tx_receipt["status"] != 1:
        reason = fetch_transaction_revert_reason(web3, tx_hash)
        return TradeFail(gas_used, effective_gas_price, revert_reason=reason)

    decoded_trx_input = codec.decode.function_input(tx["input"])[1]["inputs"]
    v3_swap_ops = list(filter(lambda x: x[0].fn_name in ["V3_SWAP_EXACT_IN", "V3_SWAP_EXACT_OUT"], decoded_trx_input))
    v2_swap_ops = list(filter(lambda x: x[0].fn_name in ["V2_SWAP_EXACT_IN", "V2_SWAP_EXACT_OUT"], decoded_trx_input))
    if len(v3_swap_ops) == 0 and len(v2_swap_ops) == 0:
        raise ValueError("No swap operation detected in the transaction")

    if len(v3_swap_ops) + len(v2_swap_ops) > 1:
        raise ValueError("Multiple swap operations detected in the transaction")

    if len(v2_swap_ops) == 1:
        raise NotImplementedError("Uniswap V2 trades are not supported yet")

    fn_name = v3_swap_ops[0][0].fn_name
    path = codec.decode.v3_path(fn_name, decoded_trx_input[0][1]["path"])
    amount_out_min = decoded_trx_input[0][1]['amountOutMin']

    events = get_tx_events(web3, tx_hash)
    assert len(events) > 0, f"No swap events detected:{tx_receipt}"

    events = list(filter(lambda tuple_e: tuple_e[0]["event"] == "Swap", events))[-1]
    assert len(events) > 0, f"No swap events detected:{tx_receipt}"

    event = events[0]
    return get_v3_by_event(web3, effective_gas_price, gas_used, path, amount_out_min, event)


def get_v3_by_event(web3, effective_gas_price, gas_used, path, amount_out_min, event: EventData):
    props = event["args"]
    amount0 = props["amount0"]
    amount1 = props["amount1"]
    tick = props["tick"]

    pool_address = event["address"]
    pool = fetch_pool_details(web3, pool_address)

    # Depending on the path, the out token can pop up as amount0Out or amount1Out
    # For complex swaps (unspported) we can have both
    assert (amount0 > 0 and amount1 < 0) or (amount0 < 0 and amount1 > 0), "Unsupported swap type"

    amount_out = amount0 if amount0 < 0 else amount1
    assert amount_out < 0, "amount out should be negative for uniswap v3"

    in_token_details = fetch_erc20_details(web3, path[0])
    out_token_details = fetch_erc20_details(web3, path[-1])
    price = pool.convert_price_to_human(tick)  # Return price of token0/token1

    amount_in = amount0 if amount0 > 0 else amount1
    lp_fee_paid = float(amount_in * pool.fee / 10 ** in_token_details.decimals)

    return TradeSuccess(
        gas_used,
        effective_gas_price,
        path,
        amount_in,
        amount_out_min,
        abs(amount_out),
        price,
        in_token_details.decimals,
        out_token_details.decimals,
        token0=pool.token0,
        token1=pool.token1,
        lp_fee_paid=lp_fee_paid,
    )


_GOOD_TRANSFER_SIGNATURES = (
    # https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/token/ERC20/IERC20.sol#L75
    "Transfer(address,address,uint)",
    # WETH9 wtf Transfer()
    # https://github.com/gnosis/canonical-weth/blob/master/contracts/WETH9.sol#L24
    "Transfer(address,address,uint,uint)",
)
