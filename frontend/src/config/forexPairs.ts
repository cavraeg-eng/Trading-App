import type { ForexPair } from '../types';

export const MAJOR_PAIRS: ForexPair[] = [
  {
    symbol: 'EUR/USD',
    name: 'Euro / US Dollar',
    nickname: 'Fiber',
    category: 'major',
    baseSpread: 0.2,
    basePriceApprox: 1.08,
  },
  {
    symbol: 'USD/JPY',
    name: 'US Dollar / Japanese Yen',
    nickname: 'Gopher',
    category: 'major',
    baseSpread: 0.5,
    basePriceApprox: 155,
  },
  {
    symbol: 'GBP/USD',
    name: 'British Pound / US Dollar',
    nickname: 'Cable',
    category: 'major',
    baseSpread: 0.6,
    basePriceApprox: 1.27,
  },
  {
    symbol: 'USD/CHF',
    name: 'US Dollar / Swiss Franc',
    nickname: 'Swissie',
    category: 'major',
    baseSpread: 0.8,
    basePriceApprox: 0.88,
  },
  {
    symbol: 'AUD/USD',
    name: 'Australian Dollar / US Dollar',
    nickname: 'Aussie',
    category: 'major',
    baseSpread: 0.6,
    basePriceApprox: 0.65,
  },
  {
    symbol: 'USD/CAD',
    name: 'US Dollar / Canadian Dollar',
    nickname: 'Loonie',
    category: 'major',
    baseSpread: 0.5,
    basePriceApprox: 1.37,
  },
  {
    symbol: 'NZD/USD',
    name: 'New Zealand Dollar / US Dollar',
    nickname: 'Kiwi',
    category: 'major',
    baseSpread: 1.0,
    basePriceApprox: 0.60,
  },
];

export const MINOR_PAIRS: ForexPair[] = [
  {
    symbol: 'EUR/GBP',
    name: 'Euro / British Pound',
    nickname: 'Chunnel',
    category: 'minor',
    baseSpread: 1.0,
    basePriceApprox: 0.85,
  },
  {
    symbol: 'EUR/JPY',
    name: 'Euro / Japanese Yen',
    nickname: 'Yuppy',
    category: 'minor',
    baseSpread: 1.2,
    basePriceApprox: 167,
  },
  {
    symbol: 'EUR/CHF',
    name: 'Euro / Swiss Franc',
    nickname: 'Euro-Swissie',
    category: 'minor',
    baseSpread: 1.5,
    basePriceApprox: 0.95,
  },
  {
    symbol: 'GBP/JPY',
    name: 'British Pound / Japanese Yen',
    nickname: 'Guppy',
    category: 'minor',
    baseSpread: 1.8,
    basePriceApprox: 197,
  },
  {
    symbol: 'GBP/CHF',
    name: 'British Pound / Swiss Franc',
    nickname: '',
    category: 'minor',
    baseSpread: 2.0,
    basePriceApprox: 1.12,
  },
  {
    symbol: 'AUD/JPY',
    name: 'Australian Dollar / Japanese Yen',
    nickname: '',
    category: 'minor',
    baseSpread: 1.5,
    basePriceApprox: 101,
  },
  {
    symbol: 'AUD/NZD',
    name: 'Australian Dollar / New Zealand Dollar',
    nickname: '',
    category: 'minor',
    baseSpread: 2.0,
    basePriceApprox: 1.08,
  },
  {
    symbol: 'GBP/CAD',
    name: 'British Pound / Canadian Dollar',
    nickname: '',
    category: 'minor',
    baseSpread: 2.5,
    basePriceApprox: 1.74,
  },
  {
    symbol: 'NZD/JPY',
    name: 'New Zealand Dollar / Japanese Yen',
    nickname: '',
    category: 'minor',
    baseSpread: 2.0,
    basePriceApprox: 93,
  },
  {
    symbol: 'EUR/NZD',
    name: 'Euro / New Zealand Dollar',
    nickname: '',
    category: 'minor',
    baseSpread: 2.5,
    basePriceApprox: 1.78,
  },
  {
    symbol: 'CAD/JPY',
    name: 'Canadian Dollar / Japanese Yen',
    nickname: '',
    category: 'minor',
    baseSpread: 1.8,
    basePriceApprox: 113,
  },
  {
    symbol: 'CHF/JPY',
    name: 'Swiss Franc / Japanese Yen',
    nickname: '',
    category: 'minor',
    baseSpread: 2.0,
    basePriceApprox: 176,
  },
  {
    symbol: 'EUR/AUD',
    name: 'Euro / Australian Dollar',
    nickname: '',
    category: 'minor',
    baseSpread: 1.8,
    basePriceApprox: 1.66,
  },
];

