from tradingagents.presentation import build_analysis_view, build_history_card


def _state(**overrides):
    state = {
        "company_of_interest": "THYAO.IS",
        "trade_date": "2026-08-26",
        "market_report": "**Market:** Trend güçlü. Momentum destekleyici.",
        "sentiment_report": "Sentiment olumlu. İlgi artıyor.",
        "news_report": "Haber akışı dengeli.",
        "kap_report": "KAP tarafında kritik olumsuzluk yok.",
        "fundamentals_report": "Bilanço görünümü güçlü.",
        "investment_debate_state": {
            "bull_history": "Bull: büyüme katalizörleri destekleyici.",
            "bear_history": "Bear: kur ve maliyet baskısı izlenmeli.",
        },
        "risk_debate_state": {
            "judge_decision": "Risk: medium. Pozisyon boyutu kontrollü tutulmalı. Stop disiplini gerekli."
        },
        "trader_investment_plan": "Teyitli giriş beklenmeli.",
        "final_trade_decision": "Rating: Overweight. Görünüm pozitif.",
    }
    state.update(overrides)
    return state


def test_build_analysis_view_maps_rating_to_arven_labels():
    view = build_analysis_view(_state())

    assert view["ticker"] == "THYAO.IS"
    assert view["rating"] == "Overweight"
    assert view["tone"] == "positive"
    assert view["stance_label"] == "POZİTİF"
    assert view["action_label"] == "POZİSYONU ARTIR"
    assert view["risk_level"] == "medium"


def test_primary_agent_summaries_are_short_and_markdown_free():
    state = _state(market_report="**Market:** " + "A" * 400 + ". İkinci cümle.")
    view = build_analysis_view(state)
    market = next(card for card in view["agents"] if card["key"] == "market")

    assert "**" not in market["summary"]
    assert len(market["summary"]) <= 180


def test_short_thesis_is_bounded_to_three_sentences():
    state = _state(
        risk_debate_state={
            "judge_decision": "Birinci. İkinci. Üçüncü. Dördüncü ekranda görünmemeli."
        }
    )
    view = build_analysis_view(state)

    assert "Birinci." in view["short_thesis"]
    assert "Üçüncü." in view["short_thesis"]
    assert "Dördüncü" not in view["short_thesis"]


def test_missing_optional_reports_do_not_create_empty_agent_cards():
    view = build_analysis_view(
        {
            "company_of_interest": "ASELS.IS",
            "trade_date": "2026-08-26",
            "final_trade_decision": "Rating: Hold",
        }
    )

    assert view["agents"] == []
    assert view["stance_label"] == "NÖTR"
    assert view["action_label"] == "İZLE"


def test_explicit_turkish_risk_markers_are_recognized():
    high = build_analysis_view(
        _state(risk_debate_state={"judge_decision": "Risk: yüksek. Volatilite güçlü."})
    )
    low = build_analysis_view(
        _state(risk_debate_state={"judge_decision": "Risk: düşük. Görünüm dengeli."})
    )

    assert high["risk_level"] == "high"
    assert low["risk_level"] == "low"


def test_details_preserve_long_form_content_for_drill_down():
    long_report = "Detaylı rapor " + "x" * 500
    view = build_analysis_view(_state(market_report=long_report))

    assert view["details"]["market"] == long_report
    assert len(next(card for card in view["agents"] if card["key"] == "market")["summary"]) <= 180


def test_build_history_card_projects_phase11_record():
    card = build_history_card(
        {
            "id": 7,
            "ticker": "THYAO.IS",
            "trade_date": "2026-08-20",
            "rating": "Buy",
            "entry_price": 312.5,
            "benchmark_ticker": "^XU100",
            "final_decision": "Rating: Buy. Güçlü fakat kontrollü pozitif görünüm.",
            "performance": [
                {
                    "horizon_days": 5,
                    "raw_return": 0.04,
                    "benchmark_return": 0.01,
                    "alpha_return": 0.03,
                }
            ],
        }
    )

    assert card["id"] == 7
    assert card["stance_label"] == "POZİTİF"
    assert card["action_label"] == "AL"
    assert card["performance"][0]["alpha_return"] == 0.03


def test_builders_do_not_mutate_input_state():
    state = _state()
    original = repr(state)

    build_analysis_view(state)

    assert repr(state) == original
