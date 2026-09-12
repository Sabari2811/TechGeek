from pathlib import Path
from datetime import time
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent.parent
app = FastAPI(title="PulseTrade – NIFTY Intraday Price Action Bot", version="2.0.0")
app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')

TRADE_START = time(9, 30)
TRADE_CUTOFF = time(15, 15)
FORCE_EXIT = time(15, 10)


def in_trade_window(ts) -> bool:
    t = pd.Timestamp(ts).time()
    return TRADE_START <= t < TRADE_CUTOFF


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.columns = [str(c).lower().strip() for c in d.columns]
    required = {'open','high','low','close','volume'}
    if not required.issubset(d.columns):
        raise ValueError(f"CSV needs columns: {', '.join(sorted(required))}")
    if not isinstance(d.index, pd.DatetimeIndex):
        d.index = pd.to_datetime(d.index)
    d = d.sort_index()
    d['ema9'] = d['close'].ewm(span=9, adjust=False).mean()
    d['ema21'] = d['close'].ewm(span=21, adjust=False).mean()
    typical = (d['high'] + d['low'] + d['close']) / 3
    session = d.index.normalize()
    vol_cum = d['volume'].groupby(session).cumsum()
    pv_cum = (typical * d['volume']).groupby(session).cumsum()
    d['vwap'] = pv_cum / vol_cum.replace(0, np.nan)
    daily = d.groupby(session).agg(day_high=('high','max'), day_low=('low','min'))
    prev = daily.shift(1)
    d['prev_resistance'] = session.map(prev['day_high'])
    d['prev_support'] = session.map(prev['day_low'])
    d['in_window'] = d.index.map(in_trade_window)
    return d


def candle_price_action(row, prev=None):
    body = abs(row.close-row.open)
    rng = max(row.high-row.low, 1e-9)
    upper = row.high-max(row.open,row.close)
    lower = min(row.open,row.close)-row.low
    close_pos = (row.close-row.low)/rng
    bull_pin = lower >= max(body*2, rng*0.45) and close_pos >= 0.60
    bear_pin = upper >= max(body*2, rng*0.45) and close_pos <= 0.40
    if prev is not None:
        bull_engulf = (prev.close < prev.open and row.close > row.open and
                       row.open <= prev.close and row.close >= prev.open)
        bear_engulf = (prev.close > prev.open and row.close < row.open and
                       row.open >= prev.close and row.close <= prev.open)
        if bull_engulf: return 'bullish_engulfing'
        if bear_engulf: return 'bearish_engulfing'
    if bull_pin: return 'bullish_pin_bar'
    if bear_pin: return 'bearish_pin_bar'
    return 'none'


def spot_bias(df15: pd.DataFrame):
    d = add_indicators(df15)
    if len(d) < 22:
        return {'bias':'WAIT','score':0,'reasons':['Need 22+ 15M candles']}
    r, p = d.iloc[-1], d.iloc[-2]
    score_long = score_short = 0
    rl, rs = [], []
    pa = candle_price_action(r,p)
    if r.ema9 > r.ema21: score_long += 2; rl.append('15M 9 EMA > 21 EMA')
    if r.ema9 < r.ema21: score_short += 2; rs.append('15M 9 EMA < 21 EMA')
    if r.close > r.vwap: score_long += 1; rl.append('15M price > VWAP')
    if r.close < r.vwap: score_short += 1; rs.append('15M price < VWAP')
    if pd.notna(r.prev_resistance) and r.close > r.prev_resistance: score_long += 2; rl.append('15M broke previous resistance')
    if pd.notna(r.prev_support) and r.close < r.prev_support: score_short += 2; rs.append('15M broke previous support')
    if pa in ('bullish_engulfing','bullish_pin_bar'): score_long += 2; rl.append(pa.replace('_',' '))
    if pa in ('bearish_engulfing','bearish_pin_bar'): score_short += 2; rs.append(pa.replace('_',' '))
    if r.close > r.ema9 and p.low <= p.ema9 <= p.high: score_long += 1; rl.append('15M EMA9 reclaim')
    if r.close < r.ema9 and p.low <= p.ema9 <= p.high: score_short += 1; rs.append('15M EMA9 rejection')
    if score_long >= 5 and score_long > score_short: return {'bias':'BULLISH','score':score_long,'reasons':rl}
    if score_short >= 5 and score_short > score_long: return {'bias':'BEARISH','score':score_short,'reasons':rs}
    return {'bias':'WAIT','score':max(score_long,score_short),'reasons':rl if score_long >= score_short else rs}