export const EXOTIC_PAIRS: ForexPair[] = [
  {
    symbol: 'USD/MXN',
    name: 'US Dollar / Mexican Peso',
    nickname: '',
    category: 'exotic',
    baseSpread: 5.0,
    basePriceApprox: 17.2,
  },
  {
    symbol: 'USD/ZAR',
    name: 'US Dollar / South African Rand',
    nickname: '',
    category: 'exotic',
    baseSpread: 8.0,
    basePriceApprox: 18.5,
  },
  {
    symbol: 'USD/TRY',
    name: 'US Dollar / Turkish Lira',
    nickname: '',
    category: 'exotic',
    baseSpread: 10.0,
    basePriceApprox: 38.5,
  },
  {
    symbol: 'USD/BRL',
    name: 'US Dollar / Brazilian Real',
    nickname: '',
    category: 'exotic',
    baseSpread: 8.0,
    basePriceApprox: 5.8,
  },
  {
    symbol: 'USD/SGD',
    name: 'US Dollar / Singapore Dollar',
    nickname: '',
    category: 'exotic',
    baseSpread: 2.0,
    basePriceApprox: 1.34,
  },
  {
    symbol: 'USD/THB',
    name: 'US Dollar / Thai Baht',
    nickname: '',
    category: 'exotic',
    baseSpread: 5.0,
    basePriceApprox: 35.2,
  },
  {
    symbol: 'USD/CNH',
    name: 'US Dollar / Chinese Yuan',
    nickname: '',
    category: 'exotic',
    baseSpread: 4.0,
    basePriceApprox: 7.25,
  },
  {
    symbol: 'USD/SEK',
    name: 'US Dollar / Swedish Krona',
    nickname: '',
    category: 'exotic',
    baseSpread: 6.0,
    basePriceApprox: 10.8,
  },
  {
    symbol: 'USD/NOK',
    name: 'US Dollar / Norwegian Krone',
    nickname: '',
    category: 'exotic',
    baseSpread: 6.0,
    basePriceApprox: 10.9,
  },
  {
    symbol: 'USD/HKD',
    name: 'US Dollar / Hong Kong Dollar',
    nickname: '',
    category: 'exotic',
    baseSpread: 1.5,
    basePriceApprox: 7.81,
  },
  {
    symbol: 'USD/PLN',
    name: 'US Dollar / Polish Zloty',
    nickname: '',
    category: 'exotic',
    baseSpread: 4.0,
    basePriceApprox: 4.05,
  },
];

export const COMMODITY_PAIRS: ForexPair[] = [
  {
    symbol: 'XAU/USD',
    name: 'Gold / US Dollar',
    nickname: 'Gold',
    category: 'commodity',
    baseSpread: 3.0,
    basePriceApprox: 2350,
  },
  {
    symbol: 'XAG/USD',
    name: 'Silver / US Dollar',
    nickname: 'Silver',
    category: 'commodity',
    baseSpread: 2.5,
    basePriceApprox: 29.5,
  },
  {
    symbol: 'WTI/USD',
    name: 'Crude Oil WTI / US Dollar',
    nickname: 'Oil',
    category: 'commodity',
    baseSpread: 3.0,
    basePriceApprox: 78.5,
  },
  {
    symbol: 'BRENT/USD',
    name: 'Brent Crude / US Dollar',
    nickname: 'Brent',
    category: 'commodity',
    baseSpread: 3.5,
    basePriceApprox: 82.0,
  },
  {
    symbol: 'NG/USD',
    name: 'Natural Gas / US Dollar',
    nickname: 'NatGas',
    category: 'commodity',
    baseSpread: 4.0,
    basePriceApprox: 2.15,
  },
  {
    symbol: 'XPT/USD',
    name: 'Platinum / US Dollar',
    nickname: 'Platinum',
    category: 'commodity',
    baseSpread: 4.0,
    basePriceApprox: 980,
  },
  {
    symbol: 'COPPER/USD',
    name: 'Copper / US Dollar',
    nickname: 'Copper',
    category: 'commodity',
    baseSpread: 3.0,
    basePriceApprox: 4.25,
  },
  {
    symbol: 'COFFEE/USD',
    name: 'Coffee / US Dollar',
    nickname: 'Coffee',
    category: 'commodity',
    baseSpread: 5.0,
    basePriceApprox: 185,
  },
];

