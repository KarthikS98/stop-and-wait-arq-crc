import zlib

def crc16_ccitt(data: bytes, poly: int = 0x1021, init_crc: int = 0xFFFF) -> int:
    crc = init_crc
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF  # Keep CRC 16-bit
    return crc

def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF

# Example usage:
if __name__ == "__main__":
    user_input = input("Enter data to calculate CRC-16-CCITT and CRC32: ")
    data = user_input.encode()
    crc16 = crc16_ccitt(data)
    crc32_val = crc32(data)
    print(f"CRC-16-CCITT of '{user_input}': {crc16:04X}")
    print(f"CRC32 of '{user_input}': {crc32_val:08X}") 