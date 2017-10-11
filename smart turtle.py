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
        'cfutures',
        'keep track or trade', # whether we are keeping track of winning or losing or really trading
        'type of breakout',
        'scale-in stage',
        'total quantity',
        'initial price',
        'second price',
        'third price',
        'fourth price',
        'stop loss price',
        'exit price',
        'ATR',
        'N',
        'current price',
        'strat 1 long breakout price',
        'strat 1 short breakout price',
        'strat 2 long breakout price',
        'strat 2 short breakout price',
        'current contract',
        'auto close date',
        'profit of last trade',
        'was last trade winning',
    ]
    context.master_table= pd.DataFrame(data = None, index = context.symbols, columns = context.required_information)
    context.master_table'scale-in price'] = 0

    context.cfutures = {symbol: continuous_future(symbol , offset = 0, roll = 'calendar' , adjustment = 'mul') for symbol in context.symbols}

    #initializations
    context.latest_trade_orders={}
    context.latest_stop_orders={}

    # Breakout signals
    context.strat_one_breakout = 20
    context.strat_one_exit = 10
    
    context.strat_two_breakout = 55
    context.strat_two_exit = 20

    # Risk
    context.capital = context.portfolio.starting_cash
    context.capital_risk_per_trade = 0.01
    context.capital_multiplier = 2

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

#not scheduled functions

def update_trade_orders(context,data,sym,order_identifier):
    "to update the latest order"
    try:
         old_order = context.latest_trade_orders[sym]
         if get_order(old_order).status == context.open:
             cancel_order(old_order)
    except KeyError:
        pass
    
    order_identifier = context.latest_trade_orders[sym]




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
    context.master_table.loc[dropped_markets] = None

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
        context.master_table.loc[sym]['strat 1 long breakout price'] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_one_breakout-1:-1]\
            .max()
        context.master_table.loc[sym]['strat 2 long breakout price'] = context.prices\
            .loc[sym, 'high']\
            [-context.strat_two_breakout-1:-1]\
            .max()
        
        context.master_table.loc[sym]['strat 1 short breakout price'] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_one_breakout-1:-1]\
            .min()
        context.master_table.loc[sym]['strat 2 short breakout price'] = context.prices\
            .loc[sym, 'low']\
            [-context.strat_two_breakout-1:-1]\
            .min()

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
    context.master_table.loc[sym]['current contract'] = contracts[sym]


def check_rollover(context, data):
    """
    see if the contract has rollovered
    """
    for sym in context.tradable_symbols:
        current_auto_close_date = context.master_table[sym]['current contract'].auto_close_date
               
        if current_auto_close_date != context.master_table[sym]['auto close date']:
                if context.master_table.loc[sym]['scale-in stage'] != 0:
                    price = data.current(context.cfutures[sym], 'price')
                    order_identifier = order(
                        context.master_table.loc[sym]['current contract'],
                        context.master_table.loc[sym]['total quantity'],
                        style = LimitOrder(price)
                    )

                    if order_identifier is not None:
                        update_trade_orders(context,data,sym,order_identifier)

                    log.info(
                        'rollover %s %i@%.2f'
                        %(
                            sym,
                            context.master_table.loc[sym]['total quantity'],
                            price
                        )
                    )
    
        context.master_table[sym]['auto close date'] = current_auto_close_date
