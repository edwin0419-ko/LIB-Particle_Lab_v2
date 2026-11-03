"""Hybrid 모드 — U-Net 확률맵 + YOLO 인스턴스 분리선 융합.

사용자 spec:
  1. U-Net P >= 0.75 = 보수적 입자 (메인 anchor)
  2. 각 배경 픽셀의 d_1+d_2 (가장 가까운/두번째 가까운 anchor component 거리)
  3. Otsu τ → M_close = d_1+d_2 < τ (좁은 틈)
     + balance_floor 조건으로 한 입자에만 붙은 외곽 픽셀 배제
  4. YOLO 인스턴스 경계 B
  5. 입자 = M_75 ∪ (M_close ∩ P>=0.30 ∩ ¬B),  분리선 = M_close ∩ B
  6. instance = connected_components(입자 − 분리선)
"""
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional

import cv2
import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from PIL import Image
from scipy import ndimage as ndi

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluate import pixel_confusion, safe_div  # noqa: E402
from hybrid_core import HybridParams, colorize_instances, hybrid_fuse  # noqa: E402
from particle_morphology import (  # noqa: E402
    PARTICLE_COLUMNS,
    detect_bottom_bar,
    distribution_summary,
    json_safe,
    particle_metrics,
    relabel_by_area,
    remove_edge_touching,
    scaled,
    shape_distribution,
    size_bins,
    unit_label,
)

from ._excel_export import (  # noqa: E402
    make_excel_3way,
    xlsx_data_url as _xlsx_data_url_shared,
)


# ─────────────── v2 인라인 유틸 (학습 캐시 없음) ───────────────


def _resolve_device(device: str) -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    d = (device or "auto").strip().lower()
    if d == "auto":
        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return d


def _save_upload(upload: UploadFile, suffix: str = ".png") -> Path:
    fd, p = tempfile.mkstemp(suffix=suffix, prefix="plab_v2_")
    upload.file.seek(0)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.file.read())
    upload.file.seek(0)
    return Path(p)

router = APIRouter(prefix="/api/run", tags=["run"])

ROLE_SUFFIXES = ("_image", "_img", "_orig", "_label", "_mask", "_gt")
METRIC_KEYS = ("Precision", "Recall", "Accuracy", "IoU", "F1",
               "mAP@0.5", "ParticleCountError")


# ─────────────── helpers ───────────────


def _make_d_histogram_figure(
    d_values: np.ndarray, tau: float, bin_width: float = 1.0,
) -> tuple[bytes, np.ndarray, np.ndarray]:
    """d_+ 분포 히스토그램 PNG (논문 figure 용).

    bin_width=1.0 → 정수 단위 binning (엑셀 분석 친화적).
    반환: (png_bytes, bin_centers, counts)
    파란 막대 = d_+ < τ* (좁은 틈 후보), 회색 막대 = d_+ ≥ τ*, 빨간 점선 = τ*.
    """
    finite = d_values[np.isfinite(d_values)]
    if finite.size == 0:
        # 빈 히스토그램
        fig, ax = plt.subplots(figsize=(6.5, 4.0), dpi=110)
        ax.text(0.5, 0.5, "No background pixels", ha="center", va="center")
        ax.set_axis_off()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue(), np.array([]), np.array([])

    # bin_width 단위로 binning. 범위 [0, ceil(max)+bin_width]
    max_d = float(np.ceil(finite.max())) + bin_width
    bin_edges = np.arange(0.0, max_d + bin_width, bin_width)
    counts, bin_edges = np.histogram(finite, bins=bin_edges)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    width = bin_edges[1] - bin_edges[0]

    fig, ax = plt.subplots(figsize=(6.5, 4.0), dpi=110)
    below = bin_centers < tau
    ax.bar(bin_centers[below], counts[below], width=width,
           color="#3b82f6", edgecolor="none",
           label=f"d₊ < τ* (좁은 틈 후보)")
    ax.bar(bin_centers[~below], counts[~below], width=width,
           color="#d1d5db", edgecolor="none",
           label="d₊ ≥ τ* (배경)")
    ax.axvline(tau, color="#dc2626", linestyle="--", linewidth=2,
               label=f"τ* = {tau:.2f}")
    ax.set_xlabel("d₊(p) = d₁(p) + d₂(p)  [pixels]")
    ax.set_ylabel("Pixel count")
    ax.set_title(f"Distribution of d₊ over background pixels  (n={finite.size:,})")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue(), bin_centers, counts


def _csv_data_url(text: str) -> str:
    return "data:text/csv;base64," + base64.b64encode(text.encode("utf-8")).decode("ascii")


def _extract_particles(label_arr: np.ndarray) -> list[dict]:
    """입자 일련번호 + 면적 + 중심 좌표 추출.

    렌더링(번호 오버레이)은 클라이언트가 실시간으로 처리 — 이 백엔드는 raw data 만 전달.

    Args:
      label_arr: relabel_by_area 를 거친 (H, W) 정수 라벨맵. 0=배경, 1..K = 면적 큰 순.

    Returns:
      particles = [{id, label, area_px, cy, cx}, ...]
        id = 라벨 값 (1 부터, 면적 큰 순) → 형상 지표 엑셀의 입자 번호와 동일.
        label = str(id) — "1", "2", ...  (사용자 요청: "p" 접두사 제거)
    """
    flat = label_arr.ravel()
    areas = np.bincount(flat)
    ys, xs = np.indices(label_arr.shape)
    sy = np.bincount(flat, weights=ys.ravel(), minlength=areas.size)
    sx = np.bincount(flat, weights=xs.ravel(), minlength=areas.size)
    particles: list[dict] = []
    for lid in range(1, areas.size):
        if areas[lid] == 0:
            continue
        particles.append({
            "id": lid,
            "label": str(lid),
            "area_px": int(areas[lid]),
            "cy": int(round(sy[lid] / areas[lid])),
            "cx": int(round(sx[lid] / areas[lid])),
        })
    return particles


