from app.market import extract_market_depth, summarize_market_depth_payload


def test_extracts_documented_indstocks_five_level_shape():
    payload = {
        "status": "success",
        "data": {
            "NFO_51011": {
                "live_price": 100.0,
                "market_depth": {
                    "aggregate": {
                        "total_buy": "1000",
                        "total_sell": "1200",
                        "buy_percentage": 45.4,
                        "sell_percentage": 54.6,
                    },
                    "depth": [
                        {"buy": {"quantity": "100", "price": "99.9"}, "sell": {"quantity": "120", "price": "100.1"}},
                        {"buy": {"quantity": "90", "price": "99.8"}, "sell": {"quantity": "110", "price": "100.2"}},
                        {"buy": {"quantity": "80", "price": "99.7"}, "sell": {"quantity": "100", "price": "100.3"}},
                        {"buy": {"quantity": "70", "price": "99.6"}, "sell": {"quantity": "90", "price": "100.4"}},
                        {"buy": {"quantity": "60", "price": "99.5"}, "sell": {"quantity": "80", "price": "100.5"}},
                    ],
                },
            }
        },
    }

    depth = extract_market_depth(payload, "51011")
    assert len(depth["market_depth"]["depth"]) == 5


def test_depth_diagnostic_is_value_free_and_reports_shape():
    payload = {
        "status": "success",
        "data": {
            "NFO_51011": {
                "market_depth": {
                    "depth": [
                        {"buy": {"quantity": "100", "price": "99.9"}, "sell": {"quantity": "120", "price": "100.1"}}
                    ]
                }
            }
        },
    }

    diagnostic = summarize_market_depth_payload(payload, "51011")
    assert "depth_found=True" in diagnostic
    assert "depth_levels=1" in diagnostic
    assert "quantity" in diagnostic
    assert "price" in diagnostic
    assert "100" not in diagnostic
    assert "99.9" not in diagnostic
