import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from binance.client import Client
from datetime import datetime, timedelta
import os
import statsmodels.api as sm
import time
from requests.exceptions import ReadTimeout
import math
import dotenv
import os


dotenv.load_dotenv()

# Inicializa el cliente de Binance
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
client = Client(api_key, api_secret, {'timeout': 60})

symbol = 'BTCFDUSD'  # símbolo a usar

# Obtener los filtros de Binance para el símbolo
symbol_info = client.get_symbol_info(symbol)
filters = {f['filterType']: f for f in symbol_info['filters']}
step_size = float(filters['LOT_SIZE']['stepSize'])
tick_size = float(filters['PRICE_FILTER']['tickSize'])
min_notional = float(filters['MIN_NOTIONAL']['minNotional']) if 'MIN_NOTIONAL' in filters else 0.0

#import pdb
#pdb.set_trace() 

def round_step(value, step):
    """Redondea un valor al múltiplo más cercano hacia abajo según step size."""
    return (math.floor(value / step)) * step

def format_price(value):
    """Formatea el precio al tick size con la cantidad correcta de decimales."""
    decimals = int(round(-math.log10(tick_size), 0))
    return format(round_step(value, tick_size), f'.{decimals}f')

def format_quantity(value):
    """Formatea la cantidad al step size con la cantidad correcta de decimales."""
    decimals = int(round(-math.log10(step_size), 0))
    return format(round_step(value, step_size), f'.{decimals}f')

# Obtener datos del balance
def get_balance(asset):
    try:
        balance = client.get_asset_balance(asset=asset)
        if balance and 'free' in balance:
            return float(balance['free'])
        return 0.0
    except Exception as e:
        print(f"Error al obtener balance de {asset}: {e}")
        return 0.0

def cancel_open_orders(symbol, order_type):
    retries = 5
    while retries > 0:
        try:
            open_orders = client.get_open_orders(symbol=symbol)
            for order in open_orders:
                if order['type'] == order_type:
                    try:
                        client.cancel_order(symbol=symbol, orderId=order['orderId'])
                        print(f"Orden {order_type} cancelada: {order['orderId']} ({order['side']})")
                    except Exception as cancel_error:
                        print(f"Error al cancelar la orden {order['orderId']}: {cancel_error}")
            return
        except ReadTimeout:
            print("ReadTimeout mientras se cancelaban órdenes. Reintentando...")
            retries -= 1
            time.sleep(5)
        except Exception as e:
            print(f"Error al obtener órdenes abiertas: {e}")
            retries -= 1
            time.sleep(5)
    print("No se pudieron cancelar las órdenes abiertas tras varios intentos.")

def get_trades_count():
    retries = 5
    while retries > 0:
        try:
            candles = client.get_klines(symbol='BTCFDUSD', interval='3m', limit=5)
            if candles and len(candles) >= 4:
                prof1 = int(candles[-4][8])
                prof2 = int(candles[-3][8])
                prof3 = int(candles[-2][8])
                #profpromedio = (prof3+prof2)/2
                #Difelastbase=74 #dolares
                #Ticksize=0.01
                #porcentajenivelesutiles=0.15 #porcentaje de niveles utilizados recomendado por chatgpt
                #Tradesprom=6283 #este valor puede ir ajustandose con el tiempo a mayores datos
                #nivelesposibles = int(Difelastbase / Ticksize)
                #nivelesutilizados = int(nivelesposibles * porcentajenivelesutiles)
                #tradesprompornivel = round(Tradesprom / nivelesutilizados, 2)
                limitausar = 1
                #limitausar = int(profpromedio * porcentajenivelesutiles)
                '''if profpromedio <= 1000:
                    limitausar = 900
                elif profpromedio >= 7000:
                    limitausar = 1100
                else:
                    limitausar = int(900 + (profpromedio - 1000) * (200 / 6000))'''
                close1 = float(candles[-4][4])
                close2 = float(candles[-3][4])
                close3 = float(candles[-2][4])
                #print(f"Close 1: {close1:.2f} Close 2: {close2:.2f} Close 3: {close3:.2f} limit a usar: {limitausar} profpromedio: {profpromedio}")
                return limitausar, [close1, close2, close3]
        except ReadTimeout:
            print("Timeout al obtener trades. Reintentando...")
            retries -= 1
            time.sleep(5)
        except Exception as e:
            print(f"Error al obtener trades: {e}")
            retries -= 1
            time.sleep(5)
    print("No se pudo obtener el número de trades. Usando valor por defecto (1000)")
    return 1000, []

