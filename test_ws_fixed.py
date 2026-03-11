import asyncio  
import websockets  
import time  
import json  
  
async def test():  
    try:  
        print('Testing Binance WebSocket...')  
        uri = 'wss://stream.binance.com:9443/ws'  
        async with websockets.connect(uri) as ws:  
            print('Connected!')  
            # Send proper ping  
            ping_msg = json.dumps({"ping": int(time.time() * 1000)})  
            await ws.send(ping_msg)  
            print(f'Sent: {ping_msg}')  
            response = await ws.recv()  
            print(f'Response: {response}')  
            # Subscribe to ticker  
            sub_msg = json.dumps({  
                "method": "SUBSCRIBE",  
                "params": ["btcusdt@ticker"],  
                "id": 1  
            })  
            await ws.send(sub_msg)  
            print(f'Subscribed to BTC ticker')  
            # Receive a few messages  
            for i in range(3):  
                msg = await ws.recv()  
                print(f'Message {i+1}: {msg[:200]}...')  
    except Exception as e:  
        print(f'Error: {e}')  
  
asyncio.run(test()) 
