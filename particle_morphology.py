"""입자 형상 · 입도분포 지표 (Particle morphology & size-distribution metrics).

hybrid 결과(instance 라벨맵) → 입자별 형상 지표 + 이미지/전체 분포 지표.
지표 정의(식 · 계산 방법 · 한/영)는 파일 하단 PARTICLE_COLUMNS / SUMMARY_ROWS /
SHAPE_STAT_* 에 모여 있고, 엑셀 '지표정의' 시트가 그대로 출력한다.

전처리 유틸:
  - detect_bottom_bar   : SEM 하단 정보바(스케일바 영역) 높이 자동 감지
  - remove_edge_touching: 이미지 모서리(테두리)에 닿은 입자 제거
  - relabel_by_area     : 라벨을 면적 큰 순 1..K 로 재부여 (입자 번호 = 라벨)

지표 (사용자 spec 1~15):
  1 ECD  2 D10/D50/D90  3 Span  4 Circularity  5 Aspect Ratio  6 Solidity
  7 Convexity  8 Roundness  9 Feret  10 Eccentricity  11 Irregular fraction
  12 Size–Circularity correlation  13 Bimodality  14 Texture entropy
  15 Fractal dimension
+ 마스크 기하 지표 확장 (크기·치수, 형상, 방사형·Hu·저차 Fourier, 국소 두께,
  입도분포 통계 31종, 형상 지표 분포 통계, Miles–Lantuéjoul 모서리 보정)
  — 경계 고주파 거칠기·곡률·골격·구멍·방향 의존 지표는 신뢰성 문제로 제외
"""
from __future__ import annotations

import math
from typing import NamedTuple, Optional

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy import stats
from scipy.spatial import ConvexHull, QhullError
from skimage.measure import perimeter_crofton, regionprops


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

_CORNERS = np.array([[-.5, -.5], [-.5, .5], [.5, -.5], [.5, .5]])
_N_RESAMPLE = 128     # 외곽선 재샘플 점 수 (방사형 · Fourier)
_N_FOURIER = 5        # 저차 Fourier 계수 개수
_N_CALIPER = 180      # Feret 평균/SD 계산 방향 수 (1° 간격)


def _hull_vertices(region_img: np.ndarray) -> Optional[np.ndarray]:
    """경계 픽셀 네 꼭짓점의 convex hull 꼭짓점 (row, col), 반시계 순서."""
    img = np.pad(region_img, 1)
    edge = img & ~ndi.binary_erosion(img)
    coords = np.argwhere(edge).astype(np.float64) - 1.0
    pts = np.unique((coords[:, None, :] + _CORNERS[None]).reshape(-1, 2), axis=0)
    try:
        return pts[ConvexHull(pts).vertices]
    except QhullError:
        return None


def _feret_set(hv: np.ndarray) -> dict:
    """Feret 최대(정확) · 최소(rotating calipers, 정확) · 180방향 평균/SD."""
    diff = hv[:, None, :] - hv[None, :, :]
    fmax = float(np.sqrt((diff ** 2).sum(-1)).max())
    fmin = math.inf
    for i in range(len(hv)):
        e = hv[(i + 1) % len(hv)] - hv[i]
        n = math.hypot(e[0], e[1])
        if n == 0:
            continue
        normal = np.array([-e[1], e[0]]) / n
        fmin = min(fmin, float(np.abs((hv - hv[i]) @ normal).max()))
    ang = np.deg2rad(np.arange(_N_CALIPER) * 180.0 / _N_CALIPER)
    proj = hv @ np.stack([np.cos(ang), np.sin(ang)], 0)
    widths = proj.max(0) - proj.min(0)
    return {
        "feret_max": fmax,
        "feret_min": fmin if math.isfinite(fmin) else float("nan"),
        "feret_mean": float(widths.mean()),
        "feret_sd": float(widths.std(ddof=0)),
    }


