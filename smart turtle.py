import math
import numpy as np
import pandas as pd
from time import time
from talib import ATR
#from zipline.api import sid, order

def initialize(context):
    """
    Initialize parameters.
    """
    context.is_test = True
    context.is_debug = True
    context.is_timed = False
    context.is_info = True

    if context.is_timed:
        start_time = time()

    # Data
    context.symbols = [
        'BP',
        'CD',
        'CL',
        'ED',
        'GC',
        'HG',
        'HO',
        'HU',
        'JY',
        'SB',
        'SF',
        'SP',
        'SV',
        'TB',
        'TY',
        'US',
        'CN',
        'SY',
        'WC',
        'ES',
        'NQ',
        'YM',
        'QM',
        'FV',
    ]

    # Use market symbols as key
    # The rest of this algorithm follows this convention as well (should @TODO)
    context.cfutures = {symbol: continuous_future(symbol , offset = 0, roll = 'calendar' , adjustment = 'mul') for symbol in context.symbols}

    context.prices = None
    context.contracts = None
    context.average_true_range = {}
    context.dollar_volatility = {}
    context.trade_size = {}
    context.position_analytics = {}
    context.future_to_symbol = {}
    context.yesterday_auto_close_date = {}

    # Breakout signals
    context.strat_one_breakout = 20
    context.strat_one_breakout_high = {}
    context.strat_one_breakout_low = {}
    context.strat_one_exit = 10
    context.strat_one_exit_high = {}
    context.strat_one_exit_low = {}
    # Keyed by root symbol
    context.is_strat_one = {}

    context.strat_two_breakout = 55
    context.strat_two_breakout_high = {}
    context.strat_two_breakout_low = {}
    context.strat_two_exit = 20
    context.strat_two_exit_high = {}
    context.strat_two_exit_low = {}
    # Keyed by root symbol
    context.is_strat_two = {}

    # Risk
    context.capital = context.portfolio.starting_cash
    context.profit = 0
    context.capital_risk_per_trade = 0.01
    context.capital_multiplier = 2
    context.stop = {}
    context.has_stop = {}
    context.stop_multiplier = 2
    context.market_risk_limit = 4
    context.market_risk = {}
    context.direction_risk_limit = 12
    context.long_risk = 0
    context.short_risk = 0

    # Order
    context.orders = {}
    context.filled = 1
    context.canceled = 2
    context.rejected = 3
    context.long_direction = 'long'
    context.short_direction = 'short'

    # Was last entry signal winning trade initial status. the last trade before this algo runs:
    context.previous_trade_won = {}

    for symbol in context.symbols:
        context.orders[symbol] = []
        context.stop[symbol] = 0
        context.has_stop[symbol] = False
        context.market_risk[symbol] = 0
        context.position_analytics[symbol] = {'state' : 0, 'entry' : 0, 'stop' : 0, 'exit' : 0}
        # Move this out of loop after implementing check for initialization of prev-trade-won
        context.previous_trade_won[symbol] = False

    # Start of day functions
    schedule_function(
        get_prices,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        validate_prices,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        compute_highs,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        compute_lows,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        get_contracts,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        check_rollover,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    # End of day functions
    schedule_function(
        log_risks,
        date_rules.every_day(),
        time_rules.market_close(minutes=1),
        False
    )
    schedule_function(
        clear_stops,
        date_rules.every_day(),
        time_rules.market_close(minutes=1),
        False
    )
    schedule_function(
        turn_limit_to_market_orders,      #make sure the limit orders are filled
        date_rules.every_day(),
        time_rules.market_close(minutes=25)
    )

    total_minutes = 6*60 + 30
    for i in range(30, total_minutes, 30):
        schedule_function(
            compute_average_true_ranges,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            compute_dollar_volatilities,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            compute_trade_sizes,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            update_risks,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            detect_entry_signals,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            scaling_signals,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            place_stop_orders,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            stop_trigger_cleanup,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            detect_exit_signals,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )
        schedule_function(
            analyzing_trade_for_next_signal,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )

    if context.is_debug:
        schedule_function(
            log_context,
            date_rules.every_day(),
            time_rules.market_close()
        )

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def check_rollover(context, data):
    """
    see if the contract have rollovered
    """
    for sym in context.tradable_symbols:
        current_auto_close_date = context.contracts[sym].auto_close_date
               
        try:
            if current_auto_close_date != context.yesterday_auto_close_date[sym]:
                previous_order = get_order(context.orders[sym][-1])
                if previous_order.stop is not None and previous_order.status == context.canceled:
                    price = data.current(context.cfutures[sym], 'price')
                    order_identifier = order(
                        context.contracts[sym],
                        -previous_order.amount,
                        style = LimitOrder(price)
                    )

                    if order_identifier is not None:
                        context.orders[sym].append(order_identifier)

                    log.info(
                        'Long(rollover) %s %i@%.2f'
                        %(
                            sym,
                            -previous_order.amount,
                            price
                        )
                    )
        except (KeyError, IndexError):
            pass
    
        context.yesterday_auto_close_date[sym] = current_auto_close_date
                  

        
        
def clear_stops(context, data):
    """
    Clear stops 1 minute before market close.
    """
    if context.is_timed:
        start_time = time()

    for sym in context.tradable_symbols:
        try:
            order_info = get_order(context.orders[sym][-1])
            unfilled_stop_price = order_info.stop
        except IndexError:
            continue

        if unfilled_stop_price is not None and order_info.status == 0:
            cancel_order(context.orders[sym][-1])
            log.info( '%s  stop order canceled due to end of day' %(sym))


    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def log_context(context, data):
    log.info('Porfolio cash: %.2f \n' % context.portfolio.cash)
    log.info('Capital:          %.2f \n' % context.capital)
    for contract in context.contracts:
        sym = contract.root_symbol
        if sym in context.tradable_symbols:
            position = context.portfolio.positions[contract]
            log.info(
                '%s  Position:%i  Trade Size:%.2f  Market Risk:%.2f'
                %(
                    sym,
                    position.amount,
                    context.trade_size[sym],
                    context.market_risk[sym],
                )
            )

def log_risks(context, data):
    """
    Log long and short risk 1 minute before market close.
    """
    record(
        long_risk = context.long_risk,
        short_risk = context.short_risk
    )

def get_prices(context, data):
    """
    Get high, low, and close prices.
    """
    if context.is_timed:
        start_time = time()

    cfutures = [v for k, v in context.cfutures.items()]
    fields = ['high', 'low', 'close']
    bars = context.strat_two_breakout + 1
    frequency = '1d'

    # Retrieves a pandas panel with axes labelled as:
    # (Index: field, Major-axis: date, Minor-axis: symbol)
    context.prices = data.history(
        cfutures,
        fields,
        bars,
        frequency
    )
    
    if context.is_test:
        assert(context.prices.shape[0] == 3)

    # Tranpose/Reindex panel in axes with:
    # (Index: symbol, Major-axis: field, Minor-axis: date)
    context.prices = context.prices.transpose(2, 0, 1)
    context.prices = context.prices.reindex()
    syms = {future: future.root_symbol for future in context.prices.axes[0]}
    context.prices = context.prices.rename(items=syms)
    
    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 8192)

