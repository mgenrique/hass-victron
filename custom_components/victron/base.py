from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.helpers.typing import StateType
from homeassistant.helpers.entity import EntityDescription


@dataclass
class VictronBaseEntityDescription(EntityDescription):
    slave: int | None = None
    value_fn: Callable[[dict, int, str], StateType] = (
        lambda data, slave, key: (data.get("data", {}) if isinstance(data, dict) else {}).get(
            f"{slave}.{key}"
        )
    )


@dataclass
class VictronWriteBaseEntityDescription(VictronBaseEntityDescription):
    address: int | None = None

