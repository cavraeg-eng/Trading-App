"""Sentiment analysis engine for market sentiment."""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class SentimentAnalyzer:
    """Analyzes market sentiment from news and generates per-pair scores."""

    # Map keywords to currency pairs
    PAIR_KEYWORDS = {
        "EUR/USD": ["euro", "ecb", "eurozone", "european central bank", "lagarde", "eu inflation"],
        "GBP/USD": ["pound", "boe", "bank of england", "uk economy", "brexit", "sterling"],
        "USD/JPY": ["yen", "boj", "bank of japan", "japanese", "japan economy", "carry trade"],
        "AUD/USD": ["aussie", "rba", "reserve bank of australia", "australian", "commodities"],
        "USD/CAD": ["loonie", "boc", "bank of canada", "canadian", "oil price", "cad"],
        "USD/CHF": ["swiss franc", "snb", "swiss national bank", "safe haven", "switzerland"],
        "NZD/USD": ["kiwi", "rbnz", "reserve bank of new zealand", "new zealand", "nzd"],
        "BTC/USD": ["bitcoin", "btc", "crypto", "cryptocurrency", "blockchain", "btc etf"],
        "ETH/USD": ["ethereum", "eth", "crypto", "defi", "smart contracts", "eth etf"],
        "XAU/USD": ["gold", "precious metals", "safe haven", "bullion", "xau"],
        "XAG/USD": ["silver", "precious metals", "industrial metals", "xag"],
        "SPX500": ["sp500", "s&p 500", "us stocks", "equities", "wall street"],
    }

    # Realistic headlines for each pair
    PAIR_HEADLINES = {
        "EUR/USD": {
            "bullish": [
                "ECB signals potential rate adjustment in upcoming meeting",
                "Eurozone inflation data beats expectations, euro strengthens",
                "Lagarde hints at hawkish stance on monetary policy",
                "European manufacturing PMI shows unexpected expansion",
                "Euro gains as EU reaches breakthrough trade agreement",
                "German economic data surprises to the upside",
                "ECB officials suggest inflation nearing target sustainably",
            ],
            "bearish": [
                "ECB cuts rates as eurozone growth concerns mount",
                "Euro weakens on disappointing GDP figures from Germany",
                "Lagarde signals dovish shift amid economic slowdown",
                "European banking sector faces headwinds from rate cuts",
                "Euro slides as political uncertainty grips EU markets",
                "ECB extends QE program citing deflation risks",
                "Eurozone unemployment rises, pressuring euro lower",
            ],
            "neutral": [
                "ECB holds rates steady, awaits more economic data",
                "Euro trades in range ahead of key inflation report",
                "Mixed signals from eurozone keep EUR/USD in consolidation",
                "ECB policymakers divided on next policy move",
                "Euro steady as markets await Lagarde speech",
                "European markets pause ahead of US data release",
            ],
        },
        "GBP/USD": {
            "bullish": [
                "Bank of England hints at maintaining higher rates for longer",
                "UK inflation remains sticky, supporting pound strength",
                "British economy shows resilience post-Brexit adjustments",
                "Sterling rallies on better-than-expected retail sales",
                "UK wage growth accelerates, boosting GBP demand",
                "BoE Governor signals patience on rate cuts",
                "UK services PMI hits multi-month high",
            ],
            "bearish": [
                "Bank of England cuts rates amid recession fears",
                "Sterling drops as UK manufacturing contracts sharply",
                "Brexit trade complications weigh on British economy",
                "UK housing market slowdown pressures pound lower",
                "BoE signals aggressive easing cycle ahead",
                "British pound weakens on political uncertainty",
                "UK GDP contracts more than expected in Q4",
            ],
            "neutral": [
                "BoE holds rates, markets await inflation guidance",
                "Sterling consolidates as traders assess UK outlook",
                "Mixed UK data keeps GBP/USD range-bound",
                "Bank of England faces challenging policy decisions",
                "UK economic indicators paint conflicting picture",
            ],
        },
        "USD/JPY": {
            "bullish": [
                "BOJ maintains ultra-loose policy, yen weakens further",
                "Japan's inflation remains below target, supporting JPY shorts",
                "Carry trade flows boost USD/JPY to new highs",
                "BOJ Governor Ueda signals no rush to normalize",
                "Japan's export data disappoints, pressuring yen",
                "Yield differential widens in favor of dollar",
                "Japanese intervention threats fail to deter yen selling",
            ],
            "bearish": [
                "BOJ surprises markets with hawkish policy shift",
                "Yen strengthens as Japan exits negative rates",
                "Safe-haven flows boost yen amid global uncertainty",
                "Japan's wage growth accelerates, supporting JPY",
                "BOJ hints at rate hikes in coming months",
                "Japanese authorities intervene to support currency",
                "Yen rallies as carry trades unwind rapidly",
            ],
            "neutral": [
                "BOJ maintains policy, awaits wage growth confirmation",
                "USD/JPY range-bound as traders assess BOJ intentions",
                "Mixed Japanese data keeps yen direction unclear",
                "Japan's economic outlook remains uncertain",
                "BOJ divided on timing of policy normalization",
            ],
        },
        "AUD/USD": {
            "bullish": [
                "RBA holds rates steady, hints at future hikes",
                "Australian commodity exports surge, boosting AUD",
                "China stimulus hopes lift Australian dollar",
                "RBA Governor signals inflation fight not over",
                "Australian employment data beats expectations",
                "Iron ore prices rally, supporting Aussie dollar",
                "Australian GDP growth exceeds forecasts",
            ],
            "bearish": [
                "RBA cuts rates as Australian economy slows",
                "China demand concerns weigh on Australian exports",
                "AUD drops on disappointing Australian retail sales",
                "RBA signals dovish pivot amid global slowdown",
                "Australian housing market weakness pressures currency",
                "Commodity prices tumble, hurting Aussie dollar",
                "China trade data misses, AUD falls",
            ],
            "neutral": [
                "RBA holds rates, monitors global developments",
                "Australian dollar consolidates ahead of RBA decision",
                "Mixed China data keeps AUD in range",
                "Australian economic indicators send mixed signals",
                "RBA faces balancing act on policy settings",
            ],
        },
        "USD/CAD": {
            "bullish": [
                "Oil prices slump, pressuring Canadian dollar",
                "Bank of Canada cuts rates more than expected",
                "Canadian housing market cools significantly",
                "BoC signals concerns about economic growth",
                "Canadian employment data disappoints markets",
                "Oil demand fears weigh on loonie",
                "Canada's trade deficit widens, CAD weakens",
            ],
            "bearish": [
                "Oil prices surge, boosting Canadian dollar",
                "Bank of Canada maintains hawkish stance",
                "Canadian economy shows resilience despite headwinds",
                "Strong Canadian jobs report supports loonie",
                "BoC hints at holding rates higher for longer",
                "Oil supply constraints benefit CAD",
                "Canadian inflation remains elevated, supporting currency",
            ],
            "neutral": [
                "BoC holds rates, awaits more economic clarity",
                "Canadian dollar range-bound on mixed oil signals",
                "Bank of Canada faces difficult policy choices",
                "Canadian economic data presents mixed picture",
                "Oil volatility keeps USD/CAD in consolidation",
            ],
        },
        "USD/CHF": {
            "bullish": [
                "Safe-haven flows favor dollar over franc",
                "SNB intervenes to weaken Swiss franc",
                "Swiss economy shows signs of slowing",
                "SNB signals potential rate cuts ahead",
                "Swiss inflation drops below target range",
                "Risk-on sentiment reduces CHF demand",
            ],
            "bearish": [
                "Safe-haven flows boost Swiss franc",
                "SNB maintains hawkish stance on rates",
                "Geopolitical tensions increase CHF demand",
                "Swiss economy outperforms expectations",
                "SNB hints at further rate increases",
                "Flight to safety benefits Swiss franc",
            ],
            "neutral": [
                "SNB holds rates steady, franc stable",
                "USD/CHF consolidates in tight range",
                "Swiss economic data meets expectations",
                "SNB monitors currency appreciation closely",
            ],
        },
        "NZD/USD": {
            "bullish": [
                "RBNZ surprises with hawkish hold on rates",
                "New Zealand dairy prices surge, boosting NZD",
                "RBNZ signals no rate cuts in near term",
                "New Zealand trade balance improves",
                "Strong NZ employment data supports kiwi",
            ],
            "bearish": [
                "RBNZ cuts rates amid slowing economy",
                "New Zealand dairy prices fall sharply",
                "RBNZ Governor signals dovish shift",
                "New Zealand housing market contracts",
                "Weak China data hurts NZ exports",
            ],
            "neutral": [
                "RBNZ holds rates, awaits more data",
                "NZD consolidates ahead of RBNZ decision",
                "New Zealand economic outlook uncertain",
            ],
        },
        "BTC/USD": {
            "bullish": [
                "Bitcoin sees increased institutional inflows amid market volatility",
                "Spot Bitcoin ETF sees record daily inflows",
                "Major corporation adds Bitcoin to treasury reserves",
                "Bitcoin network hash rate reaches all-time high",
                "Institutional adoption of Bitcoin accelerates globally",
                "Bitcoin halving event drives supply squeeze narrative",
                "Major bank launches Bitcoin custody services",
                "Bitcoin breaks above key technical resistance",
            ],
            "bearish": [
                "Regulatory concerns mount as SEC reviews crypto exchanges",
                "Bitcoin ETF outflows signal institutional profit-taking",
                "Major exchange hack raises security concerns",
                "Central bank digital currencies threaten Bitcoin adoption",
                "Bitcoin mining difficulty drops as miners capitulate",
                "Macro headwinds pressure risk assets including Bitcoin",
                "Regulatory crackdown in major market hurts sentiment",
                "Bitcoin falls below critical support level",
            ],
            "neutral": [
                "Bitcoin trades sideways as market awaits catalyst",
                "Mixed regulatory signals keep Bitcoin range-bound",
                "Bitcoin volatility drops as consolidation continues",
                "Institutional interest in Bitcoin remains steady",
                "Bitcoin market structure shows signs of maturation",
            ],
        },
        "ETH/USD": {
            "bullish": [
                "Ethereum ETF approval hopes drive price higher",
                "Ethereum network upgrade successfully implemented",
                "DeFi activity on Ethereum reaches new highs",
                "Institutional staking of Ethereum accelerates",
                "Ethereum burns more ETH than issued",
                "Major corporation adopts Ethereum for payments",
                "Ethereum Layer 2 adoption surges",
            ],
            "bearish": [
                "Ethereum ETF delayed by regulatory concerns",
                "High gas fees drive users to alternative chains",
                "Ethereum staking withdrawals pressure price",
                "Competition from Layer 1s hurts ETH dominance",
                "Ethereum foundation sells tokens amid market weakness",
                "DeFi exploits raise security concerns on Ethereum",
            ],
            "neutral": [
                "Ethereum consolidates ahead of network upgrade",
                "ETH/BTC ratio stabilizes after recent volatility",
                "Ethereum development activity remains strong",
                "Staking yields on Ethereum remain attractive",
            ],
        },
        "XAU/USD": {
            "bullish": [
                "Gold surges as geopolitical tensions escalate",
                "Central bank gold buying reaches record levels",
                "Gold benefits from dollar weakness and rate cut hopes",
                "Inflation concerns drive safe-haven demand for gold",
                "Gold breaks above $2,100 on strong buying",
                "Chinese retail demand for gold remains robust",
                "Gold mining supply disruptions support prices",
            ],
            "bearish": [
                "Gold falls as dollar strengthens on rate hike fears",
                "Rising real yields pressure gold lower",
                "Gold ETF outflows signal institutional selling",
                "Strong US jobs data reduces gold appeal",
                "Gold breaks below key support at $1,900",
                "Profit-taking hits gold after recent rally",
                "Risk-on sentiment reduces safe-haven demand",
            ],
            "neutral": [
                "Gold consolidates as traders assess Fed outlook",
                "Mixed signals keep gold in tight trading range",
                "Gold awaits catalyst from inflation data",
                "Physical gold demand offsets ETF outflows",
            ],
        },
        "XAG/USD": {
            "bullish": [
                "Silver outperforms gold on industrial demand hopes",
                "Solar panel demand boosts silver outlook",
                "Silver supply deficits support higher prices",
                "Green energy transition drives silver demand",
                "Silver breaks above $25 on strong buying",
            ],
            "bearish": [
                "Silver falls as industrial demand weakens",
                "Strong dollar pressures silver lower",
                "Silver ETF outflows signal weak sentiment",
                "Economic slowdown fears hurt industrial metals",
                "Silver breaks below $22 support level",
            ],
            "neutral": [
                "Silver trades in range between support and resistance",
                "Industrial demand outlook remains uncertain",
                "Silver awaits direction from gold price action",
            ],
        },
        "SPX500": {
            "bullish": [
                "S&P 500 hits new all-time high on earnings strength",
                "Tech sector rally drives broader market gains",
                "Fed rate cut expectations boost equity sentiment",
                "Strong corporate earnings surprise to the upside",
                "AI boom continues to lift tech valuations",
                "Economic soft landing narrative supports stocks",
                "Buyback announcements provide market support",
            ],
            "bearish": [
                "S&P 500 falls on recession fears and earnings misses",
                "Tech selloff drags broader market lower",
                "Fed hawkish pivot sparks equity market correction",
                "Earnings guidance cuts raise growth concerns",
                "Geopolitical tensions spark risk-off selling",
                "Valuation concerns trigger institutional profit-taking",
                "Credit conditions tightening worries investors",
            ],
            "neutral": [
                "S&P 500 consolidates near record highs",
                "Mixed earnings results keep market range-bound",
                "Traders await clarity on Fed policy path",
                "Sector rotation creates choppy price action",
            ],
        },
    }

    SOURCES = ["Bloomberg", "Reuters", "WSJ", "CNBC", "MarketWatch", "Financial Times", "CNBC", "ForexLive"]

    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)

    async def get_sentiment(self, symbol: str) -> dict:
        """Get sentiment for a specific symbol."""
        # Check cache
        if self._is_cache_valid() and symbol in self._cache:
            return self._cache[symbol]

        # Generate sentiment (mock for now, structured for real RSS/API integration)
        sentiment = self._generate_sentiment(symbol)
        self._cache[symbol] = sentiment
        self._cache_time = datetime.utcnow()
        return sentiment

    async def get_overview(self) -> List[dict]:
        """Get sentiment overview for all major pairs."""
        pairs = list(self.PAIR_KEYWORDS.keys())
        results = []
        for pair in pairs:
            sentiment = await self.get_sentiment(pair)
            results.append({
                "symbol": sentiment["symbol"],
                "score": sentiment["score"],
                "label": sentiment["label"],
            })
        return results

    def _generate_sentiment(self, symbol: str) -> dict:
        """Generate realistic mock sentiment data."""
        # Use symbol hash for consistent-ish but varied results
        seed = hash(symbol + datetime.utcnow().strftime("%Y-%m-%d-%H"))
        random.seed(seed)

        score = random.uniform(-0.8, 0.8)
        label = "bullish" if score > 0.2 else ("bearish" if score < -0.2 else "neutral")

        headlines = self._generate_headlines(symbol, score, label)
        trend = [round(score + random.uniform(-0.3, 0.3), 2) for _ in range(24)]
        # Ensure trend ends near current score
        trend[-1] = round(score, 2)

        random.seed()  # Reset seed

        return {
            "symbol": symbol,
            "score": round(score, 3),
            "label": label,
            "headlines": headlines,
            "trend": trend,
            "last_updated": datetime.utcnow().isoformat(),
            "source_count": random.randint(5, 25),
        }

    def _generate_headlines(self, symbol: str, bias: float, label: str) -> List[dict]:
        """Generate realistic mock headlines."""
        headlines = []
        num_headlines = random.randint(5, 8)

        # Get headline templates for this symbol
        symbol_headlines = self.PAIR_HEADLINES.get(symbol, self.PAIR_HEADLINES["EUR/USD"])

        # Determine distribution based on bias
        if label == "bullish":
            bullish_count = max(3, num_headlines - 2)
            bearish_count = max(1, num_headlines - bullish_count - 1)
            neutral_count = num_headlines - bullish_count - bearish_count
        elif label == "bearish":
            bearish_count = max(3, num_headlines - 2)
            bullish_count = max(1, num_headlines - bearish_count - 1)
            neutral_count = num_headlines - bearish_count - bullish_count
        else:
            neutral_count = max(2, num_headlines // 2)
            bullish_count = (num_headlines - neutral_count) // 2
            bearish_count = num_headlines - neutral_count - bullish_count

        # Select headlines
        selected = []
        selected.extend(random.sample(symbol_headlines["bullish"], min(bullish_count, len(symbol_headlines["bullish"]))))
        selected.extend(random.sample(symbol_headlines["bearish"], min(bearish_count, len(symbol_headlines["bearish"]))))
        selected.extend(random.sample(symbol_headlines["neutral"], min(neutral_count, len(symbol_headlines["neutral"]))))

        # Shuffle and limit
        random.shuffle(selected)
        selected = selected[:num_headlines]

        # Create headline objects
        for i, title in enumerate(selected):
            # Determine sentiment for this headline
            if title in symbol_headlines["bullish"]:
                sentiment = round(random.uniform(0.3, 0.9), 2)
            elif title in symbol_headlines["bearish"]:
                sentiment = round(random.uniform(-0.9, -0.3), 2)
            else:
                sentiment = round(random.uniform(-0.2, 0.2), 2)

            # Generate timestamp (more recent headlines first)
            minutes_ago = i * 45 + random.randint(0, 30)
            timestamp = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()

            headlines.append({
                "title": title,
                "source": random.choice(self.SOURCES),
                "sentiment": sentiment,
                "timestamp": timestamp,
                "url": None,  # Would be populated with real URLs
            })

        return headlines

    def _is_cache_valid(self) -> bool:
        if self._cache_time is None:
            return False
        return datetime.utcnow() - self._cache_time < self._cache_duration
