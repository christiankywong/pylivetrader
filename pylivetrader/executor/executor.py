import datetime
from contextlib import ExitStack

from pylivetrader.executor.realtimeclock import (
    RealtimeClock,
    BAR, SESSION_START, BEFORE_TRADING_START_BAR
)
from pylivetrader.data.bardata import BarData
from pylivetrader.misc.api_context import LiveTraderAPI


class AlgorithmExecutor:

    def __init__(self, algo, data_portal, universe_func):

        self.data_portal = data_portal
        self.algo = algo

        # This object is the way that user algorithms interact with OHLCV data,
        # fetcher data, and some API methods like `data.can_trade`.
        self.current_data = BarData(
            data_portal,
            self.algo.data_frequency,
            universe_func,
        )

        before_trading_start_minute = \
            (datetime.time(8, 45), 'America/New_York')

        self.clock = RealtimeClock(
            self.algo.trading_calendar,
            before_trading_start_minute,
            minute_emission=algo.data_frequency == 'minute',
        )

    def run(self):

        algo = self.algo

        def every_bar(dt_to_use, current_data=self.current_data,
                      handle_data=algo.event_manager.handle_data):

            # clear data portal cache.
            self.data_portal.cache_clear()

            # called every tick (minute or day).
            algo.on_dt_changed(dt_to_use)

            self.current_data.datetime = dt_to_use

            handle_data(algo, current_data, dt_to_use)

            algo.portfolio_needs_update = True
            algo.account_needs_update = True

        def once_a_day(midnight_dt, current_data=self.current_data,
                       data_portal=self.data_portal):

            # set all the timestamps
            algo.on_dt_changed(midnight_dt)
            self.current_data.datetime = midnight_dt

        def on_exit():
            # Remove references to algo, data portal, et al to break cycles
            # and ensure deterministic cleanup of these objects when the
            # simulation finishes.
            self.algo = None
            self.current_data = self.data_portal = None

        with ExitStack() as stack:
            stack.callback(on_exit)
            stack.enter_context(LiveTraderAPI(self.algo))

            # runs forever
            for dt, action in self.clock:
                if action == BAR:
                    every_bar(dt)
                elif action == SESSION_START:
                    once_a_day(dt)
                elif action == BEFORE_TRADING_START_BAR:
                    algo.on_dt_changed(dt)
                    self.current_data.datetime = dt
                    algo.before_trading_start(self.current_data)
