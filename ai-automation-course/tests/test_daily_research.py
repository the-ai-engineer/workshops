from conftest import load

research = load("04_daily_research")
P = research.Prospect


def found(*prospects):
    return research.Found(prospects=list(prospects))


def test_new_prospects_are_saved_and_the_team_is_told(world):
    world.answer = found(P(company="Acme Freight", signal="Raised £5m", source="https://news.example/acme", published="2026-11-11"))
    result = research.run()
    assert result["added"] == ["Acme Freight"]  # once: the next signals find it again, and the code skips it
    assert len(world.tabs["Prospects"]) == 1
    assert world.slack == ["1 new prospects in the sheet today: Acme Freight"]


def test_prospects_already_in_the_sheet_are_skipped(world):
    world.tabs["Prospects"] = [["date", "company"], ["2026-11-10", "Acme Freight"]]
    world.answer = found(P(company="acme freight ", signal="Raised £5m", source="https://news.example/acme", published="unknown"))
    assert research.run()["added"] == []
    assert world.slack == []


def test_a_prospect_without_a_link_is_never_saved(world):
    world.answer = found(P(company="Made Up Ltd", signal="Hired a CTO", source="not found", published="unknown"))
    assert research.run()["added"] == []