export const CRYPTO_PAIRS: ForexPair[] = [
  {
    symbol: 'BTC/USD',
    name: 'Bitcoin / US Dollar',
    nickname: 'Bitcoin',
    category: 'crypto',
    baseSpread: 15.0,
    basePriceApprox: 68500,
  },
  {
    symbol: 'ETH/USD',
    name: 'Ethereum / US Dollar',
    nickname: 'Ether',
    category: 'crypto',
    baseSpread: 5.0,
    basePriceApprox: 3450,
  },
  {
    symbol: 'SOL/USD',
    name: 'Solana / US Dollar',
    nickname: 'Solana',
    category: 'crypto',
    baseSpread: 2.0,
    basePriceApprox: 145,
  },
  {
    symbol: 'XRP/USD',
    name: 'Ripple / US Dollar',
    nickname: 'Ripple',
    category: 'crypto',
    baseSpread: 0.5,
    basePriceApprox: 0.58,
  },
  {
    symbol: 'BNB/USD',
    name: 'Binance Coin / US Dollar',
    nickname: 'BNB',
    category: 'crypto',
    baseSpread: 3.0,
    basePriceApprox: 580,
  },
  {
    symbol: 'ADA/USD',
    name: 'Cardano / US Dollar',
    nickname: 'Cardano',
    category: 'crypto',
    baseSpread: 0.3,
    basePriceApprox: 0.45,
  },
  {
    symbol: 'DOGE/USD',
    name: 'Dogecoin / US Dollar',
    nickname: 'Doge',
    category: 'crypto',
    baseSpread: 0.2,
    basePriceApprox: 0.16,
  },
  {
    symbol: 'LTC/USD',
    name: 'Litecoin / US Dollar',
    nickname: 'Litecoin',
    category: 'crypto',
    baseSpread: 1.5,
    basePriceApprox: 85,
  },
  {
    symbol: 'LINK/USD',
    name: 'Chainlink / US Dollar',
    nickname: 'Chainlink',
    category: 'crypto',
    baseSpread: 0.5,
    basePriceApprox: 14.5,
  },
  {
    symbol: 'DOT/USD',
    name: 'Polkadot / US Dollar',
    nickname: 'Polkadot',
    category: 'crypto',
    baseSpread: 0.4,
    basePriceApprox: 7.2,
  },
  {
    symbol: 'AVAX/USD',
    name: 'Avalanche / US Dollar',
    nickname: 'Avalanche',
    category: 'crypto',
    baseSpread: 0.8,
    basePriceApprox: 35,
  },
  {
    symbol: 'MATIC/USD',
    name: 'Polygon / US Dollar',
    nickname: 'Polygon',
    category: 'crypto',
    baseSpread: 0.3,
    basePriceApprox: 0.72,
  },
];

export const INDEX_PAIRS: ForexPair[] = [
  // Major Indices
  {
    symbol: 'US30',
    name: 'Dow Jones Industrial Average',
    nickname: 'Dow',
    category: 'index',
    baseSpread: 2.0,
    basePriceApprox: 39800,
  },
  {
    symbol: 'US500',
    name: 'S&P 500 Index',
    nickname: 'S&P',
    category: 'index',
    baseSpread: 0.5,
    basePriceApprox: 5250,
  },
  {
    symbol: 'US100',
    name: 'Nasdaq 100 Index',
    nickname: 'Nasdaq',
    category: 'index',
    baseSpread: 1.5,
    basePriceApprox: 18400,
  },
  {
    symbol: 'UK100',
    name: 'FTSE 100 Index',
    nickname: 'Footsie',
    category: 'index',
    baseSpread: 1.5,
    basePriceApprox: 8200,
  },
  {
    symbol: 'DE40',
    name: 'DAX 40 Index',
    nickname: 'DAX',
    category: 'index',
    baseSpread: 1.5,
    basePriceApprox: 18100,
  },
  {
    symbol: 'FR40',
    name: 'CAC 40 Index',
    nickname: 'CAC',
    category: 'index',
    baseSpread: 1.5,
    basePriceApprox: 8050,
  },
  {
    symbol: 'JP225',
    name: 'Nikkei 225 Index',
    nickname: 'Nikkei',
    category: 'index',
    baseSpread: 8.0,
    basePriceApprox: 39500,
  },
  {
    symbol: 'AU200',
    name: 'ASX 200 Index',
    nickname: 'ASX',
    category: 'index',
    baseSpread: 2.0,
    basePriceApprox: 7800,
  },
  // Minor Indices
  {
    symbol: 'EU50',
    name: 'Euro Stoxx 50 Index',
    nickname: 'Euro Stoxx',
    category: 'index',
    baseSpread: 2.0,
    basePriceApprox: 5000,
  },
  {
    symbol: 'ES35',
    name: 'IBEX 35 Index',
    nickname: 'IBEX',
    category: 'index',
    baseSpread: 5.0,
    basePriceApprox: 11200,
  },
  {
    symbol: 'IT40',
    name: 'FTSE MIB Index',
    nickname: 'MIB',
    category: 'index',
    baseSpread: 10.0,
    basePriceApprox: 34000,
  },
  {
    symbol: 'HK50',
    name: 'Hang Seng Index',
    nickname: 'Hang Seng',
    category: 'index',
    baseSpread: 8.0,
    basePriceApprox: 17500,
  },
  {
    symbol: 'CN50',
    name: 'China A50 Index',
    nickname: 'China A50',
    category: 'index',
    baseSpread: 6.0,
    basePriceApprox: 12800,
  },
  {
    symbol: 'IN50',
    name: 'Nifty 50 Index',
    nickname: 'Nifty',
    category: 'index',
    baseSpread: 5.0,
    basePriceApprox: 22500,
  },
  {
    symbol: 'SA40',
    name: 'South Africa Top 40',
    nickname: 'SA40',
    category: 'index',
    baseSpread: 15.0,
    basePriceApprox: 76000,
  },
];

