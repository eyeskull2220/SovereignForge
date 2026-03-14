// ---------------------------------------------------------------------------
// SovereignForge API response types
// ---------------------------------------------------------------------------

export interface HealthStatus {
  status: string;
  uptime?: number;
  version?: string;
  timestamp?: string;
}

export interface Model {
  id?: string;
  strategy: string;
  pair: string;
  exchange: string;
  version?: string;
  val_loss?: number;
  sharpe?: number;
  win_rate?: number;
  net_pnl?: number;
  risk_score?: number;
  epochs_completed?: number;
  created_at?: string;
  updated_at?: string;
  status?: string;
}

export interface TrainingRun {
  id?: string;
  strategy: string;
  pair: string;
  exchange: string;
  status: 'running' | 'completed' | 'failed' | 'queued';
  epoch?: number;
  total_epochs?: number;
  val_loss?: number;
  train_loss?: number;
  sharpe?: number;
  win_rate?: number;
  net_pnl?: number;
  risk_score?: number;
  started_at?: string;
  completed_at?: string;
  epochs_completed?: number;
  elapsed_seconds?: number;
  gpu?: string;
}

export interface PortfolioPosition {
  pair: string;
  exchange: string;
  side: 'buy' | 'sell';
  entry_price: number;
  current_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  status: 'open' | 'closed';
}

export interface Portfolio {
  total_value?: number;
  daily_pnl?: number;
  daily_pnl_pct?: number;
  positions?: PortfolioPosition[];
  sharpe_ratio?: number;
  win_rate?: number;
  total_trades?: number;
  max_drawdown?: number;
  exposure_pct?: number;
}

export interface Trade {
  id?: string;
  pair: string;
  exchange: string;
  side: 'buy' | 'sell';
  price: number;
  quantity: number;
  pnl?: number;
  pnl_pct?: number;
  strategy?: string;
  timestamp: string;
  status?: string;
}

export interface Signal {
  id?: string;
  pair: string;
  exchange: string;
  strategy: string;
  direction: 'long' | 'short' | 'neutral';
  strength: number;
  confidence?: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface Config {
  strategies?: Record<string, any>;
  exchanges?: string[];
  pairs?: string[];
  risk_limits?: Record<string, number>;
  [key: string]: any;
}

export interface Metrics {
  portfolio_value?: number;
  daily_pnl?: number;
  sharpe_ratio?: number;
  win_rate?: number;
  total_trades?: number;
  max_drawdown?: number;
  open_positions?: number;
  max_positions?: number;
  exposure_pct?: number;
  daily_loss_pct?: number;
  drawdown_pct?: number;
  uptime?: number;
  [key: string]: any;
}
