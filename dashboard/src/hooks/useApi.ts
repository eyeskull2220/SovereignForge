// ---------------------------------------------------------------------------
// React Query hooks for all SovereignForge API endpoints
// ---------------------------------------------------------------------------

import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '../services/api';
import type {
  HealthStatus,
  Model,
  TrainingRun,
  Portfolio,
  Trade,
  Signal,
  Config,
  Metrics,
} from '../types';

// Refetch intervals (ms)
const FAST   =  5_000;   // signals, portfolio
const MEDIUM = 30_000;   // models, training
const SLOW   = 60_000;   // config

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: () => fetchApi<HealthStatus>('/api/health'),
    refetchInterval: FAST,
    retry: 2,
  });
}

export function useModels(strategy?: string) {
  const endpoint = strategy ? `/api/models/${strategy}` : '/api/models';
  return useQuery<Model[]>({
    queryKey: ['models', strategy ?? '__all__'],
    queryFn: async () => {
      const res = await fetchApi<any>(endpoint);
      return Array.isArray(res) ? res : (res?.models ?? []);
    },
    refetchInterval: MEDIUM,
  });
}

export function useTrainingStatus() {
  return useQuery<TrainingRun[]>({
    queryKey: ['training', 'status'],
    queryFn: async () => {
      const res = await fetchApi<any>('/api/training/status');
      return Array.isArray(res) ? res : (res?.completed ?? res?.active ?? []);
    },
    refetchInterval: MEDIUM,
  });
}

export function useTrainingHistory() {
  return useQuery<TrainingRun[]>({
    queryKey: ['training', 'history'],
    queryFn: async () => {
      const res = await fetchApi<any>('/api/training/history');
      return Array.isArray(res) ? res : (res?.runs ?? res?.history ?? []);
    },
    refetchInterval: MEDIUM,
  });
}

export function usePortfolio() {
  return useQuery<Portfolio>({
    queryKey: ['portfolio'],
    queryFn: async () => {
      const raw = await fetchApi<any>('/api/portfolio');
      const m = raw?.metrics ?? raw ?? {};
      const rawPos = raw?.positions;
      const positions = Array.isArray(rawPos)
        ? rawPos
        : typeof rawPos === 'object' && rawPos !== null
          ? Object.values(rawPos)
          : [];
      return {
        total_value: m.equity ?? m.balance ?? m.total_value ?? 10000,
        daily_pnl: m.total_pnl ?? m.daily_pnl ?? 0,
        daily_pnl_pct: m.total_pnl_pct ?? m.daily_pnl_pct ?? 0,
        positions: positions as Portfolio['positions'],
        sharpe_ratio: m.sharpe_ratio ?? m.sharpe ?? 0,
        win_rate: m.win_rate ?? 0,
        total_trades: m.total_trades ?? 0,
        max_drawdown: m.max_drawdown_pct ?? m.max_drawdown ?? 0,
        exposure_pct: m.exposure_pct ?? 0,
      };
    },
    refetchInterval: FAST,
  });
}

export function useTrades() {
  return useQuery<Trade[]>({
    queryKey: ['trades'],
    queryFn: async () => {
      const res = await fetchApi<any>('/api/trades');
      return Array.isArray(res) ? res : (res?.trades ?? []);
    },
    refetchInterval: FAST,
  });
}

export function useSignals() {
  return useQuery<Signal[]>({
    queryKey: ['signals'],
    queryFn: async () => {
      const res = await fetchApi<any>('/api/signals');
      return Array.isArray(res) ? res : (res?.signals ?? []);
    },
    refetchInterval: FAST,
  });
}

export function useConfig() {
  return useQuery<Config>({
    queryKey: ['config'],
    queryFn: () => fetchApi<Config>('/api/config'),
    refetchInterval: SLOW,
  });
}

export function useMetrics() {
  return useQuery<Metrics>({
    queryKey: ['metrics'],
    queryFn: () => fetchApi<Metrics>('/api/metrics'),
    refetchInterval: FAST,
  });
}