def validate_prices(context, data):
# data is not used
    """
    Drop markets with null prices.
    """
    if context.is_timed:
        start_time = time()

    context.prices.dropna(axis=0, inplace=True)

    validated_markets = context.prices.axes[0]

    dropped_markets = list(
        set(context.symbols) - set(validated_markets)
    )

    context.tradable_symbols = validated_markets

    if context.is_debug and dropped_markets:
        log.debug(
            'Null prices for %s. Dropped.'
            % ', '.join(dropped_markets)
        )

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def compute_highs(context, data):
# data is not used
    """
    Compute high for breakout and exits
    """
    if context.is_timed:
        start_time = time()

    for sym in context.tradable_symbols:
        context.strat_one_breakout_high[sym] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_one_breakout-1:-1]\
            .max()
        context.strat_two_breakout_high[sym] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_two_breakout-1:-1]\
            .max()
        context.strat_one_exit_high[sym] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_one_exit-1:-1]\
            .max()
        context.strat_two_exit_high[sym] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_two_exit-1:-1]\
            .max()

    if context.is_test:
        assert(len(context.strat_one_breakout_high) > 0)
        assert(len(context.strat_two_breakout_high) > 0)
        assert(len(context.strat_one_exit_high) > 0)
        assert(len(context.strat_two_exit_high) > 0)

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def compute_lows(context, data):
# data is not used
    """
    Compute 20 and 55 day low.
    """
    if context.is_timed:
        start_time = time()

    for sym in context.tradable_symbols:
        context.strat_one_breakout_low[sym] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_one_breakout-1:-1]\
            .min()
        context.strat_two_breakout_low[sym] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_two_breakout-1:-1]\
            .min()
        context.strat_one_exit_low[sym] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_one_exit-1:-1]\
            .min()
        context.strat_two_exit_low[sym] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_two_exit-1:-1]\
            .min()

    if context.is_test:
        assert(len(context.strat_one_breakout_low) > 0)
        assert(len(context.strat_two_breakout_low) > 0)
        assert(len(context.strat_one_exit_low) > 0)
        assert(len(context.strat_two_exit_low) > 0)

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def get_contracts(context, data):
    """
    Get futures contracts using the dict of continuous futures objects
    The returned pd.panel from data.current() is reindex to use symbol string as key
    """
    if context.is_timed:
        start_time = time()

    cfutures = [v for k, v in context.cfutures.items()]
    fields = 'contract'

    # Dataframe indexed with date, and columned with security as according to API spec
    context.contracts = data.current(
        cfutures,
        fields
    )
    
    context.contracts = context.contracts.transpose()
    context.contracts.dropna(axis=0, inplace=True)
    context.contracts = context.contracts.rename_axis(lambda k: k.root_symbol, axis=0)

        
    if context.is_test:
        assert(context.contracts.shape[0] > 0)

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def compute_average_true_ranges(context, data):
# data is not used
    """
    Compute average true ranges, or N.
    """
    if context.is_timed:
        start_time = time()

    rolling_window = 21
    moving_average = 20

    for sym in context.tradable_symbols:
        context.average_true_range[sym] = ATR(
            context.prices.loc[sym, 'high'][-rolling_window:],
            context.prices.loc[sym, 'low'][-rolling_window:],
            context.prices.loc[sym, 'close'][-rolling_window:],
            timeperiod=moving_average
        )[-1]

    if context.is_test:
        assert(len(context.average_true_range) > 0)

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def compute_dollar_volatilities(context, data):
# data is not used
    """
    Compute dollar volatilities, or dollars per point.
    """
    if context.is_timed:
        start_time = time()

    try:
        for sym in context.tradable_symbols:
            context.dollar_volatility[sym] = context.contracts[sym].multiplier\
                * context.average_true_range[sym]
    except KeyError:
        pass

    if context.is_test:
        #assert(len(context.dollar_volatility) > 0)
        pass

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def compute_trade_sizes(context, data):
# data is not used
    """contract
    Compute trade sizes, or amount per trade.
    """
    if context.is_timed:
        start_time = time()

    context.profit = context.portfolio.portfolio_value\
        - context.portfolio.starting_cash

    if context.profit < 0:
        context.capital = context.portfolio.starting_cash\
            + context.profit\
            * context.capital_multiplier

    try:
        if context.capital <= 0:
            for sym in context.tradable_symbols:
                context.trade_size[sym] = 0
        else:
            for sym in context.tradable_symbols:
                context.trade_size[sym] = int(context.capital\
                    * context.capital_risk_per_trade\
                    / context.dollar_volatility[sym])
    except KeyError:
        pass
    except ZeroDivisionError:
        log.info(sym)
        log.info(context.dollar_volatility[sym])
        raise

    if context.is_test:
        #assert(len(context.trade_size) > 0)
        pass

    if context.is_timed:
        time_taken = (time() - start_time) * 1000
        log.debug('Executed in %f ms.' % time_taken)
        assert(time_taken < 1024)