def calcular_factor(decisiones, precios):
    factor1 = 1.0
    factor2 = 1.0
    if len(decisiones) < 2 or len(precios) < 3:
        return factor1, factor2
    tendencia = "ninguna"
    #print("Ninguna Tendencia")
    if precios[0] < precios[1] < precios[2]:
        tendencia = "subida"
        #print("Tendencia Alcista")
    elif precios[0] > precios[1] > precios[2]:
        tendencia = "bajada"
        #print("Tendencia Bajista")
    errores = 0
    for i in range(2):
        if decisiones[i] == 1 and tendencia == "bajada":
            errores += 1
        elif decisiones[i] == -1 and tendencia == "subida":
            errores += 1
    if errores >= 2:
        if tendencia == "subida":
            factor1 = 1 # este valor es modificable
        elif tendencia == "bajada":
            factor2 = 3 # este valor es modificable
    return factor1, factor2

def encontrarfactor3y4(score_alcistabase, score_bajistabase):
    factor3 = 1.0
    factor4 = 1.0
    
    if (score_alcistabase - score_bajistabase) < 300000 and score_alcistabase > score_bajistabase:
        factor4 = 3.0
    elif (score_bajistabase- score_alcistabase) < 300000 and score_bajistabase > score_alcistabase:
        factor3 = 3.0
    return factor3,factor4

def get_ticker_data(symbol):
    ticker = client.get_ticker(symbol=symbol)
    lastPrice = float(ticker['lastPrice'])
    askPrice = float(ticker['askPrice'])
    bidPrice = float(ticker['bidPrice'])
    hora_actual = datetime.now()
    data = {
        "hora_actual": [hora_actual],
        "lastPrice": [lastPrice]
    }
    df = pd.DataFrame(data)
    return df, lastPrice, hora_actual

