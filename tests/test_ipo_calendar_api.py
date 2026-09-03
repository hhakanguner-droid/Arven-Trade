"""Tests for the IPO calendar vendor and its FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tradingagents.dataflows import ipo_calendar
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.service.api import create_app

# Trimmed, structurally-faithful excerpts of halkaarztakvimi.com.tr's real
# markup (grid = primary listing content; thumbnail = sidebar cross-category
# widget, which must NOT be picked up).
_PENDING_LIST_HTML = """
<html><body>
<article class="post-1992 listing-item listing-item-grid listing-item-grid-1 main-term-17">
  <div class="item-inner">
    <h2 class="title"><a href="https://www.halkaarztakvimi.com.tr/uras-kimya-san-ve-tic-a-s/" class="post-title post-url">
      Uras Kimya San. ve Tic. A.Ş.
    </a></h2>
    <div class="post-meta">
      <span class="time"><time class="post-published updated" datetime="2023-12-26T12:59:00+00:00">Ara 26, 2023</time></span>
    </div>
    <div class="post-summary">Uras Kimya San. ve Tic. A.Ş. Halka Arz için onay bekliyor.</div>
  </div>
</article>
<article class="post-1916 listing-item listing-item-grid listing-item-grid-1 main-term-17">
  <div class="item-inner">
    <h2 class="title"><a href="https://www.halkaarztakvimi.com.tr/zorlu-yenilenebilir-enerji-a-s/" class="post-title post-url">
      Zorlu Yenilenebilir Enerji A.Ş.
    </a></h2>
    <div class="post-meta">
      <span class="time"><time class="post-published updated" datetime="2023-09-29T10:00:00+00:00">Eyl 29, 2023</time></span>
    </div>
    <div class="post-summary">Zorlu Yenilenebilir Enerji A.Ş. izahnamesi incelemede.</div>
  </div>
</article>
<aside id="sidebar-primary-sidebar" class="sidebar">
  <article class="post-3067 listing-item listing-item-thumbnail listing-item-tb-1 main-term-44">
    <div class="item-inner clearfix">
      <p class="post-subtitle">Halka Arz Bilgileri</p>
      <p class="title"><a href="https://www.halkaarztakvimi.com.tr/should-not-appear/" class="post-url post-title">
        Should Not Appear A.Ş.
      </a></p>
    </div>
  </article>
</aside>
</body></html>
"""

_COMPLETED_LIST_HTML = """
<html><body>
<article class="post-1141 listing-item listing-item-grid listing-item-grid-1 main-term-21">
  <div class="item-inner">
    <h2 class="title"><a href="https://www.halkaarztakvimi.com.tr/enpara-bank-a-s/" class="post-title post-url">
      Enpara Bank A.Ş.
    </a></h2>
    <div class="post-meta">
      <span class="time"><time class="post-published updated" datetime="2026-04-07T09:00:00+00:00">Nis 7, 2026</time></span>
    </div>
    <div class="post-summary">Enpara Bank A.Ş. PÖİP'te işlem görmeye başladı.</div>
  </div>
</article>
</body></html>
"""

_DETAIL_HTML = """
<html><body>
<div class="entry-content clearfix single-post-content">
  <h1 class="single-post-title">Türker Vangölü Enerji Yatırım A.Ş.</h1>
  <div class="post-subtitle" style="margin-top: 16px;"><span style="color: #3366ff;"><strong>Halka Arz Bilgileri</strong></span></div>
  <div class="detay1">
    <div class="flex1" style="display:grid">
      <span style="font-weight: 400;">Faaliyet Alanı:</span>
      <span style="font-weight: 500;">elektrik dağıtımı ve perakende elektrik satışı.</span>
    </div>
  </div>
  <div class="detay1" style="flex-direction: revert;">
    <div class="flex1" style="display:grid">
      <span style="font-weight: 400;">Aracı Kurum: </span>
      <span style="font-weight: 500;">&ensp;Halk Yatırım Menkul Değerler A.Ş.</span>
    </div>
  </div>
  <div class="detay2">
    <div class="flex2">
      <div class="flexiskod"><div style="font-weight: 300;">İşlem Kodu</div><div style="font-weight: 600;">VEYAS</div></div>
      <div class="flexiskod"><div style="font-weight: 300;">Halka Arz Fiyatı</div><div style="font-weight: 600;"><span style="font-weight: 300;">₺</span>136,00</div></div>
    </div>
    <div class="flex2">
      <div class="flexiskod"><div style="font-weight: 300;">Talep Toplama Tarihleri</div><div style="font-weight: 600;">12-13-14 Ağustos 2026</div></div>
    </div>
    <div class="flex2">
      <div class="flexiskod" style="border-bottom: none;"><div style="font-weight: 300;">Pazar</div><div style="font-weight: 600;">Yıldız</div></div>
    </div>
  </div>
  <div class="detay2">
    <div class="flex3">
      <div class="flexiskod"><div style="font-weight: 300;">Dağıtım Şekli</div><div style="font-weight: 600;">Eşit Dağıtım **</div></div>
    </div>
  </div>
