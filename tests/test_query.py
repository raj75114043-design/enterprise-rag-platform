from ragp.query import plan


def test_follow_up_is_resolved_with_previous_question():
    p = plan("And at Baddi?", previous="What is the closure timeline for a minor deviation?")
    assert "minor deviation" in p.resolved and p.sites == ["Baddi"]


def test_version_and_date_filters():
    assert plan("What was the Phase I timeline in version 3.0?").version == "3.0"
    assert plan("What was the password interval in v1?").version == "1.0"
    assert plan("What was the rule in 2024?").as_of == "2024-12-31"


def test_comparison_is_decomposed_per_site():
    p = plan("Compare the dirty equipment hold time between Goa and Sikkim.")
    assert [s["site"] for s in p.sub_queries] == ["Goa", "Sikkim"]
    assert all("Goa" not in s["query"].replace("at Goa", "") for s in p.sub_queries)
