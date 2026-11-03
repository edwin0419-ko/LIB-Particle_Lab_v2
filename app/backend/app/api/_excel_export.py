"""YOLO / U-Net / Hybrid 결과 → 엑셀 (.xlsx) 생성 공용 헬퍼.

- make_excel_simple : 단일 metrics (YOLO, U-Net)
- make_excel_3way   : 3-way metrics (Hybrid — YOLO/U-Net_low/Hybrid 비교)
"""
from __future__ import annotations

import base64
import io
from typing import Optional


METRIC_KEYS = ("Precision", "Recall", "Accuracy", "IoU", "F1",
               "mAP@0.5", "ParticleCountError")


def xlsx_data_url(data: bytes) -> str:
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _style_header_cell(cell, fill_hex: str = "1F5FD6") -> None:
    from openpyxl.styles import Font, PatternFill, Alignment
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor=fill_hex)
    cell.alignment = Alignment(horizontal="center")


def _style_header_row(ws, n_cols: int, fill_hex: str = "1F5FD6") -> None:
    for c in range(1, n_cols + 1):
        _style_header_cell(ws.cell(row=1, column=c), fill_hex)
    ws.freeze_panes = "A2"


def _autosize(ws, max_width: int = 32) -> None:
    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        length = max(
            (len(str(c.value)) for c in col if c.value is not None),
            default=8,
        )
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(
            length + 2, max_width
        )


def _format_numbers(ws, min_col: int, max_col: int, fmt: str = "0.0000") -> None:
    for row in ws.iter_rows(min_row=2, min_col=min_col, max_col=max_col):
        for cell in row:
            cell.number_format = fmt


# ─────────────── 단일 metrics (YOLO / U-Net) ───────────────


