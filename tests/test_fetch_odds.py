"""fetch_odds.py 解析与覆盖度测试。"""

from __future__ import annotations

from fetch_odds import (
    convert_match,
    empty_crs_market,
    empty_ttg_market,
    parse_crs,
    parse_ttg,
    summarize_market_coverage,
)


def test_parse_crs_groups_scores():
    raw = {
        "s01s00": "6.70",
        "s00s00": "9.80",
        "s00s01": "14.00",
        "s1sh": "85.00",
        "updateDate": "2026-06-18",
        "updateTime": "20:47:16",
    }
    out = parse_crs(raw)
    assert out is not None
    assert out["type"] == "比分"
    assert out["odds"]["胜"]["1:0"] == 6.7
    assert out["odds"]["平"]["0:0"] == 9.8
    assert out["odds"]["负"]["0:1"] == 14.0
    assert out["odds"]["胜"]["胜其它"] == 85.0


def test_parse_ttg_buckets():
    raw = {"s0": "9.80", "s1": "4.60", "s7": "34.00", "updateDate": "2026-06-18"}
    out = parse_ttg(raw)
    assert out is not None
    assert out["type"] == "总进球数"
    assert out["odds"]["0"] == 9.8
    assert out["odds"]["1"] == 4.6
    assert out["odds"]["7+"] == 34.0


def test_convert_match_keeps_crs_ttg_when_pool_exists_but_empty():
    sm = {
        "matchNumStr": "周四025",
        "matchId": 1,
        "leagueAbbName": "世界杯",
        "matchDate": "2026-06-19",
        "matchTime": "00:00:00",
        "homeTeamAbbName": "捷克",
        "awayTeamAbbName": "南非",
        "remark": "",
        "matchStatus": "Selling",
        "taxDateNo": "2606181",
        "had": {"h": "1.59", "d": "3.55", "a": "4.58"},
        "poolList": [{"poolCode": "CRS"}, {"poolCode": "TTG"}],
        "crs": {},
        "ttg": {},
    }
    match = convert_match(sm)
    types = [m["type"] for m in match["markets"]]
    assert "比分" in types
    assert "总进球数" in types
    crs = next(m for m in match["markets"] if m["type"] == "比分")
    ttg = next(m for m in match["markets"] if m["type"] == "总进球数")
    assert crs["status"] == "未开盘"
    assert ttg["status"] == "未开盘"


def test_summarize_market_coverage():
    matches = [
        {
            "markets": [
                empty_crs_market(),
                {**empty_ttg_market(), "status": "已开盘", "odds": {"0": 9.8}},
            ]
        }
    ]
    cov = summarize_market_coverage(matches)
    assert cov["比分"]["未开盘"] == 1
    assert cov["总进球数"]["已开盘"] == 1