def update_risks(context, data):
# data is not used
    """
    Update long, short, and market risks.
    """
    context.long_risk = 0
    context.short_risk = 0

    for contract in context.contracts:
        sym = contract.root_symbol
        
        try:
            position = context.portfolio.positions[contract]

            if context.market_risk[sym] > 0:
                context.long_risk += abs(context.market_risk[sym])
            elif context.market_risk[sym] < 0:
                context.short_risk += abs(context.market_risk[sym])
        except KeyError:
            continue
        except ZeroDivisionError:
            log.info(sym)
            log.info(position.amount)
            log.info(context.trade_size[sym])
            log.info(context.dollar_volatility[sym])
            raise

def place_stop_orders(context, data):
# data is not used
    """
    Place stop orders at 2 times average true range or continue a stop order that is canceled when market close.
    """
    for contract in context.contracts:
        sym = contract.root_symbol 
        position = context.portfolio.positions[contract]

        try:
            order_info = get_order(context.orders[sym][-1])
        except IndexError:
            continue

        #If the previous order is a limit order that starts to be filled
        if (order_info.filled != 0 and order_info.limit is not None):

            current_highest_price = order_info.limit

            if position.amount > 0:
                context.stop[sym] = current_highest_price\
                - context.average_true_range[sym]\
                * context.stop_multiplier

                order_identifier = order_target(
                    context.contracts[sym],
                    0,
                    style=StopOrder(context.stop[sym])
                )
            elif position.amount < 0:
                context.stop[sym] = current_highest_price\
                    + context.average_true_range[sym]\
                    * context.stop_multiplier

                order_identifier = order_target(
                    context.contracts[sym],
                    0,
                    style=StopOrder(context.stop[sym])
                )
            else:
                order_identifier = None

            if order_identifier is not None:
                context.orders[sym].append(order_identifier)

            if context.is_info:
                log.info(
                    'Stop  %s  %.2f (due to new limit order)'
                    % (
                        sym,
                        context.stop[sym]
                    )
                )

        elif (order_info.stop_reached == False and\
            order_info.stop is not None and order_info.status == 2):
            """
            If stop order is created but canceled due to end of day
            """

            context.stop[sym] = order_info.stop

            if position.amount > 0:
                order_identifier = order_target(
                    context.contracts[sym],
                    0,
                    style=StopOrder(context.stop[sym])
                )
            elif position.amount < 0:
                order_identifier = order_target(
                    context.contracts[sym],
                    0,
                    style=StopOrder(context.stop[sym])
                )
            else:
                order_identifier = None


            if order_identifier is not None:
                context.orders[sym].append(order_identifier)

                if context.is_info:
                    log.info(
                        'Stop  %s  %.2f (due to previous stop order canceled)'
                        % (
                            sym,
                            context.stop[sym]
                        )
                    )


