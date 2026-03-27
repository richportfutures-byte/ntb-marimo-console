from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .cl import CLContractMetadata, CLContractSpecificExtension, CLMarketPacket
from .contracts import AllContractMetadata, AllContractSpecificExtension, AllMarketPacket
from .inputs import AttachedVisuals, ChallengeState, StrictModel


class HistoricalPacket(StrictModel):
    schema_name: Literal["historical_packet_v1"] = Field(
        default="historical_packet_v1",
        alias="$schema",
    )
    challenge_state: ChallengeState
    contract_metadata: AllContractMetadata
    market_packet: AllMarketPacket
    contract_specific_extension: AllContractSpecificExtension
    attached_visuals: AttachedVisuals

    @model_validator(mode="after")
    def validate_contract_alignment(self) -> "HistoricalPacket":
        contract = self.market_packet.contract
        if (
            self.contract_metadata.contract != contract
            or self.contract_specific_extension.contract != contract
        ):
            raise ValueError("Composed packet contains mismatched contract components.")

        challenge_limits = self.challenge_state.max_position_size_by_contract.model_dump(by_alias=True)
        if challenge_limits[contract] != self.contract_metadata.max_position_size:
            raise ValueError(
                f"challenge_state.max_position_size_by_contract.{contract} must match "
                "contract_metadata.max_position_size."
            )

        return self


class CLHistoricalPacket(HistoricalPacket):
    contract_metadata: CLContractMetadata
    market_packet: CLMarketPacket
    contract_specific_extension: CLContractSpecificExtension
