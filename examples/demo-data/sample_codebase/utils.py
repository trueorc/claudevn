"""Utility functions - has duplicate code and missing error handling."""

import re
import json


def validate_email(email):
    """Validate email format."""
    if not email:
        return False
    
    # Simple regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone):
    """Validate phone number."""
    if not phone:
        return False
    
    # Remove common separators
    cleaned = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    
    # Check if all digits
    if not cleaned.isdigit():
        return False
    
    # Check length
    if len(cleaned) < 10 or len(cleaned) > 15:
        return False
    
    return True


def sanitize_input(text):
    """Sanitize user input - duplicate validation logic."""
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove special characters
    text = re.sub(r'[^\w\s@.-]', '', text)
    
    # Trim whitespace
    text = text.strip()
    
    return text


def validate_input(text, max_length=100):
    """Validate input - duplicate of sanitize_input logic."""
    if not text:
        return False
    
    # Remove HTML tags
    cleaned = re.sub(r'<[^>]+>', '', text)
    
    # Remove special characters
    cleaned = re.sub(r'[^\w\s@.-]', '', cleaned)
    
    # Trim whitespace
    cleaned = cleaned.strip()
    
    # Check length
    if len(cleaned) > max_length:
        return False
    
    return True


def read_config(filename):
    """Read configuration file - missing error handling."""
    with open(filename) as f:  # No try/except!
        config = json.load(f)
    return config


def write_log(message, level="INFO"):
    """Write to log file - missing error handling."""
    with open("app.log", "a") as f:  # No try/except!
        f.write(f"[{level}] {message}\n")


def log_event(event_type, data):
    """Log an event."""
    message = f"{event_type}: {json.dumps(data)}"
    write_log(message)


def fetch_data_from_api(url):
    """Fetch data from external API - missing error handling."""
    import urllib.request
    
    response = urllib.request.urlopen(url)  # No try/except!
    data = response.read()
    return json.loads(data)


def process_file(filename):
    """Process a file - missing error handling."""
    with open(filename) as f:  # No try/except!
        lines = f.readlines()
    
    processed = []
    for line in lines:
        # Some processing
        processed.append(line.strip().upper())
    
    return processed


def calculate_discount(price, discount_percent):
    """Calculate discounted price."""
    if discount_percent < 0 or discount_percent > 100:
        return price
    
    discount_amount = price * (discount_percent / 100)
    return price - discount_amount


def format_currency(amount):
    """Format amount as currency."""
    return f"${amount:.2f}"


def parse_date(date_string):
    """Parse date string - could use better validation."""
    from datetime import datetime
    
    # Try multiple formats
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    return None