def _contour_resampled(region_img: np.ndarray, n: int = _N_RESAMPLE) -> Optional[np.ndarray]:
    """가장 큰 외곽선을 둘레 길이 기준 n 개 등간격 점 (x, y) 로 재샘플."""
    u = np.pad(region_img.astype(np.uint8), 1)
    cs, _ = cv2.findContours(u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=len)[:, 0, :].astype(np.float64) - 1.0
    if len(c) < 4:
        return None
    closed = np.vstack([c, c[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(t, s, closed[:, 0]), np.interp(t, s, closed[:, 1])], 1)


def _radial_fourier(contour: Optional[np.ndarray], cx: float, cy: float) -> dict:
    """중심–경계 거리 r(s) 통계 + 저차 Fourier (상대 진폭)."""
    keys = ["radius_max", "radius_min", "radius_mean", "radius_sd", "radius_cv",
            "radius_range", "radius_skew", "radius_kurt", "fourier_low_energy",
            *[f"fourier_{k}" for k in range(1, _N_FOURIER + 1)]]
    if contour is None:
        return {k: float("nan") for k in keys}
    r = np.hypot(contour[:, 0] - cx, contour[:, 1] - cy)
    m = float(r.mean())
    out = {
        "radius_max": float(r.max()), "radius_min": float(r.min()),
        "radius_mean": m, "radius_sd": float(r.std(ddof=0)),
        "radius_cv": float(r.std(ddof=0) / m) if m > 0 else float("nan"),
        "radius_range": float(r.max() - r.min()),
        "radius_skew": float(stats.skew(r)) if r.std() > 0 else 0.0,
        "radius_kurt": float(stats.kurtosis(r)) if r.std() > 0 else 0.0,
    }
    R = np.abs(np.fft.rfft(r))
    fd = [2 * R[k] / R[0] if R[0] > 0 else float("nan") for k in range(1, _N_FOURIER + 1)]
    for k, v in enumerate(fd, start=1):
        out[f"fourier_{k}"] = float(v)
    out["fourier_low_energy"] = float(np.nansum(np.square(fd)))
    return out


def _disk(r: float) -> np.ndarray:
    R = int(math.floor(r))
    yy, xx = np.ogrid[-R:R + 1, -R:R + 1]
    return ((yy * yy + xx * xx) <= r * r).astype(np.uint8)


def _local_thickness(region_img: np.ndarray) -> tuple[np.ndarray, float]:
    """국소 두께 (Hildebrand–Rüegsegger, 2D): 각 픽셀을 포함하는 최대 내접원의 지름.

    1) 거리변환 d (픽셀 중심 → 가장 가까운 배경 픽셀 중심)
    2) 최대 내접원 중심(CMD): 이웃 n 의 원이 자기 원을 완전히 포함하면
       (d(n) ≥ d(c) + |n − c|) 버림
    3) 남은 중심을 반지름별로 묶어 원판 팽창 → 픽셀마다 덮는 원 중 최대 지름
    모든 픽셀을 중심 후보로 두는 완전 탐색과 동일한 결과 (검증 오차 0).
    반환: (입자 픽셀별 두께 배열, 최대 내접원 지름).
    """
    img = np.pad(region_img, 1)
    d = ndi.distance_transform_edt(img)
    keep = img.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                nb = np.roll(np.roll(d, dy, 0), dx, 1)
                keep &= ~(nb >= d + math.hypot(dy, dx) - 1e-9)
    lt = np.zeros(img.shape, dtype=np.float64)
    for r in np.unique(d[keep]):           # 오름차순 → 큰 원이 나중에 덮어씀
        centers = (keep & (d == r)).astype(np.uint8)
        covered = cv2.dilate(centers, _disk(r)) > 0
        lt[covered] = 2 * r
    vals = lt[img]
    return vals, float(2 * d.max())


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


def _ratio(a: float, b: float, cap: Optional[float] = None) -> float:
    if not (b > 0) or not math.isfinite(a):
        return float("nan")
    v = a / b
    return min(cap, v) if cap is not None else v


def particle_metrics(labels: np.ndarray, gray: np.ndarray,
                     irregular_circularity: float = 0.7) -> list[dict]:
    """라벨맵(1..K) → 입자별 지표 리스트 (id 오름차순, 길이 단위 = px)."""
    out: list[dict] = []
    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)
    Hi, Wi = labels.shape
    for rp in regionprops(labels, intensity_image=gray):
        img = rp.image
        A = float(rp.area)
        P = float(rp.perimeter_crofton)
        major = float(rp.axis_major_length)
        minor = float(rp.axis_minor_length)
        cy, cx = rp.centroid
        ly, lx = rp.centroid_local
        minr, minc, maxr, maxc = rp.bbox
        circ = _ratio(4 * math.pi * A, P ** 2, cap=1.0)
        conv_A = float(rp.area_convex)
        conv_P = float(perimeter_crofton(rp.image_convex))

        hv = _hull_vertices(img)
        if hv is not None:
            fer = _feret_set(hv)
            xy = hv[:, ::-1].astype(np.float32)
            (_, _), (rw, rh), _ = cv2.minAreaRect(xy)
            (_, _), enc_r = cv2.minEnclosingCircle(xy)
            rect_L, rect_W, enc_d = float(max(rw, rh)), float(min(rw, rh)), float(2 * enc_r)
        else:
            fer = {k: float("nan") for k in ("feret_max", "feret_min", "feret_mean", "feret_sd")}
            rect_L = rect_W = enc_d = float("nan")
        thick, ins_d = _local_thickness(img)
        rad = _radial_fourier(_contour_resampled(img), lx, ly)
        hu = cv2.HuMoments(cv2.moments(img.astype(np.uint8), binaryImage=True)).ravel()
        hu_log = [float(-math.copysign(1, h) * math.log10(abs(h))) if h != 0 else float("nan")
                  for h in hu]

        # Miles–Lantuéjoul 가중치 — 모서리 제거 시 큰 입자 과소표집 보정
        bw, bh = maxc - minc, maxr - minr
        ml_w = (Wi * Hi) / ((Wi - bw) * (Hi - bh)) if (Wi > bw and Hi > bh) else float("nan")

        p = {
            "id": int(rp.label),
            "cx": float(cx), "cy": float(cy),
            # 크기 · 치수
            "area": A,
            "perimeter": P,
            "perimeter_trace": float(rp.perimeter),
            "ecd": math.sqrt(4 * A / math.pi),
            "major": major,
            "minor": minor,
            **fer,
            "rect_length": rect_L,
            "rect_width": rect_W,
            "convex_area": conv_A,
            "convex_perimeter": conv_P,
            "inscribed_d": ins_d,
            "enclosing_d": enc_d,
            "radius_max": rad["radius_max"],
            "radius_min": rad["radius_min"],
            "radius_mean": rad["radius_mean"],
            # 형상
            "circularity": circ,
            "aspect_ratio": _ratio(major, minor),
            "feret_aspect_ratio": _ratio(fer["feret_max"], fer["feret_min"]),
            "eccentricity": float(rp.eccentricity),
            "roundness": _ratio(4 * A, math.pi * major ** 2, cap=1.0),
            "solidity": float(rp.solidity),
            "convexity": _ratio(conv_P, P, cap=1.0),
            "rectangularity": _ratio(A, rect_L * rect_W, cap=1.0),
            "compactness": _ratio(4 * A, math.pi * fer["feret_max"] ** 2, cap=1.0),
            "in_circ_ratio": _ratio(ins_d, enc_d, cap=1.0),
            # 방사형 · 모멘트 · Fourier
            "radius_sd": rad["radius_sd"],
            "radius_cv": rad["radius_cv"],
            "radius_range": rad["radius_range"],
            "radius_skew": rad["radius_skew"],
            "radius_kurt": rad["radius_kurt"],
            **{f"fourier_{k}": rad[f"fourier_{k}"] for k in range(1, _N_FOURIER + 1)},
            "fourier_low_energy": rad["fourier_low_energy"],
            **{f"hu_{k}": hu_log[k - 1] for k in range(1, 8)},
            # 국소 두께
            "thick_mean": float(thick.mean()),
            "thick_median": float(np.median(thick)),
            "thick_sd": float(thick.std(ddof=0)),
            "thick_cv": _ratio(float(thick.std(ddof=0)), float(thick.mean())),
            "thick_d10": float(np.percentile(thick, 10)),
            "thick_d90": float(np.percentile(thick, 90)),
            "thick_max": float(thick.max()),
            # 기타 (기존)
            "texture_entropy": _entropy_bits(rp.image_intensity[img]),
            "fractal_dim": _divider_fractal(img),
            "irregular": int(math.isfinite(circ) and circ < irregular_circularity),
            "ml_weight": float(ml_w),
        }
        out.append(p)
    return out


