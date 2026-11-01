# Particle Lab v2 — Inference

> ## 🧑‍🔬 처음 쓰는 분 (코딩 몰라도 됨) — Claude Code로 실행하기
>
> 1. **Claude Code 설치**: https://claude.com/claude-code 안내대로 설치하고 로그인합니다.
> 2. **터미널을 열고** 프로그램을 받을 폴더(예: 바탕화면)에서 `claude` 를 실행합니다.
> 3. 아래 문장을 그대로 붙여넣습니다.
>
>    ```
>    https://github.com/edwin0419-ko/LIB-Particle_Lab_v2 이 프로그램을 내려받아서 실행해줘
>    ```
>
> 4. Claude가 필요한 프로그램 설치 여부를 물어보면 허락해 주세요. 처음에는 설치 때문에 5~10분 걸립니다.
> 5. 브라우저에 Particle Lab 화면이 뜨면 끝입니다. 사용법은 [CLAUDE.md](CLAUDE.md)의 "사용법"을 보세요.
>
> 다음부터는 같은 폴더에서 `claude` 를 열고 "Particle Lab 실행해줘" 라고 하면 됩니다.

A practical **inference-only** edition for SEM particle segmentation. Segments particles using the U-Net × YOLO Hybrid algorithm and produces evaluation metrics.

No training/augmentation/statistics modes. A version your lab colleagues can use right away by *just receiving the trained weights*.

## Quick Start (Local, Mac/Linux)

```bash
cd Particle_lab_v2
bash scripts/setup.sh
bash scripts/start.sh
# Browser → http://localhost:3000
```

## Usage

1. Upload **U-Net weights (.pt)** — `unet_trainer.serialize_model` format
2. Upload **YOLO weights (.pt)** — ultralytics training output (or a server-side disk path)
3. Upload **images to infer** (multiple files)
4. **Ground-truth masks (optional)** — matched by filename; when attached, 7 metrics are computed automatically
5. **Run** → Hybrid inference output + 9 diagnostic views + Excel download

## Hybrid Algorithm Core

Fuses the U-Net probability map with YOLO instance separators. For the full spec, see the [hybrid_core.py](hybrid_core.py) docstring or paper section 3.3.

Core parameter operating values (defaults):

- `high_thresh = 0.75` — U-Net anchor threshold
- `low_thresh = 0.40` — boost threshold
- `boundary_thickness = 3` — YOLO separator thickness
- `min_anchor_area = 10` — minimum particle size
- `balance_floor = 0.25` — d_+ d_+ balance condition
- `tau_scale = 1.0` — Otsu τ* multiplier
- `yolo_round_strength = 3` — YOLO mask round σ
- `yolo_remove_overlaps = True` — auto-remove duplicate detections

## 9 Diagnostic Views

Overlay / Instance / Mask / U-Net prob / M_75 (anchor) / M_close (narrow gaps) / YOLO boundary / Final separator / Color diagnostic / d_+ histogram

## Evaluation Metrics (when GT is attached)

3-way comparison — per image + overall average:

- **(1) YOLO only** (with round/overlap post-processing applied)
- **(2) U-Net >= low_thresh** (simple thresholding)
- **(3) Hybrid (final)**

7 metrics: Precision / Recall / Accuracy / IoU / F1 / mAP@0.5 / ParticleCountError

## Downloads

- **Excel (.xlsx)** — 4 sheets (Parameters / Metrics_per_image / Summary / Image_diagnostics)
- **CSV** — d_+ histogram (for Excel charts) + per-pixel raw

## Directory

```
app/
  backend/    FastAPI (uvicorn 8765) — single /api/run/hybrid endpoint
  frontend/   Next.js 14 (3000) — Hybrid inference UI
scripts/
  setup.sh    Auto setup for Mac/Linux
  start.sh    Start backend + frontend (DETACHED option)
hybrid_core.py       Algorithm core (numpy/scipy/cv2)
unet_trainer.py      U-Net weight deserialize + inference
unet_models.py       U-Net / U-Net++ definitions
unet_module.py       Dataset/model modules
evaluate.py          Metric helpers
weight_maps.py       (Training weight loss — not needed for inference, but imported by unet_trainer)
```

## Where is training?

This v2 is inference only. Training is done in Particle_lab (v1) or via separate training scripts. Just bring the resulting `.pt` and upload it into v2.

## When running alongside v1

If v1 (Particle_lab) is already using ports 8765/3000, you'll get a conflict. To launch v2 on different ports:

```bash
# Change backend port only (PORT env vars)
HOST=127.0.0.1 BACKEND_PORT=8766 FRONT_PORT=3002 bash scripts/start.sh
```

Or simply shut down v1 and run only v2 — that's the simpler option.

## License

Sejong University Particle Analysis Project — internal use.
