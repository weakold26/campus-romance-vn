#!/usr/bin/env python3
"""캐릭터 스프라이트 누끼·정렬·WebP 내보내기, 배경 리사이즈."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "downloads", "campus-vn-raw")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "img")

CHARS = {
    "seoyun": ["base", "blush", "surprised", "serious"],
    "chaewon": ["base", "blush", "surprised", "serious"],
}
BGS = ["bg_campus_day", "bg_library", "bg_clubroom", "bg_campus_night"]

MX_T, SAT_T, ERODE, BLUR = 250, 8, 3, 0.7


def alpha_of(path):
    """흰 배경을 바깥에서 채워 실루엣을 잡고, 테두리 색을 안쪽 색으로 바꾼다."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    ink = (mx < MX_T) | ((mx - mn) > SAT_T)

    m = Image.fromarray(np.where(ink, 255, 0).astype(np.uint8), "L")
    w, h = m.size
    padded = Image.new("L", (w + 2, h + 2), 0)
    padded.paste(m, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    bg = (np.asarray(padded) == 128)[1:-1, 1:-1]

    al = Image.fromarray(np.where(~bg, 255, 0).astype(np.uint8), "L")
    al = al.filter(ImageFilter.MinFilter(ERODE)).filter(ImageFilter.GaussianBlur(BLUR))

    alpha = np.asarray(al).astype(np.float32)
    rgb = np.asarray(im).astype(np.float32)

    # 다리 사이·머리카락 틈처럼 실루엣 안쪽에 갇힌 흰 배경 구멍을 지운다
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    white = (mx >= 248) & ((mx - mn) <= 7) & (alpha > 60)
    lab, n = ndimage.label(white)
    for i in range(1, n + 1):
        blob = lab == i
        if blob.sum() >= 400:
            alpha[blob] = 0

    # 바지·치마 사이의 가늘고 긴 흰 틈
    thin_white = (mx >= 242) & ((mx - mn) <= 12) & (alpha > 20)
    lab2, n2 = ndimage.label(thin_white)
    for i in range(1, n2 + 1):
        blob = lab2 == i
        ys, xs = np.where(blob)
        if ys.size == 0:
            continue
        bh = ys.max() - ys.min() + 1
        bw = xs.max() - xs.min() + 1
        if bh >= 250 and bw <= 45:
            alpha[blob] = 0

    # 테두리 색 오염 제거: 불투명 픽셀 색을 바깥으로 번지게 채운다
    core = alpha > 235
    filled = rgb.copy()
    have = core.copy()
    for _ in range(8):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s_rgb = np.roll(filled, (dy, dx), axis=(0, 1))
            s_have = np.roll(have, (dy, dx), axis=(0, 1))
            take = (~have) & s_have
            filled[take] = s_rgb[take]
            have = have | take
    edge = (~core) & (alpha > 0)
    out = rgb.copy()
    out[edge] = filled[edge]

    arr = np.dstack([out.astype(np.uint8), alpha.astype(np.uint8)])
    return Image.fromarray(arr, "RGBA")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, exprs in CHARS.items():
        base = alpha_of(os.path.join(RAW, f"ch_{name}_base.png"))
        bbox = base.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        pad = 8
        box = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
               min(base.width, bbox[2] + pad), min(base.height, bbox[3] + pad))
        size = (box[2] - box[0], box[3] - box[1])
        target_h = 1400
        tw = round(size[0] * target_h / size[1])
        for e in exprs:
            rgba = alpha_of(os.path.join(RAW, f"ch_{name}_{e}.png"))
            rgba = rgba.crop(box).resize((tw, target_h), Image.LANCZOS)
            out = os.path.join(OUT, f"{name}_{e}.webp")
            rgba.save(out, "WEBP", quality=90, method=6)
            print(f"{name}_{e}", rgba.size, os.path.getsize(out))

    for b in BGS:
        im = Image.open(os.path.join(RAW, f"{b}.png")).convert("RGB")
        w, h = im.size
        target_ratio = 16 / 9
        if w / h > target_ratio:
            nw = int(h * target_ratio)
            left = (w - nw) // 2
            im = im.crop((left, 0, left + nw, h))
        else:
            nh = int(w / target_ratio)
            top = int((h - nh) * 0.42)
            im = im.crop((0, top, w, top + nh))
        im = im.resize((1536, 864), Image.LANCZOS)
        out = os.path.join(OUT, f"{b.replace('bg_', '')}.webp")
        im.save(out, "WEBP", quality=86, method=6)
        print(b, os.path.getsize(out))


if __name__ == "__main__":
    main()