# ─────────────────────────── 분포 지표 ───────────────────────────


LEN_KEYS = (
    "perimeter", "perimeter_trace", "ecd", "major", "minor",
    "feret_max", "feret_min", "feret_mean", "feret_sd",
    "rect_length", "rect_width", "convex_perimeter", "inscribed_d", "enclosing_d",
    "radius_max", "radius_min", "radius_mean", "radius_sd", "radius_range",
    "thick_mean", "thick_median", "thick_sd", "thick_d10", "thick_d90", "thick_max",
)
AREA_KEYS = ("area", "convex_area")


def scaled(p: dict, um_per_px: Optional[float]) -> dict:
    """입자 dict 의 길이/면적 값을 µm 로 변환한 사본 (scale 없으면 그대로)."""
    if not um_per_px:
        return dict(p)
    q = dict(p)
    for k in LEN_KEYS:
        if k in q:
            q[k] = p[k] * um_per_px
    for k in AREA_KEYS:
        if k in q:
            q[k] = p[k] * um_per_px ** 2
    return q


def _weighted_percentile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    o = np.argsort(x)
    x, w = x[o], w[o]
    cdf = np.cumsum(w) / w.sum()
    return float(np.interp(q, cdf, x))


def _gini(x: np.ndarray) -> float:
    x = np.sort(x[np.isfinite(x)])
    n = x.size
    if n == 0 or x.sum() == 0:
        return float("nan")
    i = np.arange(1, n + 1)
    return float((2 * (i * x).sum()) / (n * x.sum()) - (n + 1) / n)


def _norm_entropy(x: np.ndarray, bins: int = 20, log: bool = False) -> float:
    """구간 bins 개 히스토그램의 Shannon 엔트로피 / log2(bins) → 0~1."""
    x = x[np.isfinite(x)]
    if log:
        x = np.log(x[x > 0])
    if x.size < 2 or np.ptp(x) == 0:
        return 0.0 if x.size else float("nan")
    h, _ = np.histogram(x, bins=bins)
    p = h[h > 0] / h.sum()
    return float(-(p * np.log2(p)).sum() / math.log2(bins))


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
                         irregular_circularity: float, edge_corrected: bool = False) -> dict:
    """입자 리스트(px 단위) → 분포 지표. 길이 단위는 scale 있으면 µm, 없으면 px.

    edge_corrected: 모서리 입자를 제거한 경우 True → Miles–Lantuéjoul 보정 D 값 추가.
    """
    ps = [scaled(p, um_per_px) for p in particles]
    n = len(ps)
    s: dict = {"n_particles": n, "unit": "µm" if um_per_px else "px",
               "irregular_threshold": float(irregular_circularity)}
    if n == 0:
        return s

    def col(k):
        return np.array([p.get(k, np.nan) for p in ps], dtype=np.float64)

    ecd = col("ecd")
    area = col("area")
    sd = float(ecd.std(ddof=1)) if n > 1 else 0.0
    s.update({
        "ecd_mean": float(ecd.mean()), "ecd_std": sd,
        "ecd_min": float(ecd.min()), "ecd_max": float(ecd.max()),
        "area_mean": float(area.mean()),
        "ecd_cv": sd / float(ecd.mean()) if ecd.mean() > 0 else float("nan"),
    })
    q = {k: float(np.percentile(ecd, k)) for k in (10, 25, 50, 75, 90, 95)}
    s.update({"d10": q[10], "d25": q[25], "d50": q[50], "d75": q[75], "d90": q[90], "d95": q[95]})
    s["span"] = (q[90] - q[10]) / q[50] if q[50] > 0 else float("nan")
    s["iqr"] = q[75] - q[25]
    s["mad"] = float(np.median(np.abs(ecd - q[50])))
    s["d90_d10"] = q[90] / q[10] if q[10] > 0 else float("nan")
    s["d90_d50"] = q[90] / q[50] if q[50] > 0 else float("nan")

    # 미세 / 조대 입자 (D50 상대 기준)
    fine, coarse = ecd < 0.5 * q[50], ecd > 2.0 * q[50]
    s["fine_number_pct"] = 100.0 * fine.mean()
    s["fine_area_pct"] = 100.0 * area[fine].sum() / area.sum()
    s["coarse_number_pct"] = 100.0 * coarse.mean()
    s["coarse_area_pct"] = 100.0 * area[coarse].sum() / area.sum()
    k10 = max(1, math.ceil(0.1 * n))
    s["top10_area_share_pct"] = 100.0 * np.sort(area)[::-1][:k10].sum() / area.sum()

    # 가중 평균 · 로그정규 · 불균등도
    s["area_weighted_mean_d"] = float((area * ecd).sum() / area.sum())
    s["area_weighted_d50"] = _weighted_percentile(ecd, area, 0.5)
    lnd = np.log(ecd)
    s["lognorm_mu"] = float(lnd.mean())
    s["lognorm_sigma"] = float(lnd.std(ddof=0))
    s["geo_mean_d"] = float(math.exp(lnd.mean()))
    s["geo_sd"] = float(math.exp(lnd.std(ddof=1))) if n > 1 else float("nan")
    s["gini_d"] = _gini(ecd)
    s["psd_entropy"] = _norm_entropy(ecd, log=True)

    vw = ecd ** 3
    dv10, dv50, dv90 = (_weighted_percentile(ecd, vw, x) for x in (0.1, 0.5, 0.9))
    s.update({"dv10": dv10, "dv50": dv50, "dv90": dv90,
              "span_v": (dv90 - dv10) / dv50 if dv50 > 0 else float("nan")})

    if edge_corrected:
        w = col("ml_weight")
        ok = np.isfinite(w)
        if ok.sum() >= 1:
            e, ww = ecd[ok], w[ok]
            m10, m50, m90 = (_weighted_percentile(e, ww, x) for x in (0.1, 0.5, 0.9))
            s.update({"d10_ml": m10, "d50_ml": m50, "d90_ml": m90,
                      "span_ml": (m90 - m10) / m50 if m50 > 0 else float("nan"),
                      "ecd_mean_ml": float((ww * e).sum() / ww.sum())})

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


