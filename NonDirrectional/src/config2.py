from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    distance:float
    sound_speed:float
    bitrate: float

    def tx_duration(self, bits: int) -> float:
        return bits / self.bitrate

    @property
    def propagation_delay(self) -> float:
        return self.distance / self.sound_speed

cfg = Config(1500, 1500, 2400)
print(cfg.propagation_delay)      # ожидаем 1.0
print(cfg.tx_duration(2400))       # ожидаем 1.0
print(cfg.tx_duration(256))        # ожидаем ≈ 0.1067
print(cfg.distance)                # 1500

# Проверим, что frozen работает:
try:
    cfg.distance = 100
except Exception as e:
    print("Нельзя менять:", type(e).__name__)

    

    

    