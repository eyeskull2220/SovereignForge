export interface Position { symbol: string; quantity: number; avgPrice: number; currentPrice: number; pnl: number; pnlPct: number; value: number; strategy: string; age: number; } 
export interface Alert { id: string; type: string; message: string; timestamp: string; priority: string; } 
export interface PortfolioData { balance: number; positions: Position[]; pnl: number; pnlPct: number; drawdown: number; sharpeRatio: number; winRate: number; totalTrades: number; } 
