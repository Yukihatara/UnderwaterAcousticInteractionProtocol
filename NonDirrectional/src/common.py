from dataclasses import dataclass
from enum import Enum, auto


@dataclass(frozen=True)
class Config:
    sound_speed: float = 1500.0
    bitrate: float = 2400
    max_range: float = 2000

    req_bits: int = 256
    ann_bits: int = 256
    rts_bits: int = 256
    cts_bits: int = 256
    ack_bits: int = 256
    data_bits: int = 256 * 16

    packet_bits: int = 1024
    frame_overhead_bits: int = 256

    backoff: float = 0.5
    angular_resolution: float = 360.0 / 16.0
    sifs: float = 0.1

    def tx_duration(self, bits: int) -> float:
        return bits / self.bitrate


@dataclass(frozen=True)
class Frame:
    kind: str
    source: str
    bits: int
    destination: str | None = None            # финальный E — только для DATA
    local_recipients: tuple[str, ...] = ()    # кому этот кадр сейчас
    packets: tuple[int, ...] = ()
    data_senders: tuple[str, ...] = ()       # NEW: для ANN
    payload: bytes = b''
    duration: float = 0.0


class FrameType(Enum):
    RTS = auto()
    CTS = auto()
    DATA = auto()
    ACK = auto()
    ANN = auto()                             # NEW
    REQ = auto()                             # NEW