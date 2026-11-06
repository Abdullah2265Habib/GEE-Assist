"""SpeedMeter: real-time speed over a sliding window, and the average since the start."""

import pytest

from backend.business.download.speed_meter import SpeedMeter


class Clock:
    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_nothing_measured_before_the_start():
    meter = SpeedMeter(clock=Clock())
    assert meter.rate() == 0 and meter.average() == 0


def test_a_burst_counts_over_the_whole_time_it_took():
    """A GEE request of 40 MB that took 20 s is 2 MB/s, not 40 MB/s."""
    clock = Clock()
    meter = SpeedMeter(window=20, clock=clock)
    meter.start()
    clock.now += 20
    meter.add(40_000_000)
    assert meter.rate() == pytest.approx(2_000_000)


def test_speed_drops_while_nothing_arrives():
    clock = Clock()
    meter = SpeedMeter(window=20, clock=clock)
    meter.start()
    clock.now += 5
    meter.add(10_000_000)
    assert meter.rate() == pytest.approx(2_000_000)   # 10 MB in the 5 s since the start
    clock.now += 10
    assert meter.rate() == pytest.approx(10_000_000 / 15)
    clock.now += 11
    assert meter.rate() == 0                           # the burst left the 20 s window
    assert meter.average() == pytest.approx(10_000_000 / 26)


def test_an_instant_burst_right_after_the_start_is_not_absurd():
    clock = Clock()
    meter = SpeedMeter(clock=clock)
    meter.start()
    clock.now += 0.01
    meter.add(5_000_000)
    assert meter.rate() == pytest.approx(5_000_000)   # spread over at least one second


def test_start_forgets_the_previous_download():
    clock = Clock()
    meter = SpeedMeter(clock=clock)
    meter.start()
    clock.now += 2
    meter.add(1_000_000)
    meter.start()
    assert meter.rate() == 0 and meter.average() == 0
    meter.reset()
    assert meter.rate() == 0
