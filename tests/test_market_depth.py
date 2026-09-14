from app.market import extract_market_depth


def sample_depth():
    return {
        "NFO_47273": {
            "market_depth": {
                "depth": [
                    {"buy": {"quantity": "100", "price": "10.0"},
                     "sell": {"quantity": "120", "price": "10.1"}}
                ]
            }
        }
    }


def test_extract_depth_nfo_key():
    result = extract_market_depth(sample_depth(), "47273")
    assert result.get("market_depth", {}).get("depth")


def test_extract_depth_direct_payload():
    direct = sample_depth()["NFO_47273"]
    result = extract_market_depth(direct, "47273")
    assert result == direct


def test_extract_depth_missing_returns_empty():
    assert extract_market_depth({"NFO_1": {}}, "47273") == {}
