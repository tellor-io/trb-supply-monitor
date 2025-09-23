"""
Command to estimate future block time based on a given block height
"""
import sys
import pandas as pd
import datetime
import pytz
from pathlib import Path


def estimate_future_time(target_height):
    """
    Estimate the real-world date and time when a specific future block height will be reached
    
    Args:
        target_height (int): The future block height to estimate
        
    Returns:
        tuple: (estimated_datetime, seconds_until, avg_block_time, current_height)
    """
    try:
        # Get current block height and time
        current_height, current_block_time = get_block_info()
        print(f"Current block height: {current_height}")
        print(f"Current block time: {current_block_time}")
        print(f"Target block height: {target_height}")
        
        if current_height is None or current_block_time is None:
            print("Error: Could not get current block information")
            return None, None, None, None
            
        # Check if target height is valid
        if target_height <= current_height:
            print(f"Error: Target height ({target_height}) must be greater than current height ({current_height})")
            return None, None, None, None
            
        # Calculate blocks remaining
        blocks_remaining = target_height - current_height
        
        # Get historical block time stats
        stats = get_block_time_stats()
        
        # Determine which time period to use for estimation (prefer shorter time periods if available)
        # This gives more accurate recent data
        avg_block_time = None
        used_timeframe = None
        
        for timeframe in ["five_min", "thirty_min", "sixty_min", "day", "week"]:
            if isinstance(stats[timeframe], str) and "seconds" in stats[timeframe]:
                # Extract number from strings like "1.23 seconds"
                avg_block_time = float(stats[timeframe].split()[0])
                used_timeframe = timeframe
                break
        
        # If no historical data available, check if we can use recent data from the CSV
        if avg_block_time is None:
            try:
                # Try to read CSV file and get average from recent records
                df = pd.read_csv(CSV_FILE)
                if not df.empty:
                    # Get average of most recent records with valid avg_block_time
                    recent_records = df.tail(10)  # Try last 10 records
                    valid_records = recent_records.dropna(subset=['avg_block_time'])
                    
                    if not valid_records.empty:
                        avg_block_time = valid_records['avg_block_time'].mean()
                        used_timeframe = "recent records"
            except Exception as e:
                print(f"Error reading CSV data: {e}")
                
        # If still no data, use default estimate of 3 seconds per block
        if avg_block_time is None:
            avg_block_time = 3.0  # Default assumption
            used_timeframe = "default value"
            print("Warning: No historical block time data available. Using default estimate of 3 seconds per block.")
            
        # Calculate estimated time until target block
        seconds_until = blocks_remaining * avg_block_time
        
        # Calculate estimated date/time of target block
        estimated_datetime = current_block_time + datetime.timedelta(seconds=seconds_until)
        
        # Print the source of our estimate
        print(f"Using average block time of {avg_block_time:.2f} seconds from {used_timeframe}")
        
        return estimated_datetime, seconds_until, avg_block_time, current_height
        
    except Exception as e:
        print(f"Error estimating future block time: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None

def format_time_until(seconds):
    """Format seconds into a human-readable time format"""
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{int(minutes)} minutes"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f} hours"
    else:
        days = seconds / 86400
        return f"{days:.1f} days"

def estimate(height, timezone=None):
    """
    Estimate when a future block height will be reached
    
    Args:
        height (int): The future block height
        timezone (str, optional): User's local timezone (e.g., 'America/New_York', 'Europe/London')
    
    Returns:
        bool: True if estimation was successful, False otherwise
    """
    try:
        # Convert height to integer
        target_height = int(height)
        
        # Get the estimated time
        estimated_time, seconds_until, avg_block_time, current_height = estimate_future_time(target_height)
        
        if estimated_time is None:
            return False
            
        # Use user's timezone if provided, otherwise use UTC
        if timezone:
            try:
                local_tz = pytz.timezone(timezone)
                local_time = estimated_time.astimezone(local_tz)
                timezone_name = local_tz.zone
            except pytz.exceptions.UnknownTimeZoneError:
                print(f"Unknown timezone: {timezone}. Using UTC time instead.")
                local_time = estimated_time.astimezone(pytz.UTC)
                timezone_name = "UTC"
        else:
            # Use UTC as the default fallback
            local_time = estimated_time.astimezone(pytz.UTC)
            timezone_name = "UTC"
            
            # Try to get the system timezone for better user experience
            try:
                system_tz = datetime.datetime.now().astimezone().tzinfo
                if hasattr(system_tz, 'zone'):
                    timezone_name = system_tz.zone
                    local_tz = pytz.timezone(timezone_name)
                    local_time = estimated_time.astimezone(local_tz)
                else:
                    # Include system timezone offset if zone name isn't available
                    offset = datetime.datetime.now().astimezone().strftime('%z')
                    timezone_name = f"UTC{offset}"
            except Exception:
                # If anything goes wrong, just use UTC as fallback
                pass
        
        # Format the output
        print("\n=== Block Time Estimation ===")
        print(f"Current block height: {current_height}")
        print(f"Target block height: {target_height}")
        print(f"Blocks remaining: {target_height - current_height}")
        print(f"Estimated time until target: {format_time_until(seconds_until)}")
        print(f"Estimated arrival (UTC): {estimated_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"Estimated arrival ({timezone_name}): {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("===========================\n")
        
        return True
    except Exception as e:
        print(f"Error in estimation: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # If run directly, test with current height + 1000
    current_height, _ = get_block_info()
    if current_height:
        estimate(current_height + 1000)
    else:
        print("Could not get current block height for testing")