"""입자 형상 · 입도분포 지표 (Particle morphology & size-distribution metrics).

hybrid 결과(instance 라벨맵) → 입자별 형상 지표 + 이미지/전체 분포 지표.

전처리 유틸:
  - detect_bottom_bar   : SEM 하단 정보바(스케일바 영역) 높이 자동 감지
  - remove_edge_touching: 이미지 모서리(테두리)에 닿은 입자 제거
  - relabel_by_area     : 라벨을 면적 큰 순 1..K 로 재부여 (입자 번호 = 라벨)

지표 (사용자 spec 1~15):
  1 ECD  2 D10/D50/D90  3 Span  4 Circularity  5 Aspect Ratio  6 Solidity
  7 Convexity  8 Roundness  9 Feret  10 Eccentricity  11 Irregular fraction
  12 Size–Circularity correlation  13 Bimodality  14 Texture entropy
  15 Fractal dimension
"""
from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy import stats
from scipy.spatial import ConvexHull, QhullError
from skimage.measure import perimeter_crofton
from skimage.measure import regionprops


# ─────────────────────────── 전처리 ───────────────────────────


def detect_bottom_bar(gray: np.ndarray, max_frac: float = 0.35,
                      uniform_frac: float = 0.6, tol: int = 4,
                      min_height: int = 8) -> int:
    """SEM 하단 정보바 높이(px) 자동 감지. 못 찾으면 0.

    정보바 행은 '한 가지 배경색(검정/흰색 등)' 이 행의 대부분을 차지한다.
    아래에서 위로 올라가며 (행 최빈값 ±tol 픽셀 비율 ≥ uniform_frac) 이고
    최빈값이 바닥 행과 같은 행들이 이어지는 구간을 정보바로 본다.
    텍스트/스케일바 줄 때문에 잠깐 끊기는 것은 3행까지 허용.
    """
    g = gray.astype(np.int16)
    H = g.shape[0]
    limit = int(H * max_frac)
    if H < 32 or limit < min_height:
        return 0

    def row_mode(r: int) -> tuple[int, float]:
        hist = np.bincount(gray[r], minlength=256)
        m = int(hist.argmax())
        frac = float((np.abs(g[r] - m) <= tol).mean())
        return m, frac

    bar_mode, f0 = row_mode(H - 1)
    if f0 < uniform_frac:
        return 0
    top = H - 1
    gap = 0
    for r in range(H - 1, H - 1 - limit, -1):
        m, frac = row_mode(r)
        if frac >= uniform_frac and abs(m - bar_mode) <= tol:
            top = r
            gap = 0
        else:
            gap += 1
            if gap > 3:
                break
    height = H - top
    return height if height >= min_height else 0


def remove_edge_touching(labels: np.ndarray) -> tuple[np.ndarray, int]:
    """테두리(상하좌우 1px)에 닿은 instance 를 0 으로. (새 라벨맵, 제거 수)."""
    border = np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
    touch = np.unique(border)
    touch = touch[touch > 0]
    if touch.size == 0:
        return labels, 0
    out = labels.copy()
    out[np.isin(out, touch)] = 0
    return out, int(touch.size)


def relabel_by_area(labels: np.ndarray) -> np.ndarray:
    """면적 큰 순으로 1..K 재라벨 (동점은 기존 라벨 오름차순). 빈 라벨 제거."""
    areas = np.bincount(labels.ravel())
    areas[0] = 0
    ids = np.nonzero(areas)[0]
    if ids.size == 0:
        return np.zeros_like(labels, dtype=np.int32)
    order = ids[np.lexsort((ids, -areas[ids]))]
    lut = np.zeros(areas.size, dtype=np.int32)
    lut[order] = np.arange(1, order.size + 1, dtype=np.int32)
    return lut[labels]


# ─────────────────────────── 입자별 지표 ───────────────────────────


