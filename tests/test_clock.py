from paylane_agent.session.clock import Clock


def test_29_days_in_window():
    assert Clock().within_refund_window("2026-09-16T12:00:00Z")


def test_exactly_30_days_out_of_window():
    assert not Clock().within_refund_window("2026-09-15T12:00:00Z")


def test_one_second_under_30_days_in_window():
    assert Clock().within_refund_window("2026-09-15T12:00:01Z")


def test_future_date_not_in_window():
    assert not Clock().within_refund_window("2026-10-16T12:00:00Z")


def test_timezone_offset_normalised_to_utc():
    # 2026-09-15T14:00+02:00 == 12:00Z -> exactly 30 days
    assert not Clock().within_refund_window("2026-09-15T14:00:00+02:00")
