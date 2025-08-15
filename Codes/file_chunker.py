def file_chunker(file_path, chunk_size=1024):
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

if __name__ == "__main__":
    path = input("Enter file path to chunk: ")
    size = int(input("Enter chunk size (bytes): ") or 1024)
    for i, chunk in enumerate(file_chunker(path, size)):
        print(f"Chunk {i} (size {len(chunk)}): {chunk[:32]}{'...' if len(chunk) > 32 else ''}") 