# 형상 지표 분포 통계 — 지표별 11개 통계량
SHAPE_STAT_KEYS = [
    "circularity", "aspect_ratio", "feret_aspect_ratio", "solidity", "convexity",
    "roundness", "compactness", "rectangularity", "in_circ_ratio", "eccentricity",
    "radius_cv", "thick_cv", "fourier_2",
]


def shape_distribution(particles: list[dict]) -> list[dict]:
    """형상 지표별 분포 통계 (무차원이라 스케일 무관)."""
    rows = []
    for k in SHAPE_STAT_KEYS:
        a = np.array([p.get(k, np.nan) for p in particles], dtype=np.float64)
        a = a[np.isfinite(a)]
        row: dict = {"metric": k, "n": int(a.size)}
        if a.size:
            q10, q25, q50, q75, q90 = np.percentile(a, [10, 25, 50, 75, 90])
            m = float(a.mean())
            sd = float(a.std(ddof=1)) if a.size > 1 else 0.0
            row.update({
                "mean": m, "median": float(q50), "sd": sd,
                "cv": sd / m if m else float("nan"),
                "q10": float(q10), "q90": float(q90), "iqr": float(q75 - q25),
                "skew": float(stats.skew(a, bias=False)) if a.size > 2 and sd > 0 else float("nan"),
                "kurt": float(stats.kurtosis(a, bias=False)) if a.size > 3 and sd > 0 else float("nan"),
                "gini": _gini(a),
                "entropy": _norm_entropy(a),
            })
        rows.append(row)
    return rows


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


# ─────────────────────────── 엑셀용 지표 정의 (한/영 · 식 · 계산 방법) ───────────────────────────
#
# 기호: A 면적, P 둘레(Crofton), a/b 등가 타원 장축/단축, F_max/F_min Feret 최대/최소,
#       (x̄, ȳ) 면적 중심, r(s) 중심–경계 거리, s = µm/px

class Metric(NamedTuple):
    key: str
    ko: str
    en: str
    kind: str        # len | area | px | none | pct | bits | count
    formula: str
    desc_ko: str
    desc_en: str


M = Metric

