import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import add_indicators, sample_data, spot_bias, entry_signal, risk_guard

def test_indicators():
    d = add_indicators(sample_data('5min', 100))
    assert {'ema9','ema21','vwap','prev_support','prev_resistance'} <= set(d.columns)

def test_bias_and_entry_shapes():
    d15 = sample_data('15min', 100)
    d5 = sample_data('5min', 100)
    bias = spot_bias(d15)
    entry = entry_signal(d5, bias['bias'])
    assert bias['bias'] in {'BULLISH','BEARISH','WAIT'}
    assert entry['signal'] in {'BUY_CALL','BUY_PUT','WAIT','FLAT'}

def test_intraday_guard():
    assert risk_guard('WAIT', '2026-09-01 09:00')['action'] == 'BLOCK'
    assert risk_guard('WAIT', '2026-09-01 15:10')['action'] == 'EXIT_ALL'
    assert risk_guard('WAIT', '2026-09-01 15:15')['action'] == 'EXIT_ALL'
