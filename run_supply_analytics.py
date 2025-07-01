#!/usr/bin/env python3
"""
Tellor Supply Analytics Runner

Simple executable script to run the supply analytics collector.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from tellor_supply_analytics.supply_collector import main

if __name__ == '__main__':
    main()