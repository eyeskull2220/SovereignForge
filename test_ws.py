import asyncio  
import websockets  
import time  
  
async def test():  
    try:  
        print('Testing Binance WebSocket...')  
        uri = 'wss://stream.binance.com:9443/ws'  
        async with websockets.connect(uri) as ws:  
            print('Connected!')  
            ping_msg = '{"ping": ' + str(int(time.time() * 1000)) + '}'  
            await ws.send(ping_msg)  
            response = await ws.recv()  
            print(f'Response: {response}')  
    except Exception as e:  
        print(f'Error: {e}')  
  
asyncio.run(test()) 
