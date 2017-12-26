import math
import numpy as np
import pandas as pd
from time import time
from talib import ATR

def initialize(context):
    """
    Initialize parameters.
    """
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

    context.required_information = [
        'cfutures', #ok
        'keep track or trade', # trading or keeping track the performance #format: keep_track/trade
        'type of breakout', # format: strat_one/two_long/short
        'scale-in stage',
        'quantity', #ok
        'avg price', #ok/
        'initial entry time',
        'second entry time',
        'third entry time',
        'fourth entry time',
        'stop loss price',
        'exit price', #ok
        'ATR', #ok
        'unit size', #ok
        'strat 1 long breakout price', #ok
        'strat 1 short breakout price', #ok
        'strat 2 long breakout price', #ok
        'strat 2 short breakout price', #ok
        'current contract', #ok
        'auto close date', #ok
        'profit of last trade',
        'was last strat 1 trade winning', #bool
    ]

    #creating a Master Table
    context.MT= pd.DataFrame(data = None, index = context.symbols, columns = context.required_information)
    context.MT'scale-in stage'] = 0

    context.cfutures = {symbol: continuous_future(symbol , offset = 0, roll = 'calendar' , adjustment = 'mul') for symbol in context.symbols}

    #initializations
    context.latest_trade_orders={}
    context.latest_stop_orders={}

    # Breakout and exit signals
    context.strat_one_breakout = 20
    context.strat_one_exit = 10
    
    context.strat_two_breakout = 55
    context.strat_two_exit = 20

    # Risk
    context.tradable_capital = context.portfolio.starting_cash
    context.capital_risk_per_trade = 0.01
    context.capital_lost_multiplier = 2

    context.market_risk_limit = 4
    context.direction_risk_limit = 12
    context.stop_loss_in_N = 2

    # Order
    context.open = 0
    context.filled = 1
    context.canceled = 2
    context.rejected = 3

    
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
        compute_breakout_price,
        date_rules.every_day(),
        time_rules.market_open(),
        False
    )
    schedule_function(
        compute_exit_price,
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

    #repeating functions

    total_minutes = 6*60+30
    for i in range(30, total_minutes, 30):
        schedule_function(
            fetch_position_info,
            date_rules.every_day(),
            time_rules.market_open(minutes=i)
            False
        )

        schedule_function(
            compute_average_true_ranges,
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

        schedule_function(
            detect_entry_signals,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )

        schedule_function(
            detect_scaling_signals,
            date_rules.every_day(),
            time_rules.market_open(minutes=i),
            False
        )        

#not scheduled functions

def update_trade_orders(context,data,sym,order_identifier):
    "to update the latest order"
    try:
         old_order = context.latest_trade_orders[sym]
         if get_order(old_order).status == context.open:
             cancel_order(old_order)
    except KeyError:
        pass
    
    context.latest_trade_orders[sym] = order_identifier 



#Start of day functions

def get_prices(context, data):
    """
    Get high, low, and close prices.
    """

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
    
    # Tranpose/Reindex panel in axes with:
    # (Index: symbol, Major-axis: field, Minor-axis: date)
    context.prices = context.prices.transpose(2, 0, 1)
    context.prices = context.prices.reindex()
    syms = {future: future.root_symbol for future in context.prices.axes[0]}
    context.prices = context.prices.rename(items=syms)

def validate_prices(context, data):
# data is not used
    """
    Drop markets with null prices.
    """
    context.prices.dropna(axis=0, inplace=True)
    validated_markets = context.prices.axes[0]
    dropped_markets = list(
        set(context.symbols) - set(validated_markets)
    )

    context.tradable_symbols = validated_markets
    context.MT.loc[dropped_markets] = None

    log.info(
        'Null prices for %s. Dropped.'
        % ', '.join(dropped_markets)
    )

def compute_breakout_price(context, data):
# data is not used
    """
    Compute high and low for breakout price
    """
    for sym in context.tradable_symbols:
        context.MT.loc[sym]['strat 1 long breakout price'] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_one_breakout-1:-1]\
            .max()
        context.MT.loc[sym]['strat 2 long breakout price'] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_two_breakout-1:-1]\
            .max()
        
        context.MT.loc[sym]['strat 1 short breakout price'] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_one_breakout-1:-1]\
            .min()
        context.MT.loc[sym]['strat 2 short breakout price'] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_two_breakout-1:-1]\
            .min()