def make_excel_simple(
    title: str,
    params: dict,
    results: list[dict],
    summary: Optional[dict],
    *,
    extra_cols: Optional[list[tuple[str, str]]] = None,
) -> bytes:
    """단일 metrics 결과 → 4 시트 xlsx.

    시트:
        Parameters         : 모든 설정값
        Metrics_per_image  : filename + 7개 지표 + 입자 수 + (옵션) extra_cols
        Summary            : 전체 평균 (n_with_gt 명시)
        Image_diagnostics  : 이미지별 진단 (extra_cols 가 있을 때만)

    extra_cols 예: [("n_detections", "n_detections")] 또는 [("pred_pixels", "pred_pixels")]
    """
    from openpyxl import Workbook

    wb = Workbook()

    # ─── Sheet 1: Parameters ───
    ws = wb.active
    ws.title = "Parameters"
    ws.append(["Parameter", "Value"])
    _style_header_row(ws, 2)
    for k, v in params.items():
        val = str(v) if isinstance(v, bool) else v
        ws.append([str(k), val])
    _autosize(ws)

    # ─── Sheet 2: Metrics_per_image ───
    ws = wb.create_sheet("Metrics_per_image")
    headers = ["filename", *METRIC_KEYS, "n_gt_inst", "n_pred_inst"]
    extra_keys: list[str] = []
    if extra_cols:
        for key, label in extra_cols:
            headers.append(label)
            extra_keys.append(key)
    ws.append(headers)
    _style_header_row(ws, len(headers))
    for r in results:
        m = r.get("metrics")
        if m is None:
            # GT 매칭 안 된 이미지 — 지표 행 자체는 추가하되 NaN 으로
            row = [r.get("filename", ""), *(None for _ in METRIC_KEYS),
                   None, None]
            for k in extra_keys:
                row.append(r.get(k))
            ws.append(row)
            continue
        row = [
            r.get("filename", ""),
            float(m["Precision"]), float(m["Recall"]),
            float(m["Accuracy"]), float(m["IoU"]), float(m["F1"]),
            float(m["mAP@0.5"]), float(m["ParticleCountError"]),
            int(m["n_gt_inst"]), int(m["n_pred_inst"]),
        ]
        for k in extra_keys:
            row.append(r.get(k))
        ws.append(row)
    _format_numbers(ws, min_col=2, max_col=8)
    _autosize(ws)

    # ─── Sheet 3: Summary ───
    ws = wb.create_sheet("Summary")
    headers = ["scope", *METRIC_KEYS, "n_gt_inst (sum)", "n_pred_inst (sum)", "n_with_gt"]
    ws.append(headers)
    _style_header_row(ws, len(headers))
    if summary is not None:
        ws.append([
            title,
            float(summary["Precision"]), float(summary["Recall"]),
            float(summary["Accuracy"]), float(summary["IoU"]), float(summary["F1"]),
            float(summary["mAP@0.5"]), float(summary["ParticleCountError"]),
            int(summary["n_gt_inst"]), int(summary["n_pred_inst"]),
            int(summary["n_with_gt"]),
        ])
        _format_numbers(ws, min_col=2, max_col=8)
    else:
        ws.append(["(no GT — summary unavailable)"])
    _autosize(ws)

    # ─── Sheet 4: Image_diagnostics (있을 때만) ───
    if extra_cols:
        ws = wb.create_sheet("Image_diagnostics")
        diag_headers = ["filename", *[label for _, label in extra_cols]]
        ws.append(diag_headers)
        _style_header_row(ws, len(diag_headers))
        for r in results:
            ws.append([r.get("filename", ""),
                       *[r.get(k) for k, _ in extra_cols]])
        _autosize(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────── 3-way metrics (Hybrid) ───────────────


def make_excel_3way(params: dict, results: list[dict], summaries: dict,
                    morphology: Optional[dict] = None) -> bytes:
    """Hybrid 결과 → xlsx.

    시트:
        Parameters         : 알고리즘/추론 설정값
        Metrics_per_image  : (filename × method) 행, 7개 지표
        Summary            : 방법별 이미지 평균 (3행)
        Image_diagnostics  : 이미지별 진단 (K_unet, n_yolo, tau 등)
        (+ morphology 가 있으면 형상·입도 지표 시트 5개 — add_morphology_sheets)
    """
    from openpyxl import Workbook

    wb = Workbook()

    # ─── Sheet 1: Parameters ───
    ws = wb.active
    ws.title = "Parameters"
    ws.append(["Parameter", "Value"])
    _style_header_row(ws, 2)
    for k, v in params.items():
        val = str(v) if isinstance(v, bool) else v
        ws.append([str(k), val])
    _autosize(ws)

    method_labels = [
        ("metrics_yolo",     "YOLO only"),
        ("metrics_unet_low", f"U-Net ≥ {params.get('low_thresh', 0.30)}"),
        ("metrics_hybrid",   "Hybrid"),
    ]
    summary_labels = [
        ("summary_yolo",     "YOLO only"),
        ("summary_unet_low", f"U-Net ≥ {params.get('low_thresh', 0.30)}"),
        ("summary_hybrid",   "Hybrid"),
    ]

    # ─── Sheet 2: Metrics_per_image ───
    ws = wb.create_sheet("Metrics_per_image")
    headers = ["filename", "method", *METRIC_KEYS, "n_gt_inst", "n_pred_inst"]
    ws.append(headers)
    _style_header_row(ws, len(headers))
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
    _format_numbers(ws, min_col=3, max_col=9)
    _autosize(ws)

    # ─── Sheet 3: Summary ───
    ws = wb.create_sheet("Summary")
    headers = ["method", *METRIC_KEYS,
               "n_gt_inst (sum)", "n_pred_inst (sum)", "n_with_gt"]
    ws.append(headers)
    _style_header_row(ws, len(headers))
    for key, label in summary_labels:
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
    _format_numbers(ws, min_col=2, max_col=8)
    _autosize(ws)

    # ─── Sheet 4: Image_diagnostics ───
    ws = wb.create_sheet("Image_diagnostics")
    headers = ["filename", "n_instances (hybrid)",
               "K_unet_anchor", "n_yolo", "tau (used)", "pixel_csv_rows"]
    ws.append(headers)
    _style_header_row(ws, len(headers))
    for r in results:
        ws.append([
            r.get("filename", ""),
            int(r.get("n_instances", 0)),
            int(r.get("K_unet_anchor", 0)),
            int(r.get("n_yolo", 0)),
            float(r.get("tau", 0.0)),
            int(r.get("pixel_csv_rows", 0)),
        ])
    _format_numbers(ws, min_col=5, max_col=5, fmt="0.00")
    _autosize(ws)

    if morphology:
        add_morphology_sheets(wb, morphology)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────── 형상 · 입도 지표 (한/영 병기) ───────────────


def _bilingual_header(ws, ko: list[str], en: list[str], fill_hex: str = "1F5FD6") -> None:
    """1행 = 한글, 2행 = English. 두 행 고정."""
    ws.append(ko)
    ws.append(en)
    for c in range(1, len(ko) + 1):
        _style_header_cell(ws.cell(row=1, column=c), fill_hex)
        _style_header_cell(ws.cell(row=2, column=c), "4A7BE0")
    ws.freeze_panes = "B3"


def _cell(v):
    """NaN/None → 빈칸, bool → 예/Yes."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "예 / Yes" if v else "아니오 / No"
    if isinstance(v, float) and v != v:
        return None
    return v


def add_morphology_sheets(wb, morph: dict) -> None:
    """형상·입도 지표 시트 추가 + 첫 화면을 형상요약으로.

    morph = {
      "unit": "µm"|"px", "um_per_px": float|None, "settings": {...},
      "all": {"summary": {...}, "size_bins": [...], "shape_stats": [...]},
      "per_image": [{"filename", "summary", "particles"(px 단위), "size_bins", "shape_stats"}],
    }
    """
    from openpyxl.styles import Alignment, Font

    from particle_morphology import (EXCLUDED_NOTES, PARTICLE_COLUMNS,
                                     SHAPE_STAT_COLUMNS, SIZE_BIN_COLUMNS,
                                     SUMMARY_ROWS, scaled, unit_label)

    unit = morph.get("unit", "px")
    upp = morph.get("um_per_px")
    per_image = morph.get("per_image", [])
    all_s = morph.get("all", {})
    fill = "2E7D4F"
    by_key = {c.key: c for c in PARTICLE_COLUMNS}

    def u(kind):
        lab = unit_label(kind, unit)
        return f" ({lab})" if lab else ""

    # ─── 형상요약: 지표 × (전체 + 이미지별) ───
    ws = wb.create_sheet("형상요약_Summary")
    files = [p["filename"] for p in per_image]
    _bilingual_header(
        ws,
        ["지표", "단위", "식", "전체", *files],
        ["Metric", "Unit", "Formula", "ALL", *files],
        fill,
    )
    for m in SUMMARY_ROWS:
        vals = [all_s.get("summary", {}).get(m.key)] + [p["summary"].get(m.key) for p in per_image]
        ws.append([f"{m.ko} / {m.en}", unit_label(m.kind, unit), m.formula, *[_cell(v) for v in vals]])
    _format_numbers(ws, min_col=4, max_col=4 + len(files), fmt="0.0000")
    _autosize(ws, max_width=48)

    # ─── 이미지별: 행 = 이미지 (+ 전체) ───
    ws = wb.create_sheet("이미지별_PerImage")
    _bilingual_header(
        ws,
        ["파일명", *[m.ko + u(m.kind) for m in SUMMARY_ROWS]],
        ["Filename", *[m.en + u(m.kind) for m in SUMMARY_ROWS]],
        fill,
    )
    for name, s in [("전체 / ALL", all_s.get("summary", {}))] + \
                   [(p["filename"], p["summary"]) for p in per_image]:
        ws.append([name, *[_cell(s.get(m.key)) for m in SUMMARY_ROWS]])
    _format_numbers(ws, min_col=2, max_col=1 + len(SUMMARY_ROWS), fmt="0.0000")
    _autosize(ws, max_width=22)

    # ─── 입자별: 모든 이미지의 모든 입자 ───
    #   길이/면적 = 스케일 환산 단위(µm, µm²). 스케일 없으면 px.
    #   스케일이 있으면 원본 px 값은 맨 뒤에 참고용으로.
    ws = wb.create_sheet("입자별_Particles")
    len_cols = [c for c in PARTICLE_COLUMNS if c.kind in ("len", "area")]
    ko_h = ["파일명"] + [c.ko + u(c.kind) for c in PARTICLE_COLUMNS]
    en_h = ["Filename"] + [c.en + u(c.kind) for c in PARTICLE_COLUMNS]
    if upp:
        ko_h += [c.ko + (" (px², 참고)" if c.kind == "area" else " (px, 참고)") for c in len_cols]
        en_h += [c.en + (" (px², ref.)" if c.kind == "area" else " (px, ref.)") for c in len_cols]
    _bilingual_header(ws, ko_h, en_h, fill)
    for p in per_image:
        for q in p["particles"]:
            qs = scaled(q, upp)
            row = [p["filename"], *[_cell(qs.get(c.key)) for c in PARTICLE_COLUMNS]]
            if upp:
                row += [_cell(q.get(c.key)) for c in len_cols]
            ws.append(row)
    _format_numbers(ws, min_col=3, max_col=len(ko_h), fmt="0.0000")
    for row in ws.iter_rows(min_row=3, min_col=2, max_col=2):  # 입자 번호 = 정수
        for cell in row:
            cell.number_format = "0"
    _autosize(ws, max_width=20)

    # ─── 형상 지표 분포 통계 (지표별 11개 통계량) ───
    ws = wb.create_sheet("형상분포_ShapeStats")
    _bilingual_header(
        ws,
        ["파일명", "지표", *[ko for _, ko, _, _ in SHAPE_STAT_COLUMNS]],
        ["Filename", "Metric", *[en for _, _, en, _ in SHAPE_STAT_COLUMNS]],
        fill,
    )
    for name, rows in [("전체 / ALL", all_s.get("shape_stats", []))] + \
                      [(p["filename"], p.get("shape_stats", [])) for p in per_image]:
        for r in rows:
            c = by_key.get(r["metric"])
            label = f"{c.ko} / {c.en}" if c else r["metric"]
            ws.append([name, label, *[_cell(r.get(k)) for k, _, _, _ in SHAPE_STAT_COLUMNS]])
    _format_numbers(ws, min_col=4, max_col=2 + len(SHAPE_STAT_COLUMNS), fmt="0.0000")
    _autosize(ws, max_width=40)

    # ─── 크기구간별 형상 (ECD 사분위) ───
    ws = wb.create_sheet("크기구간_SizeBins")
    _bilingual_header(
        ws,
        ["파일명", *[ko + u(k) for _, ko, _, k in SIZE_BIN_COLUMNS]],
        ["Filename", *[en + u(k) for _, _, en, k in SIZE_BIN_COLUMNS]],
        fill,
    )
    for name, rows in [("전체 / ALL", all_s.get("size_bins", []))] + \
                      [(p["filename"], p.get("size_bins", [])) for p in per_image]:
        for r in rows:
            ws.append([name, *[_cell(r.get(c[0])) for c in SIZE_BIN_COLUMNS]])
    _format_numbers(ws, min_col=3, max_col=1 + len(SIZE_BIN_COLUMNS), fmt="0.0000")
    _autosize(ws, max_width=22)

    # ─── 지표 정의: 식 · 설명 (한/영) + 제외 지표 + 분석 설정 ───
    ws = wb.create_sheet("지표정의_Definitions")
    _bilingual_header(
        ws,
        ["지표 (한글)", "지표 (영문)", "단위", "식", "설명 · 계산 방법 (한글)", "설명 · 계산 방법 (영문)"],
        ["Metric (KO)", "Metric (EN)", "Unit", "Formula", "Description (KO)", "Description (EN)"],
        fill,
    )
    ws.freeze_panes = "A3"
    bold = Font(bold=True)

    def section(title):
        ws.append([])
        ws.append([title])
        ws.cell(row=ws.max_row, column=1).font = bold

    section("[기호 / Symbols]")
    for sym, ko, en in [
        ("A", "면적", "area"), ("P", "둘레 (Crofton)", "perimeter (Crofton)"),
        ("a, b", "등가 타원 장축·단축", "equivalent-ellipse major/minor axis"),
        ("F_max, F_min, F(θ)", "Feret 최대·최소·방향 θ 의 캘리퍼 폭", "max/min Feret, caliper width at θ"),
        ("A_hull, P_hull", "볼록껍질 면적·둘레", "convex-hull area/perimeter"),
        ("r(s)", "면적 중심 → 외곽선 거리 (둘레 길이 등간격 128점)", "centroid-to-boundary distance, 128 arc-length samples"),
        ("t(p)", "픽셀 p 의 국소 두께", "local thickness at pixel p"),
        ("s", f"µm/px = {upp:.6g}" if upp else "스케일 미입력 (px 단위)", "scale"),
        ("P10, P50 …", "분위수 (선형 보간)", "percentiles (linear interpolation)"),
    ]:
        ws.append([sym, "", "", "", ko, en])
    section("[입자별 지표 / Per-particle]")
    for c in PARTICLE_COLUMNS:
        ws.append([c.ko, c.en, unit_label(c.kind, unit), c.formula, c.desc_ko, c.desc_en])
    section("[분포 지표 / Distribution]")
    for m in SUMMARY_ROWS:
        ws.append([m.ko, m.en, unit_label(m.kind, unit), m.formula, m.desc_ko, m.desc_en])
    section("[형상 분포 통계량 / Shape-distribution statistics] — 형상분포 시트")
    for _, ko, en, f in SHAPE_STAT_COLUMNS:
        ws.append([ko, en, "", f, "", ""])
    section("[제외한 지표와 이유 / Excluded metrics]")
    for ko, en, why_ko, why_en in EXCLUDED_NOTES:
        ws.append([ko, en, "", "", why_ko, why_en])
    section("[분석 설정 / Analysis settings]")
    for k, (ko, en, v) in morph.get("settings", {}).items():
        ws.append([ko, en, "", _cell(v), "", ""])
    for col, wdt in zip("ABCDEF", (30, 34, 8, 40, 60, 60)):
        ws.column_dimensions[col].width = wdt
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # 첫 화면 = 형상요약 (다른 시트 tabSelected 해제 안 하면 Excel 이 그룹 선택으로 엶)
    for w in wb.worksheets:
        w.sheet_view.tabSelected = False
    wb.active = wb.sheetnames.index("형상요약_Summary")
    wb.active.sheet_view.tabSelected = True