export const ALL_FOREX_PAIRS: ForexPair[] = [
  ...MAJOR_PAIRS,
  ...MINOR_PAIRS,
  ...EXOTIC_PAIRS,
  ...COMMODITY_PAIRS,
  ...CRYPTO_PAIRS,
  ...INDEX_PAIRS,
];

export const DEFAULT_PAIR: ForexPair = MAJOR_PAIRS[0];

export function getPairBySymbol(symbol: string): ForexPair | undefined {
  return ALL_FOREX_PAIRS.find((pair) => pair.symbol === symbol);
}

/**
 * Convert pair symbol to TradingView format
 * Forex: EUR/USD → FX:EURUSD
 * Crypto: BTC/USD → CRYPTO:BTCUSD
 * Commodities: XAU/USD → TVC:GOLD, XAG/USD → TVC:SILVER, etc.
 * Indices: US30 → TVC:DJI, US500 → TVC:SPX, etc.
 */
export function getTradingViewSymbol(pair: ForexPair): string {
  const { symbol, category } = pair;

  // Commodities mapping
  if (category === 'commodity') {
    const commodityMap: Record<string, string> = {
      'XAU/USD': 'TVC:GOLD',
      'XAG/USD': 'TVC:SILVER',
      'WTI/USD': 'TVC:USOIL',
      'BRENT/USD': 'TVC:UKOIL',
      'NG/USD': 'TVC:NATURALGAS',
      'XPT/USD': 'TVC:PLATINUM',
      'COPPER/USD': 'TVC:COPPER',
      'COFFEE/USD': 'TVC:COFFEE',
    };
    return commodityMap[symbol] || `TVC:${symbol.replace('/', '')}`;
  }

  // Crypto mapping
  if (category === 'crypto') {
    return `CRYPTO:${symbol.replace('/', '')}`;
  }

  // Indices mapping
  if (category === 'index') {
    const indexMap: Record<string, string> = {
      'US30': 'TVC:DJI',
      'US500': 'TVC:SPX',
      'US100': 'NASDAQ:NDX',
      'UK100': 'TVC:UKX',
      'DE40': 'XETR:DAX',
      'FR40': 'EURONEXT:PX1',
      'JP225': 'TVC:NI225',
      'AU200': 'TVC:XJO',
      'EU50': 'TVC:SX5E',
      'HK50': 'TVC:HSI',
      'ES35': 'BME:IBC',
      'IT40': 'INDEX:FTSEMIB',
      'CN50': 'SSE:000016',
      'IN50': 'NSE:NIFTY',
      'SA40': 'JSE:J200',
    };
    return indexMap[symbol] || `TVC:${symbol}`;
  }

  // Forex (major, minor, exotic)
  return `FX:${symbol.replace('/', '')}`;
}

/**
 * Convert timeframe string to TradingView interval
 * TradingView uses: 1, 3, 5, 15, 30, 60, 120, 240, D, W, M
 */
export function getTradingViewInterval(timeframe: string): string {
  const intervalMap: Record<string, string> = {
    '1m': '1',
    '5m': '5',
    '15m': '15',
    '30m': '30',
    '1h': '60',
    '2h': '120',
    '4h': '240',
    '1d': 'D',
    '1w': 'W',
    '1M': 'M',
  };
  return intervalMap[timeframe] || '60';
}
