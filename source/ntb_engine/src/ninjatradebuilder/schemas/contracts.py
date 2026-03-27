from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .cl import CLContractMetadata, CLContractSpecificExtension, CLMarketPacket
from .inputs import ContractMetadata, MarketPacket, StrictModel

IndexCashTone = Literal["bullish", "bearish", "choppy", "flat"]
DxyContext = Literal["strengthening", "weakening", "range-bound"]
YieldContext = Literal["rising", "falling", "stable"]


class PriceRange(StrictModel):
    high: float
    low: float


class ESContractMetadata(ContractMetadata):
    contract: Literal["ES"]


class ESMarketPacket(MarketPacket):
    contract: Literal["ES"]


class ESContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["ES"] = "ES"
    breadth: str
    index_cash_tone: IndexCashTone


class NQContractMetadata(ContractMetadata):
    contract: Literal["NQ"]


class NQMarketPacket(MarketPacket):
    contract: Literal["NQ"]


class NQContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["NQ"] = "NQ"
    relative_strength_vs_es: float
    megacap_leadership_table: dict[str, Any] | None = None


class ZNContractMetadata(ContractMetadata):
    contract: Literal["ZN"]


class ZNMarketPacket(MarketPacket):
    contract: Literal["ZN"]


class ZNContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["ZN"] = "ZN"
    cash_10y_yield: float
    treasury_auction_schedule: str
    macro_release_context: str
    absorption_summary: str | None = None


class SixEContractMetadata(ContractMetadata):
    contract: Literal["6E"]


class SixEMarketPacket(MarketPacket):
    contract: Literal["6E"]


class SixEContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["6E"] = "6E"
    asia_high_low: PriceRange
    london_high_low: PriceRange
    ny_high_low_so_far: PriceRange
    dxy_context: DxyContext
    europe_initiative_status: str


class MGCContractMetadata(ContractMetadata):
    contract: Literal["MGC"]


class MGCMarketPacket(MarketPacket):
    contract: Literal["MGC"]


class MGCContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["MGC"] = "MGC"
    dxy_context: DxyContext
    yield_context: YieldContext
    swing_penetration_volume_summary: str | None = None
    macro_fear_catalyst_summary: str


AllContractMetadata = Annotated[
    ESContractMetadata
    | NQContractMetadata
    | CLContractMetadata
    | ZNContractMetadata
    | SixEContractMetadata
    | MGCContractMetadata,
    Field(discriminator="contract"),
]

AllMarketPacket = Annotated[
    ESMarketPacket
    | NQMarketPacket
    | CLMarketPacket
    | ZNMarketPacket
    | SixEMarketPacket
    | MGCMarketPacket,
    Field(discriminator="contract"),
]

AllContractSpecificExtension = Annotated[
    ESContractSpecificExtension
    | NQContractSpecificExtension
    | CLContractSpecificExtension
    | ZNContractSpecificExtension
    | SixEContractSpecificExtension
    | MGCContractSpecificExtension,
    Field(discriminator="contract"),
]