def compute_exit_price(context,data):
    """
    Compute Exit Price
    """
    exit_prices[sym]['strat_one_long'] = context.prices.loc[sym, 'low']\
        [-context.strat_one_exit-1:-1].min()

    exit_prices[sym]['strat_one_short'] = context.prices.loc[sym, 'high']\
        [-context.strat_one_exit-1:-1].max()

    exit_prices[sym]['strat_two_long'] = context.prices.loc[sym, 'low']\
        [-context.strat_two_exit-1:-1].min()

    exit_prices[sym]['strat_two_short'] = context.prices.loc[sym, 'high']\
        [-context.strat_two_exit-1:-1].max()
    
    for sym in context.tradable_symbols:
        context.MT['exit price'] = exit_prices[sym]\
            [context.MT[sym]['type of breakout']]


def get_contracts(context, data):
    """
    Get futures contracts using the dict of continuous futures objects
    The returned pd.panel from data.current() is reindex to use symbol string as key
    """

    cfutures = [v for k, v in context.cfutures.items()]
    fields = 'contract'

    # Dataframe indexed with date, and columned with security as according to API spec
    contracts = data.current(
        cfutures,
        fields
    )
    
    contracts = contracts.transpose()
    contracts.dropna(axis=0, inplace=True)
    contracts = contracts.rename_axis(lambda k: k.root_symbol, axis=0)

    for sym in context.tradable_symbols
    context.MT.loc[sym]['current contract'] = contracts[sym]


def check_rollover(context, data):
    """
    see if the contract has rollovered
    """
    for sym in context.tradable_symbols:
        current_auto_close_date = context.MT[sym]['current contract'].auto_close_date
               
        if current_auto_close_date != context.MT[sym]['auto close date']:
                if context.MT.loc[sym]['scale-in stage'] != 0:
                    price = data.current(context.cfutures[sym], 'price')
                    order_identifier = order(
                        context.MT.loc[sym]['current contract'],
                        context.MT.loc[sym]['quantity'],
                        style = LimitOrder(price)
                    )

                    if order_identifier is not None:
                        update_trade_orders(context,data,sym,order_identifier)

                    log.info(
                        'rollover %s %i@%.2f'
                        %(
                            sym,
                            context.MT.loc[sym]['quantity'],
                            price
                        )
                    )
    
        context.MT[sym]['auto close date'] = current_auto_close_date

# repeating functions

def fetch_position_info(context, data):
    context.MT['quantity'].mask(
        context.MT['keep track or trade'] == 'trade',
        context.portfolio.positions[context.MT['current contract']].amount,
        inplace=True
    )

    context.MT['avg price'].mask(
        context.MT['keep track or trade'] == 'trade',
        context.portfolio.positions[context.MT['current contract']].cost_basis,
        inplace=True
    )

           

def compute_average_true_ranges(context, data):
    """
    Compute ATR, aka N
    """

    rolling_window = context.strat_one_breakout+1
    moving_average = context.strat_one_breakout

    for sym in context.tradable_symbols:
        context.MT[sym]['ATR'] = ATR(
            context.prices.loc[sym, 'high'][-rolling_window:],
            context.prices.loc[sym, 'low'][-rolling_window:],
            context.prices.loc[sym, 'close'][-rolling_window:],
            timeperiod=moving_average
        )[-1]


def compute_trade_sizes(context, data):
    """
    how many unit equivilants to 1% of equity
    """
    for sym in context.tradable_symbols:
        dollar_volatility = context.contracts[sym].multiplier\
            * context.MT[sym]['ATR']

        context.MT[sym]['unit size'] = int(context.tradable_capital/dollar_volatility)

