import requests
from datetime import datetime

class ErrorHandler:
    def __init__(self):
        self.last_fetch_time = None
        self.cached_data = None
        self.cached_device_error_data = None
        
    def decimal_to_hex(self, decimal_error_code):
        # Convert the decimal number to a hexadecimal string without the '0x' prefix
        hex_error_code = hex(decimal_error_code)[2:]
        
        hex_error_code = hex_error_code.zfill(8)
        return hex_error_code

    def fetch_device_errors(self):
        if self.last_fetch_time is None or (datetime.now() - self.last_fetch_time).days >= 1:
            url = "https://e.bambulab.com/query.php?lang=en"
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()  # Raise an exception for bad status codes
                data = response.json()
                # Print or log the fetched data
                print("Fetched JSON data:")
                print(data)
                self.last_fetch_error_time = datetime.now()
                self.cached_device_error_data = data.get("data", {}).get("device_error", {}).get("en", [])
                return self.cached_device_error_data
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch data: {e}")
                return None
            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON from response: {e}")
                return None
            except Exception as e:
                print(f"Unexpected error in fetch_english_errors: {e}")
                return None
        else:
            return self.cached_device_error_data

    def search_error_device_error(self, error_code, english_errors):
        try:
                # Iterate through the list of error dictionaries
                for error in english_errors:
                    print(f"Loop iteration {error}")
                    if error["ecode"] == error_code:
                        print("fired")
                        return error
                return None
        except KeyError as e:
                print(f"KeyError in search_error: {e}")
                return None
        except Exception as e:
                print(f"Unexpected error in search_error: {e}")
                return None

# Example usage
if __name__ == "__main__":
    handler = ErrorHandler()
    decimal_error_code = 117538823
    hex_error_code = handler.decimal_to_hex(decimal_error_code)
    english_errors = handler.fetch_device_errors() or []
    found_device_error = handler.search_error_device_error(hex_error_code, english_errors)

    print(f"Hexadecimal code: {hex_error_code}")
    if found_device_error:
        print(f"Found device error: {found_device_error}")
    else:
        print("No matching device error found.")