def entry_signal(df: pd.DataFrame, bias: str):
    d = add_indicators(df)
    if len(d) < 22: return {'signal':'WAIT','score':0,'reasons':['Need 22+ candles']}
    r, p = d.iloc[-1], d.iloc[-2]
    if not in_trade_window(r.name):
        return {'signal':'FLAT','score':0,'reasons':['Outside 09:30–15:15 trading window']}
    pa = candle_price_action(r,p)
    bull = bear = 0; rb=[]; rs=[]
    if bias == 'BULLISH': bull += 2; rb.append('15M bias bullish')
    if bias == 'BEARISH': bear += 2; rs.append('15M bias bearish')
    if r.ema9 > r.ema21 and r.close > r.vwap: bull += 2; rb.append('EMA/VWAP bullish alignment')
    if r.ema9 < r.ema21 and r.close < r.vwap: bear += 2; rs.append('EMA/VWAP bearish alignment')
    if pa in ('bullish_engulfing','bullish_pin_bar'): bull += 2; rb.append(pa.replace('_',' '))
    if pa in ('bearish_engulfing','bearish_pin_bar'): bear += 2; rs.append(pa.replace('_',' '))
    if r.close > p.high: bull += 2; rb.append('price-action high breakout')
    if r.close < p.low: bear += 2; rs.append('price-action low breakdown')
    if r.close > r.ema9 and p.low <= r.ema9 <= p.high: bull += 1; rb.append('EMA9 pullback/reclaim')
    if r.close < r.ema9 and p.low <= r.ema9 <= p.high: bear += 1; rs.append('EMA9 pullback/rejection')
    if bull >= 6 and bull > bear: return {'signal':'BUY_CALL','score':bull,'reasons':rb}
    if bear >= 6 and bear > bull: return {'signal':'BUY_PUT','score':bear,'reasons':rs}
    return {'signal':'WAIT','score':max(bull,bear),'reasons':rb if bull >= bear else rs}


def risk_guard(signal, ts):
    t = pd.Timestamp(ts).time()
    if t >= FORCE_EXIT:
        return {'action':'EXIT_ALL','reason':'Intraday square-off window'}
    if t < TRADE_START:
        return {'action':'BLOCK','reason':'Trading starts at 09:30'}
    if t >= TRADE_CUTOFF:
        return {'action':'BLOCK','reason':'Trading cutoff 15:15'}
    return {'action':'ALLOW','reason':'Inside intraday window'}


def sample_data(freq='5min', n=500):
    rng = np.random.default_rng(7)
    idx = pd.date_range('2026-09-01 09:15', periods=n, freq=freq)
    drift = rng.normal(0.02, 0.7, n).cumsum()
    close = 24500 + drift
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(2, 18, n)
    low = np.minimum(open_, close) - rng.uniform(2, 18, n)
    vol = rng.integers(1000, 10000, n)
    return pd.DataFrame({'open':open_,'high':high,'low':low,'close':close,'volume':vol}, index=idx)

@app.get('/')
def home(): return FileResponse(BASE/'static/index.html')

@app.get('/api/sample')
def sample():
    d15 = add_indicators(sample_data('15min'))
    d5 = add_indicators(sample_data('5min'))
    bias = spot_bias(d15)
    entry = entry_signal(d5, bias['bias'])
    latest = d5.tail(1).reset_index(names='time').replace({np.nan: None}).to_dict('records')[0]
    return {'market':'NIFTY SPOT','session':{'start':'09:30','cutoff':'15:15','force_exit':'15:10','carry_forward':False},'spot_15m_bias':bias,'entry_5m':entry,'latest':latest}

@app.post('/api/analyze')
async def analyze(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'): raise HTTPException(400,'Upload a CSV file')
    raw = await file.read()
    try:
        from io import BytesIO
        d0 = pd.read_csv(BytesIO(raw))
        d0.columns = [str(c).lower().strip() for c in d0.columns]
        if 'time' not in d0.columns: raise ValueError('CSV must contain time, open, high, low, close, volume')
        d0['time'] = pd.to_datetime(d0['time']); d0 = d0.set_index('time').sort_index()
        d15 = d0.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        d5 = d0.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        d1 = d0.resample('1min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        bias = spot_bias(d15)
        entry5 = entry_signal(d5, bias['bias'])
        entry1 = entry_signal(d1, bias['bias'])
        guard = risk_guard('', d0.index[-1])
        latest = add_indicators(d5).tail(1).reset_index(names='time').replace({np.nan: None}).to_dict('records')[0]
        return {'market':'NIFTY SPOT','rules':{'decision_tf':'15M','execution_tf':['5M','1M'],'trade_window':'09:30-15:15','carry_forward':False,'btst':False},'spot_15m_bias':bias,'execution_5m':entry5,'execution_1m':entry1,'risk_guard':guard,'latest':latest}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get('/api/health')
def health():
    return {'status':'ok','mode':'paper','market':'NIFTY','decision_timeframe':'15M','execution_timeframes':['5M','1M'],'trade_window':'09:30-15:15','force_exit':'15:10','carry_forward':False,'btst':False}
