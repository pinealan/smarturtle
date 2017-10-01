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
    'keep track or trade', # whether we are keeping track of winning or losing or really trading
    'type of breakout',
    'scale-in stage',
    'total contracts',
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
    'contract name',
    'auto close date',
    'profit of last trade',
    'was last trade winning',
]
master_table= pd.dataframe(index = context.symbols, columns = context.required_information)