decisiones_previas = []
def decide_and_trade(symbol='BTCFDUSD'):
    global decisiones_previas
    retries = 5
    score_alcista = 0
    score_bajista = 0
        
    #Recuperar valores guardados de la vez pasada
    
    static_vars = decide_and_trade.__dict__
    last_decision = static_vars.get("last_decision", None)
    last_price = static_vars.get("last_price", None)
    # **Inicializamos localmente `lastPrice` para evitar UnboundLocalError**
    lastPrice = static_vars.get("lastPrice", None)
    # inicializamos `decision` para evitar NameError si llega a usarse al final
    decision = None
    hora_actual = None
    if "prev_score_alcista" not in static_vars:
        static_vars["prev_score_alcista"] = None
    if "prev_score_bajista" not in static_vars:
        static_vars["prev_score_bajista"] = None
    prev_score_alcista = static_vars["prev_score_alcista"]
    prev_score_bajista = static_vars["prev_score_bajista"]
    df_ticker = pd.DataFrame()  # inicializar vacío
    while retries > 0:
        try:
            # Obtener profundidad dinámica basada en los trades
            #limitausar, ultimos_precios = get_trades_count()
            order_book = client.get_order_book(symbol=symbol, limit=1000)
            #n_bids = max(int(limitausar * 0.83), 10) #el 0.83 es modificable
            #bids = [(float(price), float(qty)) for price, qty in order_book['bids'][:n_bids]]
            bids = [(float(price), float(qty)) for price, qty in order_book['bids']]
            asks = [(float(price), float(qty)) for price, qty in order_book['asks']]
            #factor1, factor2 = calcular_factor(decisiones_previas[-2:], ultimos_precios)
            score_alcistabase = sum(price * qty for price, qty in bids)
            score_bajistabase = sum(price * qty for price, qty in asks)
            df_ticker, lastPrice, hora_actual = get_ticker_data(symbol)
            # -------------------------
            # NUEVAS COLUMNAS
            # -------------------------
            # DeltaScore
            deltascore = score_alcistabase - score_bajistabase
            df_ticker["deltascore"] = deltascore
            columnas_fijas = ["Aciertos", "deltascore", "aciertosdeltascorecompra","aciertosdeltascoreventa"]
            for col in columnas_fijas:
                if col not in df_ticker.columns:
                    df_ticker[col] = 0  # Todo arranca en 0 para evitar None
            # Aciertos
            
            acierto = None
            
            if last_decision is not None and last_price is not None and lastPrice is not None:
                if last_decision == 1:   # predije subida
                    acierto = 1 if float(lastPrice) > float(last_price) else -1
                elif last_decision == -1: # predije bajada
                    acierto = 1 if float(lastPrice) < float(last_price) else -1
            else:
                acierto = 0 # primera vez, no hay cómo medirlo

            aciertosinfactorcompra = 0
            aciertosinfactorventa = 0
            if last_price is not None and lastPrice is not None and prev_score_alcista is not None and prev_score_bajista is not None:
                if prev_score_alcista>prev_score_bajista and deltascore < 500000:   # predije subida
                    aciertosinfactorcompra = 1 if float(lastPrice) > float(last_price) else -1
                elif prev_score_bajista>prev_score_alcista and abs(deltascore) < 500000: # predije bajada
                    aciertosinfactorventa = 1 if float(lastPrice) < float(last_price) else -1
                      
            factor5 = 1
            file_path = 'Esperanza3minBTCFDUSDLIBRO.csv'
            # Solo evaluar factor5 si el deltascore actual es < 500000
            if deltascore < 500000 and os.path.exists(file_path) and score_alcistabase>score_bajistabase:
                try:
                    df_hist = pd.read_csv(file_path)
                    if "aciertosinfactorcompra" in df_hist.columns and len(df_hist) >= 3:
                        ultimos3compra = df_hist["aciertosinfactorcompra"].tail(3).mean()
                        if ultimos3compra < 0:
                            factor5 = 3
                except Exception as e:
                    print(f"Error leyendo historial para factor5: {e}")
            
            
                      
            factor6 = 1
            file_path = 'Esperanza3minBTCFDUSDLIBRO.csv'
            # Solo evaluar factor5 si el deltascore actual es < 500000
            if abs(deltascore) < 500000 and os.path.exists(file_path) and score_bajistabase>score_alcistabase:
                try:
                    df_hist = pd.read_csv(file_path)
                    if "aciertosinfactorventa" in df_hist.columns and len(df_hist) >= 3:
                        ultimos3venta = df_hist["aciertosinfactorventa"].tail(3).mean()
                        if ultimos3venta < 0:
                            factor6 = 3
                except Exception as e:
                    print(f"Error leyendo historial para factor5: {e}")
            
            
            
            score_alcista = score_alcistabase#*factor6#*factor3#*factor1 
            score_bajista = score_bajistabase*factor5#factor2#*factor4
            btc_balance = get_balance('BTC')
            fdusd_balance = get_balance('FDUSD')
            btc_total_value = (btc_balance * lastPrice) + fdusd_balance
            print(f"Balance BTC: {btc_balance:.8f}, FDUSD: {fdusd_balance:.2f}, Valor total (FDUSD): {btc_total_value:.2f}")
            print(f"Score Alcista: {score_alcista:.2f}, Score Bajista: {score_bajista:.2f}")
            df_ticker, lastPrice, hora_actual = get_ticker_data(symbol)         
            # Ajustar precios con tick size
            adjusted_priceventa = format_price(lastPrice - 0.040)
            adjusted_pricecompra = format_price(lastPrice + 0.040)
            adjusted_stoppriceventa = format_price(lastPrice - 0.035)
            adjusted_stoppricecompra = format_price(lastPrice + 0.035)

            order_placed = False

            # Predicción bajista
            if score_alcista < score_bajista:
                if fdusd_balance > 100:
                    print("Predicción: precio bajará, manteniendo FDUSD.")
                    #df_ticker["factor2"]=factor2
                    df_ticker["factor5"]=factor5
                    df_ticker["factor6"]=factor6
                    df_ticker["score_alcistabase"] = score_alcistabase
                    df_ticker["score_bajistabase"] = score_bajistabase
                    #df_ticker["limitausar"] = limitausar
                    df_ticker["valor_total_fdusd"] = btc_total_value
                    df_ticker["Decisión"] = -1
                    '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                        decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                        if len(decisiones_previas) > 2:
                            decisiones_previas.pop(0)
                        print("Últimas 2 decisiones previas:", decisiones_previas)'''
                    df_ticker["Aciertos"] = acierto if acierto is not None else 0
                    df_ticker["deltascore"] = deltascore
                    df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                    df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                    # Guardar valores para la próxima vela
                    static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                    static_vars["last_price"] = lastPrice
                    static_vars["prev_score_alcista"] = score_alcistabase
                    static_vars["prev_score_bajista"] = score_bajistabase
                    return df_ticker
                else:
                    quantity_raw = btc_balance
                    quantity = float(format_quantity(quantity_raw))
                    if quantity >= step_size and (quantity * lastPrice) >= min_notional:
                        try:
                            client.create_order(
                                symbol=symbol,
                                side='SELL',
                                type='STOP_LOSS_LIMIT',
                                quantity=format_quantity(quantity),
                                price=adjusted_priceventa,
                                stopPrice=adjusted_stoppriceventa,
                                timeInForce='GTC'
                            )
                            print(f"Orden de venta STOP_LOSS_LIMIT colocada: {quantity} BTC, stopPrice={adjusted_stoppriceventa}, price={adjusted_priceventa}")
                            #df_ticker["factor2"]=factor2
                            df_ticker["factor5"]=factor5
                            df_ticker["factor6"]=factor6
                            df_ticker["score_alcistabase"] = score_alcistabase
                            df_ticker["score_bajistabase"] = score_bajistabase
                            #df_ticker["limitausar"] = limitausar
                            df_ticker["valor_total_fdusd"] = btc_total_value
                            df_ticker["Decisión"] = -1
                            '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                                decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                                if len(decisiones_previas) > 2:
                                    decisiones_previas.pop(0)
                                print("Últimas 2 decisiones previas:", decisiones_previas)'''
                            # Guardar valores para la próxima vela
                            static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                            static_vars["last_price"] = lastPrice
                            static_vars["prev_score_alcista"] = score_alcistabase
                            static_vars["prev_score_bajista"] = score_bajistabase
                            df_ticker["Aciertos"] = acierto if acierto is not None else 0
                            df_ticker["deltascore"] = deltascore
                            df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                            df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                            return df_ticker
                        except Exception as e:
                            print(f"Error al colocar orden de venta: {e}")
                            order_placed = True

            # Predicción alcista
            else:
                if btc_balance > 0.001:
                    print("Predicción: precio subirá, manteniendo BTC.")
                    #df_ticker["factor2"]=factor2
                    df_ticker["factor5"]=factor5
                    df_ticker["factor6"]=factor6
                    df_ticker["score_alcistabase"] = score_alcistabase
                    df_ticker["score_bajistabase"] = score_bajistabase
                    #df_ticker["limitausar"] = limitausar
                    df_ticker["valor_total_fdusd"] = btc_total_value
                    # Guardar valores para la próxima vela
                    static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                    static_vars["last_price"] = lastPrice
                    df_ticker["Decisión"] = 1
                    '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                        decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                        if len(decisiones_previas) > 2:
                            decisiones_previas.pop(0)
                        print("Últimas 2 decisiones previas:", decisiones_previas)'''
                    df_ticker["Aciertos"] = acierto if acierto is not None else 0
                    df_ticker["deltascore"] = deltascore
                    df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                    df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                    # Guardar valores para la próxima vela
                    static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                    static_vars["last_price"] = lastPrice
                    static_vars["prev_score_alcista"] = score_alcistabase
                    static_vars["prev_score_bajista"] = score_bajistabase
                    return df_ticker
                else:
                    max_quantity_raw = fdusd_balance / lastPrice
                    quantity = float(format_quantity(max_quantity_raw))
                    notional = quantity * lastPrice
                    if quantity >= step_size and notional >= min_notional:
                        try:
                            client.create_order(
                                symbol=symbol,
                                side='BUY',
                                type='STOP_LOSS_LIMIT',
                                quantity=format_quantity(quantity),
                                price=adjusted_pricecompra,
                                stopPrice=adjusted_stoppricecompra,
                                timeInForce='GTC'
                            )
                            print(f"Orden de compra STOP_LOSS_LIMIT colocada: {quantity} BTC, stopPrice={adjusted_stoppricecompra}, price={adjusted_pricecompra}")
                            #df_ticker["factor2"]=factor2
                            df_ticker["factor5"]=factor5
                            df_ticker["factor6"]=factor6
                            df_ticker["score_alcistabase"] = score_alcistabase
                            df_ticker["score_bajistabase"] = score_bajistabase
                            #df_ticker["limitausar"] = limitausar
                            df_ticker["valor_total_fdusd"] = btc_total_value
                            df_ticker["Decisión"] = 1
                            '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                                decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                                if len(decisiones_previas) > 2:
                                    decisiones_previas.pop(0)
                                print("Últimas 2 decisiones previas:", decisiones_previas)'''
                            df_ticker["Aciertos"] = acierto if acierto is not None else 0
                            df_ticker["deltascore"] = deltascore
                            df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                            df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                            # Guardar valores para la próxima vela
                            static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                            static_vars["last_price"] = lastPrice
                            static_vars["prev_score_alcista"] = score_alcistabase
                            static_vars["prev_score_bajista"] = score_bajistabase
                            return df_ticker
                        except Exception as e:
                            print(f"Error al colocar orden de compra: {e}")
                            order_placed = True

            # Reintento si hubo error
            if order_placed:
                for intento in range(20):
                    print(f"Intento {intento + 1}: Recalculando precios y cantidades para reintentar orden a las {datetime.now().strftime('%H:%M:%S')}")
                    
                    btc_balance = get_balance('BTC')
                    fdusd_balance = get_balance('FDUSD')
                    df_ticker, lastPrice, hora_actual = get_ticker_data(symbol)

                    adjusted_priceventa = format_price(lastPrice - 0.040)
                    adjusted_pricecompra = format_price(lastPrice + 0.040)
                    adjusted_stoppriceventa = format_price(lastPrice - 0.035)
                    adjusted_stoppricecompra = format_price(lastPrice + 0.035)

                    if score_alcista < score_bajista:
                        quantity_raw = btc_balance
                        quantity = float(format_quantity(quantity_raw))
                        if quantity >= step_size and (quantity * lastPrice) >= min_notional:
                            try:
                                client.create_order(
                                    symbol=symbol,
                                    side='SELL',
                                    type='STOP_LOSS_LIMIT',
                                    quantity=format_quantity(quantity),
                                    price=adjusted_priceventa,
                                    stopPrice=adjusted_stoppriceventa,
                                    timeInForce='GTC'
                                )
                                print(f"Venta SL reintentada: {quantity} BTC a {adjusted_priceventa}")
                                order_placed = False
                                #df_ticker["factor2"]=factor2
                                df_ticker["factor5"]=factor5
                                df_ticker["factor6"]=factor6
                                df_ticker["score_alcistabase"] = score_alcistabase
                                df_ticker["score_bajistabase"] = score_bajistabase
                                #df_ticker["limitausar"] = limitausar
                                df_ticker["valor_total_fdusd"] = btc_total_value
                                df_ticker["Decisión"] = -1
                                '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                                    decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                                    if len(decisiones_previas) > 2:
                                        decisiones_previas.pop(0)
                                    print("Últimas 2 decisiones previas:", decisiones_previas)'''
                                df_ticker["Aciertos"] = acierto if acierto is not None else 0
                                df_ticker["deltascore"] = deltascore
                                df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                                df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                                # Guardar valores para la próxima vela
                                static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                                static_vars["last_price"] = lastPrice
                                static_vars["prev_score_alcista"] = score_alcistabase
                                static_vars["prev_score_bajista"] = score_bajistabase
                                return df_ticker
                            except Exception as e:
                                print(f"Error al reintentar venta: {e}")
                    else:
                        max_quantity_raw = fdusd_balance / lastPrice
                        quantity = float(format_quantity(max_quantity_raw))
                        notional = quantity * lastPrice
                        if quantity >= step_size and notional >= min_notional:
                            try:
                                client.create_order(
                                    symbol=symbol,
                                    side='BUY',
                                    type='STOP_LOSS_LIMIT',
                                    quantity=format_quantity(quantity),
                                    price=adjusted_pricecompra,
                                    stopPrice=adjusted_stoppricecompra,
                                    timeInForce='GTC'
                                )
                                print(f"Compra SL reintentada: {quantity} BTC a {adjusted_pricecompra}")
                                order_placed = False
                                #df_ticker["factor2"]=factor2
                                df_ticker["factor5"]=factor5
                                df_ticker["factor6"]=factor6
                                df_ticker["score_alcistabase"] = score_alcistabase
                                df_ticker["score_bajistabase"] = score_bajistabase
                                #df_ticker["limitausar"] = limitausar
                                df_ticker["valor_total_fdusd"] = btc_total_value
                                df_ticker["Decisión"] = 1
                                '''if "Decisión" in df_ticker.columns and not df_ticker.empty:
                                    decisiones_previas.append(df_ticker["Decisión"].iloc[0])
                                    if len(decisiones_previas) > 2:
                                        decisiones_previas.pop(0)
                                    print("Últimas 2 decisiones previas:", decisiones_previas)'''
                                df_ticker["Aciertos"] = acierto if acierto is not None else 0
                                df_ticker["deltascore"] = deltascore
                                df_ticker["aciertosinfactorcompra"] = aciertosinfactorcompra
                                df_ticker["aciertosinfactorventa"] = aciertosinfactorventa
                                # Guardar valores para la próxima vela
                                static_vars["last_decision"] = df_ticker["Decisión"].iloc[0] if "Decisión" in df_ticker else None
                                static_vars["last_price"] = lastPrice
                                static_vars["prev_score_alcista"] = score_alcistabase
                                static_vars["prev_score_bajista"] = score_bajistabase
                                return df_ticker
                            except Exception as e:
                                print(f"Error al reintentar compra: {e}")
                          
            #decide_and_trade.last_price = lastPrice    # precio actual guardado como referencia
            #decide_and_trade.last_decision = decision  # decisión que tomaste
            #decide_and_trade.lastPrice = lastPrice     # también conservas el último precio leído
        
        except ReadTimeout:
            print("ReadTimeout. Reintentando...")
            retries -= 1
            time.sleep(3)
        except Exception as e:
            print(f"Error inesperado: {e}")
            retries -= 1
            time.sleep(3)
    return df_ticker

def wait_until_next_candle():
    now = datetime.utcnow()
    next_candle = (now + timedelta(minutes=(3 - now.minute % 3))).replace(second=0, microsecond=0)
    wait_time = (next_candle - now).total_seconds()
    return wait_time if wait_time > 0 else 0

def main():
    file_path = 'Esperanza3minBTCFDUSDLIBRO.csv'
    
    while True:
        cancel_open_orders(symbol=symbol, order_type='STOP_LOSS_LIMIT')
        df_ticker = decide_and_trade(symbol=symbol)
        df_ticker.to_csv(file_path, mode='a', header=not os.path.exists(file_path), index=False)
        
        wait_time = wait_until_next_candle()
        time.sleep(wait_time)

if __name__ == "__main__":
    main()
