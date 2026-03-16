"""Pydantic config schema for typed validation of YAML configs."""
from typing import Optional

from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    default_period_days: int = Field(60, ge=1, le=3650)
    tp_r: float = Field(2.0, ge=0.5, le=10.0)
    sl_r: float = Field(1.0, ge=0.1, le=5.0)
    session_filter: Optional[list[str]] = None
    session_mode: str = Field("killzone", pattern=r"^(killzone|extended)$")


class RiskConfig(BaseModel):
    max_position_pct: float = Field(0.02, ge=0.001, le=0.1)
    max_daily_loss_r: float = Field(3.0, ge=0.5, le=20.0)
    max_concurrent_positions: int = Field(3, ge=1, le=20)
    equity_kill_switch_pct: float = Field(10.0, ge=1.0, le=50.0)
    risk_pct_per_r: float = Field(0.01, ge=0.001, le=0.05)
    max_trades_per_session: int = Field(1, ge=1, le=10)


class LiquiditySweepConfig(BaseModel):
    lookback_candles: int = Field(20, ge=10, le=50)
    sweep_threshold_pct: float = Field(0.2, ge=0.05, le=1.0)
    reversal_candles: int = Field(3, ge=1, le=10)


class DisplacementConfig(BaseModel):
    min_body_pct: int = Field(70, ge=30, le=95)
    min_candles: int = Field(3, ge=1, le=10)
    min_move_pct: float = Field(1.5, ge=0.1, le=10.0)


class FairValueGapsConfig(BaseModel):
    min_gap_pct: float = Field(0.5, ge=0.05, le=5.0)
    validity_candles: int = Field(50, ge=5, le=200)


class MarketStructureShiftConfig(BaseModel):
    swing_lookback: int = Field(5, ge=2, le=30)
    break_threshold_pct: float = Field(0.2, ge=0.05, le=2.0)


class OrderBlocksConfig(BaseModel):
    min_candles: int = Field(2, ge=1, le=10)
    min_move_pct: float = Field(1.5, ge=0.5, le=10.0)
    validity_candles: int = Field(40, ge=5, le=200)


class ImbalanceZonesConfig(BaseModel):
    min_gap_size: float = Field(3.0, ge=0.1, le=50.0)
    validity_candles: int = Field(50, ge=5, le=200)


class StructureContextConfig(BaseModel):
    lookback: int = Field(30, ge=5, le=100)
    pivot_bars: int = Field(2, ge=1, le=10)


class StrategyConfig(BaseModel):
    name: str = "sqe_xauusd"
    liquidity_sweep: LiquiditySweepConfig = LiquiditySweepConfig()
    displacement: DisplacementConfig = DisplacementConfig()
    fair_value_gaps: FairValueGapsConfig = FairValueGapsConfig()
    market_structure_shift: MarketStructureShiftConfig = MarketStructureShiftConfig()
    order_blocks: OrderBlocksConfig = OrderBlocksConfig()
    imbalance_zones: ImbalanceZonesConfig = ImbalanceZonesConfig()
    structure_context: StructureContextConfig = StructureContextConfig()
    require_structure: bool = True
    structure_use_h1_gate: bool = False
    entry_require_sweep_displacement_fvg: bool = True
    entry_sweep_disp_fvg_lookback_bars: int = Field(5, ge=0, le=20)
    entry_sweep_disp_fvg_min_count: int = Field(3, ge=1, le=6)


class RSSFeedConfig(BaseModel):
    name: str
    url: str
    tier: int = Field(2, ge=1, le=4)
    category: str = ""


class NewsGateConfig(BaseModel):
    block_minutes_before_high_impact: int = Field(30, ge=0, le=120)
    block_minutes_after_high_impact: int = Field(15, ge=0, le=120)
    high_impact_events: list[str] = Field(
        default_factory=lambda: ["NFP", "FOMC", "CPI", "GDP"]
    )


class NewsSentimentConfig(BaseModel):
    mode: str = Field("hybrid", pattern=r"^(rule_based|llm|hybrid)$")
    llm_model: str = "gpt-4o-mini"
    boost_threshold: float = Field(0.7, ge=0.0, le=1.0)
    suppress_threshold: float = Field(0.3, ge=0.0, le=1.0)


class CounterNewsConfig(BaseModel):
    enabled: bool = True
    check_interval_seconds: int = Field(60, ge=10, le=600)
    exit_threshold: float = Field(0.8, ge=0.0, le=1.0)


class NewsConfig(BaseModel):
    enabled: bool = False
    poll_interval_seconds: int = Field(30, ge=5, le=300)
    sources: Optional[dict] = None
    filter: Optional[dict] = None
    gate: NewsGateConfig = NewsGateConfig()
    sentiment: NewsSentimentConfig = NewsSentimentConfig()
    counter_news: CounterNewsConfig = CounterNewsConfig()


class BrokerConfig(BaseModel):
    provider: str = "oanda"
    environment: str = Field("practice", pattern=r"^(practice|live)$")
    account_id: str = ""
    token: str = ""
    instrument: str = "XAU_USD"
    initial_balance: float = Field(10000.0, ge=100.0)
    leverage: int = Field(100, ge=1, le=500)
    margin_rate: float = Field(0.05, ge=0.001, le=1.0)


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    alerts: dict = Field(default_factory=lambda: {
        "trade_entry": True, "trade_exit": True,
        "daily_summary": True, "error_alerts": True,
        "news_event": True, "counter_news": True,
    })


class DashboardConfig(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = Field(8501, ge=1024, le=65535)


class AppConfig(BaseModel):
    """Top-level application configuration with full validation."""
    symbol: str = "XAUUSD"
    timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h"])
    backtest: BacktestConfig = BacktestConfig()
    risk: RiskConfig = RiskConfig()
    strategy: StrategyConfig = StrategyConfig()
    news: NewsConfig = NewsConfig()
    broker: BrokerConfig = BrokerConfig()
    telegram: TelegramConfig = TelegramConfig()
    dashboard: DashboardConfig = DashboardConfig()
