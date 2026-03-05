"""전략 추상 클래스 및 Signal enum"""

from abc import ABC, abstractmethod
from enum import IntEnum

import pandas as pd


class Signal(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = -1


class Strategy(ABC):
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV DataFrame -> Signal Series 반환"""

    @property
    @abstractmethod
    def params(self) -> dict:
        """전략 파라미터 dict 반환"""
