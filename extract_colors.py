import sys
from PIL import Image

def extract_colors(image_path):
    img = Image.open(image_path).convert('RGB')
    w, h = img.size
    y = h // 2
    # The image has 4 blocks. Let's sample at 12.5%, 37.5%, 62.5%, 87.5% width
    xs = [int(w * 0.125), int(w * 0.375), int(w * 0.625), int(w * 0.875)]
    for i, x in enumerate(xs):
        r, g, b = img.getpixel((x, y))
        print(f"Color {i+1}: #{r:02x}{g:02x}{b:02x}")

if __name__ == '__main__':
    extract_colors(sys.argv[1])