PARTICLE_COLUMNS: list[Metric] = [
    M("id", "입자 번호", "Particle ID", "none", "",
      "면적 큰 순 번호 (번호 이미지와 동일)", "Numbered by area, descending (matches numbered view)"),
    M("cx", "중심 x", "Centroid x", "px", "x̄ = Σx / N", "면적 중심, 이미지 좌표", "Area centroid, image coordinate"),
    M("cy", "중심 y", "Centroid y", "px", "ȳ = Σy / N", "면적 중심, 이미지 좌표", "Area centroid, image coordinate"),
    # ── 크기 · 치수 ──
    M("area", "투영 면적", "Projected Area", "area", "A = N_px · s²",
      "입자 픽셀 수 × 픽셀 면적", "Pixel count × pixel area"),
    M("perimeter", "둘레 (Crofton)", "Perimeter (Crofton)", "len", "P = Crofton 공식 (4방향)",
      "방향 편향을 줄인 둘레 추정 (skimage perimeter_crofton). 검증: 원·타원 오차 ±1%, 직선 변 −6~+3%",
      "Orientation-unbiased estimate (skimage perimeter_crofton). Checked: circles/ellipses ±1%, straight edges −6…+3%"),
    M("perimeter_trace", "둘레 (경계 추적)", "Perimeter (boundary trace)", "len", "경계 픽셀 체인 길이",
      "skimage perimeter. 검증: 원 r=40 에서 +4% (계단 경계 과대)", "skimage perimeter. Checked: +4% on r=40 circle (staircase)"),
    M("ecd", "등가원 직경 (ECD)", "Equivalent Circle Diameter (ECD)", "len", "ECD = √(4A/π)",
      "면적이 같은 원의 지름", "Diameter of the circle with equal area"),
    M("major", "장축 길이", "Major Axis Length", "len", "a = 4√λ₁",
      "2차 중심 모멘트가 같은 타원의 장축 (λ = 공분산 고유값)", "Equivalent-moment ellipse; λ = covariance eigenvalues"),
    M("minor", "단축 길이", "Minor Axis Length", "len", "b = 4√λ₂", "같은 타원의 단축", "Minor axis of that ellipse"),
    M("feret_max", "최대 Feret 직경", "Max Feret Diameter", "len", "F_max = max 두 hull 꼭짓점 거리",
      "경계 픽셀 꼭짓점 convex hull 의 최대 캘리퍼 폭", "Largest caliper width of the pixel-corner convex hull"),
    M("feret_min", "최소 Feret 직경", "Min Feret Diameter", "len", "F_min = min_변 max 수직거리",
      "rotating calipers 로 구한 최소 폭", "Smallest width via rotating calipers"),
    M("feret_mean", "평균 Feret 직경", "Mean Feret Diameter", "len", "F̄ = mean_θ F(θ), θ = 0°…179°",
      "1° 간격 180 방향 캘리퍼 폭 평균 (≈ 볼록껍질 둘레/π)", "Mean caliper width over 180 directions (≈ convex perimeter / π)"),
    M("feret_sd", "Feret 직경 SD", "Feret Diameter SD", "len", "SD_θ F(θ)",
      "방향별 캘리퍼 폭의 표준편차", "SD of caliper widths over directions"),
    M("rect_length", "최소 회전사각형 긴 변", "Min Rotated Rectangle Length", "len", "minAreaRect 긴 변",
      "면적 최소 외접 회전사각형. cv2.minAreaRect", "Minimum-area enclosing rotated rectangle; cv2.minAreaRect"),
    M("rect_width", "최소 회전사각형 짧은 변", "Min Rotated Rectangle Width", "len", "minAreaRect 짧은 변", "", ""),
    M("convex_area", "볼록껍질 면적", "Convex Hull Area", "area", "A_hull",
      "skimage area_convex", "skimage area_convex"),
    M("convex_perimeter", "볼록껍질 둘레", "Convex Hull Perimeter", "len", "P_hull (Crofton)",
      "볼록껍질 이미지의 Crofton 둘레", "Crofton perimeter of the convex-hull image"),
    M("inscribed_d", "최대 내접원 직경", "Max Inscribed Circle Diameter", "len", "D_in = 2 · max EDT",
      "입자 안 거리변환 최댓값 × 2 (픽셀 중심 기준이라 ±1px)", "2 × max Euclidean distance transform (±1 px, pixel-centre based)"),
    M("enclosing_d", "최소 외접원 직경", "Min Enclosing Circle Diameter", "len", "D_out = 2 · r_min-enclosing",
      "입자를 감싸는 최소원. cv2.minEnclosingCircle", "Smallest enclosing circle; cv2.minEnclosingCircle"),
    M("radius_max", "최대 중심반경", "Max Centroid Radius", "len", "max r(s)",
      "면적 중심 → 경계 최대 거리 (경계 128점 등간격 재샘플)", "Max centroid-to-boundary distance (128 arc-length samples)"),
    M("radius_min", "최소 중심반경", "Min Centroid Radius", "len", "min r(s)", "", ""),
    M("radius_mean", "평균 중심반경", "Mean Centroid Radius", "len", "mean r(s)", "", ""),
    # ── 형상 ──
    M("circularity", "원형도", "Circularity", "none", "4πA / P²",
      "1 = 완전한 원. 1 초과는 1 로 자름", "1 = perfect circle; capped at 1"),
    M("aspect_ratio", "종횡비", "Aspect Ratio", "none", "a / b", "등가 타원 장축/단축 (1 = 등방)", "Ellipse major/minor (1 = isotropic)"),
    M("feret_aspect_ratio", "Feret 종횡비", "Feret Aspect Ratio", "none", "F_max / F_min",
      "실제 캘리퍼 기반 종횡비", "Caliper-based aspect ratio"),
    M("eccentricity", "이심률", "Eccentricity", "none", "√(1 − (b/a)²)", "0 = 원, →1 길쭉", "0 = circle, →1 elongated"),
    M("roundness", "진원도 (Roundness)", "Roundness", "none", "4A / (π a²)", "ImageJ Round. 1 초과는 1 로 자름", "ImageJ 'Round'; capped at 1"),
    M("solidity", "고형도 (Solidity)", "Solidity", "none", "A / A_hull", "낮을수록 오목", "Lower = more concave"),
    M("convexity", "볼록도 (Convexity)", "Convexity", "none", "P_hull / P", "낮을수록 경계 굴곡. 1 초과는 1 로 자름", "Lower = rougher boundary; capped at 1"),
    M("rectangularity", "직사각형도", "Rectangularity", "none", "A / (L_rect · W_rect)",
      "최소 회전사각형 대비 점유율", "Fill ratio of the minimum rotated rectangle"),
    M("compactness", "Feret 조밀도", "Feret-Based Compactness", "none", "4A / (π F_max²)",
      "최대 Feret 를 지름으로 하는 원 대비 면적", "Area relative to circle of diameter F_max"),
    M("in_circ_ratio", "내접/외접원 비", "Inscribed/Circumscribed Ratio", "none", "D_in / D_out",
      "1 = 원, 작을수록 길쭉·불규칙", "1 = circle; lower = elongated/irregular"),
    # ── 방사형 · Fourier · 모멘트 ──
    M("radius_sd", "중심반경 SD", "Radial Distance SD", "len", "SD r(s)", "", ""),
    M("radius_cv", "중심반경 CV", "Radial Distance CV", "none", "SD r / mean r", "반경 변동계수 (원 = 0)", "Coefficient of variation (circle = 0)"),
    M("radius_range", "중심반경 범위", "Radial Distance Range", "len", "max r − min r", "", ""),
    M("radius_skew", "중심반경 왜도", "Radial Distance Skewness", "none", "skew r(s)", "", ""),
    M("radius_kurt", "중심반경 첨도", "Radial Distance Kurtosis", "none", "excess kurtosis r(s)", "", ""),
    *[M(f"fourier_{k}", f"Fourier {k}차", f"Fourier Descriptor {k}", "none",
        f"FD{k} = 2|R_{k}| / |R_0|, R = FFT r(s)",
        {1: "중심 어긋남 성분", 2: "타원형(길쭉함) 성분", 3: "삼각형 성분", 4: "사각형 성분", 5: "오각형 성분"}[k]
        + " — 평균 반경 대비 상대 진폭",
        {1: "off-centre", 2: "elongation", 3: "triangularity", 4: "squareness", 5: "pentagonal"}[k]
        + " component; amplitude relative to mean radius")
      for k in range(1, 6)],
    M("fourier_low_energy", "저주파 Fourier 에너지", "Low-Frequency Fourier Energy", "none", "Σ_{k=1..5} FD_k²",
      "전반적 형태 변형 크기", "Magnitude of overall shape deformation"),
    *[M(f"hu_{k}", f"Hu 모멘트 {k}", f"Hu Moment {k}", "none", f"−sign(φ{k})·log10|φ{k}|",
        "이동·크기·회전 불변 모멘트 (log 변환). cv2.HuMoments. φ=0 (완전 대칭) 이면 빈칸" if k == 1 else "",
        "Translation/scale/rotation invariant (log-scaled); cv2.HuMoments. Blank if φ = 0 (perfect symmetry)" if k == 1 else "")
      for k in range(1, 8)],
    # ── 국소 두께 ──
    M("thick_mean", "국소 두께 평균", "Mean Local Thickness", "len", "mean t(p)",
      "t(p) = 픽셀 p 를 포함하는 최대 내접원 지름 (Hildebrand, medial axis 기반)",
      "t(p) = diameter of the largest inscribed disk containing p (Hildebrand, via medial axis)"),
    M("thick_median", "국소 두께 중앙값", "Median Local Thickness", "len", "median t(p)", "", ""),
    M("thick_sd", "국소 두께 SD", "Local Thickness SD", "len", "SD t(p)", "", ""),
    M("thick_cv", "국소 두께 CV", "Local Thickness CV", "none", "SD t / mean t",
      "두께 불균일성 (좁은 목 + 넓은 몸통이면 큼)", "Thickness non-uniformity (necks → high)"),
    M("thick_d10", "국소 두께 D10", "Local Thickness D10", "len", "P10 t(p)", "", ""),
    M("thick_d90", "국소 두께 D90", "Local Thickness D90", "len", "P90 t(p)", "", ""),
    M("thick_max", "국소 두께 최대", "Max Local Thickness", "len", "max t(p) = D_in", "최대 내접원 직경과 같음", "Equals max inscribed diameter"),
    # ── 기타 ──
    M("texture_entropy", "표면 텍스처 엔트로피", "Surface Texture Entropy", "bits", "H = −Σ pᵢ log₂ pᵢ",
      "입자 내부 밝기(256단계) 히스토그램 엔트로피 — 원본 밝기 사용", "Gray-level (256 bins) entropy inside particle — uses image intensity"),
    M("fractal_dim", "프랙탈 차원", "Fractal Dimension", "none", "D = 1 − d log L(s) / d log s",
      "Richardson divider, s = 2px…bbox/2 (8단계). bbox<16px 이면 빈칸. ⚠ 마스크 평활화에 민감",
      "Richardson divider, s = 2px…bbox/2 (8 steps). Blank if bbox < 16px. ⚠ sensitive to mask smoothing"),
    M("irregular", "불규칙 입자 (1=예)", "Irregular (1 = yes)", "none", "1 if 원형도 < 기준값", "", ""),
    M("ml_weight", "모서리 보정 가중치", "Edge-correction weight", "none", "w = W·H / ((W − w_bb)(H − h_bb))",
      "Miles–Lantuéjoul. W·H = 분석 영역, w_bb·h_bb = 입자 외접상자. 큰 입자일수록 큼",
      "Miles–Lantuéjoul. W·H = analysis window, w_bb·h_bb = particle bounding box"),
]

