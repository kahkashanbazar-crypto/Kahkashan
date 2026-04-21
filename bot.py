import os
import requests
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
from collections import deque
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve environment variables
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID', '')

# Validate environment variables
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in environment variables")

# Configuration constants
COINGECKO_BASE_URL: str = 'https://api.coingecko.com/api/v3'
CRYPTOS: List[str] = ['bitcoin', 'binancecoin', 'solana']  # BTC, BNB, SOL
CRYPTO_IDS: Dict[str, str] = {
    'bitcoin': 'BTC',
    'binancecoin': 'BNB',
    'solana': 'SOL'
}
RSI_PERIOD: int = 14
MA_PERIODS: tuple = (10, 20)
MAX_PRICE_HISTORY: int = 100

# Retry configuration
MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 2.0  # seconds
MAX_RETRY_DELAY: float = 32.0  # seconds

# Setup logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class CryptoPriceTracker:
    """Tracks price history for technical analysis."""
    
    def __init__(self, max_size: int = MAX_PRICE_HISTORY) -> None:
        """Initialize price tracker with a deque for efficient history management."""
        self.price_history: Dict[str, deque] = {
            crypto: deque(maxlen=max_size) for crypto in CRYPTOS
        }
    
    def add_price(self, crypto: str, price: float) -> None:
        """Add a price point to the history for a specific crypto."""
        if crypto in self.price_history:
            self.price_history[crypto].append(price)
    
    def get_history(self, crypto: str) -> List[float]:
        """Get price history for a specific crypto."""
        return list(self.price_history.get(crypto, []))
    
    def has_sufficient_history(self, crypto: str, min_points: int = RSI_PERIOD) -> bool:
        """Check if we have enough price history for technical analysis."""
        return len(self.price_history.get(crypto, [])) >= min_points


