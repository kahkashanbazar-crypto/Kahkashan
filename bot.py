import telegram
import requests
import time

API_TOKEN = 'YOUR_TELEGRAM_BOT_API_TOKEN'
CHAT_ID = 'YOUR_TELEGRAM_CHAT_ID'
CRYPTO_API_URL = 'https://api.coingecko.com/api/v3/simple/price'  # Example API endpoint

# Function to get cryptocurrency price
def get_crypto_price(crypto='bitcoin'):
    response = requests.get(CRYPTO_API_URL, params={'ids': crypto, 'vs_currencies': 'usd'})
    price = response.json()[crypto]['usd']
    return price

# Function to send message via Telegram bot
def send_message(message):
    bot = telegram.Bot(token=API_TOKEN)
    bot.send_message(chat_id=CHAT_ID, text=message)

# Main function to check price and send updates
if __name__ == '__main__':
    while True:
        price = get_crypto_price('bitcoin')
        message = f'Current Bitcoin price: ${price}'
        send_message(message)
        time.sleep(600)  # Wait for 10 minutes before the next update