SUMMARY_ROWS: list[Metric] = [
    M("n_particles", "입자 수", "Particle count", "count", "N", "분석된 입자 수", "Number of analysed particles"),
    M("n_edge_removed", "모서리 제거 입자 수", "Edge particles removed", "count", "", "테두리에 닿아 제외된 입자", "Particles touching the border, excluded"),
    M("crop_bottom_px", "하단 크롭 (px)", "Bottom crop (px)", "count", "", "잘라낸 하단 정보바 높이", "Height of the cropped bottom info bar"),
    M("ecd_mean", "ECD 평균", "Mean Diameter (ECD)", "len", "Σ ECD / N", "", ""),
    M("ecd_std", "ECD 표준편차", "Diameter SD", "len", "√(Σ(ECD − mean)² / (N−1))", "", ""),
    M("ecd_cv", "ECD 변동계수", "Diameter CV", "none", "SD / mean", "", ""),
    M("ecd_min", "ECD 최소", "ECD min", "len", "", "", ""),
    M("ecd_max", "ECD 최대", "ECD max", "len", "", "", ""),
    M("d10", "D10", "D10", "len", "P10(ECD)", "개수 기준 누적 10% (선형 보간)", "Number-based 10th percentile"),
    M("d25", "D25", "D25", "len", "P25(ECD)", "", ""),
    M("d50", "D50", "D50", "len", "P50(ECD)", "중앙값", "Median"),
    M("d75", "D75", "D75", "len", "P75(ECD)", "", ""),
    M("d90", "D90", "D90", "len", "P90(ECD)", "", ""),
    M("d95", "D95", "D95", "len", "P95(ECD)", "입자 수가 적으면 불안정", "Unstable for small N"),
    M("span", "PSD Span", "PSD Span", "none", "(D90 − D10) / D50", "작을수록 균일", "Smaller = more uniform"),
    M("iqr", "직경 IQR", "Diameter IQR", "len", "D75 − D25", "", ""),
    M("mad", "직경 MAD", "Diameter MAD", "len", "median |ECD − D50|", "", ""),
    M("d90_d10", "D90/D10", "D90/D10 Ratio", "none", "D90 / D10", "", ""),
    M("d90_d50", "D90/D50", "D90/D50 Ratio", "none", "D90 / D50", "", ""),
    M("skewness", "직경 왜도", "Diameter Skewness", "none", "표본 보정 왜도 g", "", ""),
    M("kurtosis_excess", "직경 첨도 (초과)", "Diameter Kurtosis (excess)", "none", "표본 보정 초과 첨도 κ", "입자 수가 적으면 불안정", "Unstable for small N"),
    M("fine_number_pct", "미세 입자 개수 비율 (%)", "Fine Particle Number Fraction (%)", "pct", "100 · #(ECD < 0.5·D50) / N",
      "미세 기준 = 0.5 × D50", "Fine threshold = 0.5 × D50"),
    M("fine_area_pct", "미세 입자 면적 비율 (%)", "Fine Particle Area Fraction (%)", "pct", "100 · ΣA(ECD < 0.5·D50) / ΣA", "", ""),
    M("coarse_number_pct", "조대 입자 개수 비율 (%)", "Coarse Particle Number Fraction (%)", "pct", "100 · #(ECD > 2·D50) / N",
      "조대 기준 = 2 × D50", "Coarse threshold = 2 × D50"),
    M("coarse_area_pct", "조대 입자 면적 비율 (%)", "Coarse Particle Area Fraction (%)", "pct", "100 · ΣA(ECD > 2·D50) / ΣA", "", ""),
    M("top10_area_share_pct", "상위 10% 입자 면적 비중 (%)", "Top 10% Particle Area Share (%)", "pct", "100 · Σ(상위 ⌈0.1N⌉ 개 A) / ΣA", "", ""),
    M("area_weighted_mean_d", "면적 가중 평균 직경", "Area-Weighted Mean Diameter", "len", "Σ(A·ECD) / ΣA", "", ""),
    M("area_weighted_d50", "면적 가중 D50", "Area-Weighted D50", "len", "A 가중 누적 50%", "", ""),
    M("geo_mean_d", "기하평균 직경", "Geometric Mean Diameter", "len", "exp(mean ln ECD)", "", ""),
    M("geo_sd", "기하표준편차", "Geometric SD", "none", "exp(SD ln ECD)", "", ""),
    M("lognorm_mu", "로그정규 μ", "Lognormal μ", "none", "mean ln ECD (MLE)",
      "ln(단위) 기준. 로그정규를 가정할 때만 의미", "In ln(unit); meaningful only if lognormal"),
    M("lognorm_sigma", "로그정규 σ", "Lognormal σ", "none", "SD ln ECD (MLE, ddof=0)", "", ""),
    M("gini_d", "직경 Gini 계수", "Diameter Gini Coefficient", "none", "Σᵢ Σⱼ |xᵢ − xⱼ| / (2N² x̄)",
      "0 = 모두 같은 크기", "0 = all equal"),
    M("psd_entropy", "PSD 엔트로피 (정규화)", "PSD Shannon Entropy (normalised)", "none", "−Σ pᵢ log₂ pᵢ / log₂ 20",
      "ln ECD 를 20 구간 히스토그램. 0~1. 구간 수에 따라 값이 달라짐", "20-bin histogram of ln ECD; 0–1; depends on bin count"),
    M("dv10", "Dv10 (부피 기준)", "Dv10 (volume-based)", "len", "ECD³ 가중 누적 10%", "레이저 회절과 비교용", "Comparable to laser diffraction"),
    M("dv50", "Dv50 (부피 기준)", "Dv50 (volume-based)", "len", "ECD³ 가중 누적 50%", "", ""),
    M("dv90", "Dv90 (부피 기준)", "Dv90 (volume-based)", "len", "ECD³ 가중 누적 90%", "", ""),
    M("span_v", "PSD Span (부피 기준)", "PSD Span (volume-based)", "none", "(Dv90 − Dv10) / Dv50", "", ""),
    M("d10_ml", "D10 (모서리 보정)", "D10 (edge-corrected)", "len", "w 가중 누적 10%",
      "Miles–Lantuéjoul 가중치 w 로 모서리 제거 편향 보정. 모서리 제거 시에만", "Miles–Lantuéjoul weighted; only with edge removal"),
    M("d50_ml", "D50 (모서리 보정)", "D50 (edge-corrected)", "len", "w 가중 누적 50%", "", ""),
    M("d90_ml", "D90 (모서리 보정)", "D90 (edge-corrected)", "len", "w 가중 누적 90%", "", ""),
    M("span_ml", "PSD Span (모서리 보정)", "PSD Span (edge-corrected)", "none", "(D90_ml − D10_ml) / D50_ml", "", ""),
    M("ecd_mean_ml", "ECD 평균 (모서리 보정)", "Mean ECD (edge-corrected)", "len", "Σ(w·ECD) / Σw", "", ""),
    M("circularity_mean", "원형도 평균", "Circularity mean", "none", "", "", ""),
    M("circularity_std", "원형도 표준편차", "Circularity std", "none", "", "", ""),
    M("aspect_ratio_mean", "종횡비 평균", "Aspect Ratio mean", "none", "", "", ""),
    M("solidity_mean", "Solidity 평균", "Solidity mean", "none", "", "", ""),
    M("convexity_mean", "Convexity 평균", "Convexity mean", "none", "", "", ""),
    M("roundness_mean", "진원도 평균", "Roundness mean", "none", "", "", ""),
    M("feret_max_mean", "최대 Feret 평균", "Max Feret mean", "len", "", "", ""),
    M("feret_min_mean", "최소 Feret 평균", "Min Feret mean", "len", "", "", ""),
    M("eccentricity_mean", "이심률 평균", "Eccentricity mean", "none", "", "", ""),
    M("irregular_threshold", "불규칙 기준 (원형도 <)", "Irregular threshold (circularity <)", "none", "", "", ""),
    M("irregular_count", "불규칙 입자 수", "Irregular particle count", "count", "", "", ""),
    M("irregular_fraction_pct", "불규칙 입자 비율 (%)", "Irregular particle fraction (%)", "pct", "100 · #(원형도 < 기준) / N", "", ""),
    M("spearman_rho", "크기–원형도 Spearman ρ", "Size–Circularity Spearman ρ", "none", "순위 상관 (ECD, 원형도)",
      "음수 = 클수록 덜 둥글다", "Negative = larger particles are less round"),
    M("spearman_p", "Spearman p-값", "Spearman p-value", "none", "", "< 0.05 이면 유의", "Significant if < 0.05"),
    M("pearson_r", "크기–원형도 Pearson r", "Size–Circularity Pearson r", "none", "선형 상관", "", ""),
    M("pearson_p", "Pearson p-값", "Pearson p-value", "none", "", "", ""),
    M("bimodality_coefficient", "이봉 계수 (BC)", "Bimodality Coefficient (BC)", "none", "(g² + 1) / (κ + 3(N−1)² / ((N−2)(N−3)))",
      "> 0.555 이면 이봉 가능성", "> 0.555 suggests bimodality"),
    M("gmm_mu1", "GMM 모드1 평균", "GMM mode-1 mean", "len", "2성분 Gaussian mixture (EM)", "", ""),
    M("gmm_mu2", "GMM 모드2 평균", "GMM mode-2 mean", "len", "", "", ""),
    M("gmm_sigma1", "GMM 모드1 표준편차", "GMM mode-1 sigma", "len", "", "", ""),
    M("gmm_sigma2", "GMM 모드2 표준편차", "GMM mode-2 sigma", "len", "", "", ""),
    M("gmm_w1", "GMM 모드1 비중", "GMM mode-1 weight", "none", "", "", ""),
    M("gmm_w2", "GMM 모드2 비중", "GMM mode-2 weight", "none", "", "", ""),
    M("ashman_d", "Ashman D", "Ashman's D", "none", "√2 |μ₁ − μ₂| / √(σ₁² + σ₂²)", "> 2 이면 두 모드 분리", "> 2 = separated modes"),
    M("delta_bic", "ΔBIC (1성분 − 2성분)", "ΔBIC (1-comp − 2-comp)", "none", "BIC = k ln N − 2 ln L (k = 2, 5)",
      "> 10 이면 2성분 강하게 지지", "> 10 = strong support for two modes"),
    M("bimodal", "이봉 분포 판정", "Bimodal (verdict)", "none", "BC > 0.555 그리고 ΔBIC > 10", "", ""),
    M("texture_entropy_mean", "텍스처 엔트로피 평균 (bits)", "Texture entropy mean (bits)", "bits", "", "", ""),
    M("fractal_dim_mean", "프랙탈 차원 평균", "Fractal dimension mean", "none", "", "bbox ≥ 16px 입자만", "Particles with bbox ≥ 16 px only"),
    M("fractal_n_valid", "프랙탈 계산 입자 수", "Fractal valid count", "count", "", "", ""),
]