class TechnicalAnalyzer:
    """Calculates technical indicators for trading signals."""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = RSI_PERIOD) -> Optional[float]:
        """Calculate Relative Strength Index (RSI)."""
        if len(prices) < period + 1:
            return None
        
        # Calculate price changes
        deltas: List[float] = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains: List[float] = [d if d > 0 else 0 for d in deltas]
        losses: List[float] = [-d if d < 0 else 0 for d in deltas]
        
        # Calculate average gain and loss over the period
        avg_gain: float = sum(gains[-period:]) / period
        avg_loss: float = sum(losses[-period:]) / period
        
        # Avoid division by zero
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 0.0
        
        # Calculate RS and RSI
        rs: float = avg_gain / avg_loss
        rsi: float = 100 - (100 / (1 + rs))
        
        logger.debug(f"RSI calculated: {rsi:.2f}")
        return rsi
    
    @staticmethod
    def calculate_moving_average(prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average (SMA)."""
        if len(prices) < period:
            return None
        
        ma: float = sum(prices[-period:]) / period
        logger.debug(f"MA{period} calculated: {ma:.2f}")
        return ma
    
    @staticmethod
    def calculate_all_indicators(prices: List[float]) -> Dict[str, Optional[float]]:
        """Calculate all technical indicators for a price series."""
        return {
            'RSI': TechnicalAnalyzer.calculate_rsi(prices, RSI_PERIOD),
            'MA10': TechnicalAnalyzer.calculate_moving_average(prices, 10),
            'MA20': TechnicalAnalyzer.calculate_moving_average(prices, 20),
            'current_price': prices[-1] if prices else None
        }


class SignalGenerator:
    """Generates trading signals based on technical indicators."""
    
    @staticmethod
    def generate_signal(indicators: Dict[str, Optional[float]]) -> str:
        """Generate a trading signal based on technical indicators."""
        rsi: Optional[float] = indicators.get('RSI')
        ma10: Optional[float] = indicators.get('MA10')
        current_price: Optional[float] = indicators.get('current_price')
        
        # Ensure all required indicators are available
        if rsi is None or ma10 is None or current_price is None:
            return 'NO TRADE'
        
        # BUY Signal: Oversold (RSI < 30) with uptrend confirmation
        if rsi < 30 and current_price > ma10:
            logger.info(f"BUY Signal Generated - RSI: {rsi:.2f}, Price: {current_price:.2f}, MA10: {ma10:.2f}")
            return 'BUY'
        
        # SELL Signal: Overbought (RSI > 70) with downtrend confirmation
        if rsi > 70 and current_price < ma10:
            logger.info(f"SELL Signal Generated - RSI: {rsi:.2f}, Price: {current_price:.2f}, MA10: {ma10:.2f}")
            return 'SELL'
        
        # No trade signal
        logger.debug(f"No trade - RSI: {rsi:.2f}, Price: {current_price:.2f}, MA10: {ma10:.2f}")
        return 'NO TRADE'


class TelegramNotifier:
    """Handles sending messages and signals to Telegram."""
    
    @staticmethod
    def send_message(message: str, max_retries: int = MAX_RETRIES) -> bool:
        """Send a message to Telegram chat with retry logic and exponential backoff."""
        url: str = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        payload: Dict[str, str] = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        # Retry logic with exponential backoff
        retry_delay: float = BASE_RETRY_DELAY
        
        for attempt in range(1, max_retries + 1):
            try:
                response: requests.Response = requests.post(
                    url,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info(f"Message sent to Telegram: {message[:50]}...")
                    return True
                else:
                    logger.warning(f"Telegram error (attempt {attempt}/{max_retries}): Status {response.status_code}")
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request exception (attempt {attempt}/{max_retries}): {str(e)}")
            
            # Wait before retrying (exponential backoff)
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        
        logger.error(f"Failed to send message after {max_retries} attempts: {message[:50]}...")
        return False
    
    @staticmethod
    def send_signal(crypto: str, signal: str, indicators: Dict[str, Optional[float]]) -> bool:
        """Send a formatted trading signal to Telegram."""
        crypto_symbol: str = CRYPTO_IDS.get(crypto, crypto.upper())
        current_price: Optional[float] = indicators.get('current_price')
        rsi: Optional[float] = indicators.get('RSI')
        ma10: Optional[float] = indicators.get('MA10')
        ma20: Optional[float] = indicators.get('MA20')
        
        # Format signal emoji based on signal type
        emoji: str = '📈' if signal == 'BUY' else '📉' if signal == 'SELL' else '⏸️'
        
        # Build formatted message with proper newline escaping for Telegram
        message: str = (
            f"{emoji} <b>Trading Signal: {signal}</b>\n\n"
            f"<b>Asset:</b> {crypto_symbol}\n"
            f"<b>Price:</b> ${current_price:.2f}\n"
            f"<b>RSI(14):</b> {rsi:.2f}\n"
            f"<b>MA(10):</b> ${ma10:.2f}\n"
            f"<b>MA(20):</b> ${ma20:.2f}\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return TelegramNotifier.send_message(message)


class CryptoAPIClient:
    """Handles all API calls to CoinGecko for price data."""
    
    @staticmethod
    def fetch_current_prices(max_retries: int = MAX_RETRIES) -> Optional[Dict[str, float]]:
        """Fetch current cryptocurrency prices from CoinGecko with retry logic."""
        url: str = f'{COINGECKO_BASE_URL}/simple/price'
        params: Dict[str, str] = {
            'ids': ','.join(CRYPTOS),
            'vs_currencies': 'usd'
        }
        
        # Retry logic with exponential backoff
        retry_delay: float = BASE_RETRY_DELAY
        
        for attempt in range(1, max_retries + 1):
            try:
                response: requests.Response = requests.get(
                    url,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data: Dict = response.json()
                    # Extract prices from response
                    prices: Dict[str, float] = {}
                    for crypto in CRYPTOS:
                        if crypto in data and 'usd' in data[crypto]:
                            prices[crypto] = data[crypto]['usd']
                    
                    if prices:
                        logger.info(f"Prices fetched successfully: {prices}")
                        return prices
                
                logger.warning(f"CoinGecko error (attempt {attempt}/{max_retries}): Status {response.status_code}")
            
            except (ValueError, KeyError) as e:
                logger.warning(f"JSON parsing error (attempt {attempt}/{max_retries}): {str(e)}")
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request exception (attempt {attempt}/{max_retries}): {str(e)}")
            
            # Wait before retrying (exponential backoff)
            if attempt < max_retries:
                logger.info(f"Retrying price fetch in {retry_delay:.1f} seconds...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        
        logger.error(f"Failed to fetch prices after {max_retries} attempts")
        return None


class CryptoTradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self, update_interval: int = 60) -> None:
        """Initialize the trading bot."""
        self.update_interval: int = update_interval
        self.price_tracker: CryptoPriceTracker = CryptoPriceTracker()
        self.analyzer: TechnicalAnalyzer = TechnicalAnalyzer()
        self.signal_generator: SignalGenerator = SignalGenerator()
        self.notifier: TelegramNotifier = TelegramNotifier()
        self.api_client: CryptoAPIClient = CryptoAPIClient()
        
        logger.info(f"Crypto Trading Bot initialized with {update_interval}s update interval")
    
    def process_crypto(self, crypto: str, price: float) -> None:
        """Process a single cryptocurrency: calculate indicators and generate signals."""
        # Add price to history
        self.price_tracker.add_price(crypto, price)
        
        # Check if we have sufficient history for analysis
        if not self.price_tracker.has_sufficient_history(crypto):
            logger.info(f"Insufficient price history for {crypto} - collecting more data")
            return
        
        # Get price history and calculate indicators
        prices: List[float] = self.price_tracker.get_history(crypto)
        indicators: Dict[str, Optional[float]] = self.analyzer.calculate_all_indicators(prices)
        
        # Generate trading signal
        signal: str = self.signal_generator.generate_signal(indicators)
        
        # Send signal to Telegram if it's not 'NO TRADE'
        if signal != 'NO TRADE':
            self.notifier.send_signal(crypto, signal, indicators)
    
    def run(self) -> None:
        """Main bot loop: continuously fetch prices and process trading signals."""
        logger.info("Starting crypto trading bot main loop...")
        
        iteration: int = 0
        
        while True:
            try:
                iteration += 1
                logger.info(f"\n--- Iteration {iteration} ---")
                logger.info(f"Fetching prices at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Fetch current prices from CoinGecko
                prices: Optional[Dict[str, float]] = self.api_client.fetch_current_prices()
                
                if prices is None:
                    logger.error("Failed to fetch prices - will retry in next interval")
                    time.sleep(self.update_interval)
                    continue
                
                # Process each cryptocurrency
                for crypto, price in prices.items():
                    logger.info(f"Processing {CRYPTO_IDS.get(crypto, crypto.upper())}: ${price:.2f}")
                    self.process_crypto(crypto, price)
                
                # Wait for next update
                logger.info(f"Waiting {self.update_interval}s until next update...")
                time.sleep(self.update_interval)
            
            except KeyboardInterrupt:
                logger.info("Bot interrupted by user - shutting down gracefully")
                break
            
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {str(e)}", exc_info=True)
                time.sleep(self.update_interval)


def main() -> None:
    """Entry point for the crypto trading bot application."""
    logger.info("=" * 58)
    logger.info("CRYPTO TRADING BOT - STARTUP")
    logger.info("=" * 58)
    logger.info(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    logger.info(f"Monitoring: {', '.join(CRYPTO_IDS.values())}")
    logger.info(f"RSI Period: {RSI_PERIOD}")
    logger.info(f"MA Periods: {MA_PERIODS}")
    logger.info("=" * 58)
    
    # Create and run bot
    bot: CryptoTradingBot = CryptoTradingBot(update_interval=60)
    bot.run()


if __name__ == '__main__':
    main()