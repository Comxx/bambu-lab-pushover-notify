def decimal_to_hex_without_leading_zeros(decimal_error_code):
    # Convert the decimal number to a hexadecimal string
    hex_error_code = hex(decimal_error_code)[2:]  # `hex()` adds '0x' prefix, so we slice it off with [2:]
    
    # Remove leading zeros
    hex_error_code = hex_error_code.lstrip('0')
    
    # If all characters were zeros, return '0'
    return hex_error_code if hex_error_code else '0'

# Example usage
decimal_error_code = 117538823
hex_error_code = decimal_to_hex_without_leading_zeros(decimal_error_code)
print(f"Hexadecimal code without leading zeros: {hex_error_code}")

decimal_error_code = 256
hex_error_code = decimal_to_hex_without_leading_zeros(decimal_error_code)
print(f"Hexadecimal code without leading zeros: {hex_error_code}")

decimal_error_code = 1
hex_error_code = decimal_to_hex_without_leading_zeros(decimal_error_code)
print(f"Hexadecimal code without leading zeros: {hex_error_code}")

decimal_error_code = 0
hex_error_code = decimal_to_hex_without_leading_zeros(decimal_error_code)
print(f"Hexadecimal code without leading zeros: {hex_error_code}")

decimal_error_code = 16
hex_error_code = decimal_to_hex_without_leading_zeros(decimal_error_code)
print(f"Hexadecimal code without leading zeros: {hex_error_code}")
