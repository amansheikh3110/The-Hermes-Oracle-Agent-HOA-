from cwt_agent.niches import dominant_niches, score_text_for_niches


def test_politics_keywords():
    s = score_text_for_niches("Will the senate flip in the next election?")
    assert "politics" in s
    assert dominant_niches(s)[0][0] == "politics"