def update_risks(context,data):
    """
    Calculate long and short risk and calculate quota for long and short
    """

    tradingMT = context.MT[context.MT['keep track or trade'] == 'trade']
    long_risk_numbers = [x for x in tradingMT['scale-in stage'] if x > 0]
    short_risk_numbers = [x for x in tradingMT['scale-in stage'] if x < 0]

    context.long_risk = sum(long_risk_numbers)
    context.short_risk = sum(short_risk_numbers)

    context.long_quota = context.direction_risk_limit - context.long_risk
    context.short_quota = context.direction_risk_limit - context. short_risk

def detect_entry_signals(context,data):
    """
    Place limit orders when reach breakout
    hirachy of entry signals: strat 1 > strat 2 > keep track
    """
    for sym in context.tradable_symbols:

        if context.MT[sym]['scale in stage'] != 0:
            continue
    
        long_or_short = 0
        current_price = data.current(context.cfutures[sym], 'price')

        #check strat 1 breakout
        if context.MT[sym]['was last strat 1 trade winning'] != True:

            if (context.long_quota > 0 and
                current_price >= context.MT[sym]['strat 1 long breakout price']):

                context.MT[sym]['scale in stage'] = 1
                context.MT[sym]['type of breakout'] = 'strat_one_long'
                context.MT[sym]['keep track or trade'] = 'trade'
                context.long_quota -= 1
                long_or_short = 1

            else if (context.short_quota > 0 and
                     current_price <= context.MT[sym]['strat 1 short breakout price']):

                context.MT[sym]['scale in stage'] = -1
                context.MT[sym]['type of breakout'] = 'strat_one_short'
                context.MT[sym]['keep track or trade'] = 'trade'
                context.short_quota -= 1
                long_or_short = -1
        
        #check strat 2 breakout
        else:
            if (context.long_quota > 0 and
                current_price >= context.MT[sym]['strat 2 long breakout price']):

                context.MT[sym]['scale in stage'] = 1
                context.MT[sym]['type of breakout'] = 'strat_two_long'
                context.MT[sym]['keep track or trade']= 'trade'
                context.long_quota -= 1
                long_or_short = 1

            else if (context.short_quota > 0 and
                     current_price <= context.MT[sym]['strat 2 short breakout price']:
                       
                context.MT[sym]['scale in stage'] = -1
                context.MT[sym]['type of breakout'] = 'strat_two_short'
                context.MT[sym]['keep track or trade']= 'trade'
                context.short_quota -= 1
                long_or_short = -1

        #check keep track
        else:

            if current_price >= context.MT[sym]['strat 1 long breakout price']:
                context.MT[sym]['scale in stage'] = 1
                context.MT[sym]['type of breakout'] = 'strat_one_long'
                context.MT[sym]['keep track or trade'] = 'keep_track'

            else if current_price <= context.MT[sym]['strat 1 short breakout price']:
                context.MT[sym]['scale in stage'] = -1
                context.MT[sym]['type of breakout'] = 'strat_one_short'
                context.MT[sym]['keep track or trade'] = 'keep_track'         
 

        if long_or_short != 0:
            context.MT[sym]['initial entry time'] = get_datetime()

            order_identifier = order(
                context.MT[sym]['current contract'],
                long_or_short * context.MT[sym]['unit size'],
                style = LimitOrder(current_price)
            )
            update_trade_orders(context,data,sym,order_identifier)

            log.info(
                '%s(breakout) %s %i@%.2f'
                %(
                    context.MT[sym]['type of breakout'],
                    sym,
                    context.MT[sym]['unit size'],
                    current_price  
                )
            )

def detect_scaling_signals(context,data)
    """
    Place limit orders when reach scaling signals
    """
    for sym in context.tradable_symbols:
        
        if context.MT[sym]['scale in stage'] == 0 or ABS(context.MT[sym]['scale in stage']) == 4:
            continue
        
        