def detect_entry_signals(context, data):
# data is not used
    """
      Place limit orders on 20 or 55 day breakout.
    """
    long_quota = context.direction_risk_limit - math.ceil(context.long_risk)
    short_quota = context.direction_risk_limit - math.ceil(context.short_risk)

    # Exit if we don't have any cash
    if context.portfolio.cash <= 0:
        return

    for sym in context.tradable_symbols:
        price = data.current(context.cfutures[sym], 'price')
        # Get limit price of previous order; if there is no previous order, set limit to None
        try:
            prev_order = get_order(context.orders[sym][-1])
            limit = prev_order.limit
        except IndexError:
            limit = None

        enter_signal = False

        if context.market_risk[sym] == 0 and limit is None:
            if context.previous_trade_won[sym] == False:
                if price > context.strat_one_breakout_high[sym] and long_quota > 0:

                    long_quota -= 1
                    enter_signal = True
                    long_or_short = 1
                    context.is_strat_one[sym] = True
                    context.is_strat_two[sym] = False
                    

                elif price < context.strat_one_breakout_low[sym] and short_quota > 0:

                    short_quota -= 1
                    enter_signal = True
                    long_or_short = -1
                    context.is_strat_one[sym] = True
                    context.is_strat_two[sym] = False

            else:
                if price > context.strat_two_breakout_high[sym] and long_quota > 0 :

                    long_quota -= 1
                    enter_signal = True
                    long_or_short = 1
                    context.is_strat_one[sym] = True
                    context.is_strat_two[sym] = False

                elif price < context.strat_two_breakout_low[sym] and short_quota > 0:

                    short_quota -= 1
                    enter_signal = True
                    long_or_short = -1
                    context.is_strat_one[sym] = True
                    context.is_strat_two[sym] = False

        if enter_signal == True:
            order_identifier = order(
                context.contracts[sym],
                long_or_short * context.trade_size[sym],
                style=LimitOrder(price)
            )

            context.market_risk[sym] = long_or_short

            if order_identifier is not None:
                context.orders[sym].append(order_identifier)

            if context.is_info:

                if context.is_strat_one[sym] == True:
                    strat = "strat 1"
                else:
                    strat = "strat 2"
                
                if long_or_short == 1:
                    log.info(
                        'Long(breakout %s)  %s  %i@%.2f'
                        % (
                            strat,
                            sym,
                            context.trade_size[sym],
                            price
                        )
                    )
                else:
                    log.info(
                        'Short(breakout %s)  %s  %i@%.2f'
                        % (
                            strat,
                            sym,
                            context.trade_size[sym],
                            price
                        )
                    )