SHAPE_STAT_COLUMNS = [
    ("n", "입자 수", "Count", "N (유효 값)"),
    ("mean", "평균", "Mean", "Σx / N"),
    ("median", "중앙값", "Median", "P50"),
    ("sd", "표준편차", "SD", "√(Σ(x − x̄)² / (N−1))"),
    ("cv", "변동계수", "CV", "SD / mean"),
    ("q10", "하위 10%", "Q10", "P10"),
    ("q90", "하위 90%", "Q90", "P90"),
    ("iqr", "사분위 범위", "IQR", "P75 − P25"),
    ("skew", "왜도", "Skewness", "표본 보정 왜도"),
    ("kurt", "첨도 (초과)", "Kurtosis (excess)", "표본 보정 초과 첨도"),
    ("gini", "Gini 계수", "Gini", "Σᵢ Σⱼ |xᵢ − xⱼ| / (2N² x̄)"),
    ("entropy", "엔트로피 (정규화)", "Entropy (normalised)", "20 구간 히스토그램 −Σp log₂p / log₂20"),
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

# 제외한 지표와 이유 (지표정의 시트 하단)
EXCLUDED_NOTES = [
    ("경계 곡률 · 고주파 거칠기 · 돌출부 · 함몰 개수 · 고주파 Fourier",
     "Curvature, high-frequency roughness, protrusions, defect count, high-order Fourier",
     "마스크 경계가 분할 모델(U-Net 임계, YOLO σ=3 평활화)로 만들어져, 실제 표면보다 모델의 평활화를 측정함. 함몰 개수는 깊이 기준값에 크게 의존",
     "Mask boundary is produced by the model's smoothing, so these measure the model rather than the surface; defect counts depend on depth threshold"),
    ("외접상자 너비·높이·Extent · 좌우/상하 대칭 · 주축 방향",
     "Bounding box W/H/extent, X/Y mirror symmetry, principal orientation",
     "분말이 무작위 방향으로 놓여 이미지 방향에 따라 값이 바뀜 (입자 고유 성질 아님)",
     "Depend on image orientation of randomly placed powder"),
    ("골격 분기·길이 · 구멍 · Euler 수",
     "Skeleton branches/length, holes, Euler number",
     "둥근 2차 입자에서 골격은 잡음에 민감, 마스크 구멍은 대부분 분할 오류",
     "Skeleton is noise-sensitive for round particles; mask holes are mostly segmentation errors"),
    ("Zernike 모멘트 · 재구성 오차",
     "Zernike moments, reconstruction error",
     "열 수가 많고 물리적 해석이 어려움 (Hu 모멘트·저차 Fourier 로 대체)",
     "Many columns, hard to interpret (Hu moments + low-order Fourier used instead)"),
    ("입자 간 거리 · 공간 배열 · 접촉 · 기공 · 균열 · 1차 입자",
     "Spatial arrangement, contacts, pores, cracks, primary particles",
     "분말 분산 방식에 좌우되거나(공간), 별도 마스크가 필요(기공·균열·1차 입자) — 추후 단계",
     "Depend on sample dispersion, or need separate masks — future work"),
]


def unit_label(kind: str, unit: str) -> str:
    return {"len": unit, "area": f"{unit}²", "bits": "bits", "pct": "%", "px": "px"}.get(kind, "")
