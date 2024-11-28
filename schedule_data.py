from icalendar import Calendar
from datetime import datetime, time
from dateutil.rrule import rrulestr
import pytz
import boto3
from flask import session

S3_BUCKET = "schedule-data-bucket"

def read_file_from_s3(bucket_name):
    """Read file contents directly from S3.
    
    Args:
        bucket_name (str): Name of the S3 bucket
        
    Returns:
        dict: S3 object containing the file data
        None: If file not found or error occurs
    """
    if not session.get('user_id'):
        return None
        
    s3 = boto3.client("s3")
    key = f"user {session['user_id']} schedule"
    
    try:
        return s3.get_object(Bucket=bucket_name, Key=key)
    except boto3.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            print(f"No schedule found for user {session['user_id']}")
        elif error_code == 'NoSuchBucket':
            print(f"Bucket {bucket_name} does not exist")
        else:
            print(f"AWS Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def time_to_block_index(dt):
    """Convert a datetime to block index (0-31)"""
    t = dt.time()
    minutes_since_8am = (t.hour - 8) * 60 + t.minute
    return max(0, min(31, minutes_since_8am // 30))  # Ensure index is between 0 and 31

def process_calendar_file(calendar_file):

    """
    Process an ICS calendar file and return a weekly availability string.
    Marks entire blocks as busy if any part of an event falls within that block.
    """
    week_availability = ['1'] * (32 * 7)  # 224 total blocks
    cal = Calendar.from_ical(calendar_file.read())

    # Process calendar events
    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get('dtstart').dt
            dtend = component.get('dtend').dt
            
            # Skip if not datetime
            if not isinstance(dtstart, datetime):
                continue
                
            # Calculate block indices with ceiling for start and floor for end
            start_minutes = (dtstart.hour - 8) * 60 + dtstart.minute
            end_minutes = (dtend.hour - 8) * 60 + dtend.minute
            
            # If event starts in middle of block, mark entire block as busy
            start_block = max(0, min(31, start_minutes // 30))
            # If event ends in middle of block, mark entire block as busy
            end_block = max(0, min(31, (end_minutes + 29) // 30))
            
            # Handle single events (no RRULE)
            if not component.get('rrule'):
                weekday = dtstart.weekday()
                for block in range(start_block, end_block):
                    week_availability[weekday * 32 + block] = '0'
            else:
                # Handle recurring events
                rrule = component.get('rrule')
                byday = rrule.get('byday', [])
                day_mapping = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
                
                # Mark blocks as unavailable for each day this event occurs
                for day in byday:
                    weekday = day_mapping[day]
                    for block in range(start_block, end_block):
                        week_availability[weekday * 32 + block] = '0'
    
    return ''.join(week_availability)

def compress_availability(availability_string):
    """Compress availability string using letters for busy blocks (0s) and numbers for free blocks (1s)"""
    if not availability_string:
        return ""
        
    compressed = ""
    current_char = availability_string[0]
    count = 1
    
    for i in range(1, len(availability_string)):
        if availability_string[i] == current_char:
            count += 1
        else:
            if current_char == '1':
                compressed += str(count)
            else:
                compressed += chr(ord('a') + count - 1)
            current_char = availability_string[i]
            count = 1
    
    # Handle the last group
    if current_char == '1':
        compressed += str(count)
    else:
        compressed += chr(ord('a') + count - 1)
        
    return compressed

def decompress_availability(compressed_string):
    """
    Decompress string back to binary format
    Example: "3c2a3" -> "111000110111"
    """
    binary = ""
    number_buffer = ""
    
    for char in compressed_string:
        if char.isdigit():
            # Accumulate digits into number_buffer
            number_buffer += char
        else:
            # If we had numbers before this letter, process them
            if number_buffer:
                binary += '1' * int(number_buffer)
                number_buffer = ""
            
            # Process the letter (sequences of 0s)
            num_zeros = ord(char) - ord('a') + 1
            binary += '0' * num_zeros
    
    # Handle any remaining numbers at the end
    if number_buffer:
        binary += '1' * int(number_buffer)
            
    return binary

def compare_availability(user_availability1, user_availability2):
    """
    Compare two availability strings and return the number of blocks where both users are available.
    Only counts blocks where both strings have '1' (available).
    
    Args:
        user_availability1 (str): First user's compressed availability string
        user_availability2 (str): Second user's compressed availability string
    
    Returns:
        int: Number of time blocks where both users are available
    """
    avail1 = decompress_availability(user_availability1)
    avail2 = decompress_availability(user_availability2)
    return sum(1 for i in range(len(avail1)) if avail1[i] == '1' and avail2[i] == '1')

def constructor_availability(user_unavailability_blocks):
    """
    Create a compressed availability string from a list of unavailability blocks
    """
    availability_string = ['1'] * (32 * 7)
    for block in user_unavailability_blocks:
        start_block = time_to_block_index(block[0])
        end_block = time_to_block_index(block[1])
        for block in range(start_block, end_block):
            availability_string[block] = '0'
    return compress_availability(''.join(availability_string))

def preference_comparison(priority_user, priority_buddy):
    environ_user, location_user, objective_user = priority_user
    environ_buddy, location_buddy, objective_buddy = priority_buddy
    
    score = 0
    # For each preference:
    # Match = 1.0
    # One None = 0.5
    # Mismatch = 0.0
    for pref_user, pref_buddy in [(environ_user, environ_buddy), 
                                 (location_user, location_buddy), 
                                 (objective_user, objective_buddy)]:
        if pref_user == pref_buddy and pref_user is not None:
            score += 1.0
        elif pref_user is None or pref_buddy is None:
            score += 0.5
        
            
    return score 