#Exit Strategy
def detect_exit_signals(context, data):
    for pos_sid, position in context.portfolio.positions.items():
        market = position.asset.root_symbol

        price = data.current(market, 'price')

        if context.is_strat_one[market]:
            if position.amount > 0:
                if price <= context.strat_one_exit_low[market]:
                    order_identifier = order_target_percent(context.contracts[market], 0)
                    context.market_risk[sym] = 0
                    if order_identifier is not None:
                        context.orders[market].append(order_identifier)
                    context.is_strat_one[market] = False
                    log.info(
                        'Exit  %s  @%.2f'
                        % (
                            market,
                            price
                        )
                    )

            elif position.amount< 0:
                if price >= context.strat_one_exit_high[market]:
                    order_identifier = order_target_percent(context.contracts[market], 0)
                    context.market_risk[sym] = 0
                    if order_identifier is not None:
                        context.orders[market].append(order_identifier)
                    context.is_strat_one[market] = False
                    log.info(
                        'Exit  %s  @%.2f'
                        % (
                            market,
                            price
                        )
                    )


        elif context.is_strat_two[market]:
            if position.amount > 0:
                if price <= context.strat_two_exit_low[market]:
                    order_identifier = order_target_percent(context.contracts[market], 0)
                    context.market_risk[sym] = 0
                    if order_identifier is not None:
                        context.orders[market].append(order_identifier)
                    context.is_strat_one[market] = False
                    log.info(
                        'Exit  %s  @%.2f'
                        % (
                            market,
                            price
                        )
                    )

            elif position.amount < 0:
                if price >= context.strat_two_exit_high[market]:
                    order_identifier = order_target_percent(context.contracts[market], 0)
                    context.market_risk[sym] = 0
                    if order_identifier is not None:
                        context.orders[market].append(order_identifier)
                    context.is_strat_one[market] = False
                    log.info(
                        'Exit  %s  @%.2f'
                        % (
                            market,
                            price
                        )
                    )

def scaling_signals(context,data):

    for market in context.tradable_symbols:
        if context.market_risk[market] != 0 and \
            abs(round(context.market_risk[market])) < context.market_risk_limit:
            if  get_order(context.orders[market][-1]).limit is None:
                """
                'the condition in second if' is to make sure this market did not enter breakout just now because the only reason that the lastest
                order is a limit order is that the position is entered via breakout just now

                Also, we have to make use of the latest order_id's stop price to determine the scaling signal so we can
                """

                price = data.current(context.cfutures[market], 'price')
                # test if it is stop order. If it is not stop order as well, it is a market order from converting limit to market order by the end of the day

                if get_order(context.orders[market][-1]).stop is None:
                    continue


                if context.market_risk[market] > 0:
                    if price > get_order(context.orders[market][-1]).stop + (2.5)*(context.average_true_range[market]):

                        order_identifier = order(
                        context.contracts[market],
                        context.trade_size[market],
                        style=LimitOrder(price)
                        )
                        context.market_risk[sym] += 1

                        if order_identifier is not None:
                            context.orders[market].append(order_identifier)
                            
                            log.info('long(scaling)  %s  %i@%.2f'
                                     %(
                                        market,
                                        context.trade_size[market],
                                        price
                                    )
                            )


                elif context.market_risk[market] < 0:
                    if price < get_order(context.orders[market][-1]).stop - (2.5) * (context.average_true_range[market]):

                        order_identifier = order(
                        context.contracts[market],
                        -context.trade_size[market],
                        style=LimitOrder(price)
                        )
                        context.market_risk[sym] -= 1

                        if order_identifier is not None:
                            context.orders[market].append(order_identifier)
                            
                            log.info('short(scaling)  %s  %i@%.2f'
                                     %(
                                        market,
                                        context.trade_size[market],
                                        price
                                    )
                            )

