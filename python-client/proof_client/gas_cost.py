"""
gas_cost.py — Unified transaction cost calculation (Stage 13)

Converts (gas_used, effective_gas_price) receipt data into a GasCost value
object carrying total fee and per-file cost. Used by register flows, the
deployment CLI, and the gas study to report costs consistently.
"""

from dataclasses import dataclass, asdict

from web3 import Web3


@dataclass
class GasCost:
    """Cost of one on-chain transaction, amortised over file_count files."""

    gas_used: int
    effective_gas_price_wei: int
    total_fee_wei: int
    total_fee_eth: str
    native_token_symbol: str
    cost_per_file_wei: int
    cost_per_file_eth: str
    file_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_gas_cost(
    gas_used: int,
    effective_gas_price_wei: int,
    file_count: int = 1,
    native_token_symbol: str = "ETH",
) -> GasCost:
    """Compute total and per-file transaction cost from receipt data."""
    total_fee_wei = gas_used * effective_gas_price_wei
    total_fee_eth = Web3.from_wei(total_fee_wei, "ether")

    cost_per_file_wei = total_fee_wei // max(file_count, 1)
    cost_per_file_eth = Web3.from_wei(cost_per_file_wei, "ether")

    return GasCost(
        gas_used=gas_used,
        effective_gas_price_wei=effective_gas_price_wei,
        total_fee_wei=total_fee_wei,
        total_fee_eth=str(total_fee_eth),
        native_token_symbol=native_token_symbol,
        cost_per_file_wei=cost_per_file_wei,
        cost_per_file_eth=str(cost_per_file_eth),
        file_count=file_count,
    )


def merkle_savings_percentage(
    single_file_cost_per_file_wei: int,
    merkle_cost_per_file_wei: int,
) -> float:
    """Return the % saved per file by Merkle batching vs single-file registration.

    savings = 1 - (merkle_cost_per_file / single_file_cost_per_file)
    Returns 0.0 when the single-file cost is zero (nothing to compare).
    """
    if single_file_cost_per_file_wei <= 0:
        return 0.0
    ratio = merkle_cost_per_file_wei / single_file_cost_per_file_wei
    return (1.0 - ratio) * 100.0
