import asyncio
import websockets
import time
import json

async def test():
    try:
        print('Testing Binance WebSocket...')
        # Use the correct URI for raw streams
        uri = 'wss://stream.binance.com:9443/ws/btcusdt@ticker'
        async with websockets.connect(uri) as ws:
            print('Connected!')
            # Receive ticker messages (no subscription needed for single stream)
            for i in range(5):
                msg = await ws.recv()
                data = json.loads(msg)
                if 'stream' in data and '@ticker' in data['stream']:
                    ticker = data['data']
                    print(f'📊 BTC/USDT: ${ticker["c"]} (vol: {ticker["v"]})')
                else:
                    print(f'Message {i+1}: {msg[:200]}...')
                await asyncio.sleep(1)  # Rate limit
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test())
