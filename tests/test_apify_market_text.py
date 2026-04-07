from cwt_agent.apify_market_text import text_from_apify_saved_json


def test_flatten_fatihtahta_shape():
    raw = {
        "dataset_items": [
            {
                "source": "search",
                "query": "NBA",
                "parentMarket": {
                    "title": "Lakers vs Celtics",
                    "slug": "nba-test",
                    "tags": [{"label": "Sports"}, {"label": "Basketball"}],
                },
                "market": {
                    "question": "Will Lakers win?",
                    "additionalFields": {"description": "NBA finals context."},
                },
            }
        ]
    }
    t = text_from_apify_saved_json(raw)
    assert "Lakers" in t
    assert "NBA" in t
    assert "Sports" in t
