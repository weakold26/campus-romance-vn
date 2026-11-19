#!/usr/bin/env python3
"""캐릭터 스프라이트 누끼·얼굴 크기/위치 정렬·WebP 내보내기, 배경 리사이즈."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "..", "downloads", "campus-vn-raw")
RAW2 = os.path.join(RAW, "raw2")
OUT = os.path.join(HERE, "..", "assets", "img")

CHARS = {
    "seoyun": ("seo", ["base", "blush", "surprised", "serious"]),
    "chaewon": ("chae", ["base", "blush", "surprised", "serious"]),
}
BGS = ["bg_campus_day", "bg_library", "bg_clubroom", "bg_campus_night", "bg_auditorium"]

CANVAS_W, CANVAS_H = 1024, 1400
HEAD_TOP = 84          # 캔버스 위에서 머리 꼭대기 위치
TARGET_HEAD_W = 300    # 얼굴(머리) 폭 기준

MX_T, SAT_T, ERODE, BLUR = 250, 9, 5, 0.8


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

    # 실루엣 안쪽에 갇힌 흰 배경 구멍(다리 사이·머리카락 틈) 제거
    mx2 = out.max(axis=2)
    mn2 = out.min(axis=2)
    white = (mx2 >= 248) & ((mx2 - mn2) <= 8) & (alpha > 60)
    lab, n = ndimage.label(white)
    sil_w = alpha.shape[1]
    for i in range(1, n + 1):
        blob = lab == i
        if blob.sum() < 400:
            continue
        ys, xs = np.where(blob)
        bw = xs.max() - xs.min() + 1
        bh = ys.max() - ys.min() + 1
        # 다리 사이처럼 가늘고 긴 틈만 지운다 (흰 소품·옷은 남긴다)
        if bw <= sil_w * 0.22 or (bh >= 250 and bw <= 60):
            alpha[blob] = 0

    # 흰 배경과 바로 맞닿은 1px 테두리만 정리 (흰 소품을 먹지 않도록)
    outside = alpha < 24
    near_out = ndimage.binary_dilation(outside, iterations=1)
    pale = (rgb.max(axis=2) >= 246) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 8)
    alpha[near_out & pale] = 0

    # 실루엣 가장자리에 남은 흰색을 안쪽 색으로 바꾼다 (흰 테 제거)
    core = (alpha > 200) & (rgb.max(axis=2) < 236)
    if core.any():
        ind = ndimage.distance_transform_edt(~core, return_distances=False, return_indices=True)
        nearest = rgb[ind[0], ind[1]]
        outside2 = alpha < 16
        near2 = ndimage.binary_dilation(outside2, iterations=6)
        pale2 = (rgb.max(axis=2) >= 232) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 20)
        fix = near2 & pale2 & (alpha > 0)
        rgb[fix] = nearest[fix]

    # 머리카락 사이로 남은 얇은 흰 틈을 주변 색으로 메운다 (넓은 흰 소품은 그대로)
    pale3 = (rgb.max(axis=2) >= 235) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 26) & (alpha > 30)
    thick = ndimage.binary_opening(pale3, structure=np.ones((5, 5)))
    core3 = (alpha > 200) & ~pale3
    if core3.any():
        ind3 = ndimage.distance_transform_edt(~core3, return_distances=False, return_indices=True)
        near3 = rgb[ind3[0], ind3[1]]
        fill3 = pale3 & ~thick
        rgb[fill3] = near3[fill3]

    # 흰 배경이 반투명하게 남은 테두리는 지운다
    pale_hard = (rgb.max(axis=2) >= 232) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 22)
    alpha[pale_hard & (alpha < 200)] = 0

    # 실루엣 바로 바깥에 갇힌 흰 테 제거 (테두리 3px)
    out_zone = ndimage.binary_dilation(alpha < 8, iterations=3)
    pale5 = (rgb.max(axis=2) >= 240) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 16)
    alpha[out_zone & pale5] = 0

    # 테두리를 4px 깎아 흰 테·잔여 배경 조각을 없앤다
    alpha[alpha < 150] = 0
    al3 = Image.fromarray(alpha.astype(np.uint8), "L")
    al3 = al3.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(1.0))
    alpha = np.asarray(al3).astype(np.float32)

    # 머리카락 사이에 갇힌 작은 흰 배경 조각 제거 (얼굴 위쪽 영역만)
    H = alpha.shape[0]
    pale4 = (rgb.max(axis=2) >= 238) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 16) & (alpha > 40)
    lab4, n4 = ndimage.label(pale4)
    for i in range(1, n4 + 1):
        blob = lab4 == i
        ar = int(blob.sum())
        if ar < 8 or ar > 2600:
            continue
        ys, xs = np.where(blob)
        if ys.mean() < H * 0.33:
            alpha[blob] = 0

    # 다리 사이처럼 가늘고 긴 흰 틈 제거 (아래쪽 포함)
    pale6 = (rgb.max(axis=2) >= 240) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 16) & (alpha > 40)
    lab6, n6 = ndimage.label(pale6)
    for i in range(1, n6 + 1):
        blob = lab6 == i
        ar = int(blob.sum())
        if ar < 120:
            continue
        ys, xs = np.where(blob)
        bw = xs.max() - xs.min() + 1
        bh = ys.max() - ys.min() + 1
        if bw <= 46 and bh >= 90:
            alpha[blob] = 0

    # 흰 배경과 섞인 반투명 가장자리 색 되돌리기
    av = np.clip(alpha / 255.0, 0.0, 1.0)[..., None]
    un = (rgb - 255.0 * (1.0 - av)) / np.maximum(av, 0.08)
    rgb = np.where(av > 0.08, np.clip(un, 0, 255), rgb)

    # 실루엣과 떨어진 작은 티끌 제거
    mask = alpha > 0
    lab2, n2 = ndimage.label(mask)
    if n2 > 1:
        sizes = ndimage.sum(mask, lab2, range(1, n2 + 1))
        main = int(np.argmax(sizes)) + 1
        keep = sizes > max(60, sizes[main - 1] * 0.0008)
        keep[main - 1] = True
        drop = np.isin(lab2, [i + 1 for i in range(n2) if not keep[i]])
        alpha[drop] = 0

    arr = np.dstack([out.astype(np.uint8), alpha.astype(np.uint8)])
    return Image.fromarray(arr, "RGBA")


def head_metrics(rgba):
    """머리 꼭대기 y, 그 부근의 머리 폭, 머리 중심 x."""
    al = np.asarray(rgba.getchannel("A"))
    rows = np.where((al > 12).any(axis=1))[0]
    top = int(rows[0])
    bottom = int(rows[-1])
    band_end = top + int((bottom - top) * 0.17)
    best = (0, 0, 0)
    for y in range(top, min(band_end, al.shape[0])):
        xs = np.where(al[y] > 12)[0]
        if xs.size == 0:
            continue
        w = int(xs[-1] - xs[0] + 1)
        if w > best[0]:
            best = (w, y, int((xs[0] + xs[-1]) / 2))
    return top, best[0], best[2]


def build_char(name, prefix, exprs):
    for e in exprs:
        rgba = alpha_of(os.path.join(RAW2, f"{prefix}_{e}.png"))
        top, head_w, head_cx = head_metrics(rgba)
        scale = TARGET_HEAD_W / float(head_w)
        print(f"  {name}_{e}: head_w={head_w} scale={scale:.3f}")
        nw, nh = int(round(rgba.width * scale)), int(round(rgba.height * scale))
        big = rgba.resize((nw, nh), Image.LANCZOS)
        bx = int(round(head_cx * scale))
        by = int(round(top * scale))
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        dx = CANVAS_W // 2 - bx
        dy = HEAD_TOP - by
        canvas.alpha_composite(big, (dx, dy))
        out = os.path.join(OUT, f"{name}_{e}.webp")
        canvas.save(out, "WEBP", quality=90, method=6)
        print(f"   {name}_{e}", os.path.getsize(out))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (prefix, exprs) in CHARS.items():
        build_char(name, prefix, exprs)

    for b in BGS:
        im = Image.open(os.path.join(RAW, f"{b}.png")).convert("RGB")
        w, h = im.size
        ratio = 16 / 9
        if w / h > ratio:
            nw = int(h * ratio)
            left = (w - nw) // 2
            im = im.crop((left, 0, left + nw, h))
        else:
            nh = int(w / ratio)
            top = int((h - nh) * 0.42)
            im = im.crop((0, top, w, top + nh))
        im = im.resize((1536, 864), Image.LANCZOS)
        out = os.path.join(OUT, f"{b.replace('bg_', '')}.webp")
        im.save(out, "WEBP", quality=86, method=6)
        print(b, os.path.getsize(out))


if __name__ == "__main__":
    main()