def stop_trigger_cleanup(context,data):

    for market in context.tradable_symbols:
        try:
            order_info = get_order(context.orders[market][-1])
            stop_reached = order_info.stop_reached
        except IndexError:
            stop_reached = None

        if stop_reached == True:
            current_open_orders = get_open_orders(order_info.sid)

            for open_order in current_open_orders:
                cancel_order(open_order)
            
            context.market_risk[sym] = 0


def turn_limit_to_market_orders(context,data):
    unfilled_orders = get_open_orders()

    for stocks, orders in unfilled_orders.items():
        for unfilled_order in orders:
            asset = unfilled_order.sid.root_symbol

            if unfilled_order.limit is not None:
                order_identifier = order(context.contracts[asset], (unfilled_order.amount - unfilled_order.filled))

                if order_identifier is not None:
                    context.orders[asset].append(order_identifier)
                    
                    log.info('%s limit order is turned to market order so to fill better before market close' %(asset))

                cancel_order(unfilled_order)


def analyzing_trade_for_next_signal(context,data):

    for market in context.tradable_symbols:

        price = data.current(market, 'price')

        if context.position_analytics[market]['state'] == 0:
            if price > context.strat_one_breakout_high[market] or price < context.strat_one_breakout_low[market]:

                context.position_analytics[market]['state'] = 1
                context.position_analytics[market]['entry'] = price

                if price > context.strat_one_breakout_high[market]:

                    context.position_analytics[market]['stop']  = price - 2 * context.average_true_range[market]
                    context.position_analytics[market]['exit']  = context.strat_one_exit_low[market]

                else:
                    context.position_analytics[market]['stop']  = price + 2 * context.average_true_range[market]
                    context.position_analytics[market]['exit']  = context.strat_one_exit_high[market]

        elif 0 < context.position_analytics[market]['state'] and context.position_analytics[market]['state'] < 4 and\
            price > context.position_analytics[market]['entry'] + 0.5 * context.average_true_range[market]:

                context.position_analytics[market]['state'] += 1
                context.position_analytics[market]['entry'] = price
                context.position_analytics[market]['stop']  = price - 2 * context.average_true_range[market]
                context.position_analytics[market]['exit']  = context.strat_one_exit_low[market]

        elif -4 < context.position_analytics[market]['state'] and context.position_analytics[market]['state'] < 0 and\
            price < context.position_analytics[market]['entry'] - 0.5 * context.average_true_range[market]:

                context.position_analytics[market]['state'] -= 1
                context.position_analytics[market]['entry'] = price
                context.position_analytics[market]['stop']  = price + 2 * context.average_true_range[market]
                context.position_analytics[market]['exit']  = context.strat_one_exit_high[market]

        elif context.position_analytics[market]['state'] > 0 and price < context.position_analytics[market]['stop'] or\
            context.position_analytics[market]['state'] < 0 and price > context.position_analytics[market]['stop']:

                context.position_analytics[market] = {'state' :0, 'entry':0, 'stop' : 0, 'exit' : 0}
                context.previous_trade_won[market] = False

        elif context.position_analytics[market]['state'] > 0 and price < context.position_analytics[market]['exit']:

            profit = 0

            x = 1
            while x <= context.position_analytics[market]['state']:
                context.profit += context.position_analytics[market]['exit'] - \
                          (context.position_analytics[market]['entry'] + (0.5) * (x-1) * context.average_true_range[market])
                x += 1

            if profit > 0:
                context.previous_trade_won[market] = True
            elif profit < 0:
                context.previous_trade_won[market] = False

            context.position_analytics[market] = {'state' :0, 'entry':0, 'stop' : 0, 'exit' : 0}


        elif context.position_analytics[market]['state'] < 0 and price > context.position_analytics[market]['exit']:

            profit = 0

            x = 1
            while x <= context.position_analytics[market]['state']:
                profit += (context.position_analytics[market]['entry'] - (0.5) * (x-1) * context.average_true_range[market]) - \
                               context.position_analytics[market]['exit']

                x += 1

            if profit > 0:
                context.previous_trade_won[market] = True
            elif profit < 0:
                context.previous_trade_won[market] = False

            context.position_analytics[market] = {'state' :0, 'entry':0, 'stop' : 0, 'exit' : 0}