def _make_excel_bytes(
    params: dict,
    results: list[dict],
    summaries: dict,
) -> bytes:
    """Hybrid 결과 전체를 xlsx 한 파일로 묶어 반환.

    시트 구성:
      - Parameters         : 모든 알고리즘/추론 설정값
      - Metrics_per_image  : (filename × method) 행, 7개 지표 + 입자 수 + 진단
      - Summary            : method 별 이미지 평균 (3행)
      - Image_diagnostics  : 이미지별 K_unet, n_yolo, n_instances, tau 등
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F5FD6")
    center = Alignment(horizontal="center")

    def _style_header(ws, n_cols: int):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
        ws.freeze_panes = "A2"

    def _autosize(ws, max_width: int = 32):
        for col in ws.columns:
            length = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(length + 2, max_width)

    # ─── Sheet 1: Parameters ───
    ws = wb.active
    ws.title = "Parameters"
    ws.append(["Parameter", "Value"])
    _style_header(ws, 2)
    for k, v in params.items():
        ws.append([str(k), v if not isinstance(v, bool) else str(v)])
    _autosize(ws)

    # ─── Sheet 2: Metrics_per_image ───
    ws = wb.create_sheet("Metrics_per_image")
    headers = ["filename", "method",
               "Precision", "Recall", "Accuracy", "IoU", "F1",
               "mAP@0.5", "ParticleCountError",
               "n_gt_inst", "n_pred_inst"]
    ws.append(headers)
    _style_header(ws, len(headers))
    method_labels = [
        ("metrics_yolo",     "YOLO only"),
        ("metrics_unet_low", f"U-Net ≥ {params.get('low_thresh', 0.30)}"),
        ("metrics_hybrid",   "Hybrid"),
    ]
    for r in results:
        fname = r.get("filename", "")
        for key, label in method_labels:
            m = r.get(key)
            if m is None:
                continue
            ws.append([
                fname, label,
                float(m["Precision"]), float(m["Recall"]),
                float(m["Accuracy"]), float(m["IoU"]), float(m["F1"]),
                float(m["mAP@0.5"]), float(m["ParticleCountError"]),
                int(m["n_gt_inst"]), int(m["n_pred_inst"]),
            ])
    # 숫자 포맷
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=9):
        for cell in row:
            cell.number_format = "0.0000"
    _autosize(ws)

    # ─── Sheet 3: Summary ───
    ws = wb.create_sheet("Summary")
    headers = ["method",
               "Precision", "Recall", "Accuracy", "IoU", "F1",
               "mAP@0.5", "ParticleCountError",
               "n_gt_inst (sum)", "n_pred_inst (sum)", "n_with_gt"]
    ws.append(headers)
    _style_header(ws, len(headers))
    sum_map = [
        ("summary_yolo",     "YOLO only"),
        ("summary_unet_low", f"U-Net ≥ {params.get('low_thresh', 0.30)}"),
        ("summary_hybrid",   "Hybrid"),
    ]
    for key, label in sum_map:
        s = summaries.get(key)
        if s is None:
            continue
        ws.append([
            label,
            float(s["Precision"]), float(s["Recall"]),
            float(s["Accuracy"]), float(s["IoU"]), float(s["F1"]),
            float(s["mAP@0.5"]), float(s["ParticleCountError"]),
            int(s["n_gt_inst"]), int(s["n_pred_inst"]),
            int(s["n_with_gt"]),
        ])
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=8):
        for cell in row:
            cell.number_format = "0.0000"
    _autosize(ws)

    # ─── Sheet 4: Image_diagnostics ───
    ws = wb.create_sheet("Image_diagnostics")
    headers = ["filename", "n_instances (hybrid)",
               "K_unet_anchor", "n_yolo", "tau (used)", "pixel_csv_rows"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for r in results:
        ws.append([
            r.get("filename", ""),
            int(r.get("n_instances", 0)),
            int(r.get("K_unet_anchor", 0)),
            int(r.get("n_yolo", 0)),
            float(r.get("tau", 0.0)),
            int(r.get("pixel_csv_rows", 0)),
        ])
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        for cell in row:
            cell.number_format = "0.00"
    _autosize(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xlsx_data_url(data: bytes) -> str:
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _png_bytes_to_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _png_data_url(arr: np.ndarray) -> str:
    if arr.dtype == bool:
        arr = (arr.astype(np.uint8) * 255)
    elif arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("PNG 인코딩 실패")
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _read_gray(upload: UploadFile) -> np.ndarray:
    upload.file.seek(0)
    raw = upload.file.read()
    upload.file.seek(0)
    if not raw:
        raise HTTPException(400, f"빈 파일: {upload.filename}")
    return np.array(Image.open(io.BytesIO(raw)).convert("L"))


def _strip_role_suffix(stem: str) -> str:
    low = stem.lower()
    for suf in ROLE_SUFFIXES:
        if low.endswith(suf):
            return stem[: -len(suf)]
    return stem


def _match_gt_for(image_filename: str,
                  gts: list[UploadFile]) -> Optional[UploadFile]:
    if not gts:
        return None
    img_full = image_filename
    img_stem = Path(img_full).stem
    img_key = _strip_role_suffix(img_stem)
    for g in gts:
        if (g.filename or "") == img_full:
            return g
    for g in gts:
        if Path(g.filename or "").stem == img_stem:
            return g
    for g in gts:
        gt_stem = Path(g.filename or "").stem
        if _strip_role_suffix(gt_stem) == img_key:
            return g
    return None


def _mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = int(np.logical_and(a, b).sum())
    if inter == 0:
        return 0.0
    union = int(np.logical_or(a, b).sum())
    return inter / union if union else 0.0


def _compute_map50(pred_masks, gt_masks) -> float:
    n_gt = len(gt_masks)
    n_pred = len(pred_masks)
    if n_pred == 0 and n_gt == 0:
        return 1.0
    if n_pred == 0 or n_gt == 0:
        return 0.0
    tp_list, fp_list = [], []
    gt_used = np.zeros(n_gt, dtype=bool)
    for pm in pred_masks:
        best_iou, best_j = 0.0, -1
        for j in range(n_gt):
            if gt_used[j]:
                continue
            iou = _mask_iou(pm, gt_masks[j])
            if iou > best_iou:
                best_iou, best_j = iou, j
        if best_iou >= 0.5 and best_j >= 0:
            tp_list.append(1); fp_list.append(0); gt_used[best_j] = True
        else:
            tp_list.append(0); fp_list.append(1)
    tp_cum = np.cumsum(tp_list).astype(np.float64)
    fp_cum = np.cumsum(fp_list).astype(np.float64)
    recall = tp_cum / n_gt
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1)
    mrec = np.concatenate([[0.0], recall, [1.0]])
    mpre = np.concatenate([[0.0], precision, [0.0]])
    for i in range(len(mpre) - 1, 0, -1):
        mpre[i - 1] = max(mpre[i - 1], mpre[i])
    rec_thr = np.linspace(0, 1, 101)
    inds = np.searchsorted(mrec, rec_thr, side="left").clip(max=len(mpre) - 1)
    return float(mpre[inds].mean())


def _metrics_from_instances(instances: np.ndarray,
                            semantic: np.ndarray,
                            gt_bin: np.ndarray) -> dict:
    tp, fp, fn, tn = pixel_confusion(gt_bin, semantic)
    gt_lbl, n_gt = ndi.label(gt_bin)
    pred_masks = [(instances == i) for i in range(1, int(instances.max()) + 1)]
    gt_masks = [(gt_lbl == i) for i in range(1, int(n_gt) + 1)]
    map50 = _compute_map50(pred_masks, gt_masks)
    n_pred = int(instances.max())
    count_err = abs(n_pred - int(n_gt)) / max(int(n_gt), 1)
    return {
        "Precision": safe_div(tp, tp + fp),
        "Recall": safe_div(tp, tp + fn),
        "Accuracy": safe_div(tp + tn, tp + fp + fn + tn),
        "IoU": safe_div(tp, tp + fp + fn),
        "F1": safe_div(2 * tp, 2 * tp + fp + fn),
        "mAP@0.5": map50,
        "ParticleCountError": float(count_err),
        "n_gt_inst": int(n_gt),
        "n_pred_inst": n_pred,
    }


def _summary_metrics(per_image: list[dict]) -> Optional[dict]:
    if not per_image:
        return None
    out: dict = {"n_with_gt": len(per_image)}
    for k in METRIC_KEYS:
        out[k] = float(np.mean([m[k] for m in per_image]))
    for k in ("n_gt_inst", "n_pred_inst"):
        out[k] = int(np.sum([m[k] for m in per_image]))
    return out


# ─────────────── 추론 ───────────────


def _resolve_unet_weights(weights: Optional[UploadFile]) -> bytes:
    if weights is not None and (weights.filename or "").strip():
        weights.file.seek(0)
        return weights.file.read()
    raise HTTPException(400, "U-Net 가중치(.pt) 가 필요합니다.")


def _resolve_yolo_weights_path(weights: Optional[UploadFile],
                               weights_path: Optional[str]) -> tuple[Path, bool]:
    """반환: (.pt 파일 경로, 다 쓰고 삭제할지 여부)."""
    if weights_path and weights_path.strip():
        wp = Path(weights_path.strip())
        if not wp.is_file():
            raise HTTPException(400, f"yolo_weights_path 파일 없음: {wp}")
        return wp, False
    if weights is not None and (weights.filename or "").strip():
        return _save_upload(weights, ".pt"), True
    raise HTTPException(400, "YOLO 가중치(.pt) 또는 yolo_weights_path 가 필요합니다.")


# 실행 결과 → 엑셀 재생성용 캐시 (이미지 제외, 수치만). 스케일을 나중에 입력해도
# 재분석 없이 µm 엑셀을 만들 수 있게. 최근 _EXCEL_CACHE_MAX 회만 보관.
_EXCEL_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_EXCEL_CACHE_MAX = 8
_EXCEL_RESULT_KEYS = ("filename", "metrics_yolo", "metrics_unet_low", "metrics_hybrid",
                      "n_instances", "K_unet_anchor", "n_yolo", "tau", "pixel_csv_rows")


def _scale(scale_bar_px: float, scale_bar_um: float) -> Optional[float]:
    if scale_bar_px and scale_bar_px > 0 and scale_bar_um and scale_bar_um > 0:
        return float(scale_bar_um) / float(scale_bar_px)
    return None


def _morph_bundle(raw: list[dict], um_per_px: Optional[float], irr_thr: float,
                  settings: dict, scale_bar_px: float, scale_bar_um: float) -> dict:
    """입자 지표(px) 원본 → 스케일 적용된 이미지별/전체 분포 지표 + 엑셀 입력 dict."""
    unit = "µm" if um_per_px else "px"
    per_image = []
    edge = bool(raw and raw[0].get("edge_removal"))
    for m in raw:
        s = distribution_summary(m["particles"], um_per_px, irr_thr, edge_corrected=edge)
        s["n_edge_removed"] = m["n_edge_removed"]
        s["crop_bottom_px"] = m["crop_px"]
        per_image.append({
            "filename": m["filename"], "summary": s, "particles": m["particles"],
            "size_bins": size_bins(m["particles"], um_per_px),
            "shape_stats": shape_distribution(m["particles"]),
        })
    all_p = [q for m in raw for q in m["particles"]]
    all_s = distribution_summary(all_p, um_per_px, irr_thr, edge_corrected=edge)
    all_s["n_edge_removed"] = int(sum(m["n_edge_removed"] for m in raw))
    return {
        "unit": unit,
        "um_per_px": um_per_px,
        "all": {"summary": all_s, "size_bins": size_bins(all_p, um_per_px),
                "shape_stats": shape_distribution(all_p)},
        "per_image": per_image,
        "settings": {
            **settings,
            "scale_px": ("스케일바 길이 (px)", "Scale bar length (px)", float(scale_bar_px) or None),
            "scale_um": ("스케일바 실제 길이 (µm)", "Scale bar length (µm)", float(scale_bar_um) or None),
            "um_per_px": ("µm / px", "µm per px", um_per_px),
            "unit": ("길이 단위", "Length unit", unit),
        },
    }


@router.post("/hybrid/excel")
async def hybrid_excel_rescaled(
    run_id: str = Form(...),
    scale_bar_px: float = Form(...),
    scale_bar_um: float = Form(...),
):
    """이전 실행 결과의 지표 엑셀을 주어진 스케일(µm)로 다시 생성. 재분석 없음."""
    c = _EXCEL_CACHE.get(run_id)
    if c is None:
        raise HTTPException(404, "실행 결과가 서버에 없습니다 (서버 재시작 등). 분석을 다시 실행해주세요.")
    upp = _scale(scale_bar_px, scale_bar_um)
    if upp is None:
        raise HTTPException(400, "스케일바 길이(px)와 실제 길이(µm)를 0보다 크게 입력해주세요.")
    bundle = _morph_bundle(c["raw"], upp, c["irr_thr"], c["settings"],
                           scale_bar_px, scale_bar_um)
    params = {**c["params"], "scale_bar_px": float(scale_bar_px),
              "scale_bar_um": float(scale_bar_um), "um_per_px": upp}
    data = make_excel_3way(params, c["results"], c["summaries"], bundle)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/hybrid")
async def run_hybrid(
    images: List[UploadFile] = File(..., description="추론 대상 이미지들"),
    # U-Net 가중치
    unet_weights: Optional[UploadFile] = File(None, description="U-Net .pt"),
    # YOLO 가중치
    yolo_weights: Optional[UploadFile] = File(None, description="YOLO seg .pt"),
    yolo_weights_path: Optional[str] = Form(None,
        description="서버 디스크 YOLO .pt 절대 경로 (대용량 업로드 회피)"),
    # 정답 (선택)
    gts: Optional[List[UploadFile]] = File(None,
        description="정답 이진 마스크 (선택, 파일명 매칭)"),
    # Hybrid 파라미터
    high_thresh: float = Form(0.75,
        description="U-Net 확률 임계 — 확실한 입자 (anchor)"),
    low_thresh: float = Form(0.40,
        description="U-Net 확률 임계 — '가까운 픽셀'에서만 살릴 보강 (운용값)"),
    boundary_thickness: int = Form(3,
        description="YOLO 인스턴스 경계 두께 (px). 1~5 권장. 1px 는 큰 이미지에서 안 보일 수 있음"),
    min_anchor_area: int = Form(10,
        description="M_75 의 noise component 최소 크기 (px). 최종 결과에도 적용"),
    balance_floor: float = Form(0.25,
        description="d_1≈d_2 조건. 0=spec 그대로 / 0.25 권장 / 0.5=엄격"),
    tau_scale: float = Form(1.0,
        description="Otsu τ* 배수. 1.0=자동 그대로, >1 이면 좁은 틈 검출 범위 확대"),
    yolo_round_strength: int = Form(3,
        description="YOLO 마스크 라운드/스무딩 강도 (Gaussian σ). 0=끄기, 3~5 권장"),
    yolo_remove_overlaps: bool = Form(True,
        description="두 YOLO instance 가 겹친 픽셀을 배경(분리선)으로 처리"),
    yolo_remove_enclosed: bool = Form(True,
        description="더 큰 instance 외곽선 안에 완전히 포위된 작은 instance 제거"),
    enclosed_ratio: float = Form(0.9,
        description="작은 instance 픽셀의 이 비율 이상이 큰 것 안에 들어가면 포위로 판정 (0.5~1.0)"),
    # YOLO 추론 파라미터
    yolo_conf: float = Form(0.25),
    yolo_iou: float = Form(0.5),
    yolo_imgsz: int = Form(640),
    # U-Net 추론 파라미터
    unet_imgsz: Optional[int] = Form(None,
        description="U-Net 추론 입력 크기. 비우면 모델 메타값."),
    device: str = Form("auto"),
    # 전처리 · 형상 지표
    crop_bottom_mode: str = Form("none",
        description="하단 정보바(스케일바) 자르기: none / auto / manual"),
    crop_bottom_px: int = Form(0,
        description="manual 일 때 하단에서 잘라낼 높이 (px)"),
    remove_edge_particles: bool = Form(False,
        description="이미지 테두리에 닿은 입자 제거 (형상/입도 지표에서 제외)"),
    scale_bar_px: float = Form(0.0,
        description="스케일바 길이 (px). scale_bar_um 과 함께 주면 µm 환산"),
    scale_bar_um: float = Form(0.0,
        description="스케일바 실제 길이 (µm)"),
    irregular_circularity: float = Form(0.7,
        description="원형도 < 이 값이면 불규칙 입자"),
):
    """U-Net 확률맵 × YOLO 인스턴스 → fusion. 단일 endpoint."""
    if not images:
        raise HTTPException(400, "이미지를 1장 이상 첨부해주세요.")

    # U-Net 로드
    try:
        from unet_trainer import deserialize_model, predict_with_state
    except Exception as e:
        raise HTTPException(500, f"unet_trainer import 실패: {e}")
    unet_bytes = _resolve_unet_weights(unet_weights)
    if not unet_bytes:
        raise HTTPException(400, "U-Net 가중치가 비어있습니다.")
    try:
        unet_payload = deserialize_model(unet_bytes)
    except Exception as e:
        raise HTTPException(400, f"U-Net 모델 로드 실패: {e}")
    unet_method = unet_payload["method"]
    unet_state = unet_payload["state_dict"]
    unet_meta_size = int(unet_payload.get("image_size", 256))
    unet_size = int(unet_imgsz) if unet_imgsz else unet_meta_size

    # YOLO 로드
    try:
        from ultralytics import YOLO
    except Exception as e:
        raise HTTPException(500, f"ultralytics 미설치: {e}")
    yolo_pt_path, yolo_temp = _resolve_yolo_weights_path(
        yolo_weights, yolo_weights_path
    )
    yolo_model = YOLO(str(yolo_pt_path))
    resolved_device = _resolve_device(device)

    params = HybridParams(
        high_thresh=float(high_thresh),
        low_thresh=float(low_thresh),
        boundary_thickness=max(1, int(boundary_thickness)),
        min_anchor_area=max(1, int(min_anchor_area)),
        balance_floor=max(0.0, min(1.0, float(balance_floor))),
        tau_scale=max(0.1, float(tau_scale)),
        yolo_round_strength=max(0, int(yolo_round_strength)),
        yolo_remove_overlaps=bool(yolo_remove_overlaps),
        yolo_remove_enclosed=bool(yolo_remove_enclosed),
        enclosed_ratio=max(0.5, min(1.0, float(enclosed_ratio))),
    )

    crop_mode = (crop_bottom_mode or "none").strip().lower()
    if crop_mode not in ("none", "auto", "manual"):
        raise HTTPException(400, f"crop_bottom_mode 는 none/auto/manual: {crop_bottom_mode}")
    um_per_px = _scale(scale_bar_px, scale_bar_um)
    irr_thr = float(irregular_circularity)

    image_paths: list[Path] = []
    gts_list = list(gts) if gts else []
    morph_raw: list[dict] = []
    results: list[dict] = []
    per_image_metrics: list[dict] = []

    try:
        for img_up in images:
            suffix = Path(img_up.filename or "img.png").suffix or ".png"
            ip = _save_upload(img_up, suffix)
            image_paths.append(ip)

            # 이미지 로드 (gray for U-Net, BGR for YOLO)
            img_gray = np.array(Image.open(ip).convert("L"))
            H0 = img_gray.shape[0]

            # 하단 정보바(스케일바 영역) 자르기 — U-Net / YOLO / GT 모두 같은 영역
            if crop_mode == "auto":
                crop_px = detect_bottom_bar(img_gray)
            elif crop_mode == "manual":
                crop_px = int(max(0, min(int(crop_bottom_px), H0 - 16)))
            else:
                crop_px = 0
            yolo_source: object = str(ip)
            if crop_px > 0:
                img_gray = img_gray[: H0 - crop_px]
                bgr = cv2.imdecode(np.fromfile(str(ip), np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    bgr = cv2.cvtColor(np.array(Image.open(ip).convert("L")), cv2.COLOR_GRAY2BGR)
                ch = round(bgr.shape[0] * (H0 - crop_px) / H0)
                yolo_source = np.ascontiguousarray(bgr[:ch])
            h, w = img_gray.shape

            # U-Net 추론
            try:
                prob, _ = predict_with_state(
                    unet_state, unet_method, img_gray, image_size=unet_size,
                )
            except Exception as e:
                raise HTTPException(500, f"U-Net 추론 실패 ({img_up.filename}): {e}")
            if prob.shape != (h, w):
                prob = cv2.resize(prob, (w, h), interpolation=cv2.INTER_LINEAR)

            # YOLO 추론
            r = yolo_model.predict(
                source=yolo_source,
                imgsz=int(yolo_imgsz),
                conf=float(yolo_conf),
                iou=float(yolo_iou),
                max_det=100_000,  # ultralytics 기본 상한 300 해제 (고밀도 입자 이미지 대응)
                device=resolved_device,
                verbose=False,
            )[0]
            if r.masks is not None and r.masks.data.numel() > 0:
                m_raw = r.masks.data.cpu().numpy()
                yolo_inst = [
                    cv2.resize(m.astype(np.uint8), (w, h),
                               interpolation=cv2.INTER_NEAREST).astype(bool)
                    for m in m_raw
                ]
            else:
                yolo_inst = []

            # Fusion
            res = hybrid_fuse(prob, yolo_inst, params)

            # 모서리 입자 제거 + 면적순 재라벨 (번호 = 라벨 = 엑셀 입자 번호)
            #   GT 평가 지표는 제거 전 res.instances 로 계산 (분할 정확도 평가용).
            inst = res.instances
            n_edge_removed = 0
            if remove_edge_particles:
                inst, n_edge_removed = remove_edge_touching(inst)
            inst = relabel_by_area(inst)
            final_semantic = inst > 0

            # 시각화
            inst_color = colorize_instances(inst)
            particles = _extract_particles(inst)
            base_bgr = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
            overlay = base_bgr.copy()
            mask_bool = final_semantic
            overlay[mask_bool] = (
                0.45 * inst_color[mask_bool] + 0.55 * base_bgr[mask_bool]
            ).astype(np.uint8)

            # 색 진단 뷰: M_close=빨강 / boundary=파랑 / 겹침(=separator)=흰색
            #   사용자가 "왜 겹친 부분이 분리선에 없나" 시각 확인용.
            overlap_view = np.zeros((h, w, 3), dtype=np.uint8)  # BGR
            overlap_view[res.M_close & ~res.boundary] = (0, 0, 255)       # 빨강 — M_close only
            overlap_view[~res.M_close & res.boundary] = (255, 0, 0)       # 파랑 — boundary only
            overlap_view[res.M_close & res.boundary] = (255, 255, 255)    # 흰색 — separator

            # d_+ 히스토그램 figure + CSV (논문 figure / 분석 데이터)
            bg_pixels = ~res.M_high
            d_bg = res.distance_sum[bg_pixels]
            hist_png, hist_centers, hist_counts = _make_d_histogram_figure(
                d_bg, tau=res.tau, bin_width=1.0,
            )
            # CSV 1: histogram bin 데이터 (bin_width=1.0, 엑셀 분석용)
            #   d_min/d_max = bin 범위, bin_label = 정수 floor (엑셀 차트 x축 친화)
            hist_lines = ["bin_label,d_min,d_max,count,is_below_tau"]
            for c, n in zip(hist_centers, hist_counts):
                d_min = float(c) - 0.5
                d_max = float(c) + 0.5
                label = int(round(d_min))  # 0, 1, 2, ...
                below = 1 if float(c) < res.tau else 0
                hist_lines.append(
                    f"{label},{d_min:.1f},{d_max:.1f},{int(n)},{below}"
                )
            hist_csv = "\n".join(hist_lines) + "\n"
            # CSV 2: 픽셀별 d_+, d_1, d_2, balance, in_M_close (배경 픽셀만, 최대 200K 행 다운샘플)
            ys_bg, xs_bg = np.where(bg_pixels)
            if ys_bg.size > 0:
                d1_bg = res.d1[bg_pixels]
                d2_bg = res.d2[bg_pixels]
                d_sum_bg = res.distance_sum[bg_pixels]
                bal_bg = 1.0 - np.abs(d1_bg - d2_bg) / (d_sum_bg + 1e-6)
                in_close_bg = res.M_close[bg_pixels]
                # 다운샘플
                MAX_ROWS = 200_000
                if ys_bg.size > MAX_ROWS:
                    rng = np.random.default_rng(42)
                    idx = rng.choice(ys_bg.size, MAX_ROWS, replace=False)
                    ys_bg = ys_bg[idx]; xs_bg = xs_bg[idx]
                    d1_bg = d1_bg[idx]; d2_bg = d2_bg[idx]
                    d_sum_bg = d_sum_bg[idx]; bal_bg = bal_bg[idx]
                    in_close_bg = in_close_bg[idx]
                pix_lines = ["y,x,d1,d2,d_plus,balance,in_M_close"]
                for i in range(ys_bg.size):
                    if np.isfinite(d_sum_bg[i]):
                        pix_lines.append(
                            f"{int(ys_bg[i])},{int(xs_bg[i])},"
                            f"{float(d1_bg[i]):.3f},{float(d2_bg[i]):.3f},"
                            f"{float(d_sum_bg[i]):.3f},{float(bal_bg[i]):.4f},"
                            f"{int(in_close_bg[i])}"
                        )
                pix_csv = "\n".join(pix_lines) + "\n"
                pix_n = ys_bg.size
            else:
                pix_csv = "y,x,d1,d2,d_plus,balance,in_M_close\n"
                pix_n = 0

            entry: dict = {
                "filename": img_up.filename or ip.name,
                "shape": [int(h), int(w)],
                "n_instances": len(particles),
                "n_instances_before_edge": int(res.n_instances),
                "n_edge_removed": int(n_edge_removed),
                "crop_bottom_px": int(crop_px),
                "n_yolo": int(res.n_yolo),
                "K_unet_anchor": int(res.K_unet),
                "tau": float(res.tau),
                "overlay_png": _png_data_url(overlay),
                "mask_png": _png_data_url(final_semantic),
                "instances_png": _png_data_url(inst_color),
                "particles": particles,
                # 진단용 시각화
                "diag_prob_png": _png_data_url((prob * 255).astype(np.uint8)),
                "diag_high_png": _png_data_url(res.M_high),
                # P_low = U-Net 확률 >= low_thresh (fusion 적용 전 raw 영역)
                "diag_low_png": _png_data_url(prob >= float(low_thresh)),
                "diag_close_png": _png_data_url(res.M_close),
                "diag_boundary_png": _png_data_url(res.boundary),
                "diag_separator_png": _png_data_url(res.M_close & res.boundary),
                "diag_overlap_png": _png_data_url(overlap_view),
                "diag_hist_png": _png_bytes_to_data_url(hist_png),
                "hist_csv": _csv_data_url(hist_csv),
                "pixel_csv": _csv_data_url(pix_csv),
                "pixel_csv_rows": int(pix_n),
            }

            # ── separator 영향 시각화 + 통계 ─────────────────────────────────
            # P_low(τ=low_thresh) 를 CC 라벨링해서 인스턴스별 색칠 +
            # 회색조 U-Net 확률맵 위에 separator 를 빨간색으로 덮은 오버레이 +
            # (a)(b) 그래프용 이미지별 수치.
            _sep = (res.M_close & res.boundary)
            _P_low = (prob >= float(low_thresh))
            _low_labels, _K_low = ndi.label(_P_low)
            # unet_prob_instances: 검정 배경 + P_low(≥low_thresh) 픽셀만 인스턴스
            # 색으로 완전히 덮음. → 엑셀(k_at_low, converted_pct) 과 정확히 같은
            # 기준이라 색 조각 개수 = k_at_low.
            _low_inst_color = colorize_instances(_low_labels, seed=17)
            _prob_inst = np.zeros((h, w, 3), dtype=np.uint8)
            _prob_inst[_P_low] = _low_inst_color[_P_low]
            entry["diag_prob_instances_png"] = _png_data_url(_prob_inst)
            # unet_prob_with_separator: 회색조 확률맵 + 빨간 separator
            _prob_gray = (prob * 255).astype(np.uint8)
            # unet_prob(회색조) 배경 위에 separator 픽셀만 빨간색으로 덮음
            _prob_bgr = cv2.cvtColor(_prob_gray, cv2.COLOR_GRAY2BGR)
            _prob_bgr[_sep] = (0, 0, 255)  # BGR 빨간색
            entry["diag_prob_with_separator_png"] = _png_data_url(_prob_bgr)
            _p_low_px = int(_P_low.sum())
            _conv_px = int((_P_low & _sep).sum())
            _, _K_after = ndi.label(_P_low & (~_sep))
            entry["low_stats"] = {
                "p_low_px": _p_low_px,
                "converted_px": _conv_px,
                "converted_pct": float(100.0 * _conv_px / max(1, _p_low_px)),
                "k_at_low": int(_K_low),
                "k_after_separator": int(_K_after),
                "k_delta": int(_K_after - _K_low),
            }

            # ── 형상 · 입도 지표 (지표 1~15) ──
            #   분포 지표(entry["morphology"]) 는 루프 끝에서 _morph_bundle 로 채움.
            pm_list = particle_metrics(inst, img_gray, irregular_circularity=irr_thr)
            # 입자별 지표 (스케일 환산 단위) → particles[i]["metrics"] (번호 동일)
            by_id = {q["id"]: q for q in pm_list}
            for pp in particles:
                q = by_id.get(pp["id"])
                if q is not None:
                    pp["metrics"] = json_safe({
                        k: v for k, v in scaled(q, um_per_px).items()
                        if k not in ("id", "cx", "cy")
                    })
            morph_raw.append({
                "filename": entry["filename"],
                "particles": pm_list,
                "n_edge_removed": int(n_edge_removed),
                "crop_px": int(crop_px),
                "edge_removal": bool(remove_edge_particles),
            })

            # GT 매칭 — YOLO only / U-Net 75% / Hybrid 세 방법 모두 평가
            matched = _match_gt_for(entry["filename"], gts_list)
            if matched is None and len(images) == 1 and len(gts_list) == 1:
                matched = gts_list[0]
            if matched is not None:
                gt_arr = _read_gray(matched)
                if crop_px > 0 and gt_arr.shape[0] == H0:
                    gt_arr = gt_arr[: H0 - crop_px]
                if gt_arr.shape != (h, w):
                    gt_arr = cv2.resize(
                        gt_arr, (w, h), interpolation=cv2.INTER_NEAREST,
                    )
                gt_bin = gt_arr >= 128

                # 1) YOLO only (라운드/overlap 후처리된 instance 사용)
                yolo_label = np.zeros((h, w), dtype=np.int32)
                for i, m in enumerate(res.yolo_processed):
                    yolo_label[m] = i + 1
                yolo_semantic = yolo_label > 0
                metrics_yolo = _metrics_from_instances(yolo_label, yolo_semantic, gt_bin)

                # 2) U-Net low threshold (단순 임계, hysteresis 없음)
                unet_low_mask = prob >= float(low_thresh)
                unet_low_label, _ = ndi.label(unet_low_mask)
                metrics_unet_low = _metrics_from_instances(
                    unet_low_label.astype(np.int32), unet_low_mask, gt_bin
                )

                # 3) Hybrid (최종 결과)
                metrics_hybrid = _metrics_from_instances(res.instances, res.semantic, gt_bin)

                entry["metrics"] = metrics_hybrid  # 하위 호환
                entry["metrics_yolo"] = metrics_yolo
                entry["metrics_unet_low"] = metrics_unet_low
                entry["metrics_hybrid"] = metrics_hybrid
                entry["gt_png"] = _png_data_url(gt_bin)
                entry["gt_filename"] = matched.filename
                per_image_metrics.append({
                    "yolo": metrics_yolo,
                    "unet_low": metrics_unet_low,
                    "hybrid": metrics_hybrid,
                })

            results.append(entry)

        out: dict = {
            "params": (
                f"high={high_thresh}  ·  low={low_thresh}  ·  "
                f"thickness={boundary_thickness}  ·  min_area={min_anchor_area}  "
                f"·  balance={balance_floor}  ·  tau_scale={tau_scale}  ·  "
                f"round={yolo_round_strength}  ·  "
                f"no-overlap={yolo_remove_overlaps}  ·  "
                f"no-enclosed={yolo_remove_enclosed}"
                + (f"@{enclosed_ratio}" if yolo_remove_enclosed else "")
                + f"  ·  "
                f"unet={unet_method}@{unet_size}  ·  "
                f"yolo:conf={yolo_conf}/iou={yolo_iou}/imgsz={yolo_imgsz}  "
                f"·  device={resolved_device}  ·  N={len(results)}"
                f"  ·  crop={crop_mode}"
                + (f"@{crop_bottom_px}px" if crop_mode == "manual" else "")
                + f"  ·  edge-removal={remove_edge_particles}"
                + (f"  ·  scale={scale_bar_um}µm/{scale_bar_px}px" if um_per_px else "  ·  scale=none(px)")
            ),
            "n_images": len(results),
            "total_instances": int(sum(r["n_instances"] for r in results)),
            "n_with_gt": len(per_image_metrics),
            "results": results,
        }
        # 세 방법별 summary (이미지 평균)
        if per_image_metrics:
            for key in ("yolo", "unet_low", "hybrid"):
                s = _summary_metrics([m[key] for m in per_image_metrics])
                if s is not None:
                    out[f"summary_{key}"] = s
            # 하위 호환 — hybrid summary 를 "summary" 로도 제공
            out["summary"] = out.get("summary_hybrid")
        # frontend 가 동적 라벨 만들 수 있게 임계 값도 노출
        out["high_thresh"] = float(high_thresh)
        out["low_thresh"] = float(low_thresh)

        # 형상 · 입도 지표 — 이미지별 + 전체(모든 이미지 입자 합침)
        morph_settings = {
            "crop_mode": ("하단 크롭 방식", "Bottom crop mode", crop_mode),
            "crop_px": ("하단 크롭 (manual, px)", "Bottom crop (manual, px)",
                        int(crop_bottom_px) if crop_mode == "manual" else None),
            "edge": ("모서리 입자 제거", "Remove edge-touching particles", bool(remove_edge_particles)),
            "irr": ("불규칙 기준 (원형도 <)", "Irregular threshold (circularity <)", irr_thr),
        }
        morph_excel = _morph_bundle(morph_raw, um_per_px, irr_thr, morph_settings,
                                    scale_bar_px, scale_bar_um)
        for entry_, m in zip(results, morph_excel["per_image"]):
            entry_["morphology"] = json_safe(m["summary"])
        out["morphology_all"] = json_safe(morph_excel["all"]["summary"])
        out["um_per_px"] = um_per_px
        out["length_unit"] = morph_excel["unit"]
        # 입자별 지표 열 정의 (한/영 + 단위) — 프런트 입자별 엑셀용
        out["particle_columns"] = [
            {"key": c.key, "ko": c.ko, "en": c.en, "unit": unit_label(c.kind, out["length_unit"])}
            for c in PARTICLE_COLUMNS
            if c.key not in ("id", "cx", "cy")
        ]

        # 전체 결과 xlsx 생성 (시트별: Parameters / Metrics_per_image / Summary / Image_diagnostics)
        try:
            params_dict = {
                "high_thresh": float(high_thresh),
                "low_thresh": float(low_thresh),
                "boundary_thickness": int(boundary_thickness),
                "min_anchor_area": int(min_anchor_area),
                "balance_floor": float(balance_floor),
                "tau_scale": float(tau_scale),
                "yolo_round_strength": int(yolo_round_strength),
                "yolo_remove_overlaps": bool(yolo_remove_overlaps),
                "yolo_remove_enclosed": bool(yolo_remove_enclosed),
                "enclosed_ratio": float(enclosed_ratio),
                "yolo_conf": float(yolo_conf),
                "yolo_iou": float(yolo_iou),
                "yolo_imgsz": int(yolo_imgsz),
                "unet_method": str(unet_method),
                "unet_image_size": int(unet_size),
                "device": str(resolved_device),
                "n_images": len(results),
                "n_with_gt": len(per_image_metrics),
                "crop_bottom_mode": crop_mode,
                "crop_bottom_px": int(crop_bottom_px),
                "remove_edge_particles": bool(remove_edge_particles),
                "scale_bar_px": float(scale_bar_px),
                "scale_bar_um": float(scale_bar_um),
                "um_per_px": um_per_px if um_per_px else "",
                "irregular_circularity": irr_thr,
            }
            summaries = {
                "summary_yolo":     out.get("summary_yolo"),
                "summary_unet_low": out.get("summary_unet_low"),
                "summary_hybrid":   out.get("summary_hybrid"),
            }
            xlsx_bytes = make_excel_3way(params_dict, results, summaries, morph_excel)
            # 나중에 스케일 입력 → µm 엑셀 재생성용
            run_id = uuid.uuid4().hex
            _EXCEL_CACHE[run_id] = {
                "params": params_dict,
                "results": [{k: r[k] for k in _EXCEL_RESULT_KEYS if k in r} for r in results],
                "summaries": summaries,
                "raw": morph_raw,
                "irr_thr": irr_thr,
                "settings": morph_settings,
            }
            while len(_EXCEL_CACHE) > _EXCEL_CACHE_MAX:
                _EXCEL_CACHE.popitem(last=False)
            out["run_id"] = run_id
            out["excel_data_url"] = _xlsx_data_url_shared(xlsx_bytes)
            out["excel_size_bytes"] = len(xlsx_bytes)
        except Exception as e:
            out["excel_error"] = f"{type(e).__name__}: {e}"

        return out
    finally:
        for p in image_paths:
            try: p.unlink()
            except Exception: pass
        if yolo_temp:
            try: yolo_pt_path.unlink()
            except Exception: pass
