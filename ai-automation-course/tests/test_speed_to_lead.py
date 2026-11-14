from conftest import load

lead = load("05_speed_to_lead")
FORM = {"name": "Sam Price", "email": "sam@example.com", "company": "Price Logistics",
        "message": "We re-type every delivery note. Can you help?"}


def good_proposal(prompt):
    return lead.Proposal(fits=True, subject="Your delivery notes",
                         body="Hi Sam, an Automation audit (£3,000) would find what to automate first.")


def test_a_lead_gets_a_proposal_and_the_team_hears(world):
    world.answer = good_proposal
    assert lead.run(FORM)["status"] == "proposal sent"
    assert len(world.emails) == 1 and world.emails[0]["to"] == "sam@example.com"
    assert world.slack[0].startswith("New lead: Sam Price")
    assert world.slack[1] == "Proposal sent to Sam Price (Price Logistics): Your delivery notes"
    assert world.tabs["Leads"][0][-1] == "proposal sent"


def test_the_model_fails_and_the_lead_is_still_saved(world):
    world.answer = RuntimeError("model is down")
    assert lead.run(FORM)["status"] == "needs a person"
    assert world.emails == []
    assert len(world.slack) == 2  # the lead, then "needs a reply from a person"
    assert world.tabs["Leads"][0][-1] == "needs a person"


def test_the_same_lead_twice_sends_one_email(world):
    world.answer = good_proposal
    lead.run(FORM)
    assert lead.run(FORM)["status"] == "duplicate"
    assert len(world.emails) == 1


def test_a_made_up_price_is_never_sent(world):
    world.answer = lead.Proposal(fits=True, subject="Offer", body="We can do it all for £99.")
    assert lead.run(FORM)["status"] == "needs a person"
    assert world.emails == []


def test_every_price_in_the_list_can_be_quoted(world):
    # "From £12,000, quoted after..." in services.md: the comma after the price is not part of it.
    world.answer = lead.Proposal(fits=True, subject="One automation",
                                 body="Build one automation starts from £12,000, and support is £1,500 a month.")
    assert lead.run(FORM)["status"] == "proposal sent"


def test_nothing_fits_and_a_person_replies(world):
    world.answer = lead.Proposal(fits=False, subject="", body="")
    assert lead.run({**FORM, "message": "Can you build us a mobile app?"})["status"] == "needs a person"
    assert world.emails == []


def test_a_bad_form_is_refused_before_any_work(world):
    import pytest
    with pytest.raises(ValueError):
        lead.run({"name": "Sam", "email": "not an email", "message": "hi"})
    assert world.slack == [] and world.tabs == {}


def test_shadow_mode_writes_the_proposal_but_sends_nothing(world, monkeypatch):
    from toolkit import mail
    monkeypatch.setattr(mail, "send", lambda *a, **k: False)  # what the real send returns in shadow mode
    world.answer = good_proposal
    assert lead.run(FORM)["status"] == "proposal ready (shadow mode)"
    assert len(world.slack) == 1  # the lead. Nothing went, so the team isn't told it did
