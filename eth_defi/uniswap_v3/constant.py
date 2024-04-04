# Uniswap V3
dex_router = {
    "base": [
        {
            "chain": "base",
            "address": "0x19ceead7105607cd444f5ad10dd51356436095a1",
            "name": "Odos:Router V2"
        }
    ]
}


def contains_v3_router(chain: str, address: str) -> bool:
    """
    Check if router is in constant
    """
    for router in dex_router[chain]:
        if router["address"] == address:
            return True

    return False
