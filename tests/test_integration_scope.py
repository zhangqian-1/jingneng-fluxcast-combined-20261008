from scripts.check_integration_scope import check


def test_dispatch_and_single_prediction_are_unchanged():
    assert check()["passed"]
