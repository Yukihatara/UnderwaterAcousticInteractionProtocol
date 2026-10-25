from dataclasses import dataclass
from enum import Enum, auto

@dataclass(frozen=True)
class Config:
    distance: float = 1500.0
    sound_speed: float = 1500.0
    bitrate: float = 2400

    rts_bits: int = 256
    cts_bits: int = 256
    ack_bits: int = 256
    data_bits: int = 256*16

    backoff: float = 0.5

    @property
    def propagation_delay(self) -> float:
        return self.distance / self.sound_speed

    def tx_duration(self, bits: int) -> float:
        return bits / self.bitrate
    

@dataclass(frozen=True)
class Frame:
    kind: str
    source: str
    destination:str
    bits: int
    sequence: int | None = None
    payload: bytes = b''


class FrameType(Enum):
    RTS = auto()
    CTS = auto()
    DATA = auto()
    ACK = auto()