</div>
</body></html>
"""

_MISSING_DETAIL_HTML = "<html><body><p>Sayfa bulunamadı.</p></body></html>"


@pytest.fixture(autouse=True)
def _fake_fetch(monkeypatch):
    pages = {
        ipo_calendar._LIST_URLS["pending"]: _PENDING_LIST_HTML,
        ipo_calendar._LIST_URLS["completed"]: _COMPLETED_LIST_HTML,
        f"{ipo_calendar._BASE_URL}/turker-vangolu-enerji-yatirim-a-s/": _DETAIL_HTML,
        f"{ipo_calendar._BASE_URL}/delisted-company/": _MISSING_DETAIL_HTML,
    }

    def fake_fetch_html(url: str) -> str:
        return pages[url]

    monkeypatch.setattr(ipo_calendar, "_fetch_html", fake_fetch_html)


def test_get_ipo_calendar_returns_both_groups_and_ignores_sidebar_widget():
    result = ipo_calendar.get_ipo_calendar()
    assert not result["errors"]
    slugs = {item["slug"] for item in result["listings"]}
    assert slugs == {"uras-kimya-san-ve-tic-a-s", "zorlu-yenilenebilir-enerji-a-s", "enpara-bank-a-s"}
    # The sidebar's cross-category widget must never leak into the result.
    assert "should-not-appear" not in slugs

    by_slug = {item["slug"]: item for item in result["listings"]}
    pending = by_slug["uras-kimya-san-ve-tic-a-s"]
    assert pending["group"] == "pending"
    assert pending["name"] == "Uras Kimya San. ve Tic. A.Ş."
    assert pending["published_at"] == "2023-12-26T12:59:00+00:00"
    assert "onay bekliyor" in pending["summary"]

    completed = by_slug["enpara-bank-a-s"]
    assert completed["group"] == "completed"


def test_get_ipo_calendar_reports_a_failed_group_without_dropping_the_other(monkeypatch):
    def failing_fetch(url: str) -> str:
        if url == ipo_calendar._LIST_URLS["pending"]:
            raise RuntimeError("connection reset")
        return _COMPLETED_LIST_HTML

    monkeypatch.setattr(ipo_calendar, "_fetch_html", failing_fetch)
    result = ipo_calendar.get_ipo_calendar()

    assert any(err["group"] == "pending" for err in result["errors"])
    assert any(item["group"] == "completed" for item in result["listings"])


def test_get_ipo_detail_extracts_flexiskod_and_detay1_fields():
    detail = ipo_calendar.get_ipo_detail("turker-vangolu-enerji-yatirim-a-s")
    assert detail["name"] == "Türker Vangölü Enerji Yatırım A.Ş."
    assert detail["status"] == "Halka Arz Bilgileri"
    assert detail["sector"] == "elektrik dağıtımı ve perakende elektrik satışı."
    assert detail["intermediary"] == "Halk Yatırım Menkul Değerler A.Ş."
    assert detail["ticker"] == "VEYAS"
    assert detail["offer_price"] == "₺136,00"
    assert detail["subscription_dates"] == "12-13-14 Ağustos 2026"
    assert detail["market_tier"] == "Yıldız"
    assert detail["allocation_method"] == "Eşit Dağıtım **"


def test_get_ipo_detail_raises_no_market_data_when_company_page_is_gone():
    with pytest.raises(NoMarketDataError):
        ipo_calendar.get_ipo_detail("delisted-company")


def test_get_ipo_detail_rejects_a_malformed_slug():
    with pytest.raises(ValueError):
        ipo_calendar.get_ipo_detail("../../etc/passwd")


class _Service:
    def close(self):
        return None

    def health(self):
        return {"status": "ok"}


def _client():
    return TestClient(create_app(_Service(), auth_disabled=True))


def test_ipo_calendar_endpoint_returns_both_groups():
    response = _client().get("/api/v1/ipo-calendar")
    assert response.status_code == 200
    body = response.json()
    groups = {item["group"] for item in body["listings"]}
    assert groups == {"pending", "completed"}


def test_ipo_detail_endpoint_returns_company_fields():
    response = _client().get("/api/v1/ipo-calendar/turker-vangolu-enerji-yatirim-a-s")
    assert response.status_code == 200
    assert response.json()["ticker"] == "VEYAS"


def test_ipo_detail_endpoint_maps_missing_slug_to_404():
    response = _client().get("/api/v1/ipo-calendar/delisted-company")
    assert response.status_code == 404


def test_ipo_detail_endpoint_rejects_malformed_slug_with_422():
    response = _client().get("/api/v1/ipo-calendar/UPPERCASE_not_a_slug")
    assert response.status_code == 422