def _feret(region_img: np.ndarray) -> tuple[float, float]:
    """(최대 Feret, 최소 Feret) — 경계 픽셀 꼭짓점의 convex hull + rotating calipers."""
    img = np.pad(region_img, 1)
    edge = img & ~ndi.binary_erosion(img)
    coords = np.argwhere(edge).astype(np.float64)
    offs = np.array([[-.5, -.5], [-.5, .5], [.5, -.5], [.5, .5]])
    pts = np.unique((coords[:, None, :] + offs[None]).reshape(-1, 2), axis=0)
    try:
        hv = pts[ConvexHull(pts).vertices]
    except QhullError:
        return float("nan"), float("nan")
    diff = hv[:, None, :] - hv[None, :, :]
    fmax = float(np.sqrt((diff ** 2).sum(-1)).max())
    fmin = math.inf
    for i in range(len(hv)):
        e = hv[(i + 1) % len(hv)] - hv[i]
        n = np.hypot(e[0], e[1])
        if n == 0:
            continue
        normal = np.array([-e[1], e[0]]) / n
        fmin = min(fmin, float(np.abs((hv - hv[i]) @ normal).max()))
    return fmax, (fmin if math.isfinite(fmin) else float("nan"))


def _divider_fractal(region_img: np.ndarray, min_side: int = 16) -> float:
    """외곽선 프랙탈 차원 — Richardson divider (컴퍼스) 법.

    보폭 s 를 2px ~ bbox/2 로 바꿔가며 외곽선을 걸어 측정 길이 L(s) 를 구하고
    D = 1 − slope(log L vs log s). 매끈한 원 ≈ 1, 거칠수록 커짐.
    bbox 긴 변 < min_side 면 NaN.
    """
    h, w = region_img.shape
    if max(h, w) < min_side:
        return float("nan")
    u = np.pad(region_img.astype(np.uint8), 2)
    cs, _ = cv2.findContours(u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return float("nan")
    c = max(cs, key=len)[:, 0, :].astype(np.float64)
    n = len(c)
    xs, ys = [], []
    for s in np.geomspace(2.0, max(h, w) / 2.0, 8):
        cur = c[0]
        j = cnt = 0
        while True:
            k = j + 1
            while k < n and math.hypot(*(c[k] - cur)) < s:
                k += 1
            if k >= n:
                break
            cur, j = c[k], k
            cnt += 1
        if cnt < 3:
            continue
        xs.append(math.log(s))
        ys.append(math.log(cnt * s + math.hypot(*(c[0] - cur))))
    if len(xs) < 4:
        return float("nan")
    return float(1 - np.polyfit(xs, ys, 1)[0])


def _entropy_bits(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    hist = np.bincount(values.astype(np.uint8).ravel(), minlength=256).astype(np.float64)
    p = hist[hist > 0] / hist.sum()
    return float(-(p * np.log2(p)).sum())


def particle_metrics(labels: np.ndarray, gray: np.ndarray,
                     irregular_circularity: float = 0.7) -> list[dict]:
    """라벨맵(1..K) → 입자별 지표 리스트 (id 오름차순, 길이 단위 = px)."""
    out: list[dict] = []
    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)
    for rp in regionprops(labels, intensity_image=gray):
        A = float(rp.area)
        P = float(rp.perimeter_crofton)
        major = float(rp.axis_major_length)
        minor = float(rp.axis_minor_length)
        cy, cx = rp.centroid
        circ = min(1.0, 4 * math.pi * A / P ** 2) if P > 0 else float("nan")
        conv_p = float(perimeter_crofton(rp.image_convex))
        convexity = min(1.0, conv_p / P) if P > 0 else float("nan")
        fmax, fmin = _feret(rp.image)
        out.append({
            "id": int(rp.label),
            "cx": float(cx), "cy": float(cy),
            "area": A,
            "perimeter": P,
            "ecd": math.sqrt(4 * A / math.pi),
            "feret_max": fmax,
            "feret_min": fmin,
            "major": major,
            "minor": minor,
            "circularity": circ,
            "aspect_ratio": (major / minor) if minor > 0 else float("nan"),
            "solidity": float(rp.solidity),
            "convexity": convexity,
            "roundness": min(1.0, 4 * A / (math.pi * major ** 2)) if major > 0 else float("nan"),
            "eccentricity": float(rp.eccentricity),
            "texture_entropy": _entropy_bits(rp.image_intensity[rp.image]),
            "fractal_dim": _divider_fractal(rp.image),
            "irregular": int(math.isfinite(circ) and circ < irregular_circularity),
        })
    return out


# ─────────────────────────── 분포 지표 ───────────────────────────


LEN_KEYS = ("perimeter", "ecd", "feret_max", "feret_min", "major", "minor")


def scaled(p: dict, um_per_px: Optional[float]) -> dict:
    """입자 dict 의 길이/면적 값을 µm 로 변환한 사본 (scale 없으면 그대로)."""
    if not um_per_px:
        return dict(p)
    q = dict(p)
    for k in LEN_KEYS:
        q[k] = p[k] * um_per_px
    q["area"] = p["area"] * um_per_px ** 2
    return q


def _weighted_percentile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    o = np.argsort(x)
    x, w = x[o], w[o]
    cdf = np.cumsum(w) / w.sum()
    return float(np.interp(q, cdf, x))


def _gmm2(x: np.ndarray, iters: int = 300) -> Optional[dict]:
    """1D 2-성분 Gaussian mixture (EM). 단일 Gaussian 대비 ΔBIC 포함."""
    n = x.size
    sd = float(x.std())
    if n < 10 or sd == 0:
        return None
    floor = 1e-3 * sd
    mu = np.percentile(x, [25, 75]).astype(np.float64)
    sg = np.array([sd / 2, sd / 2])
    wt = np.array([0.5, 0.5])

    def comp_pdf(mu, sg):
        return np.exp(-0.5 * ((x[:, None] - mu) / sg) ** 2) / (sg * math.sqrt(2 * math.pi))

    prev = -math.inf
    for _ in range(iters):
        dens = comp_pdf(mu, sg) * wt + 1e-300
        tot = dens.sum(1, keepdims=True)
        r = dens / tot
        nk = r.sum(0) + 1e-12
        wt = nk / n
        mu = (r * x[:, None]).sum(0) / nk
        sg = np.maximum(np.sqrt((r * (x[:, None] - mu) ** 2).sum(0) / nk), floor)
        ll = float(np.log(tot).sum())
        if abs(ll - prev) < 1e-8 * abs(ll):
            break
        prev = ll
    ll2 = float(np.log((comp_pdf(mu, sg) * wt).sum(1) + 1e-300).sum())
    ll1 = float(stats.norm.logpdf(x, x.mean(), sd).sum())
    bic1 = 2 * math.log(n) - 2 * ll1
    bic2 = 5 * math.log(n) - 2 * ll2
    o = np.argsort(mu)
    mu, sg, wt = mu[o], sg[o], wt[o]
    return {
        "gmm_mu1": float(mu[0]), "gmm_mu2": float(mu[1]),
        "gmm_sigma1": float(sg[0]), "gmm_sigma2": float(sg[1]),
        "gmm_w1": float(wt[0]), "gmm_w2": float(wt[1]),
        "ashman_d": float(math.sqrt(2) * abs(mu[1] - mu[0]) / math.sqrt(sg[0] ** 2 + sg[1] ** 2)),
        "delta_bic": float(bic1 - bic2),
    }


def _nanstat(a: np.ndarray, fn) -> float:
    a = a[np.isfinite(a)]
    return float(fn(a)) if a.size else float("nan")


def distribution_summary(particles: list[dict], um_per_px: Optional[float],
                         irregular_circularity: float) -> dict:
    """입자 리스트(px 단위) → 분포 지표. 길이 단위는 scale 있으면 µm, 없으면 px."""
    ps = [scaled(p, um_per_px) for p in particles]
    n = len(ps)
    s: dict = {"n_particles": n, "unit": "µm" if um_per_px else "px",
               "irregular_threshold": float(irregular_circularity)}
    if n == 0:
        return s

    def col(k):
        return np.array([p[k] for p in ps], dtype=np.float64)

    ecd = col("ecd")
    s.update({
        "ecd_mean": float(ecd.mean()), "ecd_std": float(ecd.std(ddof=1)) if n > 1 else 0.0,
        "ecd_min": float(ecd.min()), "ecd_max": float(ecd.max()),
        "area_mean": float(col("area").mean()),
    })
    d10, d50, d90 = (float(np.percentile(ecd, q)) for q in (10, 50, 90))
    s.update({"d10": d10, "d50": d50, "d90": d90,
              "span": (d90 - d10) / d50 if d50 > 0 else float("nan")})
    vw = ecd ** 3
    dv10, dv50, dv90 = (_weighted_percentile(ecd, vw, q) for q in (0.1, 0.5, 0.9))
    s.update({"dv10": dv10, "dv50": dv50, "dv90": dv90,
              "span_v": (dv90 - dv10) / dv50 if dv50 > 0 else float("nan")})

    for k in ("circularity", "aspect_ratio", "solidity", "convexity", "roundness",
              "eccentricity", "feret_max", "feret_min", "texture_entropy", "fractal_dim"):
        a = col(k)
        s[f"{k}_mean"] = _nanstat(a, np.mean)
        s[f"{k}_std"] = _nanstat(a, lambda v: v.std(ddof=1) if v.size > 1 else 0.0)
    s["fractal_n_valid"] = int(np.isfinite(col("fractal_dim")).sum())
    s["irregular_count"] = int(col("irregular").sum())
    s["irregular_fraction_pct"] = 100.0 * s["irregular_count"] / n

    circ = col("circularity")
    ok = np.isfinite(circ)
    if ok.sum() >= 3 and np.ptp(ecd[ok]) > 0 and np.ptp(circ[ok]) > 0:
        rho, rp = stats.spearmanr(ecd[ok], circ[ok])
        r, pp = stats.pearsonr(ecd[ok], circ[ok])
        s.update({"spearman_rho": float(rho), "spearman_p": float(rp),
                  "pearson_r": float(r), "pearson_p": float(pp)})

    if n >= 4 and ecd.std() > 0:
        g = float(stats.skew(ecd, bias=False))
        k = float(stats.kurtosis(ecd, fisher=True, bias=False))
        s["skewness"] = g
        s["kurtosis_excess"] = k
        s["bimodality_coefficient"] = (g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    gm = _gmm2(ecd)
    if gm:
        s.update(gm)
    bc = s.get("bimodality_coefficient")
    if bc is not None and gm:
        s["bimodal"] = bool(bc > 0.555 and gm["delta_bic"] > 10)
    return s


def size_bins(particles: list[dict], um_per_px: Optional[float]) -> list[dict]:
    """ECD 사분위(Q1~Q4) 구간별 평균 형상 — 크기별 형상 차이."""
    ps = [scaled(p, um_per_px) for p in particles]
    if len(ps) < 4:
        return []
    ecd = np.array([p["ecd"] for p in ps])
    edges = np.percentile(ecd, [0, 25, 50, 75, 100])
    idx = np.clip(np.searchsorted(edges[1:-1], ecd, side="right"), 0, 3)
    rows = []
    for b in range(4):
        sel = [p for p, i in zip(ps, idx) if i == b]
        row = {"bin": f"Q{b + 1}", "ecd_from": float(edges[b]), "ecd_to": float(edges[b + 1]),
               "n": len(sel)}
        for k in ("ecd", "circularity", "aspect_ratio", "solidity", "convexity", "roundness"):
            a = np.array([p[k] for p in sel], dtype=np.float64)
            row[f"{k}_mean"] = _nanstat(a, np.mean)
        row["irregular_pct"] = (100.0 * sum(p["irregular"] for p in sel) / len(sel)) if sel else float("nan")
        rows.append(row)
    return rows


def json_safe(obj):
    """NaN/inf → None, numpy 스칼라 → python (Starlette JSON 은 NaN 불가)."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ─────────────────────────── 엑셀용 지표 정의 (한/영) ───────────────────────────

# (key, 한글, English, unit kind: len|area|none|pct|bits|count, 정의(한), Definition(EN))
PARTICLE_COLUMNS = [
    ("id", "입자 번호", "Particle ID", "none", "면적 큰 순 번호 (번호 이미지와 동일)", "Numbered by area, descending (matches numbered view)"),
    ("cx", "중심 x", "Centroid x", "px", "이미지 좌표 (px)", "Image coordinate (px)"),
    ("cy", "중심 y", "Centroid y", "px", "이미지 좌표 (px)", "Image coordinate (px)"),
    ("area", "면적", "Area", "area", "입자 픽셀 수 × 픽셀 면적", "Pixel count × pixel area"),
    ("perimeter", "둘레", "Perimeter", "len", "외곽선 길이 (Crofton 추정)", "Boundary length (Crofton estimate)"),
    ("ecd", "등가원 직경 (ECD)", "Equivalent Circular Diameter (ECD)", "len", "√(4A/π)", "√(4A/π)"),
    ("feret_max", "최대 Feret 직경", "Max Feret Diameter", "len", "모든 방향 중 최대 캘리퍼 폭", "Largest caliper width over all directions"),
    ("feret_min", "최소 Feret 직경", "Min Feret Diameter", "len", "모든 방향 중 최소 캘리퍼 폭", "Smallest caliper width over all directions"),
    ("major", "장축 길이", "Major Axis Length", "len", "동일 2차 모멘트 타원의 장축", "Major axis of the equivalent-moment ellipse"),
    ("minor", "단축 길이", "Minor Axis Length", "len", "동일 2차 모멘트 타원의 단축", "Minor axis of the equivalent-moment ellipse"),
    ("circularity", "원형도", "Circularity", "none", "4πA / P² (1=완전한 원)", "4πA / P² (1 = perfect circle)"),
    ("aspect_ratio", "종횡비", "Aspect Ratio", "none", "장축 / 단축 (1=등방)", "Major / minor axis (1 = isotropic)"),
    ("solidity", "고형도 (Solidity)", "Solidity", "none", "A / 볼록껍질 면적 (낮을수록 오목)", "A / convex-hull area (lower = more concave)"),
    ("convexity", "볼록도 (Convexity)", "Convexity", "none", "볼록껍질 둘레 / 둘레 (낮을수록 경계 굴곡)", "Convex-hull perimeter / perimeter (lower = rougher boundary)"),
    ("roundness", "진원도 (Roundness)", "Roundness", "none", "4A / (π·장축²)", "4A / (π·major²)"),
    ("eccentricity", "이심률", "Eccentricity", "none", "√(1 − (단축/장축)²) (0=원, →1 찌그러짐)", "√(1 − (minor/major)²) (0 = circle, →1 elongated)"),
    ("texture_entropy", "표면 텍스처 엔트로피", "Surface Texture Entropy", "bits", "입자 내부 밝기 히스토그램의 Shannon 엔트로피", "Shannon entropy of gray levels inside the particle"),
    ("fractal_dim", "프랙탈 차원", "Fractal Dimension", "none", "외곽선 Richardson divider 차원 (≈1 매끈, 클수록 복잡). bbox<16px 이면 빈칸", "Richardson divider dimension of outline (≈1 smooth). Blank if bbox < 16 px"),
    ("irregular", "불규칙 입자 (1=예)", "Irregular (1 = yes)", "none", "원형도 < 기준값", "Circularity < threshold"),
]

# (key, 한글, English, unit kind, 정의(한), Definition(EN))
SUMMARY_ROWS = [
    ("n_particles", "입자 수", "Particle count", "count", "분석된 입자 수", "Number of analysed particles"),
    ("n_edge_removed", "모서리 제거 입자 수", "Edge particles removed", "count", "테두리에 닿아 제외된 입자", "Particles touching the border, excluded"),
    ("crop_bottom_px", "하단 크롭 (px)", "Bottom crop (px)", "count", "잘라낸 하단 정보바 높이", "Height of the cropped bottom info bar"),
    ("ecd_mean", "ECD 평균", "ECD mean", "len", "", ""),
    ("ecd_std", "ECD 표준편차", "ECD std", "len", "", ""),
    ("ecd_min", "ECD 최소", "ECD min", "len", "", ""),
    ("ecd_max", "ECD 최대", "ECD max", "len", "", ""),
    ("d10", "D10 (개수 기준)", "D10 (number-based)", "len", "ECD 누적 개수 10% 지점", "ECD at 10% of cumulative count"),
    ("d50", "D50 (개수 기준)", "D50 (number-based)", "len", "ECD 중앙값", "Median ECD"),
    ("d90", "D90 (개수 기준)", "D90 (number-based)", "len", "ECD 누적 개수 90% 지점", "ECD at 90% of cumulative count"),
    ("span", "PSD Span (개수 기준)", "PSD Span (number-based)", "none", "(D90 − D10) / D50 (작을수록 균일)", "(D90 − D10) / D50 (smaller = more uniform)"),
    ("dv10", "Dv10 (부피 기준)", "Dv10 (volume-based)", "len", "ECD³ 가중 누적 10% (레이저 회절과 비교용)", "ECD³-weighted 10% (comparable to laser diffraction)"),
    ("dv50", "Dv50 (부피 기준)", "Dv50 (volume-based)", "len", "ECD³ 가중 누적 50%", "ECD³-weighted 50%"),
    ("dv90", "Dv90 (부피 기준)", "Dv90 (volume-based)", "len", "ECD³ 가중 누적 90%", "ECD³-weighted 90%"),
    ("span_v", "PSD Span (부피 기준)", "PSD Span (volume-based)", "none", "(Dv90 − Dv10) / Dv50", "(Dv90 − Dv10) / Dv50"),
    ("circularity_mean", "원형도 평균", "Circularity mean", "none", "", ""),
    ("circularity_std", "원형도 표준편차", "Circularity std", "none", "", ""),
    ("aspect_ratio_mean", "종횡비 평균", "Aspect Ratio mean", "none", "", ""),
    ("solidity_mean", "Solidity 평균", "Solidity mean", "none", "", ""),
    ("convexity_mean", "Convexity 평균", "Convexity mean", "none", "", ""),
    ("roundness_mean", "진원도 평균", "Roundness mean", "none", "", ""),
    ("feret_max_mean", "최대 Feret 평균", "Max Feret mean", "len", "", ""),
    ("feret_min_mean", "최소 Feret 평균", "Min Feret mean", "len", "", ""),
    ("eccentricity_mean", "이심률 평균", "Eccentricity mean", "none", "", ""),
    ("irregular_threshold", "불규칙 기준 (원형도 <)", "Irregular threshold (circularity <)", "none", "", ""),
    ("irregular_count", "불규칙 입자 수", "Irregular particle count", "count", "", ""),
    ("irregular_fraction_pct", "불규칙 입자 비율 (%)", "Irregular particle fraction (%)", "pct", "불규칙 입자 수 / 전체 × 100", "Irregular / total × 100"),
    ("spearman_rho", "크기–원형도 Spearman ρ", "Size–Circularity Spearman ρ", "none", "ECD 와 원형도의 순위 상관 (−: 클수록 덜 둥글다)", "Rank correlation of ECD vs circularity (− : larger = less round)"),
    ("spearman_p", "Spearman p-값", "Spearman p-value", "none", "< 0.05 이면 유의", "Significant if < 0.05"),
    ("pearson_r", "크기–원형도 Pearson r", "Size–Circularity Pearson r", "none", "선형 상관", "Linear correlation"),
    ("pearson_p", "Pearson p-값", "Pearson p-value", "none", "", ""),
    ("skewness", "ECD 왜도", "ECD skewness", "none", "", ""),
    ("kurtosis_excess", "ECD 첨도 (초과)", "ECD excess kurtosis", "none", "", ""),
    ("bimodality_coefficient", "이봉 계수 (BC)", "Bimodality Coefficient (BC)", "none", "(g²+1)/(k+3(n−1)²/((n−2)(n−3))). > 0.555 이면 이봉 가능성", "> 0.555 suggests bimodality"),
    ("gmm_mu1", "GMM 모드1 평균", "GMM mode-1 mean", "len", "2-성분 Gaussian mixture (ECD)", "2-component Gaussian mixture on ECD"),
    ("gmm_mu2", "GMM 모드2 평균", "GMM mode-2 mean", "len", "", ""),
    ("gmm_sigma1", "GMM 모드1 표준편차", "GMM mode-1 sigma", "len", "", ""),
    ("gmm_sigma2", "GMM 모드2 표준편차", "GMM mode-2 sigma", "len", "", ""),
    ("gmm_w1", "GMM 모드1 비중", "GMM mode-1 weight", "none", "", ""),
    ("gmm_w2", "GMM 모드2 비중", "GMM mode-2 weight", "none", "", ""),
    ("ashman_d", "Ashman D", "Ashman's D", "none", "√2·|μ1−μ2|/√(σ1²+σ2²). > 2 이면 두 모드 분리", "> 2 = clearly separated modes"),
    ("delta_bic", "ΔBIC (1성분 − 2성분)", "ΔBIC (1-comp − 2-comp)", "none", "> 10 이면 2성분 모델이 강하게 지지됨", "> 10 = strong support for two modes"),
    ("bimodal", "이봉 분포 판정", "Bimodal (verdict)", "none", "BC > 0.555 그리고 ΔBIC > 10", "BC > 0.555 and ΔBIC > 10"),
    ("texture_entropy_mean", "텍스처 엔트로피 평균 (bits)", "Texture entropy mean (bits)", "bits", "", ""),
    ("fractal_dim_mean", "프랙탈 차원 평균", "Fractal dimension mean", "none", "bbox ≥ 16px 입자만", "Particles with bbox ≥ 16 px only"),
    ("fractal_n_valid", "프랙탈 계산 입자 수", "Fractal valid count", "count", "", ""),
]

SIZE_BIN_COLUMNS = [
    ("bin", "구간", "Bin", "none"),
    ("ecd_from", "ECD 하한", "ECD from", "len"),
    ("ecd_to", "ECD 상한", "ECD to", "len"),
    ("n", "입자 수", "Count", "count"),
    ("ecd_mean", "ECD 평균", "ECD mean", "len"),
    ("circularity_mean", "원형도 평균", "Circularity mean", "none"),
    ("aspect_ratio_mean", "종횡비 평균", "Aspect Ratio mean", "none"),
    ("solidity_mean", "Solidity 평균", "Solidity mean", "none"),
    ("convexity_mean", "Convexity 평균", "Convexity mean", "none"),
    ("roundness_mean", "진원도 평균", "Roundness mean", "none"),
    ("irregular_pct", "불규칙 비율 (%)", "Irregular (%)", "pct"),
]


def unit_label(kind: str, unit: str) -> str:
    return {"len": unit, "area": f"{unit}²", "bits": "bits", "pct": "%", "px": "px"}.get(kind, "")
