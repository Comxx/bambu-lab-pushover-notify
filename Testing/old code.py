import requests
from datetime import datetime

class ErrorHandler:
    def __init__(self):
        self.last_fetch_time = None
        self.cached_data = None

    def decimal_to_hex_without_leading_zeros(self, decimal_error_code):
        # Convert the decimal number to a hexadecimal string without the '0x' prefix
        hex_error_code = hex(decimal_error_code)[2:]
        
        # Add a leading zero if necessary to ensure the string always starts with a zero
        if len(hex_error_code) % 2 != 0:
            hex_error_code = '0' + hex_error_code
        
        return hex_error_code

    def fetch_english_errors(self):
        if self.last_fetch_time is None or (datetime.now() - self.last_fetch_time).days >= 1:
            url = "https://e.bambulab.com/query.php?lang=en"
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                data = response.json()
                self.last_fetch_time = datetime.now()
                self.cached_data = data["data"]["device_hms"]["en"]
                return self.cached_data
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch data: {e}")
                return None
            except json.JSONDecodeError:
                print("Failed to decode JSON from response")
                return None
            except Exception as e:
                print(f"Unexpected error in fetch_english_errors: {e}")
                return None
        else:
            return self.cached_data

    def search_error(self, error_code, english_errors):
        try:
            for error in english_errors:
                if error["ecode"] == error_code:
                    return error
            return None
        except Exception as e:
            print(f"Unexpected error in search_error: {e}")
            return None

# Example usage
if __name__ == "__main__":
    handler = ErrorHandler()
    decimal_error_code = 117538823
    hex_error_code = handler.decimal_to_hex_without_leading_zeros(decimal_error_code)
    english_errors = handler.fetch_english_errors() or []
    found_device_error = handler.search_error(hex_error_code, english_errors)

    print(f"Hexadecimal code: {hex_error_code}")
    if found_device_error:
        print(f"Found device error: {found_device_error}")
    else:
        print("No matching device error found.")
